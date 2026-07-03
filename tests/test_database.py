import sqlite3

from app.database import AppRepository, slugify


def test_slugify_falls_back_for_empty_names() -> None:
    assert slugify("!!!") == "app"


def test_create_app_generates_unique_slugs(tmp_path) -> None:
    repo = AppRepository(tmp_path / "manager.db")

    first = repo.create_app("My App")
    second = repo.create_app("My App")

    assert first.slug == "my-app"
    assert second.slug == "my-app-2"
    assert [app.name for app in repo.list_apps()] == ["My App", "My App"]


def test_progress_fields_default_and_update(tmp_path) -> None:
    repo = AppRepository(tmp_path / "manager.db")
    managed_app = repo.create_app("Worker")

    assert managed_app.progress_stage == "idle"
    assert managed_app.progress_percent == 0
    assert managed_app.progress_message == ""

    repo.set_progress(managed_app.id, "installing", 70, "正在安装依赖...")
    updated = repo.get_app(managed_app.id)

    assert updated is not None
    assert updated.progress_stage == "installing"
    assert updated.progress_percent == 70
    assert updated.progress_message == "正在安装依赖..."


def test_progress_percent_is_bounded(tmp_path) -> None:
    repo = AppRepository(tmp_path / "manager.db")
    managed_app = repo.create_app("Worker")

    repo.set_progress(managed_app.id, "complete", 150, "完成")

    updated = repo.get_app(managed_app.id)
    assert updated is not None
    assert updated.progress_percent == 100


def test_existing_database_is_migrated_with_progress_defaults(tmp_path) -> None:
    db_path = tmp_path / "manager.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE managed_apps (
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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("INSERT INTO managed_apps (name, slug) VALUES (?, ?)", ("Legacy", "legacy"))

    repo = AppRepository(db_path)
    migrated = repo.get_app(1)

    assert migrated is not None
    assert migrated.progress_stage == "idle"
    assert migrated.progress_percent == 0
    assert migrated.progress_message == ""
