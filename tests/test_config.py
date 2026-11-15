import pytest

from app.config import load_settings


def test_config_file_is_required(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="Configuration file not found"):
        load_settings(tmp_path / "missing.toml")


def test_admin_password_is_required(tmp_path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("data_dir = 'data'\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="admin_password"):
        load_settings(config)


def test_load_settings_uses_local_config_file(tmp_path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        f"admin_password = 'secret'\nsecret_key = 'stable-session-key'\ndata_dir = '{tmp_path / 'runtime'}'\n",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.admin_password == "secret"
    assert settings.secret_key == "stable-session-key"
    assert settings.data_dir == (tmp_path / "runtime").resolve()
    assert settings.session_max_age == 60 * 60 * 12
    assert settings.session_https_only is False
    assert settings.max_upload_bytes == 10 * 1024 * 1024


def test_load_settings_reads_optional_security_settings(tmp_path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "admin_password = 'secret'\n"
        "session_max_age = 600\n"
        "session_https_only = true\n"
        "max_upload_bytes = 2048\n",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.session_max_age == 600
    assert settings.session_https_only is True
    assert settings.max_upload_bytes == 2048
