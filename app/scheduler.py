from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import get_session
from .models import SyncGroup
from .routers import sync_service


logger = logging.getLogger("immich_sync.scheduler")


def _daily_sync_job() -> None:
    now = datetime.now(tz=timezone.utc)
    with get_session() as session:
        groups = session.query(SyncGroup).filter(SyncGroup.active == True).all()  # noqa: E712
        for g in groups:
            if g.expires_at and g.expires_at.replace(tzinfo=timezone.utc) < now:
                continue
            logger.info("Scheduling daily sync for group_id=%s", g.id)
            sync_service.run_sync_group_in_thread(g.id)


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    # 00:00 UTC daily
    scheduler.add_job(_daily_sync_job, CronTrigger(hour=0, minute=0, timezone="UTC"))
    scheduler.start()
    return scheduler

