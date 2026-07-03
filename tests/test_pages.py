from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def test_login_page_renders_with_current_starlette_signature(monkeypatch, tmp_path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        f"admin_password = 'secret'\nsecret_key = 'stable'\ndata_dir = '{tmp_path / 'data'}'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    import app.main

    importlib.reload(app.main)

    client = TestClient(app.main.app)
    response = client.get("/login")

    assert response.status_code == 200
    assert "管理员密码" in response.text
    assert "进入控制台" in response.text


def test_dashboard_contains_upload_and_install_progress_ui(monkeypatch, tmp_path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        f"admin_password = 'secret'\nsecret_key = 'stable'\ndata_dir = '{tmp_path / 'data'}'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    import app.main

    importlib.reload(app.main)
    created = app.main.repo.create_app("演示应用")

    client = TestClient(app.main.app)
    with client:
        response = client.post("/login", data={"password": "secret"}, follow_redirects=True)

    assert response.status_code == 200
    assert "上传进度" in response.text
    assert "安装进度" in response.text
    assert f"/apps/{created.id}/upload" in response.text


def test_status_api_requires_auth_and_includes_progress_fields(monkeypatch, tmp_path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        f"admin_password = 'secret'\nsecret_key = 'stable'\ndata_dir = '{tmp_path / 'data'}'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    import app.main

    importlib.reload(app.main)
    created = app.main.repo.create_app("演示应用")
    app.main.repo.set_progress(created.id, "installing", 70, "正在安装依赖...")

    client = TestClient(app.main.app)
    with client:
        unauthenticated = client.get(f"/api/apps/{created.id}/status")
        login = client.post("/login", data={"password": "secret"}, follow_redirects=False)
        authenticated = client.get(f"/api/apps/{created.id}/status")

    assert unauthenticated.status_code == 401
    assert login.status_code == 303
    assert authenticated.status_code == 200
    assert authenticated.json()["progress_stage"] == "installing"
    assert authenticated.json()["progress_percent"] == 70
    assert authenticated.json()["progress_message"] == "正在安装依赖..."
