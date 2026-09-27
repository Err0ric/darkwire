from datetime import UTC, datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
from app.throttle import cap, heavy_limit, read_limit, require_audit

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


def _one_per_outlet(sources: list[ItemSource]) -> list[SourceLink]:
    """One link per outlet, to its newest article in the cluster, in first-seen order."""
    far = datetime.min.replace(tzinfo=UTC)
    newest: dict[str, ItemSource] = {}
    for s in sources:
        cur = newest.get(s.source.name)
        if cur is None or (s.published_at or far) > (cur.published_at or far):
            newest[s.source.name] = s
    return [SourceLink(name=n, url=s.url, published_at=s.published_at) for n, s in newest.items()]


def _feed_fields(item: Item, all_sources: bool = False) -> dict:
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
        "kev_due_date": item.cve.kev_due_date if item.cve and item.cve.kev else None,
        "exploited": item.exploited,
        "patch_status": item.patch_status,
        "stale": is_stale(item, datetime.now(UTC)),
        "epss": item.epss,
        "sources": (
            [SourceLink(name=s.source.name, url=s.url, published_at=s.published_at) for s in item.sources]
            if all_sources
            else _one_per_outlet(item.sources)
        ),
        "last_event_at": item.last_event_at,
        "last_event_kind": item.last_event_kind,
    }


@router.get("/feed", response_model=FeedPage)
@read_limit
@heavy_limit
async def feed(
    request: Request,
    tab: Tab = Tab.all,
    vendor: str | None = Query(None, description="vendor slug"),
    vendors: str | None = Query(None, max_length=2000, description="comma-separated vendor slugs (a stack)"),
    q: str | None = Query(None, max_length=200, description="headline text or CVE ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    since: datetime | None = Query(None, description="only rows with an event after this time (or a change, see changed_since)"),
    changed_since: datetime | None = Query(None, description="with since: also rows changed after this time (default: since)"),
    pinned: bool = Query(False, description="only Critical, KEV or EXPLOITED rows with an event in the last 48h"),
    critical: bool = Query(False, description="only Critical or KEV rows (old CVEs excluded)"),
    all_sources: bool = Query(False, description="every article, not one per outlet (feed audit)"),
    severity: Severity | None = Query(None, description="only this severity (window below), old CVEs excluded"),
    window: str = Query("7d", pattern="^(24h|7d)$", description="window for severity: 24h (header counts) or 7d (rail)"),
    session: AsyncSession = Depends(get_session),
) -> FeedPage:
    limit = cap(request, limit)
    if all_sources:
        require_audit(request, "all_sources")
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
        where.append(or_(Item.last_event_at > since, Item.changed_at > (changed_since or since)))
    if severity is not None:
        # Matches the header's 24h counts or the rail's "Last 7 days" counts exactly.
        where.append(Item.severity == severity)
        span = timedelta(hours=24) if window == "24h" else timedelta(days=7)
        where.append(Item.last_event_at >= datetime.now(UTC) - span)
        where.append(not_stale(datetime.now(UTC)))
    if critical:
        where.append(or_(Item.severity == Severity.critical, Item.kev.is_(True)))
        where.append(not_stale(datetime.now(UTC)))
    if pinned:
        where.append(or_(Item.severity == Severity.critical, Item.kev.is_(True), Item.exploited.is_(True)))
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
    return FeedPage(items=[FeedItem(**_feed_fields(i, all_sources)) for i in rows], total=total or 0)


@router.get("/items/{item_id}", response_model=ItemDetail)
@read_limit
async def item_detail(request: Request, item_id: int, session: AsyncSession = Depends(get_session)) -> ItemDetail:
    item = await session.scalar(
        select(Item).where(Item.id == item_id).options(*_load)
    )
    if item is None:
        raise HTTPException(404, "item not found")
    msrc = await session.get(MsrcUpdate, item.cve_id) if item.cve_id else None
    return ItemDetail(
        **_feed_fields(item),
        summary=item.summary,
        action=item.action,
        patch_url=item.patch_url,
        first_seen_at=item.first_seen_at,
        cve=CveDetail.model_validate(item.cve) if item.cve else None,
        msrc=MsrcDetail.model_validate(msrc) if msrc else None,
    )


@router.get("/elsewhere", response_model=list[ElsewhereItem])
@read_limit
@heavy_limit
async def elsewhere(
    request: Request, limit: int = Query(5, ge=1, le=500), session: AsyncSession = Depends(get_session)
) -> list[ElsewhereItem]:
    limit = cap(request, limit)
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
