from __future__ import annotations

import logging

import uvicorn
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import Base, engine
from app.routers import router
from app.scheduler import start_scheduler


logging.basicConfig(level=logging.INFO)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve built frontend (single-host setup)
DIST_DIR = Path(__file__).parent / "frontend" / "dist"
if DIST_DIR.exists():
    # Serve all static files and enable SPA index fallback
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="spa")


@app.get("/", include_in_schema=False)
def root():  # type: ignore[override]
    if DIST_DIR.exists():  # StaticFiles handles this path; keep docs link if not built
        return RedirectResponse(url="/")
    return RedirectResponse(url="/docs")

@app.on_event("startup")
def _on_startup() -> None:
    start_scheduler()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

