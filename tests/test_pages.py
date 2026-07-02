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
    assert "Admin password" in response.text
