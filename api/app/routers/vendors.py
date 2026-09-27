from datetime import UTC, datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Item, Stream, Vendor
from app.schemas import VendorOut

router = APIRouter(tags=["vendors"])


class Sort(str, Enum):
    name = "name"
    active = "active"


@router.get("/vendors", response_model=list[VendorOut])
async def vendors(sort: Sort = Sort.name, session: AsyncSession = Depends(get_session)) -> list[VendorOut]:
    week_ago = datetime.now(UTC) - timedelta(days=7)
    counts = (
        select(Item.vendor_id, func.count().label("n"))
        .where(Item.stream == Stream.main, Item.last_event_at >= week_ago)
        .group_by(Item.vendor_id)
        .subquery()
    )
    n = func.coalesce(counts.c.n, 0)
    stmt = select(Vendor, n).outerjoin(counts, counts.c.vendor_id == Vendor.id)
    stmt = stmt.order_by(n.desc(), Vendor.name) if sort == Sort.active else stmt.order_by(Vendor.name)

    rows = (await session.execute(stmt)).all()
    return [
        VendorOut(
            id=v.id,
            slug=v.slug,
            name=v.name,
            aliases=v.aliases,
            domain=v.domain,
            logo_path=v.logo_path,
            items_7d=count,
        )
        for v, count in rows
    ]
