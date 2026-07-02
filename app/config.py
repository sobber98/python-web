from __future__ import annotations

import secrets
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path("config.toml")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    admin_password: str
    secret_key: str


def load_settings(config_path: Path | str = DEFAULT_CONFIG_PATH) -> Settings:
    path = Path(config_path)
    if not path.exists():
        raise RuntimeError(f"Configuration file not found: {path}. Copy config.example.toml to config.toml first.")

    with path.open("rb") as config_file:
        raw = tomllib.load(config_file)

    data_dir = Path(str(raw.get("data_dir", "data"))).resolve()
    db_path = Path(str(raw.get("db_path", data_dir / "manager.db"))).resolve()
    admin_password = str(raw.get("admin_password", "")).strip()
    if not admin_password:
        raise RuntimeError("admin_password must be set in config.toml before starting the manager")
    return Settings(
        data_dir=data_dir,
        db_path=db_path,
        admin_password=admin_password,
        secret_key=str(raw.get("secret_key") or secrets.token_urlsafe(32)),
    )
