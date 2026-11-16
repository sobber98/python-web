from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import load_settings
from app.database import (
    ADMIN_PASSWORD_HASH_SETTING_KEY,
    AppRepository,
    GITHUB_TOKEN_SETTING_KEY,
    GITHUB_WEBHOOK_SECRET_SETTING_KEY,
    PIP_INDEX_URL_SETTING_KEY,
    PIP_INDEX_SELECTOR_SETTING_KEY,
)
from app.dependency_inference import (
    infer_dependencies,
    infer_dependencies_for_tree,
    merge_dependencies,
    parse_requirements_file,
)
from app.github import (
    GitHubError,
    RepoSnapshot,
    discover_apps,
    fetch_snapshot,
    parse_repo_slug,
    validate_branch,
)
from app.models import ManagedApp
from app.passwords import hash_password, verify_password
from app.pip_mirror import (
    OFFICIAL_INDEX,
    PIP_MIRROR_PRESETS,
    get_preset,
    normalize_mirror_url,
    selector_url,
    validate_mirror_url,
)
from app.process_manager import ProcessManager, listening_ports

settings = load_settings()
repo = AppRepository(settings.db_path)
manager = ProcessManager(repo, settings.data_dir)
APP_DIR = Path(__file__).resolve().parent
FRONTEND_INDEX = APP_DIR / "static" / "app" / "index.html"
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.0f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} B"


@asynccontextmanager
async def lifespan(_: FastAPI):
    manager.restore_desired()
    try:
        yield
    finally:
        manager.shutdown()


