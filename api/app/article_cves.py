"""CVE IDs from the article text fetched for summarization (app/fetcher.py), added to the row.

A feed's excerpt often names no CVE while the article does ("New CVSS 10.0 VeloCloud Flaw
Actively Exploited"): without its ID the row shows no score and never meets the coverage that
has one. When summarize_pending() fetches an article, the IDs it ties to its headline are added
to the row:

- Well-formed IDs only (CVE-YYYY-NNNN+), read by the same attachment rules as ingest
  (tagging.headline_cves: IDs in the title, all when three or fewer, the lead's, the counted
  ones, the exploitation sentences', repeated ones, else the first), at most PER_ARTICLE each.
- From the fetched text only, with related-article blocks already cut (fetcher.main_body).
  Never from the model's output.
- Only rows that have no CVE yet, and only CVEs published within MAX_CVE_AGE (else numbered in a
  recent enough year): older IDs are context ("like last year's CVE-2025-43300").
- Not on a row a CISA KEV alert started (it holds exactly the alert's CVEs), an ICS advisory (its
  CVEs come from CISA), or a recap / roundup (ROUNDUP: it names many stories' CVEs).

Then the row is checked against the clustering rule for shared CVEs (app/dedupe.py), within
MERGE_WINDOW: the later row folds into the earlier one, never an alert into anything, never a
recap either way, and into a row a KEV alert started only when that row holds exactly one CVE.
Each merge is logged.

    python -m app.article_cves             # dry run: rows of the last 9 days, CVEs gained, merges
    python -m app.article_cves --apply     # writes; never against production without sign-off

In production the one-time backfill runs from the scheduler (schedule()): BACKFILL_MODE
"dry-run" only logs the plan, "apply" writes it, once per BACKFILL_VERSION each.
"""

import asyncio
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import dedupe, fetcher, ics, jobstate
from app.models import Category, Cve, Item, ItemCve, ItemSource, Stream
from app.tagging import guess_category, headline_cves

log = logging.getLogger(__name__)

PER_ARTICLE = 10
MERGE_WINDOW = timedelta(hours=72)
# A CVE published (or, before NVD has it, numbered in a year) more than this long ago is a
# context mention ("like CVE-2025-43300 last year"), not the story's.
MAX_CVE_AGE = timedelta(days=90)
# Recaps and roundups name many stories' CVEs: they gain none and never merge.
ROUNDUP = re.compile(r"\b(weekly recap|recap|round-?up|metasploit|wrap[- ]?up|week in review|this week in)\b", re.I)
BACKFILL_DAYS = 9
BACKFILL_STATE = "article_cves_backfill"
BACKFILL_VERSION = "2"
BACKFILL_MODE = "dry-run"  # "dry-run" logs the plan once; "apply" writes it, only with sign-off


def article_cves(title: str, lead: str, fetched: str) -> list[str]:
    """The CVE IDs the fetched article ties to its headline, at most PER_ARTICLE."""
    return headline_cves(title or "", lead or "", fetched or "")[:PER_ARTICLE]


def is_roundup(headline: str | None) -> bool:
    return bool(ROUNDUP.search(headline or ""))


def eligible(item: Item) -> bool:
    return (
        item.stream == Stream.main
        and not dedupe.alert_led(item)
        and not ics.is_ics_advisory(item.primary_url)
        and not is_roundup(item.headline)
    )


def too_old(cve_id: str, published: datetime | None, now: datetime) -> bool:
    """Published over MAX_CVE_AGE ago; with no NVD date yet, numbered in a year that ended
    before then."""
    if published is not None:
        return now - published > MAX_CVE_AGE
    return int(cve_id.split("-")[1]) < (now - MAX_CVE_AGE).year


async def recent_only(session: AsyncSession, cves: list[str], now: datetime) -> tuple[list[str], list[str]]:
    """(kept, dropped as context mentions) by too_old()."""
    if not cves:
        return [], []
    dates = dict((await session.execute(select(Cve.id, Cve.published_at).where(Cve.id.in_(cves)))).all())
    old = [c for c in cves if too_old(c, dates.get(c), now)]
    return [c for c in cves if c not in old], old


def gained(item: Item, fetched: dict[int, str], have: set[str]) -> list[str]:
    """New CVE IDs for the row from its fetched articles (source id -> text), in order."""
    out: list[str] = []
    for src in item.sources:
        body = fetched.get(src.id)
        if body:
            out += [c for c in article_cves(src.title, src.excerpt or "", body) if c not in have and c not in out]
    return out


async def add_cves(session: AsyncSession, item: Item, cves: list[str], reason: str) -> None:
    """Link cves to the row after its own. Placeholder CVE rows first (NVD fills them in on the
    next enrich pass); a row with no CVE takes the first as its CVE and, if it was plain news,
    becomes a vulnerability row. Scores, KEV and patch status come from the roll-up."""
    if not cves:
        return
    await session.execute(insert(Cve).values([{"id": c} for c in cves]).on_conflict_do_nothing())
    last = await session.scalar(select(func.coalesce(func.max(ItemCve.position), -1)).where(ItemCve.item_id == item.id))
    await session.execute(
        insert(ItemCve)
        .values([{"item_id": item.id, "cve_id": c, "position": last + 1 + i} for i, c in enumerate(cves)])
        .on_conflict_do_nothing()
    )
    if item.cve_id is None:
        item.cve_id = cves[0]
    if item.category == Category.news:
        item.category = guess_category(item.headline, "", True)
    log.info("article cves: item %d +%s (%s)", item.id, ",".join(cves), reason)


