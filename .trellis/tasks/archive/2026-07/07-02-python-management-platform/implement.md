# Implementation Plan

## Steps

1. Create the Python web app structure, dependency metadata, and basic FastAPI entrypoint.
2. Add SQLite persistence for managed apps and lifecycle/status fields.
3. Implement administrator password login, session protection, and local config-file configuration.
4. Implement app directory layout and safe file upload handling for `.py` scripts.
5. Implement dependency inference with `ast`, standard-library/local-module filtering, manual dependency merging, and pip install logging.
6. Implement per-app virtual environment creation and dependency installation.
7. Implement process manager start, stop, restart, delete, log capture, and platform startup restore.
8. Implement API routes for app CRUD, upload, controls, status, and log tail.
9. Implement responsive management UI: login, app list, app detail, upload/manual dependency form, controls, status indicators, inferred dependencies, and logs.
10. Add tests for dependency inference, persistence/state transitions, and process manager behavior where feasible.
11. Add Docker build artifacts, production Docker Compose deployment, and CI workflow that tests, builds the image, and pushes it to GitHub Packages / GHCR.
12. Run formatting/lint/tests and perform a manual smoke test with a simple uploaded Python script.

## Validation Commands

- `python -m compileall .`
- `python -m pytest` if tests are added.
- `docker build -t python-management-platform:local .` if Docker is available.
- Render `/login` through a FastAPI test client to catch Starlette/Jinja template signature regressions.
- Manual smoke test: start the platform, log in, create an app, upload a simple script that prints periodically, confirm logs update, re-upload replacement script, confirm only that app restarts.

## Review Gates

- Confirm arbitrary upload is still documented as trusted-admin-only.
- Confirm APIs require authentication.
- Confirm `config.toml` is local-only and `config.example.toml` documents required settings.
- Confirm each app gets a separate venv, log file, and process state.
- Confirm dependency install failures are visible in the UI and do not falsely show running status.
- Confirm platform restart attempts to restore apps with `desired_running = true`.
- Confirm Docker Compose production deployment pulls the GHCR image, mounts `config.toml`, and persists `data/`.
- Confirm CI logs in to GHCR and pushes the Docker image to GitHub Packages.

## Rollback Points

- If dependency inference is unreliable, keep manual dependency input as the supported fallback and surface clear install logs.
- If process restart behavior is unstable, preserve uploaded files and metadata while disabling automatic startup restore until fixed.
- If UI polling creates load or log-size issues, reduce polling frequency and tail log output server-side.
