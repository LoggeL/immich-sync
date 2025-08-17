from __future__ import annotations

import asyncio
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from .config import settings
from .db import get_session
from .models import SyncGroup


def schedule_daily_jobs(app: FastAPI) -> None:
    scheduler = getattr(app.state, "scheduler", None)
    sync_service = getattr(app.state, "sync_service", None)
    if not scheduler or not sync_service:
        return

    for job in scheduler.get_jobs():
        scheduler.remove_job(job.id)

    with get_session() as session:
        for group in session.query(SyncGroup).all():
            hh, mm = (group.schedule_time or settings.default_sync_time).split(":", 1)
            trigger = CronTrigger(hour=int(hh), minute=int(mm))
            scheduler.add_job(lambda gid=group.id: asyncio.create_task(sync_service.run_sync_group(gid)), trigger)

