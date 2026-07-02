# Directory Structure

> How backend code is organized in this project.

---

## Overview

The application backend lives under `app/` as a small FastAPI service. Keep framework wiring in `app/main.py`, persistence in `app/database.py`, runtime process control in `app/process_manager.py`, and dependency parsing in `app/dependency_inference.py`.

---

## Directory Layout

```
app/
├── config.py                 # Environment-backed settings
├── database.py               # SQLite repository and schema setup
├── dependency_inference.py   # Import parsing and dependency merging
├── main.py                   # FastAPI routes and template rendering
├── models.py                 # Shared dataclasses
├── process_manager.py        # venv, subprocess, logs, restore control
├── static/                   # CSS and browser JS
└── templates/                # Jinja templates
tests/                        # pytest tests for backend contracts
```

---

## Module Organization

- Keep cross-layer status fields owned by `ManagedApp` in `app/models.py` and returned through route handlers without re-parsing in templates.
- Keep filesystem/process side effects in `ProcessManager`; route handlers should orchestrate requests but not directly spawn app scripts.
- Keep dependency parsing pure where possible so it can be tested without FastAPI or subprocesses.

---

## Naming Conventions

- Runtime app directories use repository-generated slugs, not raw display names.
- Uploaded scripts are stored as `main.py` inside the app directory to avoid trusting user-provided filenames.

---

## Examples

- `app/main.py` validates uploads, persists inferred dependencies, and delegates start/stop work to `ProcessManager`.
- `app/process_manager.py` owns virtual environment creation, pip install, subprocess lifecycle, and log-tail reads.
