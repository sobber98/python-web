from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import tarfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import GITHUB_WEBHOOK_SECRET_SETTING_KEY
from app.github import (
    RepoSnapshot,
    _extract_archive,
    _safe_relative_path,
    discover_apps,
    parse_repo_slug,
)
from app.dependency_inference import infer_dependencies_for_tree, parse_requirements_file


def _reload_main_with(tmp_path: Path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(
        f"admin_password = 'secret'\nsecret_key = 'stable'\ndata_dir = '{tmp_path / 'data'}'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    import app.main

    importlib.reload(app.main)
    return app.main


def _login(client: TestClient) -> None:
    assert client.post("/api/auth/login", json={"password": "secret"}).status_code == 200


class _InlineThread:
    """让后台部署线程在测试中同步执行，便于断言。"""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_extra):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        if self._target:
            self._target(*self._args, **self._kwargs)


def _signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_parse_repo_slug_accepts_common_forms() -> None:
    assert parse_repo_slug("https://github.com/owner/repo") == "owner/repo"
    assert parse_repo_slug("https://github.com/owner/repo.git") == "owner/repo"
    assert parse_repo_slug("git@github.com:owner/repo.git") == "owner/repo"
    assert parse_repo_slug("owner/repo") == "owner/repo"


def test_parse_repo_slug_rejects_non_github_hosts() -> None:
    for value in ("", "https://gitlab.com/owner/repo", "just-a-name"):
        try:
            parse_repo_slug(value)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {value!r}")


def test_discover_apps_splits_files_and_directories(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "tools").mkdir(parents=True)
    (root / "multi").mkdir()
    (root / "tests").mkdir()
    (root / ".github").mkdir()
    (root / "docs").mkdir()

    (root / "alpha.py").write_text("print('alpha')\n", encoding="utf-8")
    (root / "tools" / "main.py").write_text("print('tools')\n", encoding="utf-8")
    (root / "tools" / "helper.py").write_text("print('helper')\n", encoding="utf-8")
    (root / "multi" / "one.py").write_text("print(1)\n", encoding="utf-8")
    (root / "multi" / "two.py").write_text("print(2)\n", encoding="utf-8")
    (root / "tests" / "test_sample.py").write_text("print(3)\n", encoding="utf-8")
    (root / ".github" / "workflow.py").write_text("print(4)\n", encoding="utf-8")
    (root / "docs" / "guide.py").write_text("print(5)\n", encoding="utf-8")

    result = discover_apps(root)

    assert [(app.name, app.path, app.entry) for app in result.apps] == [
        ("alpha", "alpha.py", "alpha.py"),
        ("tools", "tools", "main.py"),
    ]
    assert any("multi" in warning for warning in result.warnings)


def test_dependency_inference_scans_whole_app_tree(tmp_path: Path) -> None:
    app_dir = tmp_path / "bot"
    app_dir.mkdir()
    (app_dir / "main.py").write_text(
        "import requests\nfrom helper import run\nimport yaml\n", encoding="utf-8"
    )
    (app_dir / "helper.py").write_text("import flask\n", encoding="utf-8")
    (app_dir / "requirements.txt").write_text(
        "pandas==2.2.0\n# comment\n-r other.txt\ngit+https://example.com/repo.git\n",
        encoding="utf-8",
    )

    assert infer_dependencies_for_tree(app_dir) == ["flask", "requests", "PyYAML"]
    assert parse_requirements_file(app_dir / "requirements.txt") == ["pandas==2.2.0"]


def test_archive_extraction_skips_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "repo.tar.gz"
    payload = b"print('x')\n"
    with tarfile.open(archive, mode="w:gz") as tar:
        good = tarfile.TarInfo("repo-main/good.py")
        good.size = len(payload)
        import io

        tar.addfile(good, io.BytesIO(payload))
        evil = tarfile.TarInfo("../evil.py")
        evil.size = len(payload)
        tar.addfile(evil, io.BytesIO(payload))

    destination = tmp_path / "extracted"
    destination.mkdir()
    _extract_archive(archive, destination)

    assert (destination / "repo-main" / "good.py").read_text(encoding="utf-8") == "print('x')\n"
    assert not (tmp_path / "evil.py").exists()
    assert _safe_relative_path("../evil.py") is None
    assert _safe_relative_path("/etc/passwd") is None


def test_github_settings_require_auth(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    client = TestClient(main.app)

    response = client.get("/api/github")

    assert response.status_code == 401


def test_webhook_rejects_invalid_signature(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    main.repo.set_setting(GITHUB_WEBHOOK_SECRET_SETTING_KEY, "top-secret")
    client = TestClient(main.app)
    body = json.dumps({"ref": "refs/heads/main"}).encode("utf-8")

    response = client.post(
        "/api/github/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=deadbeef",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 401
    assert "签名" in response.json()["error"]


def test_webhook_triggers_redeploy_for_matching_branch(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    secret = "top-secret"
    main.repo.set_setting(GITHUB_WEBHOOK_SECRET_SETTING_KEY, secret)
    created = main.repo.create_app("Repo App")
    main.repo.update_source(
        created.id,
        script_name="hello.py",
        manual_dependencies="",
        inferred_dependencies=[],
        source_repo="owner/repo",
        source_branch="main",
        source_path="hello.py",
        source_commit="aaa1111",
    )

    calls: list[tuple] = []
    monkeypatch.setattr(main, "_redeploy_matching_github_apps", lambda *args: calls.append(args))
    monkeypatch.setattr(main.threading, "Thread", _InlineThread)

    body = json.dumps(
        {
            "ref": "refs/heads/main",
            "after": "bbb2222",
            "repository": {"full_name": "owner/repo"},
        }
    ).encode("utf-8")
    client = TestClient(main.app)
    response = client.post(
        "/api/github/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _signature(secret, body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"ok": True, "deployed": [created.id]}
    assert calls == [("owner/repo", "main", "bbb2222", [created.id])]


def test_webhook_ignores_already_deployed_commit(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    secret = "top-secret"
    main.repo.set_setting(GITHUB_WEBHOOK_SECRET_SETTING_KEY, secret)
    created = main.repo.create_app("Repo App")
    main.repo.update_source(
        created.id,
        script_name="hello.py",
        manual_dependencies="",
        inferred_dependencies=[],
        source_repo="owner/repo",
        source_branch="main",
        source_path="hello.py",
        source_commit="bbb2222",
    )

    body = json.dumps(
        {
            "ref": "refs/heads/main",
            "after": "bbb2222",
            "repository": {"full_name": "owner/repo"},
        }
    ).encode("utf-8")
    client = TestClient(main.app)
    response = client.post(
        "/api/github/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _signature(secret, body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "deployed": []}


def test_import_repository_creates_and_reuses_apps(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    repo_root = tmp_path / "repo"
    (repo_root / "beta").mkdir(parents=True)
    (repo_root / "alpha.py").write_text("import requests\n", encoding="utf-8")
    (repo_root / "beta" / "main.py").write_text("import flask\n", encoding="utf-8")
    (repo_root / "beta" / "helper.py").write_text("print('helper')\n", encoding="utf-8")
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    def fake_fetch(repo_slug: str, branch: str, token: str, workdir: Path) -> RepoSnapshot:
        return RepoSnapshot(
            archive_dir=archive_dir,
            root=repo_root,
            commit="c0ffee1",
            branch="main",
        )

    deployments: list[tuple] = []
    monkeypatch.setattr(main, "fetch_snapshot", fake_fetch)
    monkeypatch.setattr(
        main,
        "_deploy_github_targets",
        lambda snapshot, *args: deployments.append((snapshot, args)),
    )
    monkeypatch.setattr(main.threading, "Thread", _InlineThread)

    client = TestClient(main.app)
    with client:
        _login(client)
        first = client.post(
            "/api/github/import",
            json={"repo_url": "https://github.com/owner/repo", "branch": ""},
        )
        second = client.post(
            "/api/github/import",
            json={"repo_url": "https://github.com/owner/repo", "branch": "main"},
        )

    assert first.status_code == 201
    payload = first.json()
    assert payload["repo"] == "owner/repo"
    assert payload["branch"] == "main"
    assert payload["commit"] == "c0ffee1"
    assert sorted(app["name"] for app in payload["apps"]) == ["alpha", "beta"]
    assert all(app["source"]["type"] == "github" for app in payload["apps"])
    assert sorted(app["source"]["path"] for app in payload["apps"]) == ["alpha.py", "beta"]

    assert second.status_code == 201
    assert sorted(app["id"] for app in second.json()["apps"]) == sorted(
        app["id"] for app in payload["apps"]
    )
    assert len(main.repo.list_apps()) == 2
    assert len(deployments) == 2
