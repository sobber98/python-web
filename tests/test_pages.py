from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def _reload_main_with(tmp_path: Path, monkeypatch, extra_config: str = ""):
    config = tmp_path / "config.toml"
    config.write_text(
        f"admin_password = 'secret'\nsecret_key = 'stable'\ndata_dir = '{tmp_path / 'data'}'\n{extra_config}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    import app.main

    importlib.reload(app.main)
    return app.main


def _login(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"password": "secret"})
    assert response.status_code == 200


def test_spa_entry_serves_built_index(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>SPA 控制台</title>", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_INDEX", index)

    client = TestClient(main.app)
    response = client.get("/apps/123")

    assert response.status_code == 200
    assert "SPA 控制台" in response.text


def test_unknown_api_returns_json_404(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    client = TestClient(main.app)

    for path in ("/api/unknown", "/api"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json() == {"error": "Not found"}


def test_auth_session_login_and_logout(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    client = TestClient(main.app)

    assert client.get("/api/auth/session").json() == {"authenticated": False}

    rejected = client.post("/api/auth/login", json={"password": "wrong"})
    assert rejected.status_code == 401
    assert "密码错误" in rejected.json()["error"]

    accepted = client.post("/api/auth/login", json={"password": "secret"})
    assert accepted.status_code == 200
    assert accepted.json() == {"authenticated": True}
    assert client.get("/api/auth/session").json() == {"authenticated": True}

    logged_out = client.post("/api/auth/logout")
    assert logged_out.status_code == 200
    assert client.get("/api/auth/session").json() == {"authenticated": False}


def test_login_is_rate_limited_after_repeated_failures(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    client = TestClient(main.app)

    for _ in range(main.LOGIN_MAX_FAILURES):
        rejected = client.post("/api/auth/login", json={"password": "wrong"})
        assert rejected.status_code == 401

    blocked = client.post("/api/auth/login", json={"password": "secret"})

    assert blocked.status_code == 429
    assert "频繁" in blocked.json()["error"]


def test_apps_api_requires_auth(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    client = TestClient(main.app)

    response = client.get("/api/apps")

    assert response.status_code == 401
    assert response.json() == {"error": "请先登录后再操作。"}


def test_create_app_and_read_status_payload(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    client = TestClient(main.app)

    with client:
        _login(client)
        created = client.post("/api/apps", json={"name": "演示应用"})

        assert created.status_code == 201
        payload = created.json()
        assert payload["name"] == "演示应用"
        assert payload["slug"] == "app"
        assert payload["status"] == "new"
        assert payload["ports"] == []
        assert payload["progress"] == {"stage": "idle", "percent": 0, "message": ""}
        assert payload["dependencies"] == {"inferred": [], "manual": []}

        listed = client.get("/api/apps")
        detail = client.get(f"/api/apps/{payload['id']}")

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["apps"]] == [payload["id"]]
    assert detail.status_code == 200
    assert detail.json()["id"] == payload["id"]


def test_create_app_rejects_blank_name(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    client = TestClient(main.app)

    with client:
        _login(client)
        response = client.post("/api/apps", json={"name": "   "})

    assert response.status_code == 400
    assert response.json() == {"error": "应用名称不能为空。"}


def test_upload_rejects_non_python_file(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    created = main.repo.create_app("演示应用")
    client = TestClient(main.app)

    with client:
        _login(client)
        response = client.post(
            f"/api/apps/{created.id}/upload",
            files={"file": ("notes.txt", b"print('hi')", "text/plain")},
            data={"manual_dependencies": ""},
        )

    assert response.status_code == 400
    assert response.json() == {"error": "仅支持上传 .py 文件。"}


def test_upload_rejects_oversized_file(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch, extra_config="max_upload_bytes = 8")
    created = main.repo.create_app("演示应用")
    client = TestClient(main.app)

    with client:
        _login(client)
        response = client.post(
            f"/api/apps/{created.id}/upload",
            files={"file": ("main.py", b"print('hello world')\n", "text/x-python")},
            data={"manual_dependencies": ""},
        )

    assert response.status_code == 413
    assert "8 B" in response.json()["error"]
    managed_app = main.repo.get_app(created.id)
    assert managed_app is not None
    app_dir = main.manager.app_dir(managed_app)
    assert not app_dir.exists() or not list(app_dir.glob(".pending-upload-*.py"))


def test_download_requires_uploaded_script(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    created = main.repo.create_app("演示应用")
    client = TestClient(main.app)

    with client:
        _login(client)
        response = client.get(f"/api/apps/{created.id}/download")

    assert response.status_code == 404
    assert response.json() == {"error": "当前应用尚未上传脚本。"}
