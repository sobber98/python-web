# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

The platform is a small FastAPI/SQLite/process-manager application. Prefer standard-library modules for persistence, filesystem, and subprocess orchestration unless a concrete requirement justifies another dependency.

## Scenario: Dependency Inference And Manual Override

### 1. Scope / Trigger

- Trigger: dependency resolution crosses uploaded Python source, inferred package list, manual dependency text, pip install, and UI feedback.

### 2. Signatures

- `infer_dependencies(script_path: Path) -> list[str]`
- `parse_manual_dependencies(text: str) -> list[str]`
- `merge_dependencies(inferred: list[str], manual_text: str) -> list[str]`

### 3. Contracts

- Infer top-level imports using `ast`, not regex.
- Exclude standard library modules and local modules in the app directory.
- Map known import/package mismatches such as `bs4 -> beautifulsoup4`.
- Manual dependencies are newline-delimited pip requirement strings.
- Manual dependency entries override inferred dependencies with the same normalized package key.

### 4. Validation & Error Matrix

- Python syntax error -> upload marks app `error` and does not start it.
- Blank/comment manual lines -> ignored.
- Duplicate inferred/manual package -> install the manual entry once.

### 5. Good/Base/Bad Cases

- Good: inferred `requests` plus manual `requests==2.32.3` installs only `requests==2.32.3`.
- Base: no third-party imports and no manual dependencies yields no pip install command.
- Bad: regex-parse source text and install every imported name including stdlib modules.

### 6. Tests Required

- Assert stdlib and local modules are skipped.
- Assert known import/package mappings are applied.
- Assert manual versions override inferred package names.

### 7. Wrong vs Correct

#### Wrong

Install both `requests` and `requests==2.32.3` after manual override.

#### Correct

Normalize package keys and let manual dependency lines replace inferred entries for the same package.

## Scenario: Docker Production Deployment

### 1. Scope / Trigger

- Trigger: production deployment crosses image build, runtime config, persistent storage, and managed app virtual environments.

### 2. Signatures

- Image build: `docker build -t python-management-platform:<tag> .`
- Compose deploy: `docker compose -f docker-compose.prod.yml up -d --build`
- Runtime command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### 3. Contracts

- `config.toml` is mounted read-only at `/app/config.toml`.
- `/app/data` is persistent storage for SQLite, uploaded scripts, per-app venvs, and logs.
- The image includes Python venv support because managed apps call `python -m venv` at runtime.
- The container runs as a non-root `manager` user.

### 4. Validation & Error Matrix

- Missing mounted `config.toml` -> app fails fast with configuration-file error.
- Missing `admin_password` -> app fails fast before serving traffic.
- Missing venv support in image -> app upload/start fails during per-app dependency setup.

### 5. Good/Base/Bad Cases

- Good: compose mounts config read-only and data as a named volume.
- Base: local `docker build` completes and app imports with a mounted config.
- Bad: bake real `config.toml`, `data/`, or `.venv/` into the image.

### 6. Tests Required

- CI must run pytest and compileall.
- CI must build the Docker image and push it to GitHub Packages / GHCR on push events.
- Local smoke should import `app.main` with a generated `config.toml` before deployment.

### 7. Wrong vs Correct

#### Wrong

Copy `config.toml` into the Docker image and run as root with ephemeral `/app/data`.

#### Correct

Ignore local secrets in `.dockerignore`, mount `config.toml` read-only, persist `/app/data`, and run the process as the non-root `manager` user.

---

## Forbidden Patterns

- Do not add a default production admin password.
- Do not start managed scripts before upload syntax/import parsing and dependency install finish.
- Do not expose app logs or controls without authentication.

---

## Required Patterns

- Require local `config.toml` with `admin_password` before importing/starting the web app.
- Use per-app virtual environments and runtime directories.
- Stop a running app before overwriting its `main.py` during re-upload.
- Keep production Docker images free of local secrets and runtime data.

---

## Testing Requirements

- Unit-test pure dependency inference and merge behavior.
- Unit-test SQLite repository slug/status behavior.
- Unit-test process stop behavior for persisted PIDs where feasible.

---

## Code Review Checklist

- Authentication protects both page routes and `/api/*` routes.
- `desired_running` changes match operator intent.
- Dependency install failure is visible to users and does not leave status as running.
- Logs are per-app and tail-bounded.
- Docker deployment preserves `/app/data` and mounts `config.toml` read-only.