app = FastAPI(title="Python Management Platform", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    max_age=settings.session_max_age,
    https_only=settings.session_https_only,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


@app.middleware("http")
async def cache_hashed_assets(request: Request, call_next):
    response = await call_next(request)
    # Vite 产物文件名带内容哈希，可以长期强缓存；入口 HTML 仍由 spa_entry 控制。
    if request.url.path.startswith("/static/app/assets/"):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    return response


class LoginPayload(BaseModel):
    password: str


class CreateAppPayload(BaseModel):
    name: str


class SettingsPayload(BaseModel):
    source: str
    custom_url: str = ""


class PasswordPayload(BaseModel):
    current_password: str
    new_password: str


class GithubSettingsPayload(BaseModel):
    token: str | None = None
    webhook_secret: str | None = None
    regenerate_webhook_secret: bool = False


class GithubImportPayload(BaseModel):
    repo_url: str
    branch: str = ""
    manual_dependencies: str = ""


class GithubDeployPayload(BaseModel):
    branch: str = ""
    manual_dependencies: str | None = None


# 重新部署时保留运行环境与日志，只替换源码文件。
PRESERVED_APP_ENTRIES = {
    ".venv",
    "runtime.log",
    "runtime.log.1",
    "install.log",
    "install.log.1",
    ".deps-hash",
}


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def require_auth(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required")


LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 60.0
PASSWORD_MIN_LENGTH = 8
_login_failures: dict[str, list[float]] = {}
_login_failures_lock = threading.Lock()


def _password_matches(candidate: str) -> bool:
    # 后台改过的密码以 PBKDF2 哈希存于数据库，未改过时回退到 config.toml 中的初始密码。
    stored_hash = repo.get_setting(ADMIN_PASSWORD_HASH_SETTING_KEY)
    if stored_hash:
        return verify_password(candidate, stored_hash)
    return secrets.compare_digest(
        candidate.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_rate_limited(key: str) -> bool:
    now = time.monotonic()
    with _login_failures_lock:
        attempts = [stamp for stamp in _login_failures.get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
        if attempts:
            _login_failures[key] = attempts
        else:
            _login_failures.pop(key, None)
        return len(attempts) >= LOGIN_MAX_FAILURES


def _record_login_failure(key: str) -> None:
    with _login_failures_lock:
        _login_failures.setdefault(key, []).append(time.monotonic())


def app_payload(managed_app: ManagedApp, ports: list[int] | None = None) -> dict[str, object]:
    if ports is None:
        ports = listening_ports([managed_app.pid]).get(managed_app.pid or 0, [])
    return {
        "id": managed_app.id,
        "name": managed_app.name,
        "slug": managed_app.slug,
        "script_name": managed_app.script_name,
        "status": managed_app.status,
        "desired_running": managed_app.desired_running,
        "pid": managed_app.pid,
        "ports": ports,
        "last_error": managed_app.last_error,
        "progress": {
            "stage": managed_app.progress_stage,
            "percent": managed_app.progress_percent,
            "message": managed_app.progress_message,
        },
        "dependencies": {
            "inferred": managed_app.inferred_list,
            "manual": managed_app.manual_list,
        },
        "source": {
            "type": managed_app.source_type,
            "repo": managed_app.source_repo,
            "branch": managed_app.source_branch,
            "path": managed_app.source_path,
            "commit": managed_app.source_commit,
        },
        "created_at": managed_app.created_at,
        "updated_at": managed_app.updated_at,
    }


def settings_payload() -> dict[str, object]:
    selector = repo.get_setting(PIP_INDEX_SELECTOR_SETTING_KEY, "official")
    custom_url = repo.get_setting(PIP_INDEX_URL_SETTING_KEY, "") if selector == "custom" else ""
    preset = get_preset(selector)
    if preset and selector != "custom":
        effective_url = preset.url
    elif selector == "custom":
        effective_url = custom_url
    else:
        effective_url = OFFICIAL_INDEX
    return {
        "presets": [
            {"key": item.key, "label": item.label, "url": item.url}
            for item in PIP_MIRROR_PRESETS
        ],
        "selector": selector,
        "custom_url": custom_url,
        "effective_url": effective_url,
    }


def github_settings_payload(request: Request) -> dict[str, object]:
    token = repo.get_setting(GITHUB_TOKEN_SETTING_KEY)
    return {
        "token_configured": bool(token),
        "token_hint": f"****{token[-4:]}" if token else "",
        "webhook_secret": repo.get_setting(GITHUB_WEBHOOK_SECRET_SETTING_KEY),
        "webhook_url": f"{str(request.base_url).rstrip('/')}/api/github/webhook",
    }


def _substitute_source(source: Path, target_dir: Path) -> None:
    """用仓库快照替换应用源码，同时保留虚拟环境与日志。"""
    for child in target_dir.iterdir():
        if child.name in PRESERVED_APP_ENTRIES:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    if source.is_file():
        shutil.copy2(source, target_dir / source.name)
        return
    for child in source.iterdir():
        if child.name == ".git":
            continue
        destination = target_dir / child.name
        if child.is_dir():
            shutil.copytree(child, destination, symlinks=False)
        else:
            shutil.copy2(child, destination)


def _source_dependencies(source: Path) -> list[str]:
    if source.is_file():
        inferred = infer_dependencies(source)
    else:
        inferred = infer_dependencies_for_tree(source)
    requirements_root = source if source.is_dir() else source.parent
    requirements = "\n".join(parse_requirements_file(requirements_root / "requirements.txt"))
    return merge_dependencies(inferred, requirements)


def _deploy_github_app(
    app_id: int,
    source: Path,
    entry: str,
    repo_slug: str,
    branch: str,
    commit: str,
    source_path: str,
    manual_dependencies: str | None,
) -> None:
    managed_app = repo.get_app(app_id)
    if managed_app is None:
        return

    def progress(stage: str, percent: int, message: str) -> None:
        repo.set_progress(app_id, stage, percent, message)

    revision = f"{repo_slug}@{commit[:7]}" if commit else f"{repo_slug}@{branch or 'HEAD'}"
    try:
        with manager.app_lock(app_id):
            progress("github", 20, f"已拉取 {revision}，正在停止当前应用...")
            if not manager.stop(app_id, desired=False, reset_progress=False):
                progress("failed", 100, "无法停止当前应用，未更新代码。")
                return
            repo.set_status(app_id, "installing", pid=None)
            progress("parsing", 35, "正在同步仓库文件并解析依赖...")
            target_dir = manager.ensure_app_dir(managed_app)
            _substitute_source(source, target_dir)
            if not (target_dir / entry).is_file():
                raise FileNotFoundError(f"{entry} 在仓库中不存在")
            repo.update_source(
                app_id,
                script_name=entry,
                manual_dependencies=(
                    managed_app.manual_dependencies
                    if manual_dependencies is None
                    else manual_dependencies
                ),
                inferred_dependencies=_source_dependencies(source),
                source_repo=repo_slug,
                source_branch=branch,
                source_path=source_path,
                source_commit=commit,
            )
            progress("venv", 45, "正在准备虚拟环境...")
            manager.start(app_id, install=True, progress=progress, force_install=True)
    except SyntaxError as exc:
        repo.set_status_with_progress(
            app_id,
            "error",
            f"Python syntax error: {exc}",
            "failed",
            100,
            "Python 语法错误，请检查仓库代码。",
        )
    except Exception as exc:
        repo.set_status_with_progress(
            app_id,
            "error",
            f"GitHub deploy failed: {exc}",
            "failed",
            100,
            "GitHub 部署失败，请查看日志。",
        )


def _deploy_github_targets(
    snapshot: RepoSnapshot,
    repo_slug: str,
    branch: str,
    commit: str,
    targets: list[tuple[int, str, str]],
    manual_dependencies: str | None,
) -> None:
    try:
        for app_id, source_path, entry in targets:
            _deploy_github_app(
                app_id,
                snapshot.root / source_path,
                entry,
                repo_slug,
                branch,
                commit,
                source_path,
                manual_dependencies,
            )
    finally:
        snapshot.cleanup()


def _redeploy_matching_github_apps(
    repo_slug: str,
    branch: str,
    commit: str,
    app_ids: list[int],
) -> None:
    token = repo.get_setting(GITHUB_TOKEN_SETTING_KEY)
    workdir = Path(tempfile.mkdtemp(prefix="github-webhook-"))
    try:
        snapshot = fetch_snapshot(repo_slug, branch, token, workdir)
    except GitHubError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        for app_id in app_ids:
            repo.set_status_with_progress(
                app_id,
                "error",
                f"GitHub webhook deploy failed: {exc}",
                "failed",
                100,
                "Webhook 自动部署失败，请查看日志。",
            )
        return

    targets: list[tuple[int, str, str]] = []
    for app_id in app_ids:
        managed_app = repo.get_app(app_id)
        if managed_app is None:
            continue
        if not (snapshot.root / managed_app.source_path).exists():
            repo.set_status_with_progress(
                app_id,
                "error",
                f"GitHub source missing: {managed_app.source_path}",
                "failed",
                100,
                "仓库中已找不到对应文件或目录。",
            )
            continue
        targets.append(
            (
                app_id,
                managed_app.source_path,
                managed_app.script_name or Path(managed_app.source_path).name,
            )
        )
    _deploy_github_targets(snapshot, repo_slug, snapshot.branch, commit or snapshot.commit, targets, None)


def get_app_or_404(app_id: int) -> ManagedApp:
    managed_app = repo.get_app(app_id)
    if managed_app is None:
        raise HTTPException(status_code=404, detail="应用不存在。")
    return managed_app


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求失败。"
    if exc.status_code == 401 and detail == "Authentication required":
        detail = "请先登录后再操作。"
    return JSONResponse({"error": detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"error": "请求参数不合法，请检查后重试。"}, status_code=422)


@app.get("/api/auth/session")
def auth_session(request: Request) -> dict[str, bool]:
    return {"authenticated": is_authenticated(request)}


@app.post("/api/auth/login")
def auth_login(request: Request, payload: LoginPayload) -> dict[str, bool]:
    client_key = _client_key(request)
    if _login_rate_limited(client_key):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试。")
    password_matches = _password_matches(payload.password)
    if not password_matches:
        _record_login_failure(client_key)
        raise HTTPException(status_code=401, detail="密码错误，请重试。")
    with _login_failures_lock:
        _login_failures.pop(client_key, None)
    request.session["authenticated"] = True
    return {"authenticated": True}


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@app.get("/api/apps")
def list_apps(_: None = Depends(require_auth)) -> dict[str, object]:
    apps = repo.list_apps()
    ports = listening_ports([managed_app.pid for managed_app in apps])
    return {
        "apps": [
            app_payload(managed_app, ports.get(managed_app.pid or 0, []))
            for managed_app in apps
        ]
    }


@app.post("/api/apps", status_code=201)
def create_app(payload: CreateAppPayload, _: None = Depends(require_auth)) -> dict[str, object]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="应用名称不能为空。")
    created = repo.create_app(name)
    manager.ensure_app_dir(created)
    return app_payload(created)


@app.get("/api/apps/{app_id}")
def app_detail(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]:
    return app_payload(get_app_or_404(app_id))


@app.delete("/api/apps/{app_id}")
def delete_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, bool]:
    get_app_or_404(app_id)
    manager.delete(app_id)
    return {"ok": True}


@app.post("/api/apps/{app_id}/start")
def start_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]:
    get_app_or_404(app_id)
    return app_payload(manager.start(app_id, install=True))


@app.post("/api/apps/{app_id}/stop")
def stop_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]:
    get_app_or_404(app_id)
    manager.stop(app_id, desired=False)
    return app_payload(get_app_or_404(app_id))


