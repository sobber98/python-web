# Quality Guidelines

> Code quality standards for frontend development.

---

## Overview

The frontend is server-rendered Jinja plus small progressive-enhancement JavaScript in templates. Preserve basic form behavior where feasible and add JavaScript only for interactions that require browser APIs, such as upload progress events.

## Scenario: Upload And Install Progress UI

### 1. Scope / Trigger

- Trigger: upload progress crosses browser `XMLHttpRequest`, form submission, backend status polling, and dashboard rendering.

### 2. Signatures

- Upload form: `#upload-form`
- Upload progress elements: `#upload-progress`, `#upload-bar`, `#upload-percent`
- Install progress elements: `#install-progress`, `#install-bar`, `#install-percent`, `#progress-message`

### 3. Contracts

- Use `XMLHttpRequest` for enhanced uploads because `fetch` does not expose standard upload progress events.
- Set `Accept: application/json` and `X-Requested-With: XMLHttpRequest` for enhanced uploads.
- Keep the original form action and method so the route can keep a non-JavaScript redirect fallback.
- Display upload progress separately from backend install/start progress.

### 4. Validation & Error Matrix

- Upload network error -> show a visible failure message in the progress panel.
- Upload HTTP error -> show a visible failure message.
- Backend status has progress message -> show install progress panel and message.

### 5. Good/Base/Bad Cases

- Good: upload bar reaches 100%, then install bar shows backend step messages.
- Base: dashboard renders progress UI even before upload starts, hidden until needed.
- Bad: use one progress bar for both browser upload and backend install without explaining what it represents.

### 6. Tests Required

- Render the dashboard and assert upload/install progress UI copy is present.
- Render login/dashboard pages through FastAPI `TestClient` after changing `cwd`.

### 7. Wrong vs Correct

#### Wrong

Use `fetch(new FormData(form))` and claim upload percentage is available.

#### Correct

Use `XMLHttpRequest` with `xhr.upload.onprogress` for transfer progress, then poll `/api/apps/{id}/status` for install/start progress.

---

## Forbidden Patterns

- Do not parse raw backend logs in the browser to infer app state.
- Do not remove non-JavaScript form behavior unless explicitly required.

---

## Required Patterns

- Keep user-visible management UI copy in Simplified Chinese.
- Keep API/status internal values unchanged and map them only at the display layer.

---

## Testing Requirements

- Page rendering tests should assert important visible Chinese UI labels.

---

## Code Review Checklist

- Upload and install progress are represented separately.
- Authenticated endpoints remain protected.
- The dashboard still renders without an active app.
