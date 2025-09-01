# Immich Sync

## Backend (FastAPI)

- Install deps: `uv sync`
- Run dev: `uv run uvicorn main:app --reload`
- Env: set `IMMICH_SYNC_DATABASE_URL` if needed (default `sqlite:///./data.db`)

## Frontend (Vite React)

- cd frontend
- Install deps: `pnpm install`
- Dev server: `pnpm run dev` (proxies `/api` to `http://127.0.0.1:8000`)
- Build: `pnpm run build`

## Single-port deployment

- Build the frontend: `cd frontend && pnpm build`
- Start FastAPI: `cd .. && uv run uvicorn main:app --host 0.0.0.0 --port 8000`
- The FastAPI app serves the built SPA from `frontend/dist` and exposes the API at `/api` on the same port.
- Any non-`/api` path falls back to the SPA `index.html`.

## Auth flow

- Register: POST `/api/auth/register` { username, password }
- Login: POST `/api/auth/login_json` { username, password } → store `access_token`
- Subsequent calls send `Authorization: Bearer <token>`

## Features

- Manage groups and instances
- Trigger sync and view progress
