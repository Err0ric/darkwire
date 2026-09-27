"""One-time re-application of the current ingest rules to rows ingested under older ones:
ad filter, category rules, vendor tagging. Guarded by job_state so it runs once per version."""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import jobstate
from app.models import Category, Item, ItemCve, ItemSource, Stream
from app.tagging import VendorMatcher, guess_category, is_ad

log = logging.getLogger(__name__)

# v2: "extortion" no longer means ransomware.
STATE = "retag_v2"


def _primary(item: Item) -> ItemSource:
    """Vendor feed first, else the earliest article (the live rule)."""
    far = datetime.max.replace(tzinfo=UTC)
    return min(item.sources, key=lambda s: (s.source.vendor_id is None, s.published_at or far, s.id))


async def retag_once(session: AsyncSession, matcher: VendorMatcher) -> dict | None:
    if await jobstate.get(session, STATE):
        return None
    counts = {"items": 0, "ad_articles_removed": 0, "items_deleted": 0, "category_changed": 0, "vendor_changed": 0}
    items = (
        await session.scalars(select(Item).options(selectinload(Item.sources).selectinload(ItemSource.source)))
    ).all()
    for item in items:
        counts["items"] += 1
        ads = [s for s in item.sources if is_ad(s.title, s.url, s.excerpt or "")]
        if ads and len(ads) == len(item.sources):
            log.info("cleanup: deleting ad row %d %r", item.id, item.headline[:80])
            await session.delete(item)
            counts["items_deleted"] += 1
            continue
        for s in ads:
            item.sources.remove(s)
            counts["ad_articles_removed"] += 1
        if not item.sources:
            continue

        primary = _primary(item)
        if ads:
            item.headline, item.primary_url = primary.title, primary.url
        if item.stream != Stream.main:
            continue

        has_cve = await session.scalar(select(exists().where(ItemCve.item_id == item.id)))
        category = guess_category(primary.title, primary.excerpt or "", bool(has_cve))
        if category != item.category:
            counts["category_changed"] += 1
            item.category = category

        feed_vendor = next((s.source.vendor_id for s in item.sources if s.source.vendor_id), None)
        vendor_id = feed_vendor or matcher.match(primary.title, primary.excerpt or "")
        if vendor_id != item.vendor_id:
            counts["vendor_changed"] += 1
            item.vendor_id = vendor_id

    await jobstate.put(session, STATE, json.dumps({"at": datetime.now(UTC).isoformat(), **counts}))
    await session.commit()
    log.info("cleanup: %s", ", ".join(f"{k}={v}" for k, v in counts.items()))
    return counts
