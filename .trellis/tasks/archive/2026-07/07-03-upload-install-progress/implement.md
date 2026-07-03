# Implementation Plan

## Steps

1. Add progress fields to SQLite schema initialization and row mapping.
2. Add repository helper to update progress fields.
3. Refactor upload handling into a background job with JSON response for enhanced clients and redirect fallback for normal form submits.
4. Update process/install workflow to set step-based progress messages and percentages.
5. Extend `/api/apps/{id}/status` with progress fields.
6. Add dashboard progress UI: upload bar, backend install/start bar, progress message, and automatic polling.
7. Update tests for progress fields, upload page rendering, and repository defaults.
8. Run pytest and compileall.

## Validation Commands

- `.venv/bin/python -m pytest`
- `.venv/bin/python -m compileall app tests`

## Review Gates

- Upload progress only represents browser transfer progress.
- Backend progress is step-based and does not parse pip percentages.
- Existing status values and controls remain compatible.
- Auth still protects upload/status/log endpoints.

## Rollback Points

- If background upload introduces instability, keep synchronous fallback while retaining progress fields.
- If polling is too noisy, increase interval after upload completes.
