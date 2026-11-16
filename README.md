# Python Management Platform

A FastAPI + React web platform for trusted administrators to upload and run multiple Python scripts as managed background apps.

## Features

- Admin password login with signed session cookies.
- Change the admin password from the settings page (stored as a PBKDF2 hash in SQLite).
- Multiple managed Python apps.
- `.py` upload with automatic dependency inference, reinstall, and restart.
- Deploy Python apps directly from GitHub repositories (public or private).
- Optional GitHub webhook to redeploy automatically on push.
- Multi-file apps: a directory of Python files is deployed as one app.
- Per-app virtual environment, process state, and log file.
- Start, stop, restart, download, and delete controls.
- Upload progress and backend install progress shown separately.
- Real-time status and log polling.
- Startup recovery for apps marked as running.
- Configurable pip mirror for dependency installation.
- Responsive, dark-themed management console.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | FastAPI, Starlette sessions, SQLite, subprocess management |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query |
| Frontend tests | Vitest, Testing Library, jsdom |
| Backend tests | pytest, FastAPI `TestClient` |

The frontend is a standalone SPA in [`frontend/`](frontend). Vite builds it into `app/static/app/`, and FastAPI serves the built assets plus a catch-all route for client-side routing. All data operations go through JSON endpoints under `/api`.

## Local Development

Requirements: Python 3.11+ and Node.js 20+.

### 1. Backend

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp config.example.toml config.toml
# edit config.toml and set admin_password
```

### 2. Frontend

```bash
cd frontend
npm install
npm run build
```

### 3. Run

```bash
uvicorn app.main:app --reload --port 7999
```

Open `http://127.0.0.1:7999` and log in with `admin_password` from `config.toml`.

### Frontend Hot Reload

Run the backend on port 7999 and Vite on port 5173:

```bash
# terminal 1
uvicorn app.main:app --reload --port 7999

# terminal 2
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` requests to the backend.

## Tests

```bash
# Backend
pytest

# Frontend
cd frontend
npm test
npm run typecheck
```

## Docker

The multi-stage build compiles the SPA with Node and copies the result into the Python runtime image.

```bash
docker build -t python-management-platform:local .
```

GitHub Actions pushes images to GitHub Packages / GHCR on `master` and `main` pushes:

```text
ghcr.io/sobber98/python-management-platform:latest
ghcr.io/sobber98/python-management-platform:<commit-sha>
```

Pull a published image:

```bash
docker pull ghcr.io/sobber98/python-management-platform:latest
```

Run it with local config and persistent runtime data:

```bash
cp config.example.toml config.toml
# edit config.toml and set admin_password/secret_key
docker run --rm \
  -p 7999:7999 \
  -v "$(pwd)/config.toml:/app/config.toml:ro" \
  -v python-manager-data:/app/data \
  python-management-platform:local
```

## Production Deployment With Docker Compose

```bash
cp config.example.toml config.toml
# edit config.toml and set strong admin_password and secret_key
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

The production compose file pulls `ghcr.io/sobber98/python-management-platform:latest`, mounts `config.toml` read-only, and stores uploaded apps, per-app virtual environments, SQLite data, and logs in the `python-manager-data` Docker volume.

Stop the deployment:

```bash
docker compose -f docker-compose.prod.yml down
```

## Configuration

- `admin_password`: initial admin login password and required bootstrap secret. After you change the password from the settings page, the PBKDF2 hash stored in the database takes precedence, and the value in `config.toml` is no longer used for login.
- `secret_key`: optional session signing key. If omitted, a random key is generated at startup, which invalidates existing sessions after restart.
- `data_dir`: runtime data directory. Defaults to `data`.
- `db_path`: SQLite path. Defaults to `<data_dir>/manager.db`.
- `session_max_age`: session lifetime in seconds. Defaults to 12 hours.
- `session_https_only`: set to `true` when served over HTTPS so the session cookie is HTTPS-only. Defaults to `false`.
- `max_upload_bytes`: maximum uploaded script size in bytes. Defaults to 10 MiB.

## GitHub Deployment

Open **GitHub 部署** in the console, enter a repository URL (`https://github.com/owner/repo`,
`git@github.com:owner/repo.git`, or `owner/repo`) and an optional branch, then click deploy.
The repository is downloaded as a tarball and the Python sources are synced into app directories.

Repository conventions:

- Every top-level `.py` file becomes its own managed app.
- Every top-level directory containing `.py` files becomes one app. The entry file is resolved in
  order: `main.py`, `app.py`, `run.py`, `__main__.py`, or the only top-level `.py` file.
- A `requirements.txt` inside the app directory is merged with inferred imports. For single-file
  apps, the repository-root `requirements.txt` is used.
- `tests`, `test`, `docs`, `examples`, `.github`, `venv`, `.venv`, and hidden directories are skipped.
- Re-importing the same repository updates existing apps in place instead of creating duplicates.
- Uploading a `.py` file manually replaces the GitHub source for that app.

Private repositories: save a GitHub token in **系统设置 → GitHub 集成**. The token is stored in the
SQLite settings table; prefer a read-only fine-grained token.

Webhook auto-deploy: copy the webhook URL and secret from the same settings card into the
repository's **Settings → Webhooks** (Content type `application/json`, event: `push`). Pushes to the
app's deployment branch trigger a background redeploy; signature verification uses
`X-Hub-Signature-256`. If the default branch could not be resolved, pushes to any branch trigger a
redeploy.

Limits: 100 MB archive, 500 MB extracted, 5000 archive entries, and a 120-second download timeout.

## Security Scope

This MVP is for trusted administrator-uploaded code only. Uploaded Python code runs on the host inside a per-app virtual environment, but it is not sandboxed from the machine.

When deployed with Docker, uploaded scripts run inside the management container, but this is still not a security sandbox for untrusted public code. Put the service behind a trusted network or reverse proxy and keep `config.toml` private.
