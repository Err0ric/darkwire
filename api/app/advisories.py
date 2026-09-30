"""Stale-source safeguard: a CISA or vendor advisory on a row is read once more, 24-48h after it
was first read. Advisories get corrected (row 873, 2026-09-30: CISA's MikroTik advisory first said
"update to 7.23 or later", then "7.24 or later"), and the row's facts and summary were read from
the first version.

- An advisory source: from the CISA feed, from a vendor's own feed, or on the row's vendor's domain.
- First read: an advisory source added in the last FIRST_READ_WITHIN (or read by the summarizer)
  is fetched politely (fetcher.py). Only a digest of its fix and affected sentences is kept, never
  the text.
- Re-read: once, between RECHECK_AFTER and RECHECK_BEFORE after the first read. When the fix or
  affected sentences changed, the row's summary and facts are made again (refresh()) and the
  change is logged. Nothing else is fetched again.
"""

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import anthropic
from sqlalchemy import and_, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import facts, fetcher, ics, summaries, versions
from app.config import get_settings
from app.models import Item, ItemSource, PatchStatus, Source, Stream

log = logging.getLogger(__name__)

FIRST_READ_WITHIN = timedelta(hours=24)
RECHECK_AFTER = timedelta(hours=24)
RECHECK_BEFORE = timedelta(hours=48)
PER_RUN = 20

# A sentence about where a flaw is fixed or which versions it affects: fix or version words and
# a number.
_FIX_WORDS = re.compile(
    r"\b(fix(es|ed)?|patch(es|ed)?|updat(e|es|ed|ing)|upgrad(e|es|ed|ing)|affect(s|ed)?|vulnerable|prior to|before"
    r"|earlier|later|versions?|releases?|builds?|firmware)\b",
    re.I,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n")


def fix_sentences(text: str) -> list[str]:
    """The text's fix and affected sentences, whitespace collapsed, in order."""
    out = []
    for s in _SENTENCE.split(text or ""):
        s = " ".join(s.split())
        if s and re.search(r"\d", s) and _FIX_WORDS.search(s):
            out.append(s)
    return out


def digest(text: str) -> str:
    return hashlib.sha256("\n".join(fix_sentences(text)).encode()).hexdigest()


def is_advisory(src: ItemSource, item: Item) -> bool:
    outlet = None if "source" in sa_inspect(src).unloaded else src.source
    if outlet is not None and (outlet.name == "CISA" or outlet.vendor_id):
        return True
    vendor = None if "vendor" in sa_inspect(item).unloaded else item.vendor
    host = urlsplit(src.url or "").hostname or ""
    return bool(vendor and vendor.domain and (host == vendor.domain or host.endswith("." + vendor.domain)))


def note_reads(items: list[Item], fetched: dict[int, dict[int, str]], now: datetime | None = None) -> None:
    """The summarizer's fetch counts as the first read of an advisory it read."""
    now = now or datetime.now(UTC)
    for item in items:
        for src in item.sources:
            text = (fetched.get(item.id) or {}).get(src.id)
            if text and src.advisory_read_at is None and is_advisory(src, item):
                src.advisory_read_at, src.advisory_digest = now, digest(text)


async def refresh(session: AsyncSession, item: Item, fetched: dict[int, str], reason: str) -> None:
    """The row's summary and facts made again from its articles, with `fetched` (text read just
    now, by source id) in place of the stored text; nothing else is fetched. Facts are replaced,
    not merged. A CISA ICS advisory keeps its template summary (app/ics.py); the model's summary
    is only logged. A failed or rejected summary keeps the old one. Before and after logged."""
    if not get_settings().anthropic_api_key:
        log.info("advisories: item %d: %s; no model key, not refreshed", item.id, reason)
        return
    material = summaries._articles(item, fetched)
    async with anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key, max_retries=3) as client:
        msg = await client.messages.create(**summaries.request(material))
    if msg.stop_reason != "end_turn":
        log.info("advisories: item %d: %s; the call stopped (%s), not refreshed", item.id, reason, msg.stop_reason)
        return
    said, stated = facts.parse(" ".join(b.text for b in msg.content if b.type == "text"))
    found = facts.verify(stated, material, item.cve_id)
    before_facts, before_summary = item.facts, item.summary
    item.facts = found
    patched = item.patch_status == PatchStatus.patched
    vendor = summaries.fix_vendor(item, fetched)
    text, why = summaries.review_summary(said, patched=patched, material=material, vendor=vendor)
    if text and versions.summary_conflict(text):
        text, why = await summaries.without_version_conflict(item.id, text, material, patched, vendor)
    if ics.is_ics_advisory(item.primary_url):
        log.info("advisories: item %d: ICS advisory keeps its template summary; the model wrote (%s) %r", item.id, why, text)
    elif text:
        item.summary = text
    else:
        log.info("advisories: item %d: new summary rejected (%s), kept the old one", item.id, why)
    item.summary_sources, item.summarized_at = len(item.sources), datetime.now(UTC)
    await session.commit()
    log.info("advisories: item %d refreshed (%s) | facts %s -> %s | summary %r -> %r",
             item.id, reason, _facts_line(before_facts), _facts_line(item.facts), before_summary, item.summary)


