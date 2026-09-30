from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Cve, Item, ItemCve, KevEntry
from app.schemas import KevRow
from app.throttle import cap, heavy_limit, read_limit

router = APIRouter(tags=["kev"])

WEEK = 7


def kev_since(days: int):
    """The first date_added in a window of `days` (UTC). /status counts the week with it too."""
    return (datetime.now(UTC) - timedelta(days=days)).date()


@router.get("/kev", response_model=list[KevRow])
@read_limit
@heavy_limit
async def kev(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    limit: int | None = Query(None, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[KevRow]:
    """Recent additions to the whole CISA KEV catalog, newest first, with a board row when one exists.
    With no limit, a window of a week or less returns every addition in it (the wire's "Added to
    KEV this week", which must match /status kev_added_7d); a longer one the newest 20."""
    if limit is not None:
        limit = cap(request, limit)
    elif days > WEEK:
        limit = 20
    since = kev_since(days)
    on_board = (
        select(ItemCve.cve_id, Item.id)
        .join(Item, Item.id == ItemCve.item_id)
        .distinct(ItemCve.cve_id)
        .order_by(ItemCve.cve_id, Item.last_event_at.desc())
        .subquery()
    )
    rows = (
        await session.execute(
            select(KevEntry, on_board.c.id, Cve.base_score, Cve.base_severity)
            .outerjoin(on_board, on_board.c.cve_id == KevEntry.cve_id)
            .outerjoin(Cve, Cve.id == KevEntry.cve_id)
            .where(KevEntry.date_added >= since)
            .order_by(KevEntry.date_added.desc(), KevEntry.cve_id.desc())
            .limit(limit)
        )
    ).all()
    return [
        KevRow(
            cve_id=k.cve_id, vendor=k.vendor, product=k.product, date_added=k.date_added, due_date=k.due_date,
            item_id=item_id, cvss=float(score) if score is not None else None, severity=severity,
        )
        for k, item_id, score, severity in rows
    ]
