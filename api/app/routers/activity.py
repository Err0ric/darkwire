from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.events import derived_events
from app.models import BoardEvent, Item, ItemSource, Severity, Stream
from app.schemas import Activity, ActivityHour, BoardEventOut
from app.throttle import read_limit

router = APIRouter(tags=["activity"])

HOURS = 24
# The landing filters by kind (no headlines), so send enough to fill its lines.
EVENTS = 40
PEAK_DAYS = 7
# A derived event is the same as a recorded one: same kind and subject, and for ingest and
# services within this much time (kev and nvd: at any time, plus the same detail for nvd).
SAME_WITHIN = timedelta(minutes=10)


def _key(kind: str, subject: str, detail: str, at: datetime) -> str:
    return f"{kind}|{subject}|{detail}|{at.astimezone(UTC).isoformat(timespec='seconds')}"


def _is_recorded(d: dict, recorded: list[BoardEvent]) -> bool:
    for r in recorded:
        if r.kind != d["kind"] or r.subject != d["subject"]:
            continue
        if d["kind"] == "kev" or (d["kind"] == "nvd" and r.detail == d["detail"]):
            return True
        if d["kind"] in ("ingest", "services") and abs(r.at - d["at"]) <= SAME_WITHIN:
            return True
    return False


@router.get("/activity", response_model=Activity)
@read_limit
async def activity(request: Request, session: AsyncSession = Depends(get_session)) -> Activity:
    """The landing's trace and log.

    hours: rows per hour over the last 24 hours, oldest first, the last slot being the current
    hour, each row counted at its first article's published time (its first-seen time when no
    article has one; a future date counts as now), and how many of those are now Critical, KEV
    or exploited.

    events: the last EVENTS things the board did in the last 24 hours, newest first: recorded board_events merged
    with events derived from the last 24 hours of data (ingest batches, KEV additions, NVD
    scores, service incidents), so the log is full right after a deploy; a derived event the
    board also recorded is dropped."""
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
    # The busiest single hour of the last PEAK_DAYS days, the same way: the trace's scale, so a
    # quiet day draws small blips and a busy one tall spikes.
    per_hour = (
        select(func.count().label("n"))
        .select_from(Item)
        .outerjoin(published, published.c.item_id == Item.id)
        .where(Item.stream == Stream.main, when >= now - timedelta(days=PEAK_DAYS))
        .group_by(hour)
        .subquery()
    )
    peak = await session.scalar(select(func.coalesce(func.max(per_hour.c.n), 0)))
    hours = []
    for k in range(HOURS):
        start = first + timedelta(hours=k)
        n, c = counts.get(start, (0, 0))
        hours.append(ActivityHour(start=start, items=n, critical=c))

    since = now - timedelta(hours=HOURS)
    recorded = list(
        (
            await session.scalars(
                select(BoardEvent).where(BoardEvent.at >= since).order_by(BoardEvent.at.desc(), BoardEvent.id.desc()).limit(200)
            )
        ).all()
    )
    merged = [
        BoardEventOut(
            id=e.id, at=e.at, kind=e.kind, subject=e.subject, detail=e.detail, item_id=e.item_id,
            key=_key(e.kind, e.subject, e.detail, e.at),
        )
        for e in recorded[:EVENTS]
    ]
    for d in await derived_events(session, since, now):
        if not _is_recorded(d, recorded):
            merged.append(BoardEventOut(id=None, key=_key(d["kind"], d["subject"], d["detail"], d["at"]), **d))
    merged.sort(key=lambda e: e.at, reverse=True)
    return Activity(hours=hours, peak_7d=peak or 0, events=merged[:EVENTS])

