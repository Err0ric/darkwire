from enum import Enum

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Cve, Item, Vendor
from app.schemas import CveRow, VendorRef

router = APIRouter(tags=["cves"])


class Sort(str, Enum):
    published = "published"
    cvss = "cvss"
    epss = "epss"
    cve = "cve"


class Order(str, Enum):
    asc = "asc"
    desc = "desc"


SORT_COLUMN = {
    Sort.published: Cve.published_at,
    Sort.cvss: Cve.base_score,
    Sort.epss: Cve.epss,
    Sort.cve: Cve.id,
}


def _product(cpes: list | None) -> str | None:
    """cpe:2.3:a:vendor:product:version:... -> product, from the first CPE match."""
    for match in cpes or []:
        criteria = match.get("criteria", "") if isinstance(match, dict) else str(match)
        parts = criteria.split(":")
        if len(parts) > 4 and parts[4] not in ("*", "-"):
            return parts[4].replace("_", " ")
    return None


@router.get("/cves", response_model=list[CveRow])
async def cves(
    sort: Sort = Sort.published,
    order: Order = Order.desc,
    vendor: str | None = Query(None, description="vendor slug"),
    kev: bool | None = None,
    q: str | None = Query(None, max_length=200),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[CveRow]:
    # Several rows can share a CVE (coverage >48h apart). Use the most recent one.
    latest = (
        select(Item.id, Item.cve_id, Item.vendor_id)
        .where(Item.cve_id.is_not(None))
        .distinct(Item.cve_id)
        .order_by(Item.cve_id, Item.last_event_at.desc())
        .subquery()
    )
    stmt = (
        select(Cve, latest.c.id, Vendor)
        .outerjoin(latest, latest.c.cve_id == Cve.id)
        .outerjoin(Vendor, Vendor.id == latest.c.vendor_id)
    )
    if vendor:
        stmt = stmt.where(Vendor.slug == vendor)
    if kev is not None:
        stmt = stmt.where(Cve.kev.is_(kev))
    if q and q.strip():
        term = q.strip()
        stmt = stmt.where(
            Cve.id.icontains(term, autoescape=True) | Cve.description.icontains(term, autoescape=True)
        )
    direction = asc if order == Order.asc else desc
    stmt = stmt.order_by(direction(SORT_COLUMN[sort]).nulls_last(), Cve.id.desc())
    stmt = stmt.limit(limit).offset(offset)

    rows = (await session.execute(stmt)).all()
    return [
        CveRow(
            id=cve.id,
            vendor=VendorRef.model_validate(v) if v else None,
            product=_product(cve.cpes),
            cvss=float(cve.base_score) if cve.base_score is not None else None,
            severity=cve.base_severity,
            epss=cve.epss,
            kev=cve.kev,
            published_at=cve.published_at,
            item_id=item_id,
        )
        for cve, item_id, v in rows
    ]
