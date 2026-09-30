"""CVE IDs from the article text fetched for summarization (app/fetcher.py), added to the row.

A feed's excerpt often names no CVE while the article does ("New CVSS 10.0 VeloCloud Flaw
Actively Exploited"): without its ID the row shows no score and never meets the coverage that
has one. When summarize_pending() fetches an article for a row with no CVE, the article's CVEs
are added to it:

- Candidates: well-formed IDs (CVE-YYYY-NNNN+) the article ties to its headline under ingest's
  attachment rules (tagging.headline_cves), at most PER_ARTICLE, read from the fetched text only
  (related-article blocks cut by fetcher.main_body), never from the model's output.
- Subject CVEs (tagging.subject_cves: in the title or lede, or named 2+ times) are kept whatever
  their age. Any other candidate is context: kept only when published within MAX_CVE_AGE, by
  NVD's date, else CVE.org's, else (neither has one) treated as recent (app/cve_facts.py).
- Only rows that have no CVE yet; the row displays the highest-scored subject CVE
  (cve_facts.pick_pinned). Never a row a CISA KEV alert started (it holds exactly the alert's
  CVEs), an ICS advisory (its CVEs come from CISA), or a recap / roundup (ROUNDUP).
- A multi-story article (its kept CVEs belong to 2+ vendors, by the KEV catalog, CPE or CNA
  data) gets its CVEs but does not merge, except into a KEV alert row whose CVEs it holds all of.

Then the row is checked against the shared-CVE clustering rule (app/dedupe.py) within
MERGE_WINDOW: the later row folds into the earlier one; never an alert into anything; never a
recap either way; into a row a KEV alert started only when that row holds one CVE or the article
holds all of its CVEs (dedupe.alert_row_takes); news into news only when a shared CVE is a
subject CVE of both rows. A merge never moves the surviving row's displayed CVE (enrich.roll_up
pins it). Each merge is logged.

    python -m app.article_cves             # dry run: rows of the last 9 days, CVEs gained, merges
    python -m app.article_cves --apply     # writes; never against production without sign-off

In production the one-time backfill runs from the scheduler (schedule()): BACKFILL_MODE
"dry-run" only logs the plan, "apply" writes it, once per BACKFILL_VERSION each. An apply makes
only the merges listed in APPLY_MERGES (the signed-off dry run); any other is logged and skipped.
"""

import asyncio
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import cve_facts, dedupe, fetcher, ics, jobstate
from app.models import Category, Cve, Item, ItemCve, ItemSource, KevEntry, Stream
from app.tagging import guess_category, headline_cves, subject_cves, subject_reasons

log = logging.getLogger(__name__)

PER_ARTICLE = 10
MERGE_WINDOW = timedelta(hours=72)
# A context CVE (not the article's subject) stays only when it was published this recently.
MAX_CVE_AGE = timedelta(days=90)
# Recaps and roundups name many stories' CVEs: they gain none and never merge.
ROUNDUP = re.compile(r"\b(weekly recap|recap|round-?up|metasploit|wrap[- ]?up|week in review|this week in)\b", re.I)
BACKFILL_DAYS = 9
BACKFILL_STATE = "article_cves_backfill"
BACKFILL_VERSION = "5"
BACKFILL_MODE = "apply"  # "dry-run" logs the plan once; "apply" writes it, only with sign-off
APPLY_MERGES: set[tuple[int, int]] = {(801, 747), (795, 794), (797, 796)}  # (merged, survivor) an apply may make
# Rows an apply may add CVEs to (the signed-off v5 dry run, 2026-09-30); any other is logged, skipped.
APPLY_ROWS: set[int] = {129, 135, 138, 788, 789, 790, 792, 793, 795, 797, 801, 834, 882}
# (merged, survivor) pairs this backfill never makes, whatever the rules say (signed off 2026-09-30:
# 834 keeps CVE-2026-35273 but stays out of 819). The backfill only; the live path ignores it.
SKIP_MERGES: set[tuple[int, int]] = {(834, 819)}


def article_cves(title: str, lead: str, fetched: str) -> list[str]:
    """The CVE IDs the fetched article ties to its headline, at most PER_ARTICLE."""
    return headline_cves(title or "", lead or "", fetched or "")[:PER_ARTICLE]


def keep(candidates: list[str], subject: set[str], published: dict[str, datetime | None], now: datetime) -> tuple[list[str], list[str]]:
    """(kept, dropped): subject CVEs always; context CVEs when published within MAX_CVE_AGE, or
    when no source has a date for them (treated as recent)."""
    kept, dropped = [], []
    for c in candidates:
        date = published.get(c)
        (kept if c in subject or date is None or now - date <= MAX_CVE_AGE else dropped).append(c)
    return kept, dropped


