from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.ingest import next_run_at
from app.models import Health, Item, ItemSource, KevEntry, Severity, Source, Stream, SyncRun
from app.schemas import Counts, SourceStatus, Status, SyncStatus

router = APIRouter(tags=["status"])


@router.get("/status", response_model=Status)
async def status(session: AsyncSession = Depends(get_session)) -> Status:
    now = datetime.now(UTC)
    day_ago = now - timedelta(hours=24)

    last_run = await session.scalar(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1))
    sources = (await session.scalars(select(Source).order_by(Source.stream, Source.name))).all()
    enabled = [s for s in sources if s.enabled]

    by_severity = dict(
        (
            await session.execute(
                select(Item.severity, func.count())
                .where(Item.stream == Stream.main, Item.last_event_at >= day_ago)
                .group_by(Item.severity)
            )
        ).all()
    )
    items_24h = sum(by_severity.values())
    articles_24h = await session.scalar(
        select(func.count())
        .select_from(ItemSource)
        .join(Source, Source.id == ItemSource.source_id)
        .where(Source.stream == Stream.main, ItemSource.published_at >= day_ago)
    )
    # Whole catalog, not just CVEs on the board: "4 added to KEV this week".
    kev_added_7d = await session.scalar(
        select(func.count()).select_from(KevEntry).where(KevEntry.date_added >= (now - timedelta(days=7)).date())
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
        counts=Counts(
            critical_24h=by_severity.get(Severity.critical, 0),
            high_24h=by_severity.get(Severity.high, 0),
            medium_24h=by_severity.get(Severity.medium, 0),
            low_24h=by_severity.get(Severity.low, 0),
            items_24h=items_24h,
            articles_24h=articles_24h or 0,
            kev_added_7d=kev_added_7d or 0,
        ),
    )
