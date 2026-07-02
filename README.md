# Python Management Platform

A FastAPI-based web platform for trusted administrators to upload and run multiple Python scripts as managed background apps.

## Features

- Admin password login.
- Multiple managed Python apps.
- `.py` upload with automatic restart for that app.
- Best-effort dependency inference from imports plus manual dependency input.
- Per-app virtual environment, process state, and log file.
- Start, stop, restart, and delete controls.
- Startup recovery for apps marked as running.
- Responsive management UI.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
cp config.example.toml config.toml
# edit config.toml and set admin_password
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` and log in with the `admin_password` from `config.toml`.

## Docker

Build the production image locally:

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
  -p 8000:8000 \
  -v "$(pwd)/config.toml:/app/config.toml:ro" \
  -v python-manager-data:/app/data \
  python-management-platform:local
```

## Production Deployment With Docker Compose

```bash
cp config.example.toml config.toml
# edit config.toml and set strong admin_password and secret_key
docker compose -f docker-compose.prod.yml up -d --build
```

The production compose file mounts `config.toml` read-only and stores uploaded apps, per-app virtual environments, SQLite data, and logs in the `python-manager-data` Docker volume.

To deploy an image already published to GitHub Packages, set the image in `docker-compose.prod.yml` to `ghcr.io/sobber98/python-management-platform:latest` and remove or ignore the `build` section.

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