def vendor_key(name: str | None) -> str | None:
    key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    return key if key and key not in ("na", "unknown") else None


async def cve_vendors(session: AsyncSession, cves: list[str]) -> dict[str, str]:
    """Each CVE's vendor where the data names one: the KEV catalog, else the first CPE, else the
    CNA's affected list. A CVE nobody has described yet has none."""
    out: dict[str, str] = {}
    for cve_id, vendor in (await session.execute(select(KevEntry.cve_id, KevEntry.vendor).where(KevEntry.cve_id.in_(cves)))).all():
        if vendor_key(vendor):
            out[cve_id] = vendor_key(vendor)
    for cve in (await session.scalars(select(Cve).where(Cve.id.in_([c for c in cves if c not in out])))).all():
        for match in cve.cpes or []:
            parts = (match.get("criteria", "") if isinstance(match, dict) else str(match)).split(":")
            if len(parts) > 3 and parts[3] not in ("*", "-") and vendor_key(parts[3]):
                out[cve.id] = vendor_key(parts[3])
                break
        if cve.id in out:
            continue
        for a in (cve.nvd_raw or {}).get("affected") or []:
            for d in (a.get("affectedData") or []) if isinstance(a, dict) else []:
                if vendor_key(d.get("vendor")):
                    out[cve.id] = vendor_key(d.get("vendor"))
                    break
            if cve.id in out:
                break
    return out


def is_roundup(headline: str | None) -> bool:
    return bool(ROUNDUP.search(headline or ""))


def eligible(item: Item) -> bool:
    return (
        item.stream == Stream.main
        and not dedupe.alert_led(item)
        and not ics.is_ics_advisory(item.primary_url)
        and not is_roundup(item.headline)
    )


@dataclass
class Plan:
    new: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    subject: set[str] = field(default_factory=set)
    vendors: set[str] = field(default_factory=set)  # of one article's kept CVEs, when 2+
    multi_story: bool = False


async def plan_row(session: AsyncSession, http: httpx.AsyncClient, item: Item, fetched: dict[int, str], now: datetime) -> Plan:
    """What the row's fetched articles (source id -> text) add: kept CVEs in order, dropped
    context CVEs, the subject CVEs, and whether any one article spans 2+ vendors."""
    plan = Plan()
    for src in item.sources:
        body = fetched.get(src.id)
        if not body:
            continue
        candidates = article_cves(src.title, src.excerpt or "", body)
        if not candidates:
            continue
        subject = subject_cves(src.title, src.excerpt or "", body)
        plan.subject |= subject & set(candidates)
        context = [c for c in candidates if c not in subject]  # only these need a date
        kept, dropped = keep(candidates, subject, await cve_facts.published(session, http, context), now)
        reasons = subject_reasons(src.title, src.excerpt or "", body)
        for c in kept:
            if c in subject:
                log.info("article cves: item %d subject %s: %r", item.id, c, reasons.get(c, "")[:200])
        plan.new += [c for c in kept if c not in plan.new]
        plan.dropped += [c for c in dropped if c not in plan.dropped]
        vendors = set((await cve_vendors(session, kept)).values())
        if len(vendors) >= 2:
            plan.multi_story = True
            plan.vendors |= vendors
    return plan


async def add_cves(session: AsyncSession, item: Item, cves: list[str], subject: set[str], reason: str) -> None:
    """Link cves to the row after its own. Placeholder CVE rows first (NVD fills them in on the
    next enrich pass); a row with no CVE takes the highest-scored subject CVE as its pinned CVE
    and, if it was plain news, becomes a vulnerability row. Scores, KEV and patch status come
    from the roll-up."""
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
        item.cve_id = await cve_facts.pick_pinned(session, cves, subject, item.headline)
    if item.category == Category.news:
        item.category = guess_category(item.headline, "", True)
    log.info("article cves: item %d +%s, displays %s (%s)", item.id, ",".join(cves), item.cve_id, reason)


def _log_plan(tag: str, item: Item, plan: Plan) -> None:
    if plan.dropped:
        log.info("article cves: %sitem %d dropped %s (context: not in title/lede, named once, published over 90 days ago)",
                 tag, item.id, ",".join(plan.dropped))
    if plan.multi_story:
        log.info("article cves: %sitem %d multi-story (vendors %s): CVEs attach, merges only into an alert row it covers",
                 tag, item.id, ",".join(sorted(plan.vendors)))


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
    multi_story: bool = False  # its article spans 2+ vendors: merges only into an alert row it covers
    subject: set[str] = field(default_factory=set)  # its subject CVEs (tagging.subject_cves)


