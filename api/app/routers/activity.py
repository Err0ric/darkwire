from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import BoardEvent, Item, Severity, Stream
from app.schemas import Activity, ActivityHour, BoardEventOut
from app.throttle import read_limit

router = APIRouter(tags=["activity"])

HOURS = 24
EVENTS = 20


@router.get("/activity", response_model=Activity)
@read_limit
async def activity(request: Request, session: AsyncSession = Depends(get_session)) -> Activity:
    """The landing's trace and log: rows the board took in per hour over the last 24 hours (all,
    and those now Critical, KEV or exploited), oldest first, the last slot being the current
    hour; and the last EVENTS board events, newest first."""
    now = datetime.now(UTC)
    first = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=HOURS - 1)
    hour = func.date_trunc("hour", Item.first_seen_at, "UTC")
    hot = or_(Item.severity == Severity.critical, Item.kev.is_(True), Item.exploited.is_(True))
    rows = (
        await session.execute(
            select(hour, func.count(), func.count().filter(hot))
            .where(Item.stream == Stream.main, Item.first_seen_at >= first)
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