# ---------------------------------------------------------------- merges


@dataclass
class Row:
    id: int
    first_pub: datetime
    last_event_at: datetime
    alert: bool  # holds a CISA KEV alert: never joins another row, joined only by a shared CVE
    cves: set[str] = field(default_factory=set)
    led: bool = False  # started by a KEV alert (the alert is its primary source)
    roundup: bool = False  # a recap or roundup: never merges either way


def merge_target(n: Row, rows: list[Row]) -> Row | None:
    """The row n folds into under the shared-CVE rule, or None. As dedupe.merge_existing: the
    later-published row joins an earlier one it shares a CVE with, within MERGE_WINDOW, the most
    recent such row; a row holding a KEV alert never joins another. Stricter here: a row a KEV
    alert started takes news only when it holds exactly one CVE (a multi-CVE alert would gather
    unrelated stories), and recaps / roundups never merge."""
    if n.alert or n.roundup:
        return None
    candidates = [
        o for o in rows
        if o.id != n.id
        and not o.roundup
        and not (o.led and len(o.cves) != 1)
        and (o.first_pub, o.id) < (n.first_pub, n.id)
        and o.cves & n.cves
        and abs(n.first_pub - o.last_event_at) <= MERGE_WINDOW
    ]
    return max(candidates, key=lambda o: o.last_event_at) if candidates else None


def pair(n: Row, rows: list[Row]) -> tuple[Row, Row] | None:
    """(survivor, merged) for a row that just gained CVEs: it joins an earlier row, or a later
    row joins it."""
    o = merge_target(n, rows)
    if o:
        return o, n
    for later in sorted((r for r in rows if (r.first_pub, r.id) > (n.first_pub, n.id)), key=lambda r: (r.first_pub, r.id)):
        if merge_target(later, [n]) is n:
            return n, later
    return None


async def _rows(session: AsyncSession, since: datetime) -> dict[int, Row]:
    got = (
        await session.execute(text("""
            SELECT i.id, i.last_event_at, i.headline, i.primary_url,
                   coalesce((SELECT min(published_at) FROM item_sources s WHERE s.item_id = i.id), i.last_event_at) AS first_pub
            FROM items i WHERE i.stream = 'main' AND i.last_event_at >= :since
        """), {"since": since})
    ).all()
    rows = {
        r.id: Row(
            r.id, r.first_pub, r.last_event_at, False,
            led=dedupe.is_kev_alert(r.headline, r.primary_url), roundup=is_roundup(r.headline),
        )
        for r in got
    }
    for item_id, cve_id in (await session.execute(select(ItemCve.item_id, ItemCve.cve_id).where(ItemCve.item_id.in_(rows)))).all():
        rows[item_id].cves.add(cve_id)
    for item_id, title, url in (await session.execute(select(ItemSource.item_id, ItemSource.title, ItemSource.url).where(ItemSource.item_id.in_(rows)))).all():
        if dedupe.is_kev_alert(title, url):
            rows[item_id].alert = True
    return rows


async def _merge_dict(session: AsyncSession, item_id: int) -> dict:
    return dict(
        (
            await session.execute(text("""
                SELECT i.id, i.last_event_at, i.last_event_kind, i.first_seen_at, i.vendor_id, i.category::text AS category,
                       i.summary, i.kev, i.cvss, i.exploited
                FROM items i WHERE i.id = :id
            """), {"id": item_id})
        ).mappings().one()
    )


async def merge(session: AsyncSession, survivor: Row, merged: Row, reason: str) -> None:
    o, n = await _merge_dict(session, survivor.id), await _merge_dict(session, merged.id)
    await dedupe._merge(session, o, n, merged.first_pub)
    survivor.cves |= merged.cves
    log.info(
        "article cves: merged item %d into item %d (shared %s; %s)",
        merged.id, survivor.id, ",".join(sorted(survivor.cves & merged.cves)), reason,
    )


async def recheck(session: AsyncSession, item_ids: list[int]) -> int:
    """After rows gained CVEs: apply the shared-CVE merge rule to each. Returns merges made."""
    rows = await _rows(session, datetime.now(UTC) - timedelta(days=14))
    done = 0
    for item_id in item_ids:
        n = rows.get(item_id)
        found = pair(n, list(rows.values())) if n else None
        if found:
            await merge(session, *found, reason="after gaining CVEs from its article")
            rows.pop(found[1].id, None)
            done += 1
    return done


