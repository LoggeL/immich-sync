# Immich Sync

A web dashboard and service to synchronize albums across multiple Immich instances.

- Create a sync group and keep target albums in sync across instances
- Per-instance size limits (default 100 MB) with oversized file categorization
- Daily scheduled syncs, plus manual “Sync Now”
- Progress tracking per instance and on the main dashboard

## Quickstart (uv)

Requirements: Python 3.11+ and uv installed.

```bash
uv venv && . .venv/bin/activate
uv pip install -e .
immich-sync  # or: uv run immich-sync
```
The server starts on 0.0.0.0:8080 (reload enabled).

## Configuration

Environment variables (prefix `IMMICH_SYNC_`):
- `DATABASE_URL`: SQLModel connection string (default: local SQLite file `immich_sync.db`)
- `DEFAULT_SYNC_TIME`: default daily time, e.g. `02:00`

Use a `.env` file in the repo root to set these.

## Usage

1) Open the dashboard (default `http://localhost:8080`).
2) Create a group (name + daily time).
3) Add instances to the group (label, base URL, API key, album ID, size limit).
4) Click “Sync Now” or wait for the scheduled time.

## Progress and Oversized Files

- Group page shows live per-instance progress during a sync.
- Main page shows per-group progress and instance counts.
- Assets larger than an instance’s limit are skipped and listed as “Oversized”.

## Notes

- Syncs run in a background thread to avoid blocking the web UI.
- Album IDs link to the Immich album page on that instance.

## Development

```bash
uv venv && . .venv/bin/activate
uv pip install -e .
uv run ruff check
uv run uvicorn app.main:app --reload
```

License: MIT
