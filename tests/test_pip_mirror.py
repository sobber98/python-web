from __future__ import annotations

from pathlib import Path

from app.database import AppRepository, PIP_INDEX_URL_SETTING_KEY
from app.pip_mirror import build_pip_index_args, validate_mirror_url


def test_get_setting_returns_default_when_missing(tmp_path: Path) -> None:
    repo = AppRepository(tmp_path / "manager.db")
    assert repo.get_setting("anything", "fallback") == "fallback"
    assert repo.get_setting("anything") == ""


def test_set_setting_round_trips_and_updates(tmp_path: Path) -> None:
    repo = AppRepository(tmp_path / "manager.db")
    repo.set_setting("pip_index_url", "https://mirrors.aliyun.com/pypi/simple")
    assert repo.get_setting("pip_index_url") == "https://mirrors.aliyun.com/pypi/simple"

    # ON CONFLICT path：再次写入会更新而不是报错
    repo.set_setting("pip_index_url", "https://pypi.org/simple")
    assert repo.get_setting("pip_index_url") == "https://pypi.org/simple"


def test_migrated_database_creates_app_settings_table(tmp_path: Path) -> None:
    db_path = tmp_path / "manager.db"
    repo = AppRepository(db_path)
    repo.create_app("Worker")
    repo.set_progress(1, "installing", 50, "正在安装依赖...")
    # 再次构造应保持幂等，表已存在不报错
    AppRepository(db_path)
    assert repo.get_setting(PIP_INDEX_URL_SETTING_KEY, "") == ""


def test_validate_mirror_url_accepts_https_and_rejects_invalid() -> None:
    assert validate_mirror_url("https://pypi.org/simple") == (True, "")
    assert validate_mirror_url("http://mirrors.intra:8081/simple") == (True, "")

    ok, msg = validate_mirror_url("")
    assert ok is False and msg
    ok, msg = validate_mirror_url("notaurl")
    assert ok is False and "http" in msg
    ok, msg = validate_mirror_url("https://")
    assert ok is False and "主机名" in msg


def test_build_pip_index_args_handles_scheme_and_normalization() -> None:
    assert build_pip_index_args("") == []
    assert build_pip_index_args("https://mirrors.aliyun.com/pypi/simple") == [
        "-i",
        "https://mirrors.aliyun.com/pypi/simple",
    ]
    # http 自动追加 --trusted-host，并去掉尾部斜杠
    assert build_pip_index_args("http://mirrors.intra:8081/simple/") == [
        "-i",
        "http://mirrors.intra:8081/simple",
        "--trusted-host",
        "mirrors.intra:8081",
    ]