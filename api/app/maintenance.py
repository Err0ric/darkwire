"""One-off, signed-off data changes, run once each from the scheduler (schedule()) and logged.

Each step runs once (job_state key STATE + step name) and logs every change it makes or would
make. Steps that were signed off conditionally ("apply only if the dry run shows exactly X")
check that condition themselves and stop, logging the difference, when it does not hold.
"""

import json
import logging
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import article_cves, cve_facts, facts_backfill, fetcher, ics, jobstate, summaries, versions
from app.config import get_settings
from app.models import Cve, Item, ItemCve, ItemSource, Stream
from app.tagging import row_subject_cves

log = logging.getLogger(__name__)

STATE = "maintenance"

# Signed off 2026-09-30: 834 folds into row 1 (the same ShinyHunters PeopleSoft campaign, both
# about CVE-2026-35273). (merged, survivor).
MERGES = [(834, 1)]

# Re-pin under the KEV-first rule (cve_facts.rank): signed off to apply only if this is the whole
# change set; anything else is logged and nothing is written.
REPIN_EXPECTED = {793: "CVE-2026-67279"}


async def merges(session) -> None:
    rows = await article_cves._rows(session, datetime.now(UTC) - timedelta(days=30))
    for merged_id, survivor_id in MERGES:
        merged, survivor = rows.get(merged_id), rows.get(survivor_id)
        if merged is None or survivor is None:
            log.info("maintenance: merge %d -> %d skipped (row gone: %s)", merged_id, survivor_id,
                     ", ".join(str(i) for i in (merged_id, survivor_id) if i not in rows))
            continue
        await article_cves.merge(session, survivor, merged, "signed off")
        rows.pop(merged_id)
    await session.commit()


async def repin_plan(session) -> dict[int, tuple[str, str]]:
    """{row: (displayed now, displayed under the KEV-first rule)} for rows whose choice changes.
    The pool is the row's subject CVEs by its stored articles, else all of its CVEs."""
    items = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, Item.cve_id.is_not(None))
            .options(selectinload(Item.sources))
            .order_by(Item.id)
        )
    ).all()
    links = (await session.execute(select(ItemCve.item_id, ItemCve.cve_id).order_by(ItemCve.item_id, ItemCve.position))).all()
    by_item: dict[int, list[str]] = {}
    for item_id, cve_id in links:
        by_item.setdefault(item_id, []).append(cve_id)
    all_ids = {c for cs in by_item.values() for c in cs}
    scores = {c: float(s) if s is not None else None for c, s in (await session.execute(select(Cve.id, Cve.base_score).where(Cve.id.in_(all_ids)))).all()}
    kev = await cve_facts.kev_listed(session, list(all_ids))
    changes: dict[int, tuple[str, str]] = {}
    for item in items:
        cves = by_item.get(item.id, [])
        if len(cves) < 2:
            continue
        subject = row_subject_cves(item.sources)
        pool = [c for c in cves if c in subject] or cves
        best = cve_facts.rank(pool, kev, scores)
        if best != item.cve_id:
            changes[item.id] = (item.cve_id, best)
    return changes


async def repin(session) -> bool:
    """Dry run, then apply only when the change set is exactly REPIN_EXPECTED. True if applied."""
    changes = await repin_plan(session)
    for item_id, (now, new) in sorted(changes.items()):
        log.info("maintenance: repin (dry run): item %d %s -> %s", item_id, now, new)
    log.info("maintenance: repin (dry run): %d rows would change", len(changes))
    if {k: v[1] for k, v in changes.items()} != REPIN_EXPECTED:
        log.info("maintenance: repin STOPPED: the change set is not exactly %s; nothing written", REPIN_EXPECTED)
        return False
    for item_id, (_, new) in changes.items():
        item = await session.get(Item, item_id)
        item.cve_id = new  # the next roll-up copies its score, severity and fix status
    await session.commit()
    log.info("maintenance: repin applied: %s", ", ".join(f"item {k} -> {v}" for k, v in REPIN_EXPECTED.items()))
    return True


