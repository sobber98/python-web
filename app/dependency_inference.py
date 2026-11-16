from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


KNOWN_IMPORT_TO_PACKAGE = {
    "bs4": "beautifulsoup4",
    "Crypto": "pycryptodome",
    "cv2": "opencv-python",
    "dotenv": "python-dotenv",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
}


EXCLUDED_SOURCE_DIRECTORIES = {"__pycache__", ".venv", "venv", "env", "node_modules", ".git"}


def infer_dependencies(script_path: Path) -> list[str]:
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    imports = _collect_imports(tree)
    local_modules = _local_modules(script_path.parent)
    return _imports_to_packages(imports, local_modules)


def infer_dependencies_for_tree(root: Path) -> list[str]:
    # 多文件应用需要合并目录内所有脚本的导入，并排除同目录下的本地模块。
    py_files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if any(part.startswith(".") or part in EXCLUDED_SOURCE_DIRECTORIES for part in relative.parts):
            continue
        py_files.append(path)

    imports: set[str] = set()
    for path in py_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        imports.update(_collect_imports(tree))
    return _imports_to_packages(imports, _local_modules_deep(root))


def parse_requirements_file(path: Path) -> list[str]:
    if not path.is_file():
        return []
    requirements: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-") or "://" in line:
            continue
        requirements.append(line)
    return requirements


def _collect_imports(tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module.split(".", 1)[0])
    return imports


def _imports_to_packages(imports: set[str], local_modules: set[str]) -> list[str]:
    packages: list[str] = []
    for name in sorted(imports):
        if name in sys.stdlib_module_names or name in local_modules:
            continue
        packages.append(KNOWN_IMPORT_TO_PACKAGE.get(name, name))
    return packages


def parse_manual_dependencies(text: str) -> list[str]:
    dependencies: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        dependencies.append(line)
    return dependencies


def merge_dependencies(inferred: list[str], manual_text: str) -> list[str]:
    manual = parse_manual_dependencies(manual_text)
    manual_keys = {_dependency_key(dependency) for dependency in manual}
    merged: list[str] = []
    seen: set[str] = set()
    for dependency in inferred:
        key = _dependency_key(dependency)
        if key in manual_keys or key in seen:
            continue
        seen.add(key)
        merged.append(dependency)
    for dependency in manual:
        key = _dependency_key(dependency)
        if key in seen:
            continue
        seen.add(key)
        merged.append(dependency)
    return merged


def _dependency_key(dependency: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", dependency)
    return (match.group(1) if match else dependency).replace("_", "-").lower()


def _local_modules(directory: Path) -> set[str]:
    modules: set[str] = set()
    if not directory.exists():
        return modules
    for child in directory.iterdir():
        if child.is_file() and child.suffix == ".py":
            modules.add(child.stem)
        elif child.is_dir() and (child / "__init__.py").exists():
            modules.add(child.name)
    return modules


def _local_modules_deep(root: Path) -> set[str]:
    modules: set[str] = set()
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if any(part.startswith(".") or part in EXCLUDED_SOURCE_DIRECTORIES for part in relative.parts):
            continue
        modules.add(path.stem)
        modules.update(part for part in relative.parent.parts if part not in (".", ""))
    return modules
