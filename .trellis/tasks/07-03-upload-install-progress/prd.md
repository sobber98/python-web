# Upload and install progress

## Goal

Show clear progress feedback while an operator uploads a Python file and while the platform infers/installs dependencies before restarting the managed app.

## Background And Current Behavior

- The dashboard currently submits uploads through a normal HTML form in `app/templates/dashboard.html`.
- The upload route in `app/main.py` writes the file, infers imports, installs dependencies synchronously via `ProcessManager.start(..., install=True)`, then redirects back to the app detail page.
- `ProcessManager.install_dependencies()` currently runs venv creation and `pip install` synchronously, writing pip output to `install.log`.
- The UI already polls `/api/apps/{app_id}/status` and `/api/apps/{app_id}/logs` every 4 seconds for selected apps.
- Backend status values are currently `new`, `installing`, `starting`, `running`, `stopped`, and `error`.
- Product decision: dependency installation progress should be step-based rather than parsing fine-grained pip percentages.

## Requirements

- Show upload progress while the browser is sending the `.py` file.
- Show dependency/install progress after upload is accepted and before the app reaches running or error state.
- Use coarse steps for backend progress: upload received, dependency parsing, virtual environment setup, dependency installation, app startup, complete, or failed.
- Keep users on the app detail page during upload/install instead of leaving them with no feedback during a long request.
- Continue showing install output/logs so users can diagnose slow or failed dependency installation.
- Preserve authenticated access for all progress/status endpoints.
- Preserve existing app status semantics unless a new status/progress contract is explicitly planned.

## Acceptance Criteria

- [ ] Uploading a Python file shows a visible progress indicator that reaches 100% when the file transfer completes.
- [ ] Dependency inference/install/start steps are visible after upload completes.
- [ ] Progress is step-based and does not rely on fragile parsing of pip percentage output.
- [ ] If dependency installation fails, the UI shows the failure state and install log output.
- [ ] The app detail page updates to running/stopped/error without manual refresh.
- [ ] Existing start/stop/restart/delete controls continue to work.
- [ ] Existing tests pass, with new tests for upload/progress UI or progress state where feasible.

## Out Of Scope Candidates

- Exact pip package-by-package percentage based on download/build progress unless explicitly required.
- WebSocket/SSE real-time streaming unless polling is insufficient.
- Background job persistence across management-platform restarts beyond existing app desired-state recovery.

## Open Questions

- None blocking.
