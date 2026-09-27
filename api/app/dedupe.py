"""Clustering rules shared by live ingest and the one-time merge of existing rows.

CLAUDE.md: cluster by CVE ID first; else normalized-title similarity > 0.85 within 48h,
same vendor. Also: same vendor + a shared product alias + "zero-day" in both titles, which
catches two outlets' very different headlines about the same zero-day.
"""

import logging
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Item, ItemSource, Stream
from app.tagging import ZERO_DAY, VendorMatcher

log = logging.getLogger(__name__)

WINDOW = timedelta(hours=48)
SIMILARITY = 0.85
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize(title: str) -> str:
    return _NON_WORD.sub(" ", title.lower()).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def titles_match(a: str, b: str, vendor_id: int | None, matcher: VendorMatcher) -> bool:
    if similarity(a, b) > SIMILARITY:
        return True
    return bool(
        ZERO_DAY.search(a) and ZERO_DAY.search(b) and matcher.products(vendor_id, a) & matcher.products(vendor_id, b)
    )


async def find_title_cluster(
    session: AsyncSession, title: str, vendor_id: int | None, published: datetime, matcher: VendorMatcher
) -> Item | None:
    """Same vendor, within 48h, and a headline of the cluster matches this title."""
    if vendor_id is None:
        return None
    candidates = (
        await session.scalars(
            select(Item)
            .where(
                Item.stream == Stream.main,
                Item.vendor_id == vendor_id,
                Item.last_event_at.between(published - WINDOW, published + WINDOW),
            )
            .options(selectinload(Item.sources).selectinload(ItemSource.source))
            .order_by(Item.last_event_at.desc())
        )
    ).all()
    for item in candidates:
        if any(titles_match(title, t, vendor_id, matcher) for t in {item.headline, *(s.title for s in item.sources)}):
            return item
    return None


async def refresh_exploited(session: AsyncSession) -> None:
    """items.exploited: a headline in the cluster says zero-day / actively exploited / in the
    wild, and the row has no CVE. Recomputed for every main row, so it clears once a CVE lands."""
    await session.execute(text(r"""
        UPDATE items i SET exploited = flagged
        FROM (
            SELECT i2.id,
                   NOT EXISTS (SELECT 1 FROM item_cves c WHERE c.item_id = i2.id)
                   AND EXISTS (
                       SELECT 1 FROM item_sources s WHERE s.item_id = i2.id
                       AND s.title ~* '\y(zero[- ]days?|0-days?|actively exploited|in the wild)\y'
                   ) AS flagged
            FROM items i2 WHERE i2.stream = 'main'
        ) f
        WHERE f.id = i.id AND i.exploited IS DISTINCT FROM f.flagged
    """))


# ---------------------------------------------------------------- one-time merge


async def merge_existing(session: AsyncSession, matcher: VendorMatcher) -> int:
    """Replay both clustering rules over existing rows, oldest first. A row folds into an
    earlier row that it would have joined at ingest. Returns rows merged."""
    rows = (
        await session.execute(text("""
            SELECT i.id, i.last_event_at, i.last_event_kind, i.first_seen_at, i.vendor_id, i.category::text AS category,
                   i.summary, i.kev, i.cvss, i.exploited,
                   (SELECT min(published_at) FROM item_sources s WHERE s.item_id = i.id) AS first_pub
            FROM items i WHERE i.stream = 'main'
        """))
    ).mappings().all()
    cves: dict[int, set[str]] = {}
    for item_id, cve_id in (await session.execute(text("SELECT item_id, cve_id FROM item_cves"))).all():
        cves.setdefault(item_id, set()).add(cve_id)
    titles: dict[int, set[str]] = {}
    for item_id, title in (await session.execute(text("SELECT item_id, title FROM item_sources"))).all():
        titles.setdefault(item_id, set()).add(title)

    order = sorted((dict(r) for r in rows), key=lambda r: (r["first_pub"] or r["last_event_at"], r["id"]))
    survivors: list[dict] = []
    merged = 0
    for n in order:
        pub = n["first_pub"] or n["last_event_at"]

        def joins(o: dict) -> bool:
            if abs(pub - o["last_event_at"]) > WINDOW:
                return False
            if cves.get(o["id"], set()) & cves.get(n["id"], set()):
                return True
            return (
                o["vendor_id"] is not None
                and o["vendor_id"] == n["vendor_id"]
                and any(titles_match(a, b, o["vendor_id"], matcher) for a in titles.get(n["id"], ()) for b in titles.get(o["id"], ()))
            )

        candidates = [o for o in survivors if joins(o)]
        if not candidates:
            survivors.append(n)
            continue
        o = max(candidates, key=lambda r: r["last_event_at"])
        await _merge(session, o, n, pub)
        cves.setdefault(o["id"], set()).update(cves.pop(n["id"], set()))
        titles.setdefault(o["id"], set()).update(titles.pop(n["id"], set()))
        merged += 1
    await session.commit()
    return merged


async def _merge(session: AsyncSession, o: dict, n: dict, n_pub: datetime) -> None:
    oid, nid = o["id"], n["id"]
    await session.execute(text("UPDATE item_sources SET item_id = :o WHERE item_id = :n"), {"o": oid, "n": nid})
    await session.execute(
        text("""
            INSERT INTO item_cves (item_id, cve_id, position)
            SELECT :o, cve_id, (SELECT coalesce(max(position), -1) + 1 FROM item_cves WHERE item_id = :o) + position
            FROM item_cves WHERE item_id = :n
            ON CONFLICT DO NOTHING
        """),
        {"o": oid, "n": nid},
    )
    # A publish-only row moves to its earliest article, as ingest does; a real event on
    # either row (KEV added, score change) is kept.
    event, kind = o["last_event_at"], o["last_event_kind"]
    if kind == "published" and n_pub < event:
        event = n_pub
    if n["last_event_kind"] not in (None, "published") and n["last_event_at"] > event:
        event, kind = n["last_event_at"], n["last_event_kind"]

    primary = (
        await session.execute(
            text("""
                SELECT s.url, s.title, src.vendor_id FROM item_sources s JOIN sources src ON src.id = s.source_id
                WHERE s.item_id = :o
                ORDER BY (src.vendor_id IS NULL), s.published_at NULLS LAST, s.id LIMIT 1
            """),
            {"o": oid},
        )
    ).mappings().one()
    scores = [x for x in (o["cvss"], n["cvss"]) if x is not None]
    values = {
        "vendor_id": primary["vendor_id"] or o["vendor_id"] or n["vendor_id"],
        "category": n["category"] if o["category"] == "news" else o["category"],
        "summary": o["summary"] or n["summary"],
        # Kept at the pair's max so the next roll-up does not see a change and resurface it.
        "kev": bool(o["kev"] or n["kev"]),
        "cvss": max(scores) if scores else None,
        "exploited": bool(o["exploited"] or n["exploited"]),
        "last_event_at": event,
        "last_event_kind": kind,
        "first_seen_at": min(o["first_seen_at"], n["first_seen_at"]),
    }
    await session.execute(
        text("""
            UPDATE items SET headline = :headline, primary_url = :url, vendor_id = :vendor_id,
                   category = CAST(:category AS category), summary = :summary, kev = :kev, cvss = :cvss,
                   exploited = :exploited, last_event_at = :last_event_at, last_event_kind = :last_event_kind,
                   first_seen_at = :first_seen_at
            WHERE id = :o
        """),
        {"o": oid, "headline": primary["title"], "url": primary["url"], **values},
    )
    await session.execute(text("DELETE FROM items WHERE id = :n"), {"n": nid})
    o.update(values)
