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
