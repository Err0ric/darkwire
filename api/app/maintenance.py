"""One-off, signed-off data changes, run once each from the scheduler (schedule()) and logged.

Each step runs once (job_state key STATE + step name) and logs every change it makes or would
make. Steps that were signed off conditionally ("apply only if the dry run shows exactly X")
check that condition themselves and stop, logging the difference, when it does not hold.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import article_cves, cve_facts, jobstate
from app.models import Cve, Item, ItemCve, Stream
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


STEPS = [("merge_834_1", merges), ("repin_kev_first_v1", repin)]


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
