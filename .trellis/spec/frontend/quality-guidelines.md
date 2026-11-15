# Quality Guidelines

> Code quality standards for frontend development.

---

## Overview

The frontend is a React 18 + TypeScript SPA built with Vite, styled with Tailwind CSS, and served by FastAPI. All server communication goes through the typed client in `src/lib/api.ts`. Server state is managed with TanStack Query; do not mirror it into separate global stores.

## Scenario: Upload And Install Progress UI

### 1. Scope / Trigger

- Trigger: upload progress crosses browser `XMLHttpRequest`, FastAPI multipart handling, backend status polling, and dashboard rendering.

### 2. Signatures

- Upload hook: `useUploadScript(appId)` in `src/lib/queries.ts`
- Upload progress state: `active`, `percent`, `error`, `success`
- Install progress source: `app.progress = { stage, percent, message }`
- Backend upload endpoint: `POST /api/apps/{app_id}/upload`
- Backend detail endpoint: `GET /api/apps/{app_id}`

### 3. Contracts

- Use `XMLHttpRequest` for uploads because `fetch` does not expose standard upload progress events.
- Send `Accept: application/json` and `X-Requested-With: XMLHttpRequest`.
- Display browser upload progress separately from backend install progress.
- After a successful upload, invalidate the app detail, app list, and logs queries.
- Handle `401` by redirecting to `/login`.

### 4. Validation & Error Matrix

- Upload network error -> visible failure message.
- Upload HTTP error -> parse `{"error": ...}` or `{"detail": ...}` and show it.
- Backend progress message -> show install panel with stage label and percentage.

### 5. Good/Base/Bad Cases

- Good: upload bar reaches 100%, then install bar shows backend stage messages until running.
- Base: install panel stays hidden until `progress.percent > 0` or a message exists.
- Bad: use one progress bar for both browser upload and backend install without explaining what it represents.

### 6. Tests Required

- Render login, dashboard, and settings pages with Vitest + Testing Library and assert important visible Chinese labels.
- Dashboard test must cover empty state, app detail, upload/install copy, and log output.
- Backend API tests must cover auth, app payload shape, upload validation, and settings validation.

### 7. Wrong vs Correct

#### Wrong

Use `fetch(new FormData(form))` and claim upload percentage is available.

#### Correct

Use `XMLHttpRequest` with `xhr.upload.onprogress` for transfer progress, then read install progress from the polled `ManagedApp.progress` payload.

---

## Forbidden Patterns

- Do not parse raw backend logs in the browser to infer app state.
- Do not duplicate server state into a separate global store.
- Do not call `fetch` directly from components; use `src/lib/api.ts`.
- Do not hardcode API base URLs; use same-origin paths under `/api`.
- Do not render untrusted HTML; logs are rendered as text inside `<pre>`.
- Do not use `any` in API payload types; update `src/types.ts` instead.

---

## Required Patterns

- Keep user-visible management UI copy in Simplified Chinese.
- Keep API/status internal values unchanged and map them only at the display layer (`src/lib/format.ts`).
- Use `queryKeys` for every query and invalidation.
- Guard protected routes with `ProtectedRoute` and `useSession`.
- Use the shared UI primitives for buttons, cards, fields, badges, and progress bars.

---

## Testing Requirements

- `cd frontend && npm test` must pass.
- `cd frontend && npm run typecheck` must pass.
- Page tests should assert important visible Chinese UI labels.
- Backend tests run with `pytest` from the repository root.

---

## Code Review Checklist

- Upload and install progress are represented separately.
- Authenticated endpoints remain protected and 401s redirect to `/login`.
- The dashboard still renders without an active app.
- Loading, empty, and error states are handled for every page-level query.
- No unused imports or `any` types; `tsc --noEmit` is clean.