@app.post("/api/apps/{app_id}/restart")
def restart_app(app_id: int, _: None = Depends(require_auth)) -> dict[str, object]:
    get_app_or_404(app_id)
    return app_payload(manager.restart(app_id))


@app.post("/api/apps/{app_id}/upload")
def upload_script(
    app_id: int,
    file: UploadFile = File(...),
    manual_dependencies: str = Form(""),
    _: None = Depends(require_auth),
) -> dict[str, object]:
    managed_app = get_app_or_404(app_id)
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="仅支持上传 .py 文件。")

    limit = settings.max_upload_bytes
    too_large = HTTPException(
        status_code=413,
        detail=f"上传文件不能超过 {_format_size(limit)}。",
    )
    if file.size is not None and file.size > limit:
        raise too_large

    app_dir = manager.ensure_app_dir(managed_app)
    pending_path = app_dir / f".pending-upload-{uuid.uuid4().hex}.py"
    received = 0
    try:
        with pending_path.open("wb") as output:
            while chunk := file.file.read(UPLOAD_CHUNK_SIZE):
                received += len(chunk)
                if received > limit:
                    raise too_large
                output.write(chunk)
    except Exception:
        pending_path.unlink(missing_ok=True)
        raise

    repo.set_progress(app_id, "upload_received", 25, "上传完成，等待处理...")
    threading.Thread(
        target=_process_uploaded_script,
        args=(app_id, pending_path, manual_dependencies),
        daemon=True,
    ).start()
    return {"accepted": True, "app_id": app_id}


