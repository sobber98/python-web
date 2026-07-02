# Python management platform

## Goal

Build a web-based Python process management platform where an operator can upload Python source files, install required dependencies, keep the uploaded script running in the background, view runtime logs, and automatically restart the process when a replacement Python file is uploaded.

The page should feel modern and usable on desktop and mobile.

## Background And Decisions

- The repository currently has Trellis/OpenCode project metadata only; there is no existing application code or established web framework.
- The feature spans backend process management, dependency installation, file upload/storage, log capture, and a frontend management UI.
- Because arbitrary Python upload and dependency installation can execute code on the host, the product must explicitly define its trust boundary before implementation.
- MVP trust boundary: uploaded code is provided by a trusted administrator/operator, not by untrusted public users.
- MVP scope: manage multiple independent Python apps/scripts, not just a single uploaded script.
- Dependency declaration decision: MVP should attempt automatic dependency inference from uploaded `.py` files and also allow manual dependency input for packages/versions that inference cannot resolve correctly.
- Process controls decision: each app should support manual start, stop, restart, and delete actions in addition to automatic restart after re-upload.
- Restart recovery decision: when the management platform restarts, apps that were previously intended to be running should be automatically restored.
- Access control decision: protect the management UI and APIs with a simple administrator password login; the password and platform settings are configured through a local configuration file.

## Requirements

- Provide a web UI for uploading a Python file.
- Provide a way to create and view multiple managed Python apps.
- After upload, install dependencies needed by the script based on inferred imports and manual dependency input.
- Infer likely third-party dependencies from uploaded Python imports and install them before running the app.
- Provide a manual dependency input field per app so the operator can add or override packages to install.
- Show dependency inference and installation logs so failures are diagnosable.
- Keep each managed app's uploaded file, dependency environment, process state, and logs separate from other apps.
- Run each uploaded script as a background process after dependencies are installed.
- Capture and persist runtime logs from each process.
- Display each app's current process status and logs in the web UI.
- When a new Python file is uploaded for the same managed app, stop that app's existing process and start the new version automatically without affecting other apps.
- Provide manual start, stop, restart, and delete controls per app.
- Persist each app's desired running state and automatically restore apps marked as running when the management platform starts.
- Provide a modern, responsive page design.
- Require login before accessing management pages or APIs.
- Provide Docker-based build and production deployment artifacts.
- Provide a workflow that runs tests and validates Docker image buildability.
- Treat sandboxing for untrusted public code as outside the MVP.

## Acceptance Criteria

- [ ] A user can open the web page and upload a Python file through the UI.
- [ ] A user can create or select multiple managed apps from the UI.
- [ ] The backend stores the uploaded Python file in an app-managed location.
- [ ] The backend attempts to infer import dependencies from the uploaded script and installs inferred packages before starting the script.
- [ ] A user can manually provide additional dependencies or version-pinned packages for an app.
- [ ] The backend installs the combination of inferred dependencies and manually entered dependencies before starting the app.
- [ ] If dependency inference or installation fails, the UI clearly shows the failed package/command output and does not report the app as running.
- [ ] Each app has an isolated dependency environment from other managed apps.
- [ ] Each uploaded script continues running after the upload request finishes.
- [ ] Standard output and standard error from each script are recorded and viewable in the UI.
- [ ] Re-uploading a replacement Python file for one app restarts only that app's managed process without requiring a server restart.
- [ ] A user can manually start, stop, restart, and delete an app from the UI.
- [ ] If the management platform restarts, apps previously marked as running are started again automatically.
- [ ] The UI shows per-app upload state, dependency/install state, running/stopped/error state, and logs.
- [ ] The UI remains usable on desktop and mobile widths.
- [ ] Management pages and APIs require an authenticated administrator session.
- [ ] The administrator password and runtime paths are configurable through a local configuration file.
- [ ] A Docker image can be built for the platform.
- [ ] A production deployment path is documented using Docker Compose with persistent runtime data and local config mounting.
- [ ] A workflow runs tests and builds the Docker image.

## Out of Scope Candidate Items

- Multi-user authorization and role management.
- Running untrusted public code safely; this may require container or VM isolation and is outside the MVP.
- Distributed deployment across multiple machines.
- Fully reliable dependency resolution for dynamic imports, package/import name mismatches, system packages, native build dependencies, or automatically inferred version constraints.
