# Upload And Install Progress Design

## Architecture

- Keep the current server-rendered dashboard but progressively enhance the upload form with JavaScript.
- Use `XMLHttpRequest` for upload because it exposes browser upload progress events.
- Add persisted progress fields to `managed_apps` so the UI can poll progress through the existing status endpoint.
- Move upload/install/start work into a background thread so the request returns quickly and the UI can keep polling.
- Keep pip output in `install.log`; progress is step-based, not parsed from pip percentage output.

## Data Model Additions

- `progress_stage`: machine-readable stage such as `idle`, `upload_received`, `parsing`, `venv`, `installing`, `starting`, `complete`, `failed`.
- `progress_percent`: integer 0-100 for coarse UI progress.
- `progress_message`: human-readable Chinese message for current operation.

Existing status values remain unchanged for API compatibility.

## Data Flow

1. Browser intercepts the upload form and sends `FormData` through `XMLHttpRequest`.
2. Browser displays upload transfer percentage from `xhr.upload.onprogress`.
3. Backend accepts the uploaded file, starts a background job, and returns JSON with `accepted: true`.
4. Background job stops the app, stores the script, infers dependencies, updates progress, creates/checks venv, installs dependencies, starts the app, and sets final progress.
5. UI polls `/api/apps/{id}/status` and `/api/apps/{id}/logs` to update install/start progress and logs.
6. Non-JavaScript fallback can still submit the form, but enhanced progress requires JavaScript.

## Progress Contract

- Upload progress is browser-side transfer progress only.
- Backend progress starts after upload is accepted.
- Failed operations set `status = error`, `progress_stage = failed`, and a visible `progress_message`.
- Successful operations end with `status = running`, `progress_stage = complete`, and `progress_percent = 100`.

## API Contract

- Upload route may return JSON when called with `Accept: application/json` or XMLHttpRequest.
- Status endpoint adds `progress_stage`, `progress_percent`, and `progress_message`.
- Existing fields remain unchanged.

## Trade-Offs

- Polling reuses existing infrastructure and avoids WebSocket/SSE complexity.
- Step-based progress is reliable across pip versions and package types.
- Background thread keeps implementation small, but work is still in-process; production restarts during install may lose in-flight progress.