def _process_uploaded_script(app_id: int, pending_path: Path, manual_dependencies: str) -> None:
    managed_app = repo.get_app(app_id)
    if managed_app is None:
        return

    def progress(stage: str, percent: int, message: str) -> None:
        repo.set_progress(app_id, stage, percent, message)

    try:
        with manager.app_lock(app_id):
            progress("upload_received", 25, "上传完成，正在停止当前应用...")
            if not manager.stop(app_id, desired=False, reset_progress=False):
                progress("failed", 100, "无法停止当前应用，未覆盖脚本。")
                return
            repo.set_status(app_id, "installing", pid=None)
            progress("parsing", 35, "正在解析依赖...")
            inferred = infer_dependencies(pending_path)
            script_path = manager.ensure_app_dir(managed_app) / "main.py"
            pending_path.replace(script_path)
            repo.update_upload(app_id, "main.py", manual_dependencies, inferred)
            progress("venv", 45, "正在准备虚拟环境...")
            manager.start(app_id, install=True, progress=progress, force_install=True)
    except SyntaxError as exc:
        repo.set_status_with_progress(
            app_id, "error", f"Python syntax error: {exc}", "failed", 100, "Python 语法错误，请检查上传文件。"
        )
    except Exception as exc:
        repo.set_status_with_progress(
            app_id, "error", f"Upload processing failed: {exc}", "failed", 100, "上传处理失败，请查看日志。"
        )
    finally:
        if pending_path.exists():
            pending_path.unlink()


@app.get("/api/apps/{app_id}/download")
def download_script(app_id: int, _: None = Depends(require_auth)) -> Response:
    managed_app = get_app_or_404(app_id)
    script_path = manager.script_path(managed_app)
    if script_path is None or not script_path.exists():
        raise HTTPException(status_code=404, detail="当前应用尚未上传脚本。")
    return FileResponse(
        script_path,
        media_type="text/x-python",
        filename=managed_app.script_name or "main.py",
    )


@app.get("/api/apps/{app_id}/logs")
def app_logs(app_id: int, _: None = Depends(require_auth)) -> dict[str, str]:
    return {"logs": manager.read_log_tail(get_app_or_404(app_id))}


@app.get("/api/settings")
def get_settings(_: None = Depends(require_auth)) -> dict[str, object]:
    return settings_payload()


