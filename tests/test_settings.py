from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from unittest import mock

from app.database import AppRepository, PIP_INDEX_URL_SETTING_KEY
from app.process_manager import ProcessManager


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


def test_dashboard_topbar_contains_settings_link(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    with client:
        client.post("/login", data={"password": "secret"}, follow_redirects=True)
        response = client.get("/")

    assert response.status_code == 200
    assert 'href="/settings"' in response.text
    assert "系统设置" in response.text


def test_settings_page_requires_auth(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    response = client.get("/settings", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_settings_page_lists_presets_and_current_selection(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    with client:
        client.post("/login", data={"password": "secret"}, follow_redirects=True)
        response = client.get("/settings")

    assert response.status_code == 200
    assert "PyPI 官方源" in response.text
    assert "清华大学" in response.text
    assert "阿里云" in response.text
    assert "腾讯云" in response.text
    assert "中国科学技术大学" in response.text
    assert "自定义" in response.text
    # 默认选中 official
    assert 'value="official"' in response.text and "checked" in response.text


def test_save_selects_preset_then_persists(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    with client:
        client.post("/login", data={"password": "secret"}, follow_redirects=True)
        saved = client.post("/settings", data={"source": "tsinghua"}, follow_redirects=False)
        assert saved.status_code == 303
        assert saved.headers["location"] == "/settings"
        redis = client.get("/settings")

    assert redis.status_code == 200
    assert 'value="tsinghua"' in redis.text and "checked" in redis.text
    assert main.repo.get_setting(PIP_INDEX_URL_SETTING_KEY) == "https://pypi.tuna.tsinghua.edu.cn/simple"


def test_save_invalid_custom_url_rejected(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    with client:
        client.post("/login", data={"password": "secret"}, follow_redirects=True)
        rejected = client.post(
            "/settings",
            data={"source": "custom", "custom_url": "notaurl"},
            follow_redirects=False,
        )

    assert rejected.status_code == 400
    assert main.repo.get_setting(PIP_INDEX_URL_SETTING_KEY, "") == ""
    assert "http" in rejected.text


def test_install_dependencies_appends_index_url(tmp_path: Path) -> None:
    repo = AppRepository(tmp_path / "manager.db")
    repo.set_setting(PIP_INDEX_URL_SETTING_KEY, "https://mirrors.aliyun.com/pypi/simple")
    managed_app = repo.create_app("Worker")
    repo.update_upload(managed_app.id, "main.py", "requests", ["requests"])

    manager = ProcessManager(repo, tmp_path / "data")
    captured: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured.append(list(cmd))
        return mock.Mock(returncode=0)

    with mock.patch.object(subprocess, "run", side_effect=fake_run):
        ok = manager.install_dependencies(repo.get_app(managed_app.id))

    pip_calls = [cmd for cmd in captured if "pip" in cmd]
    assert ok is True
    assert pip_calls == [
        [
            str(manager.venv_python(managed_app)),
            "-m",
            "pip",
            "install",
            "requests",
            "-i",
            "https://mirrors.aliyun.com/pypi/simple",
        ]
    ]


def test_install_dependencies_without_setting_keeps_default(tmp_path: Path) -> None:
    repo = AppRepository(tmp_path / "manager.db")
    managed_app = repo.create_app("Worker")
    repo.update_upload(managed_app.id, "main.py", "requests", ["requests"])

    manager = ProcessManager(repo, tmp_path / "data")
    captured: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured.append(list(cmd))
        return mock.Mock(returncode=0)

    with mock.patch.object(subprocess, "run", side_effect=fake_run):
        ok = manager.install_dependencies(repo.get_app(managed_app.id))

    pip_calls = [cmd for cmd in captured if "pip" in cmd]
    assert ok is True
    assert pip_calls == [
        [
            str(manager.venv_python(managed_app)),
            "-m",
            "pip",
            "install",
            "requests",
        ]
    ]