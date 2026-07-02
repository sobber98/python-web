# Logging Guidelines

> How logging is done in this project.

---

## Overview

Managed app output is captured as app-scoped log files, not as process manager application logs. Each app has an `install.log` for venv/pip output and a `runtime.log` for script stdout/stderr.

## Scenario: App Log Capture

### 1. Scope / Trigger

- Trigger: user-uploaded process output crosses subprocess, filesystem, API, and UI boundaries.

### 2. Signatures

- `ProcessManager.install_log_path(app) -> Path`
- `ProcessManager.log_path(app) -> Path`
- `ProcessManager.read_log_tail(app, limit=20000) -> str`
- API: `GET /api/apps/{app_id}/logs -> {"logs": str}`

### 3. Contracts

- `install.log` receives venv creation and pip install output.
- `runtime.log` receives stdout and stderr from the managed script.
- Log reads are tail-bounded so large logs do not freeze the UI.
- Logs are per app and stored below the slugged app runtime directory.

### 4. Validation & Error Matrix

- Unknown app id -> `404`.
- Unauthenticated API request -> `401` JSON response.
- Missing log file -> empty log segment, not an exception.

### 5. Good/Base/Bad Cases

- Good: dependency install failure is visible in `install.log` and app status is `error`.
- Base: app has no logs yet and the UI renders an empty log block.
- Bad: route handlers read entire unbounded log files into memory.

### 6. Tests Required

- Assert log-tail reads include install and runtime content when present.
- Assert missing log files produce an empty string.
- Assert install failure marks app status `error`.

### 7. Wrong vs Correct

#### Wrong

Expose subprocess output only in server stdout or one global log file.

#### Correct

Write per-app `install.log` and `runtime.log`, then expose a bounded combined tail through the authenticated log API.

---

## Log Levels

- App process logs are raw user script output and do not use manager log levels.
- Manager lifecycle errors are stored in `managed_apps.last_error` for UI display.

---

## Structured Logging

- Store structured status in SQLite fields; keep raw subprocess output in files.

---

## What to Log

- Pip install output.
- Script stdout/stderr.
- User-visible lifecycle errors in `last_error`.

---

## What NOT to Log

- Do not log `admin_password` from `config.toml` or session secrets.
- Do not assume uploaded script output is safe or non-sensitive; keep the UI authenticated.
