from pathlib import Path

from app.dependency_inference import infer_dependencies, merge_dependencies, parse_manual_dependencies


def test_infer_dependencies_skips_stdlib_and_local_modules(tmp_path: Path) -> None:
    (tmp_path / "local_tool.py").write_text("VALUE = 1\n", encoding="utf-8")
    script = tmp_path / "main.py"
    script.write_text(
        "import os\nimport requests\nimport local_tool\nfrom bs4 import BeautifulSoup\nfrom pathlib import Path\n",
        encoding="utf-8",
    )

    assert infer_dependencies(script) == ["beautifulsoup4", "requests"]


def test_parse_manual_dependencies_ignores_blank_lines_and_comments() -> None:
    assert parse_manual_dependencies("\n# note\nrequests==2.32.3\n rich \n") == ["requests==2.32.3", "rich"]


def test_merge_dependencies_preserves_order_and_deduplicates() -> None:
    assert merge_dependencies(["requests", "rich"], "requests\nuvicorn") == ["rich", "requests", "uvicorn"]


def test_manual_dependency_versions_override_inferred_dependencies() -> None:
    assert merge_dependencies(["requests", "python-dotenv"], "requests==2.32.3\npython_dotenv>=1") == [
        "requests==2.32.3",
        "python_dotenv>=1",
    ]