async def explain_873(session) -> None:
    """For review: row 873's article facts as the batch stored them, and the CISA advisory's own
    sentences about versions and release channels (fetched politely, as the summarizer does)."""
    item = await session.get(Item, 873)
    if item is None:
        log.info("maintenance: explain 873: row gone")
        return
    state = json.loads(await jobstate.get(session, facts_backfill.STATE) or "{}")
    found = (state.get("results_original") or state.get("results") or {}).get("873") or {}
    for key, fact in found.items():
        value = fact.get("text") or fact.get("version") or ""
        log.info("maintenance: explain 873 | stored %s%s | quote %r", key, f" = {value!r}" if value else "", fact.get("quote", ""))
    log.info("maintenance: explain 873 | summary %r", item.summary)
    async with fetcher.client() as client:
        text = await fetcher.article_text(client, item.primary_url)
    if not text:
        log.info("maintenance: explain 873 | the advisory could not be fetched (%s)", item.primary_url)
        return
    pattern = re.compile(r"\b7\.2\d|\bstable\b|long[- ]term|\bchannel|\btesting\b|\bbranch", re.I)
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        if pattern.search(sentence):
            log.info("maintenance: explain 873 | article: %r", sentence.strip()[:300])


async def summary_versions(session) -> None:
    """Existing summaries that state a fix version inside their own affected range: an ICS
    advisory row gets its deterministic summary (it never goes to the model); any other row is
    regenerated once without version numbers, else its versions are stripped. Each one logged."""
    rows = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, Item.summary.is_not(None), Item.summary != "",
                   Item.last_event_at >= datetime.now(UTC) - timedelta(days=14))
            .options(selectinload(Item.sources).selectinload(ItemSource.source))
        )
    ).all()
    hits = [i for i in rows if versions.summary_conflict(i.summary)]
    log.info("maintenance: summary versions: %d of %d summaries state a fix inside their affected range", len(hits), len(rows))
    for item in hits:
        before = item.summary
        if ics.is_ics_advisory(item.primary_url):
            n = len(set(await session.scalars(select(ItemCve.cve_id).where(ItemCve.item_id == item.id))))
            item.summary = ics.ics_summary(item.headline, n, float(item.cvss) if item.cvss is not None else None, item.severity, item.patch_status)
        elif get_settings().anthropic_api_key:
            fetched = await summaries._fetch_articles([item])
            material = summaries._articles(item, fetched.get(item.id))
            text, _ = await summaries.without_version_conflict(item.id, before, material, False)
            item.summary = text or ""
        else:
            log.info("maintenance: summary versions: item %d left as is (no model key)", item.id)
            continue
        log.info("maintenance: summary versions: item %d %r -> %r", item.id, before, item.summary)
    await session.commit()


async def resummarize_933(session) -> None:
    """Row 933's summary lost its version phrases mid-sentence ("Affected versions are; ...") under
    the first stripping rule; it is summarized again by the next pass (versions.strip now drops
    whole sentences)."""
    item = await session.get(Item, 933)
    if item is None:
        log.info("maintenance: resummarize 933: row gone")
        return
    log.info("maintenance: resummarize 933: %r -> queued", item.summary)
    item.summary = None
    await session.commit()


async def recategorize_breach(session) -> None:
    """Rows of the last 14 days tagged Breach, re-derived under the incident rule
    (tagging.guess_category); each change logged. Other categories are left alone."""
    from app.models import Category
    from app.tagging import guess_category

    rows = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, Item.category == Category.breach,
                   Item.last_event_at >= datetime.now(UTC) - timedelta(days=14))
            .options(selectinload(Item.sources))
        )
    ).all()
    changed = 0
    for item in rows:
        primary = next((s for s in item.sources if s.url == item.primary_url), item.sources[0] if item.sources else None)
        if primary is None:
            continue
        has_cve = await session.scalar(select(ItemCve.cve_id).where(ItemCve.item_id == item.id).limit(1)) is not None
        category = guess_category(primary.title, primary.excerpt or "", has_cve)
        if category != item.category:
            log.info("maintenance: recategorize item %d breach -> %s | %s", item.id, category.value, item.headline[:90])
            item.category = category
            changed += 1
    await session.commit()
    log.info("maintenance: recategorize: %d of %d breach rows changed", changed, len(rows))


STEPS = [
    ("merge_834_1", merges),
    ("repin_kev_first_v1", repin),
    ("explain_873_v1", explain_873),
    ("summary_versions_v1", summary_versions),
    ("resummarize_933_v1", resummarize_933),
    ("recategorize_breach_v1", recategorize_breach),
]


async def run_once() -> None:
    from app.db import SessionLocal

    for name, step in STEPS:
        key = f"{STATE}_{name}"
        try:
            async with SessionLocal() as session:
                if await jobstate.get(session, key):
                    continue
                await step(session)
                await jobstate.put(session, key, datetime.now(UTC).isoformat())
                await session.commit()
        except Exception:
            log.exception("maintenance: %s failed", name)


def schedule(scheduler) -> None:
    scheduler.add_job(run_once, "date", run_date=datetime.now(UTC) + timedelta(minutes=2), id="maintenance")
