"""Three-line row summaries, generated once per item with Claude and cached in items.summary.

Runs at the end of each enrichment pass so CVE rows are summarized with their NVD facts
(affected versions, fix status). Never regenerated. Without ANTHROPIC_API_KEY it does nothing
and the row keeps showing "No summary yet."
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import anthropic
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Cve, Item, ItemSource, PatchStatus, Stream

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"
PER_RUN = 40
CONCURRENCY = 4
# A CVE row waits this long for NVD before being summarized from the articles alone.
NVD_GRACE = timedelta(hours=2)

SYSTEM = """You write the summary under a headline on darkwire, a board of security news and CVEs read by security engineers.

Write at most three short sentences, under 60 words in total, covering in order:
1. What it is: the flaw, incident or finding, in concrete terms.
2. Who is affected: products and versions, organizations, or users.
3. Whether there is a fix: patched versions, a workaround, or no fix yet.

Use only facts from the material provided. If the material does not say whether a fix exists, write "Fix status not stated." Do not speculate.
No adjectives of emphasis (critical, severe, major, alarming), no marketing language, no advice, no headline restatement, no source names.
Plain text only: no markdown, no bullet points, no preamble."""

PATCH_TEXT = {
    PatchStatus.patched: "a fix is available",
    PatchStatus.no_fix: "no fix is available",
    PatchStatus.workaround: "no fix; a workaround is available",
    PatchStatus.unverified: "fix status not verified",
}


def _material(item: Item, cve: Cve | None) -> str:
    lines = [f"Headline: {item.headline}"]
    for s in item.sources:
        if s.excerpt:
            lines.append(f"Article excerpt: {s.excerpt}")
    if cve is not None and cve.fetched_at is not None:
        if cve.description:
            lines.append(f"{cve.id} (NVD): {cve.description}")
        if cve.affected:
            lines.append(f"Affected versions: {cve.affected}")
        if cve.patch_status:
            lines.append(f"Fix status: {PATCH_TEXT[cve.patch_status]}")
    return "\n".join(lines)


def _ready(item: Item, cve: Cve | None, now: datetime) -> bool:
    # Rows without a CVE are ready at once; CVE rows once NVD answered or after a grace period.
    return cve is None or cve.fetched_at is not None or now - item.first_seen_at > NVD_GRACE


async def summarize_pending(session: AsyncSession) -> int | None:
    """Summarize up to PER_RUN items that have none. None when skipped (no key)."""
    key = get_settings().anthropic_api_key
    if not key:
        return None
    now = datetime.now(UTC)
    items = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, or_(Item.summary.is_(None), Item.summary == ""))
            .options(selectinload(Item.sources).selectinload(ItemSource.source), selectinload(Item.cve))
            .order_by(Item.last_event_at.desc())
            .limit(PER_RUN * 3)
        )
    ).all()
    todo = [i for i in items if _ready(i, i.cve, now)][:PER_RUN]
    if not todo:
        return 0

    sem = asyncio.Semaphore(CONCURRENCY)
    stop = asyncio.Event()

    async with anthropic.AsyncAnthropic(api_key=key, max_retries=3) as client:

        async def one(item: Item) -> str | None:
            if stop.is_set():
                return None
            async with sem:
                if stop.is_set():
                    return None
                try:
                    msg = await client.messages.create(
                        model=MODEL,
                        max_tokens=300,
                        system=SYSTEM,
                        messages=[{"role": "user", "content": _material(item, item.cve)}],
                    )
                except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError) as e:
                    log.warning("summaries: %s, stopping (%s)", type(e).__name__, e.message)
                    stop.set()
                    return None
                except anthropic.RateLimitError:
                    log.info("summaries: rate limited, the rest wait for the next pass")
                    stop.set()
                    return None
                except anthropic.APIStatusError as e:
                    log.warning("summaries: item %d failed: HTTP %d", item.id, e.status_code)
                    return None
                except anthropic.APIConnectionError as e:
                    log.warning("summaries: connection error, stopping: %s", e)
                    stop.set()
                    return None
            if msg.stop_reason not in ("end_turn", "max_tokens"):
                log.info("summaries: item %d stopped with %s, left empty", item.id, msg.stop_reason)
                return None
            text = " ".join(b.text for b in msg.content if b.type == "text").strip()
            return text or None

        results = await asyncio.gather(*(one(i) for i in todo))

    written = 0
    for item, text in zip(todo, results, strict=True):
        if text:
            item.summary = text
            written += 1
    await session.commit()
    return written
