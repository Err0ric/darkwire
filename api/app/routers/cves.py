import re
from enum import Enum

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Cve, Item, ItemCve, KevEntry, Vendor
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


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _vendor_product(
    cpes: list | None, cna: list | None, known: dict[str, str]
) -> tuple[str | None, str | None]:
    """Vendor and product as a pair from one source: the first CPE match with a product
    (cpe:2.3:o:microsoft:windows_10_1607:... -> Microsoft, Windows 10 1607), else the CNA's
    affected list. The vendor always comes from the same entry as the product, never from the
    row's tag (a Google article about a Windows bug is still Microsoft's CVE). `known` maps
    normalized seeded vendor slugs/names to their display names."""
    def vendor_name(raw: str | None) -> str | None:
        if not raw or raw in ("*", "-"):
            return None
        return known.get(_norm(raw)) or display_name(raw)

    for match in cpes or []:
        criteria = match.get("criteria", "") if isinstance(match, dict) else str(match)
        parts = criteria.split(":")
        if len(parts) > 4 and parts[4] not in ("*", "-"):
            return vendor_name(parts[3]), display_name(parts[4])
    for a in cna or []:
        for d in (a.get("affectedData") or []) if isinstance(a, dict) else []:
            vendor, product = _cna_name(d.get("vendor")), _cna_name(d.get("product"))
            if vendor or product:
                return (known.get(_norm(vendor)) or vendor) if vendor else None, product
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
    known: dict[str, str] = {}
    for sv in (await session.scalars(select(Vendor))).all():
        for key in (sv.slug, sv.name, *(sv.aliases or [])):
            known.setdefault(_norm(key), sv.name)
    kev_names = {
        k.cve_id: (k.vendor, k.product)
        for k in (
            await session.execute(
                select(KevEntry.cve_id, KevEntry.vendor, KevEntry.product).where(
                    KevEntry.cve_id.in_([c.id for c, *_ in rows])
                )
            )
        ).all()
    }
    out = []
    for cve, item_id, v, cna in rows:
        vendor_name, product = _vendor_product(cve.cpes, cna, known)
        kv = kev_names.get(cve.id, (None, None))[0]
        if vendor_name and kv and _norm(kv) == _norm(vendor_name) and _norm(vendor_name) not in known:
            vendor_name = kv  # CISA's casing ("MikroTik") over a CPE slug's ("Mikrotik")
        if not vendor_name and not product and cve.id in kev_names:
            # CISA's catalog names vendor and product for every KEV entry.
            kv, kp = kev_names[cve.id]
            vendor_name, product = (known.get(_norm(kv)) or kv) if kv else None, kp
        if not vendor_name and not product and v:
            vendor_name = v.name  # only the row's tag is known
        out.append(
            CveRow(
                id=cve.id,
                description=cve.description,
                vendor=VendorRef.model_validate(v) if v else None,
                vendor_name=vendor_name,
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