@app.put("/api/settings")
def update_settings(payload: SettingsPayload, _: None = Depends(require_auth)) -> dict[str, object]:
    if payload.source == "custom":
        ok, message = validate_mirror_url(payload.custom_url)
        if not ok:
            raise HTTPException(status_code=400, detail=message)
        url = normalize_mirror_url(payload.custom_url)
    elif get_preset(payload.source) is not None:
        url = selector_url(payload.source, payload.custom_url)
    else:
        raise HTTPException(status_code=400, detail="未知的镜像源选项。")

    repo.set_setting(PIP_INDEX_SELECTOR_SETTING_KEY, payload.source)
    repo.set_setting(PIP_INDEX_URL_SETTING_KEY, url)
    return settings_payload()


@app.put("/api/settings/password")
def update_admin_password(payload: PasswordPayload, _: None = Depends(require_auth)) -> dict[str, bool]:
    if not _password_matches(payload.current_password):
        raise HTTPException(status_code=400, detail="当前密码不正确。")
    if len(payload.new_password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"新密码至少需要 {PASSWORD_MIN_LENGTH} 个字符。",
        )
    if secrets.compare_digest(
        payload.new_password.encode("utf-8"),
        payload.current_password.encode("utf-8"),
    ):
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同。")

    repo.set_setting(ADMIN_PASSWORD_HASH_SETTING_KEY, hash_password(payload.new_password))
    return {"ok": True}


@app.get("/api/github")
def get_github_integration(request: Request, _: None = Depends(require_auth)) -> dict[str, object]:
    return github_settings_payload(request)


@app.put("/api/github")
def update_github_integration(
    request: Request,
    payload: GithubSettingsPayload,
    _: None = Depends(require_auth),
) -> dict[str, object]:
    if payload.token is not None:
        repo.set_setting(GITHUB_TOKEN_SETTING_KEY, payload.token.strip())
    if payload.webhook_secret is not None:
        repo.set_setting(GITHUB_WEBHOOK_SECRET_SETTING_KEY, payload.webhook_secret.strip())
    if payload.regenerate_webhook_secret:
        repo.set_setting(GITHUB_WEBHOOK_SECRET_SETTING_KEY, secrets.token_urlsafe(32))
    return github_settings_payload(request)


