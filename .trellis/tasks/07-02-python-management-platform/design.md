# Python Management Platform Design

## Architecture

- Backend: FastAPI application serving JSON APIs and server-rendered HTML pages.
- Frontend: Jinja templates with modern responsive CSS and small progressive-enhancement JavaScript for uploads, polling, controls, and log refresh.
- Persistence: SQLite database for app metadata, desired state, dependency inputs, status, timestamps, and auth session data if needed.
- Runtime storage: app-managed data directory with one subdirectory per managed app containing the uploaded script, virtual environment, logs, and install/runtime metadata.
- Process manager: in-process registry that starts/stops subprocesses and reconciles persisted desired state on platform startup.

## Core Data Model

- `ManagedApp`: id, name, slug, script path, manual dependency text, inferred dependencies, status, desired_running, pid, last_error, created_at, updated_at.
- `AppEvent` or log files: lifecycle/install events and captured stdout/stderr. MVP may store process logs as files and lifecycle summaries in SQLite.
- Auth/session: administrator login state; password is read from the local configuration file and never stored in plaintext.

## Data Flow

1. Admin logs in with the configured password.
2. Admin creates or selects an app.
3. Admin uploads a `.py` file and optionally enters manual dependencies.
4. Backend validates file type/name, stores it under the app directory, stops the current app process if running, infers imports, creates/updates the app venv, installs inferred plus manual dependencies, then starts the script.
5. Process stdout/stderr are appended to the app log file.
6. UI polls status/log endpoints and renders per-app state.
7. Platform startup loads apps with `desired_running = true` and starts them again.

## Dependency Inference Contract

- Parse the uploaded Python file with `ast` and collect top-level import module names from `import x` and `from x import y`.
- Exclude Python standard library modules and local modules/files in the app directory.
- Treat remaining names as best-effort package names for `pip install`.
- Combine inferred names with manual dependency lines. Manual lines allow versions such as `requests==2.32.3` and package names that differ from import names.
- Show inferred dependencies, manual dependencies, and pip output in the UI.
- Inference is explicitly best-effort and not expected to solve dynamic imports, native system dependencies, or all package/import naming mismatches.

## Process Management Contract

- Each app gets its own virtual environment.
- Starting an app uses that app's venv Python executable and the stored script path.
- Stop first sends terminate, then kills after a timeout if the process does not exit.
- Restart is stop followed by dependency install/start.
- Delete stops the process, removes app metadata, and removes that app's runtime directory.
- Re-upload restarts only the selected app and must not affect other running apps.
- `desired_running` records operator intent. Manual stop sets it false; start/restart/upload-start sets it true after successful launch.

## API/UI Boundaries

- Pages require an authenticated administrator session.
- API endpoints return normalized status fields that the UI can render without parsing backend logs.
- Expected endpoints: login/logout, list apps, create app, app detail, upload script, start, stop, restart, delete, status, logs.
- Validation happens at API entry points: app name, uploaded extension, dependency text, and app existence.

## Configuration Contract

- Default config path: `config.toml` in the project root.
- Example config path: `config.example.toml` committed to the repository.
- Real `config.toml` is local-only and ignored by git because it contains secrets.
- Required key: `admin_password`.
- Optional keys: `secret_key`, `data_dir`, `db_path`.
- If `secret_key` is omitted, a random key is generated at startup and sessions are invalidated on restart.

## Operational Notes

- MVP is for trusted administrator-uploaded code only. It does not sandbox arbitrary untrusted code.
- Default bind should be safe for local development; production exposure should be behind a trusted network/reverse proxy.
- Logs should be bounded or tail-readable so large output does not freeze the UI.
- Platform startup recovery should not block server readiness indefinitely; failed restores mark the affected app as error and record logs.
- Production Docker deployment runs the management platform in a container with `config.toml` mounted read-only and app runtime `data/` mounted as persistent storage.
- The Docker image must include Python venv support because managed apps create per-app virtual environments at runtime.

## Build And Deployment Contract

- `Dockerfile` builds a production image for the FastAPI platform.
- `.dockerignore` excludes local runtime data, virtual environments, git metadata, caches, and local secrets.
- `docker-compose.prod.yml` documents production deployment with persistent `data` volume and local `config.toml` bind mount.
- `.github/workflows/ci.yml` installs dependencies, runs tests, and builds the Docker image.

## Trade-Offs

- FastAPI plus server-rendered templates keeps the first version smaller than a separate SPA while still supporting a modern UI.
- SQLite is enough for a single-node manager and keeps deployment simple.
- In-process process tracking is simple but means an external supervisor is still recommended for the management platform itself.
- Docker Compose provides a simple single-node production supervisor via container restart policy, while managed app process supervision remains inside the platform.
