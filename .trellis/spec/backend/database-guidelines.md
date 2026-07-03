# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

The Python management platform uses SQLite through the standard `sqlite3` module. `AppRepository` owns schema creation and all `managed_apps` reads/writes.

## Scenario: Managed App State

### 1. Scope / Trigger

- Trigger: multi-app process state crosses database, process manager, API, and UI boundaries.

### 2. Signatures

- Table: `managed_apps`
- Repository: `AppRepository.create_app(name) -> ManagedApp`
- Repository: `AppRepository.update_upload(app_id, script_name, manual_dependencies, inferred_dependencies) -> None`
- Repository: `AppRepository.set_status(app_id, status, last_error='', pid=None) -> None`
- Repository: `AppRepository.set_desired_running(app_id, desired) -> None`

### 3. Contracts

- `slug` is unique and generated from the app display name.
- `script_name` is nullable until a script is uploaded.
- `manual_dependencies` and `inferred_dependencies` are newline-delimited text.
- `desired_running` stores operator intent and is used for platform startup recovery.
- `pid` is the current process group leader PID when running, otherwise null.
- `progress_stage`, `progress_percent`, and `progress_message` store coarse upload/install/start progress for UI polling.

### 4. Validation & Error Matrix

- Empty app name -> route returns `400` before repository insert.
- Duplicate slug -> repository appends numeric suffix.
- Missing app id -> route returns `404`.
- Process start without uploaded script -> status becomes `error` with a user-visible message.

### 5. Good/Base/Bad Cases

- Good: create `My App`, slug becomes `my-app`, second create becomes `my-app-2`.
- Base: app exists with no script and status `new`.
- Bad: route stores raw uploaded filenames or raw display names as runtime paths.

### 6. Tests Required

- Assert duplicate display names receive unique slugs.
- Assert upload/start status transitions persist in SQLite.
- Assert stop clears `pid` and `desired_running`.
- Assert progress defaults to `idle`/`0`/empty message and updates with bounded percentages.

### 7. Wrong vs Correct

#### Wrong

Store runtime app files under a path built from raw `name` or uploaded filename.

#### Correct

Generate a slug in `AppRepository`, store uploaded scripts as `main.py`, and derive runtime paths from the slug.

---

## Query Patterns

- Use parameterized SQLite queries only.
- Keep row-to-dataclass conversion centralized in `AppRepository`.

---

## Migrations

- MVP uses `CREATE TABLE IF NOT EXISTS` in `AppRepository.init_schema()`.
- Add explicit migration steps before changing existing column meanings.

---

## Naming Conventions

- Tables use snake_case plural names.
- Runtime state columns use explicit names such as `desired_running`, `last_error`, and `updated_at`.

---

## Common Mistakes

- Do not mark an app stopped if the persisted PID could not be terminated; preserve error status instead.
