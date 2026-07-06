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

- Good: production compose pulls the published GHCR image, mounts config read-only, and stores data in a named volume.
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

## Scenario: Managed App Shutdown During Container Restarts

### 1. Scope / Trigger

- Trigger: Docker or the ASGI server stops the manager process while uploaded app subprocesses are still running.

### 2. Signatures

- `ProcessManager.shutdown() -> None`
- FastAPI lifespan shutdown must call `manager.shutdown()` after serving stops.
- App process state persists in SQLite fields `status`, `desired_running`, `pid`, and `last_error`.

### 3. Contracts

- Container shutdown should terminate tracked app subprocesses before the manager exits.
- Production Compose should allow enough stop grace for lifespan cleanup before Docker force-kills the container.
- Shutdown preserves `desired_running=True` for apps that should be restored on the next manager startup.
- Shutdown clears the runtime `pid` and stores status `stopped` without writing `Process exited with code -15` as an app error.
- Startup restore uses `desired_running=True` as the source of truth and restarts those apps without reinstalling dependencies.

### 4. Validation & Error Matrix

- Tracked app receives shutdown `SIGTERM` -> status `stopped`, `pid=NULL`, `desired_running=True`, `last_error=''`.
- App was intentionally stopped by operator -> status `stopped`, `pid=NULL`, `desired_running=False`.
- App exits non-zero while still desired outside shutdown -> status `error`, `last_error='Process exited with code <code>'`.
- Per-app restore failure during platform startup -> status `error` for that app only; other apps still restore.

### 5. Good/Base/Bad Cases

- Good: `docker compose restart` stops tracked apps cleanly, then the next container startup restores desired apps.
- Base: manual app stop remains manual and does not auto-restore.
- Bad: allow Docker restart `SIGTERM` to race with watcher threads and persist `Process exited with code -15` as an app failure.

### 6. Tests Required

- Regression-test `ProcessManager.shutdown()` with a tracked subprocess and watcher thread, asserting status `stopped`, `pid is None`, `desired_running is True`, and empty `last_error`.
- Keep persisted-PID stop coverage for manager restarts that happen without a container restart.

### 7. Wrong vs Correct

#### Wrong

Let the ASGI app exit without stopping tracked subprocesses, then rely on Docker to terminate them.

#### Correct

Call `manager.shutdown()` from the FastAPI lifespan shutdown hook so process-manager state is updated before Docker tears down the container.

## Scenario: FastAPI Template Rendering

### 1. Scope / Trigger

- Trigger: page routes cross FastAPI, Starlette, Jinja templates, and packaged static/template files.

### 2. Signatures

- `templates.TemplateResponse(request, "template.html", context)`
- `Jinja2Templates(directory=APP_DIR / "templates")`
- `StaticFiles(directory=APP_DIR / "static")`

### 3. Contracts

- Use the current Starlette `TemplateResponse(request, name, context)` calling convention.
- Resolve template/static directories relative to `app/main.py`, not the process current working directory.
- Page routes must render successfully in the Docker working directory and in tests that change `cwd`.

### 4. Validation & Error Matrix

- Old positional signature `TemplateResponse("login.html", {"request": request})` -> can raise `TypeError: unhashable type: 'dict'` on current Starlette.
- Relative `app/templates` path from `cwd` -> can fail when the process starts outside the repository root.

### 5. Good/Base/Bad Cases

- Good: `TemplateResponse(request, "login.html", {"error": ""})`.
- Base: login page returns 200 and contains `Admin password`.
- Bad: passing request inside context while also using old positional argument order.

### 6. Tests Required

- Render `/login` through FastAPI `TestClient`.
- Test after changing `cwd` away from the repository root.

### 7. Wrong vs Correct

#### Wrong

```python
templates.TemplateResponse("login.html", {"request": request, "error": ""})
```

#### Correct

```python
templates.TemplateResponse(request, "login.html", {"error": ""})
```

## Scenario: Upload And Install Progress

### 1. Scope / Trigger

- Trigger: upload/install progress crosses browser upload events, FastAPI upload route, background process manager work, SQLite progress fields, status API, and dashboard rendering.

### 2. Signatures

- `AppRepository.set_progress(app_id, stage, percent, message) -> None`
- `ProcessManager.start(app_id, install=True, progress=None) -> None`
- API: `POST /apps/{app_id}/upload` returns JSON for XMLHttpRequest clients.
- API: `GET /api/apps/{app_id}/status` includes `progress_stage`, `progress_percent`, and `progress_message`.

### 3. Contracts

- Browser upload progress is transfer progress only.
- Backend progress is step-based: `upload_received`, `parsing`, `venv`, `installing`, `starting`, `complete`, or `failed`.
- Do not parse pip percentage output for progress.
- Failed install/start sets status `error` and progress stage `failed`.
- Existing status enum values remain stable.

### 4. Validation & Error Matrix

- Invalid app id -> `404`.
- Invalid file extension -> `400`.
- Python syntax error -> status `error`, progress `failed`, visible Chinese progress message.
- Dependency install failure -> status `error`, progress `failed`, pip output remains in `install.log`.

### 5. Good/Base/Bad Cases

- Good: XHR upload reaches 100%, backend progress advances through step messages, then status becomes `running`.
- Base: normal non-JS form submission redirects back to the app detail page.
- Bad: keep the request blocked during pip install so the UI cannot poll progress.

### 6. Tests Required

- Assert progress fields default and update in SQLite.
- Assert dashboard renders upload/install progress UI.
- Assert status API includes progress fields when app exists.

### 7. Wrong vs Correct

#### Wrong

Parse pip output to infer exact percentage and block the upload request until install completes.

#### Correct

Return quickly for XHR uploads, run install/start in a background thread, and expose coarse progress through the authenticated status API.

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
- Explicitly limit setuptools package discovery to `app*` so runtime `data/` is never treated as a Python package.

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
- Docker deployment uses the published GHCR image, preserves `/app/data`, and mounts `config.toml` read-only.
- Template rendering works with current Starlette and does not depend on the process working directory.
- Upload/install progress is step-based and exposed through persisted status fields, not pip percentage parsing.
