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


def _login(client) -> None:
    response = client.post("/api/auth/login", json={"password": "secret"})
    assert response.status_code == 200


def test_settings_api_requires_auth(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    response = client.get("/api/settings")

    assert response.status_code == 401
    assert response.json() == {"error": "请先登录后再操作。"}


def test_settings_api_lists_presets_and_current_selection(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    with client:
        _login(client)
        response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    labels = [preset["label"] for preset in payload["presets"]]
    assert "PyPI 官方源" in labels
    assert "清华大学" in labels
    assert "阿里云" in labels
    assert "腾讯云" in labels
    assert "中国科学技术大学" in labels
    assert "自定义" in labels
    assert payload["selector"] == "official"
    assert payload["effective_url"] == "https://pypi.org/simple"


def test_update_settings_selects_preset_then_persists(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    with client:
        _login(client)
        saved = client.put("/api/settings", json={"source": "tsinghua", "custom_url": ""})
        reread = client.get("/api/settings")

    assert saved.status_code == 200
    assert saved.json()["selector"] == "tsinghua"
    assert saved.json()["effective_url"] == "https://pypi.tuna.tsinghua.edu.cn/simple"
    assert reread.json()["selector"] == "tsinghua"
    assert main.repo.get_setting(PIP_INDEX_URL_SETTING_KEY) == "https://pypi.tuna.tsinghua.edu.cn/simple"


def test_update_settings_rejects_invalid_custom_url(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    with client:
        _login(client)
        rejected = client.put("/api/settings", json={"source": "custom", "custom_url": "notaurl"})

    assert rejected.status_code == 400
    assert "http" in rejected.json()["error"]
    assert main.repo.get_setting(PIP_INDEX_URL_SETTING_KEY, "") == ""


def test_update_settings_rejects_unknown_source(monkeypatch, tmp_path: Path) -> None:
    main = _reload_main_with(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    with client:
        _login(client)
        rejected = client.put("/api/settings", json={"source": "unknown", "custom_url": ""})

    assert rejected.status_code == 400
    assert rejected.json() == {"error": "未知的镜像源选项。"}


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
