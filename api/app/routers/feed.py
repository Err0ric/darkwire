from datetime import UTC, datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.staleness import is_stale, not_stale
from app.models import Category, Item, ItemCve, ItemSource, MsrcUpdate, Severity, Stream, Vendor
from app.schemas import (
    CveDetail,
    ElsewhereItem,
    FeedItem,
    FeedPage,
    ItemDetail,
    MsrcDetail,
    SourceLink,
    VendorRef,
)

router = APIRouter(tags=["feed"])


class Tab(str, Enum):
    all = "all"
    vulnerabilities = "vulnerabilities"
    breaches = "breaches"
    ransomware = "ransomware"
    advisories = "advisories"
    research = "research"
    kev = "kev"


TAB_CATEGORY = {
    Tab.vulnerabilities: Category.vulnerability,
    Tab.breaches: Category.breach,
    Tab.ransomware: Category.ransomware,
    Tab.advisories: Category.advisory,
    Tab.research: Category.research,
}

_load = (
    selectinload(Item.vendor),
    selectinload(Item.cve),
    selectinload(Item.sources).selectinload(ItemSource.source),
)


def _num(v) -> float | None:
    return float(v) if v is not None else None


def _feed_fields(item: Item) -> dict:
    return {
        "id": item.id,
        "headline": item.headline,
        "primary_url": item.primary_url,
        "vendor": VendorRef.model_validate(item.vendor) if item.vendor else None,
        "category": item.category,
        "cve_id": item.cve_id,
        "cvss": _num(item.cvss),
        "severity": item.severity,
        "kev": item.kev,
        "exploited": item.exploited,
        "stale": is_stale(item.cve, datetime.now(UTC)),
        "epss": item.epss,
        "sources": [
            SourceLink(name=s.source.name, url=s.url, published_at=s.published_at)
            for s in item.sources
        ],
        "last_event_at": item.last_event_at,
        "last_event_kind": item.last_event_kind,
    }


@router.get("/feed", response_model=FeedPage)
async def feed(
    tab: Tab = Tab.all,
    vendor: str | None = Query(None, description="vendor slug"),
    vendors: str | None = Query(None, max_length=2000, description="comma-separated vendor slugs (a stack)"),
    q: str | None = Query(None, max_length=200, description="headline text or CVE ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    since: datetime | None = Query(None, description="only rows with an event after this time"),
    pinned: bool = Query(False, description="only Critical or KEV rows with an event in the last 48h"),
    critical: bool = Query(False, description="only Critical or KEV rows (old CVEs excluded)"),
    session: AsyncSession = Depends(get_session),
) -> FeedPage:
    where = [Item.stream == Stream.main]
    if tab == Tab.kev:
        where.append(Item.kev.is_(True))
    elif tab in TAB_CATEGORY:
        where.append(Item.category == TAB_CATEGORY[tab])
    if vendor:
        where.append(Item.vendor.has(Vendor.slug == vendor))
    if vendors is not None:
        slugs = [v.strip() for v in vendors.split(",") if v.strip()][:50]
        where.append(Item.vendor.has(Vendor.slug.in_(slugs)))
    if q and q.strip():
        term = q.strip()
        where.append(
            or_(
                Item.headline.icontains(term, autoescape=True),
                # Any CVE the row's articles mention, not only the one it displays.
                Item.id.in_(select(ItemCve.item_id).where(ItemCve.cve_id.icontains(term, autoescape=True))),
            )
        )
    if since:
        where.append(Item.last_event_at > since)
    if critical:
        where.append(or_(Item.severity == Severity.critical, Item.kev.is_(True)))
        where.append(not_stale(datetime.now(UTC)))
    if pinned:
        where.append(or_(Item.severity == Severity.critical, Item.kev.is_(True)))
        where.append(not_stale(datetime.now(UTC)))
        where.append(Item.last_event_at >= datetime.now(UTC) - timedelta(hours=48))

    total = await session.scalar(select(func.count()).select_from(Item).where(*where))
    rows = await session.scalars(
        select(Item)
        .where(*where)
        .options(*_load)
        .order_by(Item.last_event_at.desc(), Item.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return FeedPage(items=[FeedItem(**_feed_fields(i)) for i in rows], total=total or 0)


@router.get("/items/{item_id}", response_model=ItemDetail)
async def item_detail(item_id: int, session: AsyncSession = Depends(get_session)) -> ItemDetail:
    item = await session.scalar(
        select(Item).where(Item.id == item_id).options(*_load)
    )
    if item is None:
        raise HTTPException(404, "item not found")
    msrc = await session.get(MsrcUpdate, item.cve_id) if item.cve_id else None
    return ItemDetail(
        **_feed_fields(item),
        summary=item.summary,
        patch_status=item.patch_status,
        patch_url=item.patch_url,
        first_seen_at=item.first_seen_at,
        cve=CveDetail.model_validate(item.cve) if item.cve else None,
        msrc=MsrcDetail.model_validate(msrc) if msrc else None,
    )


@router.get("/elsewhere", response_model=list[ElsewhereItem])
async def elsewhere(
    limit: int = Query(5, ge=1, le=50), session: AsyncSession = Depends(get_session)
) -> list[ElsewhereItem]:
    rows = await session.scalars(
        select(Item)
        .where(Item.stream == Stream.elsewhere)
        .options(selectinload(Item.sources).selectinload(ItemSource.source))
        .order_by(Item.last_event_at.desc())
        .limit(limit)
    )
    out = []
    for item in rows:
        first = item.sources[0] if item.sources else None
        out.append(
            ElsewhereItem(
                id=item.id,
                headline=item.headline,
                url=item.primary_url,
                source=first.source.name if first else "",
                published_at=(first.published_at if first else None) or item.last_event_at,
            )
        )
    return out
