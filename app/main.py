from __future__ import annotations

import asyncio
from datetime import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .db import init_db
from .routes import router
from .sync_service import SyncService
from .scheduler_utils import schedule_daily_jobs


templates = Jinja2Templates(directory="app/templates")


def create_app() -> FastAPI:
    app = FastAPI(title="Immich Sync")

    static_dir = Path("app/static")
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.state.templates = templates

    @app.on_event("startup")
    async def on_startup() -> None:
        init_db()
        app.state.sync_service = SyncService()
        app.state.scheduler = AsyncIOScheduler()
        app.state.scheduler.start()
        schedule_daily_jobs(app)

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler:
            scheduler.shutdown(wait=False)

    app.include_router(router)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
