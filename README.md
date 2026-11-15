# Python Management Platform

A FastAPI + React web platform for trusted administrators to upload and run multiple Python scripts as managed background apps.

## Features

- Admin password login with signed session cookies.
- Multiple managed Python apps.
- `.py` upload with automatic dependency inference, reinstall, and restart.
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

- `admin_password`: required admin login password.
- `secret_key`: optional session signing key. If omitted, a random key is generated at startup, which invalidates existing sessions after restart.
- `data_dir`: runtime data directory. Defaults to `data`.
- `db_path`: SQLite path. Defaults to `<data_dir>/manager.db`.

## Security Scope

This MVP is for trusted administrator-uploaded code only. Uploaded Python code runs on the host inside a per-app virtual environment, but it is not sandboxed from the machine.

When deployed with Docker, uploaded scripts run inside the management container, but this is still not a security sandbox for untrusted public code. Put the service behind a trusted network or reverse proxy and keep `config.toml` private.
