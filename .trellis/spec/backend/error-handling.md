# Error Handling

> How errors are handled in this project.

---

## Overview

The management platform returns user-facing route/API errors for validation failures and persists per-app lifecycle failures in `managed_apps.last_error`.

---

## Error Types

- Route validation errors use FastAPI `HTTPException`.
- Lifecycle errors use persisted status `error` plus `last_error`.

---

## Error Handling Patterns

- A failed dependency install must mark the app `error`, clear `desired_running`, and leave pip output in `install.log`.
- A script syntax error during upload must mark the app `error` and avoid reporting it as running.
- Platform startup restore must catch per-app exceptions so one broken app does not block server readiness.

---

## API Error Responses

- Unauthenticated `/api/*` requests return `401` with `{"error": "Authentication required"}`.
- Unknown app ids return `404` with an `error` payload.
- Page routes may redirect unauthenticated users to `/login`.

---

## Common Mistakes

- Do not set status to `stopped` if stopping a persisted PID fails because of permission errors.
- Do not overwrite an uploaded script before stopping the currently running process for that app.
