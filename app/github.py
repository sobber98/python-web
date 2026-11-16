from __future__ import annotations

import json
import re
import shutil
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


GITHUB_API_BASE = "https://api.github.com"
GITHUB_CODELOAD_BASE = "https://codeload.github.com"
USER_AGENT = "python-management-platform"

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 5000
DOWNLOAD_TIMEOUT_SECONDS = 120

ENTRY_CANDIDATES = ("main.py", "app.py", "run.py", "__main__.py")
SKIPPED_TOP_LEVEL = {
    ".github",
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "tests",
    "test",
    "docs",
    "examples",
}

_REPO_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")
_COMMIT_SUFFIX = re.compile(r"-([0-9a-f]{7,40})$")


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepoSnapshot:
    archive_dir: Path
    root: Path
    commit: str
    branch: str

    def cleanup(self) -> None:
        shutil.rmtree(self.archive_dir, ignore_errors=True)


@dataclass(frozen=True)
class DiscoveredApp:
    name: str
    path: str
    entry: str


@dataclass
class DiscoveryResult:
    apps: list[DiscoveredApp] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_repo_slug(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("请填写 GitHub 仓库地址。")
    if raw.startswith("git@"):
        raw = raw.partition(":")[2]
    elif "://" in raw:
        parsed = urllib.parse.urlparse(raw)
        if parsed.hostname not in {"github.com", "www.github.com"}:
            raise ValueError("仅支持 github.com 上的仓库地址。")
        raw = parsed.path
    raw = raw.strip().strip("/")
    if raw.endswith(".git"):
        raw = raw[: -len(".git")]
    parts = [part for part in raw.split("/") if part]
    if len(parts) < 2:
        raise ValueError("仓库地址格式应为 owner/repo。")
    owner, repo = parts[0], parts[1]
    if not _REPO_COMPONENT.match(owner) or not _REPO_COMPONENT.match(repo):
        raise ValueError("仓库地址包含非法字符。")
    return f"{owner}/{repo}"


def validate_branch(branch: str) -> str:
    value = branch.strip()
    if not value:
        return ""
    if (
        not _BRANCH_PATTERN.match(value)
        or ".." in value
        or value.startswith("/")
        or value.endswith("/")
    ):
        raise ValueError("分支名称不合法。")
    return value


def fetch_snapshot(repo_slug: str, branch: str, token: str, workdir: Path) -> RepoSnapshot:
    resolved_branch = validate_branch(branch)
    if not resolved_branch:
        try:
            resolved_branch = resolve_default_branch(repo_slug, token)
        except GitHubError:
            # 无网络或触发限流时退回到 HEAD，让下载阶段给出更具体的错误。
            resolved_branch = ""

    archive_path = workdir / "repository.tar.gz"
    reference = resolved_branch or "HEAD"
    attempted: list[str] = [reference]
    try:
        _download_archive(repo_slug, reference, token, archive_path)
    except GitHubError as first_error:
        if branch.strip():
            raise
        # 默认分支无法确定时，依次尝试 main / master。
        last_error = first_error
        for fallback in ("main", "master"):
            if fallback in attempted:
                continue
            attempted.append(fallback)
            archive_path.unlink(missing_ok=True)
            try:
                _download_archive(repo_slug, fallback, token, archive_path)
                resolved_branch = fallback
                break
            except GitHubError as exc:
                last_error = exc
        else:
            raise last_error

    extract_dir = workdir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    _extract_archive(archive_path, extract_dir)
    root, archive_commit = _archive_root(extract_dir)
    commit = _resolve_commit(repo_slug, resolved_branch or reference, token) or archive_commit
    return RepoSnapshot(
        archive_dir=workdir,
        root=root,
        commit=commit,
        # 无法确定默认分支名时保留空值，Webhook 会按推送分支自动部署。
        branch=resolved_branch,
    )


def _resolve_commit(repo_slug: str, reference: str, token: str) -> str:
    # 新版归档包不再以 commit 命名，改用 Commits API 获取精确 SHA，失败时不影响部署。
    request = _request(
        f"{GITHUB_API_BASE}/repos/{repo_slug}/commits/{urllib.parse.quote(reference, safe='/')}",
        token,
        "application/vnd.github+json",
    )
    try:
        with _opener().open(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ""
    sha = payload.get("sha")
    return sha if isinstance(sha, str) else ""


def resolve_default_branch(repo_slug: str, token: str) -> str:
    request = _request(
        f"{GITHUB_API_BASE}/repos/{repo_slug}",
        token,
        "application/vnd.github+json",
    )
    try:
        with _opener().open(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise GitHubError(_describe_http_error(exc)) from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise GitHubError(f"无法读取仓库信息：{exc}") from exc
    branch = payload.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise GitHubError("无法确定仓库默认分支。")
    return branch


def discover_apps(root: Path) -> DiscoveryResult:
    result = DiscoveryResult()
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") or child.name in SKIPPED_TOP_LEVEL:
            continue
        if child.is_file():
            if child.suffix == ".py":
                result.apps.append(
                    DiscoveredApp(name=child.stem, path=child.name, entry=child.name)
                )
            continue
        if not child.is_dir() or not _contains_python(child):
            continue
        entry = _resolve_entry(child)
        if entry is None:
            result.warnings.append(
                f"目录 {child.name} 中未找到入口文件（main.py / app.py / run.py / __main__.py），已跳过。"
            )
            continue
        result.apps.append(DiscoveredApp(name=child.name, path=child.name, entry=entry))
    return result


def _request(url: str, token: str, accept: str) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


class _StripAuthOnHostChange(urllib.request.HTTPRedirectHandler):
    """GitHub API 会重定向到 codeload，跨域时不要继续携带 Token。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        old_host = urllib.parse.urlparse(req.full_url).hostname
        new_host = urllib.parse.urlparse(newurl).hostname
        if new_host != old_host:
            for key in ("Authorization", "authorization"):
                redirected.headers.pop(key, None)
        return redirected


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_StripAuthOnHostChange())


def _describe_http_error(exc: urllib.error.HTTPError) -> str:
    if exc.code == 404:
        return "仓库或分支不存在（私有仓库请先在设置中配置 GitHub Token）。"
    if exc.code in {401, 403}:
        return "没有访问该仓库的权限，请检查 GitHub Token 是否有效。"
    return f"GitHub 返回 HTTP {exc.code}。"


def _download_archive(repo_slug: str, reference: str, token: str, destination: Path) -> None:
    quoted_reference = urllib.parse.quote(reference, safe="")
    if token:
        url = f"{GITHUB_API_BASE}/repos/{repo_slug}/tarball/{quoted_reference}"
        accept = "application/vnd.github+json"
    else:
        url = f"{GITHUB_CODELOAD_BASE}/{repo_slug}/tar.gz/{quoted_reference}"
        accept = "application/gzip"
    request = _request(url, token, accept)
    try:
        with _opener().open(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            with destination.open("wb") as output:
                total = 0
                while chunk := response.read(64 * 1024):
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise GitHubError("仓库压缩包超过 100 MB 限制。")
                    output.write(chunk)
    except urllib.error.HTTPError as exc:
        destination.unlink(missing_ok=True)
        raise GitHubError(_describe_http_error(exc)) from exc
    except GitHubError:
        destination.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise GitHubError(f"下载仓库失败：{exc}") from exc


def _extract_archive(archive: Path, destination: Path) -> None:
    try:
        with tarfile.open(archive, mode="r:gz") as tar:
            members = tar.getmembers()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise GitHubError("仓库文件数量过多，无法部署。")
            total = 0
            for member in members:
                relative = _safe_relative_path(member.name)
                if relative is None:
                    continue
                if member.isdir():
                    (destination / relative).mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    continue
                total += member.size
                if total > MAX_EXTRACTED_BYTES:
                    raise GitHubError("仓库解压后体积超过 500 MB 限制。")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    continue
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except tarfile.TarError as exc:
        raise GitHubError("仓库压缩包格式无法解析。") from exc


def _safe_relative_path(name: str) -> Path | None:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        return None
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        return None
    if not parts:
        return None
    return Path(*parts)


def _archive_root(extract_dir: Path) -> tuple[Path, str]:
    entries = list(extract_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        root = entries[0]
        match = _COMMIT_SUFFIX.search(root.name)
        return root, match.group(1) if match else ""
    return extract_dir, ""


def _contains_python(directory: Path) -> bool:
    for path in directory.rglob("*.py"):
        relative = path.relative_to(directory)
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            continue
        return True
    return False


def _resolve_entry(directory: Path) -> str | None:
    for candidate in ENTRY_CANDIDATES:
        if (directory / candidate).is_file():
            return candidate
    top_level = sorted(
        path.name for path in directory.iterdir() if path.is_file() and path.suffix == ".py"
    )
    if len(top_level) == 1:
        return top_level[0]
    return None