async def after_fetch(session: AsyncSession, items: list[Item], fetched: dict[int, dict[int, str]]) -> None:
    """From summarize_pending(): add each fetched article's CVEs to its row, then re-check merges."""
    changed = []
    for item in items:
        if not eligible(item) or not fetched.get(item.id):
            continue
        if await session.scalar(select(ItemCve.cve_id).where(ItemCve.item_id == item.id).limit(1)):
            continue  # only rows with no CVE gain them
        new, old = await recent_only(session, gained(item, fetched[item.id], set()), datetime.now(UTC))
        if old:
            log.info("article cves: item %d: dropped %s (published over 90 days ago)", item.id, ",".join(old))
        if new:
            await add_cves(session, item, new, "fetched article")
            changed.append(item.id)
    if changed:
        await session.commit()
        if await recheck(session, changed):
            await session.commit()
        session.expire_all()


# ---------------------------------------------------------------- one-time backfill


async def backfill(session: AsyncSession, apply: bool) -> dict:
    """Rows of the last BACKFILL_DAYS days: fetch their articles again (politely, fetcher.py),
    and plan or apply the CVEs they gain and the merges that follow. Logs every line."""
    tag = "apply" if apply else "dry run"
    candidates = (
        await session.scalars(
            select(Item)
            .where(
                Item.stream == Stream.main,
                Item.last_event_at >= datetime.now(UTC) - timedelta(days=BACKFILL_DAYS),
                ~Item.id.in_(select(ItemCve.item_id)),  # only rows with no CVE
            )
            .options(selectinload(Item.sources))
            .order_by(Item.id)
        )
    ).all()
    for i in candidates:
        if is_roundup(i.headline):
            log.info("article cves: backfill (%s): item %d skipped (recap/roundup) | %s", tag, i.id, i.headline[:90])
    items = [i for i in candidates if eligible(i) and i.sources]
    log.info("article cves: backfill (%s): fetching articles for %d rows with no CVE", tag, len(items))
    fetched: dict[int, dict[int, str]] = {}
    async with fetcher.client() as client:

        async def one(item: Item) -> None:
            got = {}
            for src in sorted(item.sources, key=lambda x: x.url != item.primary_url)[: 2]:
                body = await fetcher.article_text(client, src.url)
                if body:
                    got[src.id] = body
            fetched[item.id] = got

        await asyncio.gather(*(one(i) for i in items))
    fetcher.log_stats()

    rows = await _rows(session, datetime.now(UTC) - timedelta(days=14))
    gains: dict[int, list[str]] = {}
    now = datetime.now(UTC)
    for item in items:
        if item.id not in rows or rows[item.id].cves:
            continue  # only rows with no CVE gain them
        new, old = await recent_only(session, gained(item, fetched.get(item.id, {}), set()), now)
        if old:
            log.info("article cves: backfill (%s): item %d dropped %s (published over 90 days ago)", tag, item.id, ",".join(old))
        if new:
            gains[item.id] = new
            log.info("article cves: backfill (%s): item %d +%s | %s", tag, item.id, ",".join(new), item.headline[:90])
            if item.id in rows:
                rows[item.id].cves |= set(new)
            if apply:
                await add_cves(session, item, new, "backfill")
    if apply:
        await session.commit()

    # Merges, simulated in order so a planned merge is seen by the next (no chaining past it).
    merges = []
    for item_id in sorted(gains, key=lambda i: (rows[i].first_pub, i) if i in rows else (datetime.max.replace(tzinfo=UTC), i)):
        n = rows.get(item_id)
        found = pair(n, list(rows.values())) if n else None
        if not found:
            continue
        survivor, merged = found
        merges.append((merged.id, survivor.id))
        if apply:
            await merge(session, survivor, merged, "backfill")
        else:
            log.info(
                "article cves: backfill (dry run): item %d would merge into item %d (shared %s)",
                merged.id, survivor.id, ",".join(sorted(survivor.cves & merged.cves)),
            )
            survivor.cves |= merged.cves
        rows.pop(merged.id, None)
    if apply:
        await session.commit()
    fetched_rows = sum(1 for v in fetched.values() if v)
    log.info(
        "article cves: backfill (%s): %d rows, %d with article text, %d gain CVEs, %d merges",
        tag, len(items), fetched_rows, len(gains), len(merges),
    )
    return {"rows": len(items), "fetched": fetched_rows, "gains": gains, "merges": merges}


async def run_once() -> None:
    """Scheduled once after start: the backfill in BACKFILL_MODE, once per BACKFILL_VERSION."""
    from app.db import SessionLocal

    key = f"{BACKFILL_STATE}_{BACKFILL_MODE}"
    try:
        async with SessionLocal() as session:
            if await jobstate.get(session, key) == BACKFILL_VERSION:
                return
            await backfill(session, apply=BACKFILL_MODE == "apply")
            await jobstate.put(session, key, BACKFILL_VERSION)
            await session.commit()
    except Exception:
        log.exception("article cves: backfill failed")


def schedule(scheduler) -> None:
    scheduler.add_job(run_once, "date", run_date=datetime.now(UTC) + timedelta(minutes=3), id="article_cves_backfill")


async def main(apply: bool) -> None:
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    async with SessionLocal() as session:
        await backfill(session, apply)


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
