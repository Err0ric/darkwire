from enum import Enum

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Cve, Item, ItemCve, Vendor
from app.product_names import display_name
from app.schemas import CveRow, VendorRef
from app.throttle import cap, heavy_limit, read_limit

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


def _cna_name(name: str | None) -> str | None:
    name = (name or "").strip()
    if not name or name.lower() in ("n/a", "unknown", "*", "-"):
        return None
    return display_name(name.replace(" ", "_")) if name.islower() else name


def _vendor_product(cpes: list | None, cna: list | None) -> tuple[str | None, str | None]:
    """Vendor and product for a CVE not tagged to a vendor: the first CPE match
    (cpe:2.3:a:vendor:product:...), else the CNA's affected list. None when neither says."""
    for match in cpes or []:
        criteria = match.get("criteria", "") if isinstance(match, dict) else str(match)
        parts = criteria.split(":")
        if len(parts) > 4 and parts[4] not in ("*", "-"):
            return (display_name(parts[3]) if parts[3] not in ("*", "-") else None), display_name(parts[4])
    for a in cna or []:
        for d in (a.get("affectedData") or []) if isinstance(a, dict) else []:
            vendor, product = _cna_name(d.get("vendor")), _cna_name(d.get("product"))
            if vendor or product:
                return vendor, product
    return None, None


@router.get("/cves", response_model=list[CveRow])
@read_limit
@heavy_limit
async def cves(
    request: Request,
    sort: Sort = Sort.published,
    order: Order = Order.desc,
    vendor: str | None = Query(None, description="vendor slug"),
    kev: bool | None = None,
    q: str | None = Query(None, max_length=200),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[CveRow]:
    limit = cap(request, limit)
    # Several rows can share a CVE (coverage >48h apart). Use the most recent one.
    latest = (
        select(Item.id, ItemCve.cve_id, Item.vendor_id)
        .join(ItemCve, ItemCve.item_id == Item.id)
        .distinct(ItemCve.cve_id)
        .order_by(ItemCve.cve_id, Item.last_event_at.desc())
        .subquery()
    )
    stmt = (
        select(Cve, latest.c.id, Vendor, Cve.nvd_raw["affected"].label("cna"))
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
    out = []
    for cve, item_id, v, cna in rows:
        vendor_name, product = _vendor_product(cve.cpes, cna)
        out.append(
            CveRow(
                id=cve.id,
                description=cve.description,
                vendor=VendorRef.model_validate(v) if v else None,
                vendor_name=v.name if v else vendor_name,
                product=product,
                cvss=float(cve.base_score) if cve.base_score is not None else None,
                severity=cve.base_severity,
                epss=cve.epss,
                kev=cve.kev,
                patch_status=cve.patch_status,
                published_at=cve.published_at,
                item_id=item_id,
            )
        )
    return out