def takes(o: Row, n: Row) -> bool:
    """Whether n may fold into the earlier row o on their shared CVEs."""
    shared = o.cves & n.cves
    if not shared or o.roundup:
        return False
    if o.led:
        # A KEV alert row: one CVE, or all of them in the article. A multi-story article that
        # holds every CVE of the alert is the alert's story (795: WSO2 and Adobe Commerce).
        return o.cves <= n.cves if n.multi_story else dedupe.alert_row_takes(o.cves, n.cves)
    if n.multi_story or o.multi_story:
        return False
    # News into news: a shared CVE must be what both rows are about.
    return bool(shared & o.subject & n.subject)


def merge_target(n: Row, rows: list[Row]) -> Row | None:
    """The row n folds into, or None. As dedupe.merge_existing: the later-published row joins an
    earlier one within MERGE_WINDOW, the most recent such row; a row holding a KEV alert never
    joins another; recaps never merge; takes() decides the rest."""
    if n.alert or n.roundup:
        return None
    candidates = [
        o for o in rows
        if o.id != n.id
        and (o.first_pub, o.id) < (n.first_pub, n.id)
        and abs(n.first_pub - o.last_event_at) <= MERGE_WINDOW
        and takes(o, n)
    ]
    return max(candidates, key=lambda o: o.last_event_at) if candidates else None


def pair(n: Row, rows: list[Row], skip: set[tuple[int, int]] = frozenset()) -> tuple[Row, Row] | None:
    """(survivor, merged) for a row that just gained CVEs: it joins an earlier row, or a later
    row joins it. `skip`: (merged, survivor) pairs never made."""
    o = merge_target(n, [r for r in rows if (n.id, r.id) not in skip])
    if o:
        return o, n
    for later in sorted((r for r in rows if (r.first_pub, r.id) > (n.first_pub, n.id)), key=lambda r: (r.first_pub, r.id)):
        if (later.id, n.id) not in skip and merge_target(later, [n]) is n:
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
    sources = await session.execute(
        select(ItemSource.item_id, ItemSource.title, ItemSource.url, ItemSource.excerpt, ItemSource.body).where(ItemSource.item_id.in_(rows))
    )
    for item_id, title, url, excerpt, body in sources.all():
        if dedupe.is_kev_alert(title, url):
            rows[item_id].alert = True
        rows[item_id].subject |= subject_cves(title or "", excerpt or "", body or "")
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
    """dedupe._merge: sources and CVEs move to the survivor, which keeps its displayed CVE."""
    o, n = await _merge_dict(session, survivor.id), await _merge_dict(session, merged.id)
    await dedupe._merge(session, o, n, merged.first_pub)
    shared = sorted(survivor.cves & merged.cves)
    survivor.cves |= merged.cves
    survivor.subject |= merged.subject
    log.info("article cves: merged item %d into item %d (shared %s; %s)", merged.id, survivor.id, ",".join(shared), reason)


async def recheck(session: AsyncSession, gained: dict[int, Plan]) -> int:
    """After rows gained CVEs: apply the merge rules to each. Returns merges made."""
    rows = await _rows(session, datetime.now(UTC) - timedelta(days=14))
    for i, plan in gained.items():
        if i in rows:
            rows[i].multi_story = plan.multi_story
            rows[i].subject |= plan.subject
    done = 0
    for item_id in gained:
        n = rows.get(item_id)
        found = pair(n, list(rows.values())) if n else None
        if found:
            await merge(session, *found, reason="after gaining CVEs from its article")
            rows.pop(found[1].id, None)
            done += 1
    return done


async def after_fetch(session: AsyncSession, items: list[Item], fetched: dict[int, dict[int, str]]) -> None:
    """From summarize_pending(): add each fetched article's CVEs to its row, then re-check merges."""
    gained: dict[int, Plan] = {}
    now = datetime.now(UTC)
    async with httpx.AsyncClient(follow_redirects=True) as http:
        for item in items:
            if not eligible(item) or not fetched.get(item.id):
                continue
            if await session.scalar(select(ItemCve.cve_id).where(ItemCve.item_id == item.id).limit(1)):
                continue  # only rows with no CVE gain them
            plan = await plan_row(session, http, item, fetched[item.id], now)
            _log_plan("", item, plan)
            if plan.new:
                await add_cves(session, item, plan.new, plan.subject, "fetched article")
                gained[item.id] = plan
    if gained:
        await session.commit()
        if await recheck(session, gained):
            await session.commit()
        session.expire_all()


# ---------------------------------------------------------------- one-time backfill


