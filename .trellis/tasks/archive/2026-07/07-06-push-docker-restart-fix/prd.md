# Push Docker restart fix

## Goal

Commit and push the Docker restart lifecycle fix to the configured GitHub remote so the server deployment can consume the updated code.

## Background

- The prior diagnosis found that `Process exited with code -15` is caused by managed app subprocesses receiving `SIGTERM` during Docker Compose restarts.
- The working tree already contains the fix: FastAPI lifespan shutdown calls `ProcessManager.shutdown()`, production Compose has a longer stop grace period, regression coverage was added, and the backend spec was updated.
- The user explicitly requested pushing the changes to GitHub and chose to create a Trellis task first.

## Requirements

- Inspect git status, diff, and recent history before committing.
- Commit only the intended Docker restart lifecycle fix, related regression test, backend spec update, production Compose grace-period change, and this Trellis task's planning artifacts.
- Do not commit ignored local secrets or runtime data such as `config.toml`, `data/`, virtualenvs, or cache directories.
- Push the resulting commit to the configured GitHub remote for the current branch.

## Acceptance Criteria

- [ ] `git status`, `git diff`, and recent commit history are reviewed before commit.
- [ ] Available local validation remains passing before commit.
- [ ] A commit containing the intended files is created.
- [ ] The commit is pushed successfully to GitHub.
- [ ] The user receives the pushed commit hash and remote/branch target.

## Notes

- Lightweight PRD-only task; no `design.md` or `implement.md` is required.