@app.post("/api/github/import", status_code=201)
def import_github_repository(
    payload: GithubImportPayload,
    _: None = Depends(require_auth),
) -> dict[str, object]:
    try:
        repo_slug = parse_repo_slug(payload.repo_url)
        branch = validate_branch(payload.branch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token = repo.get_setting(GITHUB_TOKEN_SETTING_KEY)
    workdir = Path(tempfile.mkdtemp(prefix="github-import-"))
    try:
        snapshot = fetch_snapshot(repo_slug, branch, token, workdir)
    except GitHubError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        discovery = discover_apps(snapshot.root)
        if not discovery.apps:
            raise HTTPException(status_code=400, detail="仓库中未发现可部署的 Python 文件。")
        existing = {
            (app.source_repo.lower(), app.source_path): app
            for app in repo.list_apps()
            if app.source_type == "github"
        }
        targets: list[tuple[int, str, str]] = []
        for found in discovery.apps:
            managed_app = existing.get((repo_slug.lower(), found.path))
            if managed_app is None:
                managed_app = repo.create_app(found.name)
            repo.set_source_origin(
                managed_app.id,
                source_repo=repo_slug,
                source_branch=snapshot.branch,
                source_path=found.path,
                source_commit=snapshot.commit,
            )
            repo.set_progress(
                managed_app.id,
                "queued",
                5,
                f"已发现 {found.path}，等待部署...",
            )
            targets.append((managed_app.id, found.path, found.entry))
    except HTTPException:
        snapshot.cleanup()
        raise
    except Exception:
        snapshot.cleanup()
        raise

    threading.Thread(
        target=_deploy_github_targets,
        args=(
            snapshot,
            repo_slug,
            snapshot.branch,
            snapshot.commit,
            targets,
            payload.manual_dependencies.strip() or None,
        ),
        daemon=True,
    ).start()

    refreshed = [repo.get_app(app_id) for app_id, _, _ in targets]
    return {
        "accepted": True,
        "repo": repo_slug,
        "branch": snapshot.branch,
        "commit": snapshot.commit,
        "warnings": discovery.warnings,
        "apps": [app_payload(app) for app in refreshed if app is not None],
    }


@app.post("/api/apps/{app_id}/github/deploy")
def redeploy_github_app(
    app_id: int,
    payload: GithubDeployPayload,
    _: None = Depends(require_auth),
) -> dict[str, object]:
    managed_app = get_app_or_404(app_id)
    if (
        managed_app.source_type != "github"
        or not managed_app.source_repo
        or not managed_app.source_path
    ):
        raise HTTPException(status_code=400, detail="当前应用不是从 GitHub 部署的。")
    try:
        branch = validate_branch(payload.branch or managed_app.source_branch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token = repo.get_setting(GITHUB_TOKEN_SETTING_KEY)
    workdir = Path(tempfile.mkdtemp(prefix="github-deploy-"))
    try:
        snapshot = fetch_snapshot(managed_app.source_repo, branch, token, workdir)
    except GitHubError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source = snapshot.root / managed_app.source_path
    entry = managed_app.script_name or Path(managed_app.source_path).name
    if not source.exists() or (source.is_dir() and not (source / entry).is_file()):
        snapshot.cleanup()
        raise HTTPException(status_code=400, detail="仓库中已找不到对应文件或入口脚本。")

    threading.Thread(
        target=_deploy_github_targets,
        args=(
            snapshot,
            managed_app.source_repo,
            snapshot.branch,
            snapshot.commit,
            [(app_id, managed_app.source_path, entry)],
            payload.manual_dependencies,
        ),
        daemon=True,
    ).start()
    return {
        "accepted": True,
        "branch": snapshot.branch,
        "commit": snapshot.commit,
    }


WEBHOOK_MAX_BYTES = 5 * 1024 * 1024


@app.post("/api/github/webhook", include_in_schema=False)
async def github_webhook(request: Request) -> JSONResponse:
    secret = repo.get_setting(GITHUB_WEBHOOK_SECRET_SETTING_KEY)
    if not secret:
        raise HTTPException(status_code=400, detail="尚未配置 GitHub Webhook 密钥。")
    body = await request.body()
    if len(body) > WEBHOOK_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Webhook 负载过大。")
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(request.headers.get("X-Hub-Signature-256", ""), expected):
        raise HTTPException(status_code=401, detail="Webhook 签名校验失败。")
    if request.headers.get("X-GitHub-Event", "") != "push":
        return JSONResponse({"ok": True, "ignored": True})

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Webhook 负载不是合法 JSON。") from exc

    ref = str(payload.get("ref", ""))
    repository = payload.get("repository") or {}
    full_name = str(repository.get("full_name", ""))
    commit = str(payload.get("after", ""))
    if not ref.startswith("refs/heads/") or not full_name:
        return JSONResponse({"ok": True, "ignored": True})

    branch = ref.removeprefix("refs/heads/")
    matched = [
        app
        for app in repo.list_apps()
        if app.source_type == "github"
        and app.source_repo.lower() == full_name.lower()
        and (not app.source_branch or app.source_branch == branch)
        and (not commit or app.source_commit != commit)
    ]
    if not matched:
        return JSONResponse({"ok": True, "deployed": []})

    app_ids = [app.id for app in matched]
    threading.Thread(
        target=_redeploy_matching_github_apps,
        args=(full_name, branch, commit, app_ids),
        daemon=True,
    ).start()
    return JSONResponse({"ok": True, "deployed": app_ids}, status_code=202)


@app.get("/{full_path:path}", include_in_schema=False)
def spa_entry(full_path: str) -> Response:
    if (
        full_path == "api"
        or full_path.startswith("api/")
        or full_path == "static"
        or full_path.startswith("static/")
    ):
        raise HTTPException(status_code=404, detail="Not found")
    if not FRONTEND_INDEX.exists():
        return HTMLResponse(
            "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<title>前端尚未构建</title>"
            "<body style='font-family:system-ui;background:#060a14;color:#e2e8f0;padding:3rem'>"
            "<h1>前端尚未构建</h1>"
            "<p>请运行 <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code> 后重启服务。</p>"
            "</body></html>",
            status_code=503,
        )
    return FileResponse(FRONTEND_INDEX, headers={"Cache-Control": "no-cache"})
