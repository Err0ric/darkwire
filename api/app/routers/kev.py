from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Item, ItemCve, KevEntry
from app.schemas import KevRow

router = APIRouter(tags=["kev"])


@router.get("/kev", response_model=list[KevRow])
async def kev(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[KevRow]:
    """Recent additions to the whole CISA KEV catalog, newest first, with a board row when one exists."""
    since = (datetime.now(UTC) - timedelta(days=days)).date()
    on_board = (
        select(ItemCve.cve_id, Item.id)
        .join(Item, Item.id == ItemCve.item_id)
        .distinct(ItemCve.cve_id)
        .order_by(ItemCve.cve_id, Item.last_event_at.desc())
        .subquery()
    )
    rows = (
        await session.execute(
            select(KevEntry, on_board.c.id)
            .outerjoin(on_board, on_board.c.cve_id == KevEntry.cve_id)
            .where(KevEntry.date_added >= since)
            .order_by(KevEntry.date_added.desc(), KevEntry.cve_id.desc())
            .limit(limit)
        )
    ).all()
    return [
        KevRow(cve_id=k.cve_id, vendor=k.vendor, product=k.product, date_added=k.date_added, item_id=item_id)
        for k, item_id in rows
    ]
