from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.routers.kev import WEEK, kev_since
from app.ingest import next_run_at
from app.staleness import not_stale
from app.models import Cve, Health, Item, ItemSource, KevEntry, Severity, Source, Stream, SyncRun
from app.schemas import Counts, SourceStatus, Status, SummariesStatus, SyncStatus
from app.summaries import health
from app.throttle import read_limit

router = APIRouter(tags=["status"])


@router.get("/status", response_model=Status)
@read_limit
async def status(request: Request, session: AsyncSession = Depends(get_session)) -> Status:
    now = datetime.now(UTC)
    day_ago = now - timedelta(hours=24)

    last_run = await session.scalar(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1))
    sources = (await session.scalars(select(Source).order_by(Source.stream, Source.name))).all()
    enabled = [s for s in sources if s.enabled]

    by_severity = dict(
        (
            await session.execute(
                select(Item.severity, func.count())
                .where(Item.stream == Stream.main, Item.last_event_at >= day_ago, not_stale(now))
                .group_by(Item.severity)
            )
        ).all()
    )
    items_24h = sum(by_severity.values())
    by_severity_7d = dict(
        (
            await session.execute(
                select(Item.severity, func.count())
                .where(Item.stream == Stream.main, Item.last_event_at >= now - timedelta(days=7), not_stale(now))
                .group_by(Item.severity)
            )
        ).all()
    )
    articles_24h = await session.scalar(
        select(func.count())
        .select_from(ItemSource)
        .join(Source, Source.id == ItemSource.source_id)
        .where(Source.stream == Stream.main, ItemSource.published_at >= day_ago)
    )
    # Whole catalog, not just CVEs on the board: "4 added to KEV this week".
    kev_added_7d = await session.scalar(
        select(func.count()).select_from(KevEntry).where(KevEntry.date_added >= kev_since(WEEK))
    )

    # Board CVEs in KEV whose due date is today or in the next 6 days.
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    kev_due_7d = await session.scalar(
        select(func.count(func.distinct(Cve.id)))
        .select_from(Cve)
        .join(Item, Item.cve_id == Cve.id)
        .where(
            Item.stream == Stream.main,
            Cve.kev.is_(True),
            Cve.kev_due_date >= today,
            Cve.kev_due_date < today + timedelta(days=7),
        )
    )

    return Status(
        now=now,
        sync=SyncStatus(
            last_started_at=last_run.started_at if last_run else None,
            last_finished_at=last_run.finished_at if last_run else None,
            last_ok=last_run.ok if last_run else None,
            skipped_ads=last_run.skipped_ads if last_run else None,
            next_run_at=next_run_at(),
            interval_minutes=get_settings().ingest_interval_minutes,
        ),
        sources_total=len(enabled),
        sources_ok=sum(s.health == Health.ok for s in enabled),
        sources_failing=sum(s.health == Health.failing for s in enabled),
        sources_disabled=len(sources) - len(enabled),
        sources=[SourceStatus.model_validate(s) for s in sources],
        summaries=SummariesStatus(**await health(session)),
        counts=Counts(
            critical_24h=by_severity.get(Severity.critical, 0),
            high_24h=by_severity.get(Severity.high, 0),
            medium_24h=by_severity.get(Severity.medium, 0),
            low_24h=by_severity.get(Severity.low, 0),
            items_24h=items_24h,
            articles_24h=articles_24h or 0,
            kev_added_7d=kev_added_7d or 0,
            kev_due_7d=kev_due_7d or 0,
            critical_7d=by_severity_7d.get(Severity.critical, 0),
            high_7d=by_severity_7d.get(Severity.high, 0),
            medium_7d=by_severity_7d.get(Severity.medium, 0),
            low_7d=by_severity_7d.get(Severity.low, 0),
        ),
    )
