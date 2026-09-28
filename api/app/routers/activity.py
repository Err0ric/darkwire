from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import BoardEvent, Item, ItemSource, Severity, Stream
from app.schemas import Activity, ActivityHour, BoardEventOut
from app.throttle import read_limit

router = APIRouter(tags=["activity"])

HOURS = 24
EVENTS = 20


@router.get("/activity", response_model=Activity)
@read_limit
async def activity(request: Request, session: AsyncSession = Depends(get_session)) -> Activity:
    """The landing's trace and log: rows per hour over the last 24 hours (all, and those now
    Critical, KEV or exploited), oldest first, the last slot being the current hour, each row
    counted at its first article's published time (its first-seen time when no article has one;
    a future date counts as now); and the last EVENTS board events, newest first."""
    now = datetime.now(UTC)
    first = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=HOURS - 1)
    published = (
        select(ItemSource.item_id, func.min(ItemSource.published_at).label("at")).group_by(ItemSource.item_id).subquery()
    )
    when = func.least(func.coalesce(published.c.at, Item.first_seen_at), func.now())
    hour = func.date_trunc("hour", when, "UTC")
    hot = or_(Item.severity == Severity.critical, Item.kev.is_(True), Item.exploited.is_(True))
    rows = (
        await session.execute(
            select(hour, func.count(), func.count().filter(hot))
            .select_from(Item)
            .outerjoin(published, published.c.item_id == Item.id)
            .where(Item.stream == Stream.main, when >= first)
            .group_by(hour)
        )
    ).all()
    counts = {h.astimezone(UTC): (n, c) for h, n, c in rows}
    hours = []
    for k in range(HOURS):
        start = first + timedelta(hours=k)
        n, c = counts.get(start, (0, 0))
        hours.append(ActivityHour(start=start, items=n, critical=c))
    events = (await session.scalars(select(BoardEvent).order_by(BoardEvent.at.desc(), BoardEvent.id.desc()).limit(EVENTS))).all()
    return Activity(hours=hours, events=[BoardEventOut.model_validate(e) for e in events])
