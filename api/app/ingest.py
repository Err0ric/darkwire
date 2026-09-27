"""Scheduled ingest. Stubbed: it records the run and logs what it would fetch."""

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Source, SyncRun

log = logging.getLogger(__name__)

JOB_ID = "ingest"
scheduler = AsyncIOScheduler(timezone=UTC)


async def run_ingest() -> None:
    async with SessionLocal() as session:
        run = SyncRun(started_at=datetime.now(UTC))
        session.add(run)
        await session.commit()

        sources = (await session.scalars(select(Source).where(Source.enabled))).all()
        for s in sources:
            log.info("ingest (stub): would fetch %s [%s] %s", s.name, s.stream.value, s.feed_url)

        run.finished_at = datetime.now(UTC)
        run.ok = True
        await session.commit()
        log.info("ingest (stub): run %d done, %d sources", run.id, len(sources))


def start_scheduler() -> None:
    interval = get_settings().ingest_interval_minutes
    scheduler.add_job(
        run_ingest,
        "interval",
        minutes=interval,
        id=JOB_ID,
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("scheduler: ingest every %d min", interval)


def next_run_at() -> datetime | None:
    job = scheduler.get_job(JOB_ID) if scheduler.running else None
    return job.next_run_time if job else None