async def backfill(session: AsyncSession, apply: bool) -> dict:
    """Rows of the last BACKFILL_DAYS days with no CVE: fetch their articles again (politely,
    fetcher.py), and plan or apply the CVEs they gain and the merges that follow. Logs every line."""
    tag = "apply" if apply else "dry run"
    prefix = f"backfill ({tag}): "
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
            log.info("article cves: %sitem %d skipped (recap/roundup) | %s", prefix, i.id, i.headline[:90])
    items = [i for i in candidates if eligible(i) and i.sources]
    log.info("article cves: %sfetching articles for %d rows with no CVE", prefix, len(items))
    fetched: dict[int, dict[int, str]] = {}
    async with fetcher.client() as client:

        async def one(item: Item) -> None:
            got = {}
            for src in sorted(item.sources, key=lambda x: x.url != item.primary_url)[:2]:
                body = await fetcher.article_text(client, src.url)
                if body:
                    got[src.id] = body
            fetched[item.id] = got

        await asyncio.gather(*(one(i) for i in items))
    fetcher.log_stats()

    rows = await _rows(session, datetime.now(UTC) - timedelta(days=14))
    gains: dict[int, list[str]] = {}
    now = datetime.now(UTC)
    async with httpx.AsyncClient(follow_redirects=True) as http:
        for item in items:
            if item.id not in rows:
                continue
            plan = await plan_row(session, http, item, fetched.get(item.id, {}), now)
            _log_plan(prefix, item, plan)
            if not plan.new:
                continue
            if apply and item.id not in APPLY_ROWS:
                log.info("article cves: %sitem %d +%s not in the signed-off rows, skipped", prefix, item.id, ",".join(plan.new))
                continue
            gains[item.id] = plan.new
            rows[item.id].cves |= set(plan.new)
            rows[item.id].subject |= plan.subject
            rows[item.id].multi_story = plan.multi_story
            if apply:
                await add_cves(session, item, plan.new, plan.subject, "backfill")
            else:
                pinned = await cve_facts.pick_pinned(session, plan.new, plan.subject, item.headline)
                log.info("article cves: %sitem %d +%s, displays %s | %s", prefix, item.id, ",".join(plan.new), pinned, item.headline[:90])
    if apply:
        await session.commit()

    # Merges, simulated in order so a planned merge is seen by the next (no chaining past it).
    merges = []
    for item_id in sorted(gains, key=lambda i: (rows[i].first_pub, i)):
        n = rows.get(item_id)
        found = pair(n, list(rows.values()), SKIP_MERGES) if n else None
        if not found:
            continue
        survivor, merged = found
        if apply and (merged.id, survivor.id) not in APPLY_MERGES:
            log.info("article cves: %sitem %d -> item %d not in the signed-off merges, skipped", prefix, merged.id, survivor.id)
            continue
        merges.append((merged.id, survivor.id))
        if apply:
            await merge(session, survivor, merged, "backfill")
        else:
            log.info(
                "article cves: %sitem %d would merge into item %d (shared %s)",
                prefix, merged.id, survivor.id, ",".join(sorted(survivor.cves & merged.cves)),
            )
            survivor.cves |= merged.cves
            survivor.subject |= merged.subject
        rows.pop(merged.id, None)
    if apply:
        await session.commit()
    fetched_rows = sum(1 for v in fetched.values() if v)
    log.info(
        "article cves: %s%d rows, %d with article text, %d gain CVEs, %d merges",
        prefix, len(items), fetched_rows, len(gains), len(merges),
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
            if BACKFILL_MODE == "apply":
                # The same plan again, nothing written: it must find 0 gains and 0 merges.
                log.info("article cves: verification dry run after the apply")
                await backfill(session, apply=False)
                for item_id, cve in EXPLAIN:
                    await explain(session, item_id, cve)
    except Exception:
        log.exception("article cves: backfill failed")


# Rows whose subject CVE sentences are logged after an apply, for review (834 and row 1 share
# CVE-2026-35273; 834 -> 1 is not signed off).
EXPLAIN = [(834, "CVE-2026-35273"), (1, "CVE-2026-35273")]


async def explain(session: AsyncSession, item_id: int, cve: str) -> None:
    """Log a row's headline and, per stored article, the sentence making `cve` a subject (or that
    it is not one in the stored feed text; a fetched article is not stored)."""
    item = await session.scalar(
        select(Item).where(Item.id == item_id).options(selectinload(Item.sources).selectinload(ItemSource.source))
    )
    if item is None:
        log.info("article cves: explain item %d: gone", item_id)
        return
    log.info("article cves: explain item %d %s | %s", item_id, cve, item.headline)
    for s in item.sources:
        reason = subject_reasons(s.title or "", s.excerpt or "", s.body or "").get(cve)
        log.info("article cves: explain item %d %s | %s: %s", item_id, cve, s.source.name,
                 repr(reason[:200]) if reason else "not a subject in the stored feed text")


def schedule(scheduler) -> None:
    scheduler.add_job(run_once, "date", run_date=datetime.now(UTC) + timedelta(minutes=3), id="article_cves_backfill")


async def main(apply: bool) -> None:
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    async with SessionLocal() as session:
        await backfill(session, apply)


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