def _facts_line(found: dict | None) -> str:
    parts = []
    for key, fact in (found or {}).items():
        value = fact.get("text") or fact.get("version")
        parts.append(f"{key}={value!r} (quote {fact.get('quote', '')!r})" if value else key)
    return "; ".join(parts) or "none"


async def run(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """First reads and re-reads due now. Counts by outcome."""
    now = now or datetime.now(UTC)
    counts = {"read": 0, "rechecked": 0, "changed": 0, "unreadable": 0}
    due = (
        await session.scalars(
            select(ItemSource)
            .join(Item, Item.id == ItemSource.item_id)
            .join(Source, Source.id == ItemSource.source_id)
            .where(
                Item.stream == Stream.main,
                or_(
                    and_(ItemSource.advisory_read_at.is_(None), ItemSource.fetched_at >= now - FIRST_READ_WITHIN),
                    and_(
                        ItemSource.advisory_rechecked_at.is_(None),
                        ItemSource.advisory_digest.is_not(None),  # a first read that failed is not retried
                        ItemSource.advisory_read_at <= now - RECHECK_AFTER,
                        ItemSource.advisory_read_at >= now - RECHECK_BEFORE,
                    ),
                ),
            )
            .options(
                selectinload(ItemSource.source),
                selectinload(ItemSource.item).selectinload(Item.sources).selectinload(ItemSource.source),
                selectinload(ItemSource.item).selectinload(Item.vendor),
            )
            .order_by(ItemSource.id)
        )
    ).all()
    due = [s for s in due if is_advisory(s, s.item)][:PER_RUN]
    if not due:
        return counts
    async with fetcher.client() as client:
        for src in due:
            text = await fetcher.article_text(client, src.url)
            if src.advisory_read_at is None:
                # A first read that fails is not retried: the row keeps what it was made from.
                src.advisory_read_at = now
                src.advisory_digest = digest(text) if text else None
                counts["read" if text else "unreadable"] += 1
                continue
            src.advisory_rechecked_at = now
            if not text:
                counts["unreadable"] += 1
                log.info("advisories: item %d: %s could not be read again", src.item_id, src.url)
                continue
            counts["rechecked"] += 1
            if digest(text) == src.advisory_digest:
                continue
            counts["changed"] += 1
            log.info("advisories: item %d: %s changed its fix/affected text since %s; now: %s", src.item_id, src.url,
                     src.advisory_read_at.isoformat(timespec="minutes"), " | ".join(fix_sentences(text))[:1500])
            src.advisory_digest = digest(text)
            await session.commit()
            try:
                await refresh(session, src.item, {src.id: text}, "advisory changed")
            except anthropic.APIError as e:
                log.info("advisories: item %d: refresh failed: %s", src.item_id, e)
    await session.commit()
    fetcher.log_stats()
    log.info("advisories: %s", ", ".join(f"{k} {v}" for k, v in counts.items()))
    return counts
