"""Whether a vendor's own feed owns a row: only then does its article become the row's primary
source and its vendor the row's vendor (ingest, dedupe._merge, split_clusters).

A vendor feed owns a row when the data on the row's displayed CVE names that vendor (the KEV
catalog, else the first CPE, else the CNA's affected list; article_cves.cve_vendors), or, with no
such data, when a news headline in the row names it, or the row has no news source yet (the feed
started it). Palo Alto's advisory on PHP's CVE-2026-109618 (prod row 1766, 2026-10-21) does not
own the PHP2Shell row: the CVE is PHP's.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vendor
from app.tagging import VendorMatcher

FAR = datetime.max.replace(tzinfo=UTC)


def news_titles(sources) -> list[str]:
    """Titles of a row's news articles: not a vendor feed's, not a CISA KEV alert. Each source
    has .title, .url and .source (its feed)."""
    from app import dedupe

    return [
        s.title for s in sources
        if s.source.vendor_id is None and not dedupe.is_kev_alert(s.title, s.url)
    ]


async def owns(
    session: AsyncSession, vendor_id: int | None, cve_id: str | None, titles: list[str],
    matcher: VendorMatcher | None = None,
) -> bool:
    """Whether the vendor feed of `vendor_id` owns a row displaying `cve_id` whose news headlines
    are `titles` (news_titles)."""
    from app.article_cves import cve_vendors, vendor_key

    if vendor_id is None:
        return False
    vendor = await session.get(Vendor, vendor_id)
    if vendor is None:
        return False
    named = (await cve_vendors(session, [cve_id])).get(cve_id) if cve_id else None
    if named:
        return named in {vendor_key(vendor.name), vendor_key(vendor.slug)}
    if not titles:
        return True
    if matcher is None:
        matcher = VendorMatcher((await session.scalars(select(Vendor))).all())
    return any(matcher.match(t, "") == vendor_id for t in titles)


async def owned_vendors(
    session: AsyncSession, sources, cve_id: str | None, matcher: VendorMatcher | None = None,
) -> set[int]:
    """The vendor feeds among `sources` that own the row (owns)."""
    titles = news_titles(sources)
    feeds = {s.source.vendor_id for s in sources if s.source.vendor_id is not None}
    return {v for v in feeds if await owns(session, v, cve_id, titles, matcher)}


def primary_key(published: datetime | None, source_vendor: int | None, owned: set[int], tiebreak=0):
    """Sort key for the primary source: an owning vendor feed first, then the earliest."""
    return (source_vendor not in owned, published or FAR, tiebreak)
