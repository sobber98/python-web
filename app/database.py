from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.models import ManagedApp


PIP_INDEX_URL_SETTING_KEY = "pip_index_url"
PIP_INDEX_SELECTOR_SETTING_KEY = "pip_index_selector"


class AppRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_apps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    script_name TEXT,
                    manual_dependencies TEXT NOT NULL DEFAULT '',
                    inferred_dependencies TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    desired_running INTEGER NOT NULL DEFAULT 0,
                    pid INTEGER,
                    last_error TEXT NOT NULL DEFAULT '',
                    progress_stage TEXT NOT NULL DEFAULT 'idle',
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    progress_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_columns(
                conn,
                {
                    "progress_stage": "TEXT NOT NULL DEFAULT 'idle'",
                    "progress_percent": "INTEGER NOT NULL DEFAULT 0",
                    "progress_message": "TEXT NOT NULL DEFAULT ''",
                },
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _ensure_columns(self, conn: sqlite3.Connection, definitions: dict[str, str]) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(managed_apps)").fetchall()}
        for column, definition in definitions.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE managed_apps ADD COLUMN {column} {definition}")

    def list_apps(self) -> list[ManagedApp]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM managed_apps ORDER BY updated_at DESC, id DESC").fetchall()
        return [self._row_to_app(row) for row in rows]

    def get_app(self, app_id: int) -> ManagedApp | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM managed_apps WHERE id = ?", (app_id,)).fetchone()
        return self._row_to_app(row) if row else None

    def get_app_by_slug(self, slug: str) -> ManagedApp | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM managed_apps WHERE slug = ?", (slug,)).fetchone()
        return self._row_to_app(row) if row else None

    def create_app(self, name: str) -> ManagedApp:
        slug_base = slugify(name)
        slug = slug_base
        suffix = 2
        with self._connection() as conn:
            while conn.execute("SELECT 1 FROM managed_apps WHERE slug = ?", (slug,)).fetchone():
                slug = f"{slug_base}-{suffix}"
                suffix += 1
            cur = conn.execute(
                "INSERT INTO managed_apps (name, slug) VALUES (?, ?)",
                (name.strip(), slug),
            )
            app_id = int(cur.lastrowid)
        app = self.get_app(app_id)
        if app is None:
            raise RuntimeError("failed to create app")
        return app

    def update_upload(
        self,
        app_id: int,
        script_name: str,
        manual_dependencies: str,
        inferred_dependencies: list[str],
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE managed_apps
                SET script_name = ?, manual_dependencies = ?, inferred_dependencies = ?,
                    status = 'installing', last_error = '', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (script_name, manual_dependencies, "\n".join(inferred_dependencies), app_id),
            )

    def set_status(self, app_id: int, status: str, last_error: str = "", pid: int | None = None) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE managed_apps
                SET status = ?, last_error = ?, pid = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, last_error, pid, app_id),
            )

    def set_progress(self, app_id: int, stage: str, percent: int, message: str) -> None:
        bounded_percent = max(0, min(100, percent))
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE managed_apps
                SET progress_stage = ?, progress_percent = ?, progress_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (stage, bounded_percent, message, app_id),
            )

    def set_status_with_progress(
        self,
        app_id: int,
        status: str,
        last_error: str,
        stage: str,
        percent: int,
        message: str,
    ) -> None:
        # 状态与进度合并为一条 UPDATE，避免失败路径上的两次独立事务。
        bounded_percent = max(0, min(100, percent))
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE managed_apps
                SET status = ?, last_error = ?, pid = NULL,
                    progress_stage = ?, progress_percent = ?, progress_message = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, last_error, stage, bounded_percent, message, app_id),
            )

    def set_desired_running(self, app_id: int, desired: bool) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE managed_apps
                SET desired_running = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (1 if desired else 0, app_id),
            )

    def delete_app(self, app_id: int) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM managed_apps WHERE id = ?", (app_id,))

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )

    def _row_to_app(self, row: sqlite3.Row) -> ManagedApp:
        return ManagedApp(
            id=int(row["id"]),
            name=str(row["name"]),
            slug=str(row["slug"]),
            script_name=row["script_name"],
            manual_dependencies=str(row["manual_dependencies"]),
            inferred_dependencies=str(row["inferred_dependencies"]),
            status=str(row["status"]),
            desired_running=bool(row["desired_running"]),
            pid=row["pid"],
            last_error=str(row["last_error"]),
            progress_stage=str(row["progress_stage"]),
            progress_percent=int(row["progress_percent"]),
            progress_message=str(row["progress_message"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "app"
