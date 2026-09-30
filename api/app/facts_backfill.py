"""One-time backfill of items.facts (app/facts.py) through the Message Batches API.

Rows of the last DAYS days that have no facts yet are sent as one batch of the same request the
summary pass makes (summaries.request, the same articles; the summary it returns is ignored
here, rows keep theirs). Batches cost half and usually finish within the hour. Scheduled once
after start (schedule()), per VERSION:

- MODE "dry-run": submit, poll, verify each row's facts against its articles, log a line per row
  that gains any (the diff), and keep the verified results in job_state. Nothing is written to
  items.
- MODE "apply" (only with sign-off): write the results the dry run kept, for rows that still have
  no facts. No second batch.

A restart while a batch runs resumes polling the same batch. Needs ANTHROPIC_API_KEY.
"""

import asyncio
import inspect
import json
import logging
from datetime import UTC, datetime, timedelta

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import facts, jobstate, summaries
from app.config import get_settings
from app.models import Item, ItemSource, Stream

log = logging.getLogger(__name__)

DAYS = 14
VERSION = "1"
MODE = "dry-run"  # "dry-run" or "apply" (only with sign-off)
STATE = "facts_backfill"
REPORT_VERSION = "3"  # once the dry run is done: re-check its results (facts.recheck), log them, apply if signed off
POLL = 60


async def _todo(session) -> list[Item]:
    return list(
        (
            await session.scalars(
                select(Item)
                .where(
                    Item.stream == Stream.main,
                    Item.facts.is_(None),
                    Item.sources.any(),
                    Item.last_event_at >= datetime.now(UTC) - timedelta(days=DAYS),
                )
                .options(selectinload(Item.sources).selectinload(ItemSource.source))
                .order_by(Item.id)
            )
        ).all()
    )


def _line(item_id: int, headline: str, found: dict) -> str:
    parts = []
    if "exploited_in_wild" in found:
        parts.append("EXPLOITED (per article)")
    if "public_poc" in found:
        parts.append("POC")
    if "affected" in found:
        parts.append(f"Affected: {found['affected']['text']} (per article)")
    if "fixed" in found:
        parts.append(f"Fixed: {found['fixed']['version']} (per article)")
    return f"facts backfill (dry run): item {item_id}: {' | '.join(parts)} | {headline[:80]}"


async def _dry_run(session, client: anthropic.AsyncAnthropic, state: dict) -> dict:
    if not state.get("batch"):
        items = await _todo(session)
        if not items:
            return {"done": True, "results": {}}
        fetched = await summaries._fetch_articles(items)
        material = {i.id: summaries._articles(i, fetched.get(i.id)) for i in items}
        batch = await client.messages.batches.create(
            requests=[{"custom_id": str(i.id), "params": summaries.request(material[i.id])} for i in items]
        )
        # The material is kept so verification checks quotes against exactly what the model read.
        state = {"version": VERSION, "batch": batch.id, "material": {str(k): v for k, v in material.items()}, "headlines": {str(i.id): i.headline for i in items}}
        await jobstate.put(session, STATE, json.dumps(state))
        await session.commit()
        log.info("facts backfill (dry run): batch %s submitted for %d rows", batch.id, len(items))

    while True:
        batch = await client.messages.batches.retrieve(state["batch"])
        if batch.processing_status == "ended":
            break
        await asyncio.sleep(POLL)

    results: dict[str, dict] = {}
    counts = {"rows": 0, "with facts": 0, "errored": 0}
    stream = client.messages.batches.results(state["batch"])
    if inspect.isawaitable(stream):
        stream = await stream
    async for r in stream:
        counts["rows"] += 1
        if r.result.type != "succeeded":
            counts["errored"] += 1
            continue
        text = "".join(b.text for b in r.result.message.content if b.type == "text")
        _, stated = facts.parse(text)
        found = facts.verify(stated, state["material"].get(r.custom_id, ""))
        results[r.custom_id] = found
        if found:
            counts["with facts"] += 1
            log.info(_line(int(r.custom_id), state["headlines"].get(r.custom_id, ""), found))
    log.info("facts backfill (dry run): %s", ", ".join(f"{k} {v}" for k, v in counts.items()))
    return {"done": True, "batch": state["batch"], "results": results}


# Signed off 2026-09-30: apply the batch once the section 2 rules drop exactly these facts from
# the previous report, and nothing else changes. (row, fact, "removed" | "added" | "changed").
APPLY_IF_ONLY = {("91", "fixed", "removed"), ("76", "affected", "removed"), ("873", "fixed", "removed"), ("873", "affected", "removed")}


def changes(before: dict, after: dict) -> set[tuple[str, str, str]]:
    out = set()
    for row in set(before) | set(after):
        b, a = before.get(row) or {}, after.get(row) or {}
        for key in set(b) | set(a):
            if key not in a:
                out.add((row, key, "removed"))
            elif key not in b:
                out.add((row, key, "added"))
            elif a[key] != b[key]:
                out.add((row, key, "changed"))
    return out


async def report_and_maybe_apply(session, state: dict) -> bool:
    """Re-check and log the batch results (_report); apply them only when the changes since the
    last report are exactly APPLY_IF_ONLY. True if applied."""
    before = dict(state.get("results") or {})
    await _report(session, state)
    state["reported"] = REPORT_VERSION
    diff = changes(before, state["results"])
    for row, key, what in sorted(diff):
        log.info("facts report: vs the last report: item %s %s %s", row, key, what)
    if state.get("applied"):
        return False
    if diff != APPLY_IF_ONLY:
        log.info("facts report: STOPPED, not applied: the changes since the last report are not exactly %s", sorted(APPLY_IF_ONLY))
        return False
    await _apply(session, state)
    state["applied"] = True
    return True


async def _apply(session, state: dict) -> None:
    results = state.get("results") or {}
    written = 0
    for item in await _todo(session):
        if str(item.id) in results:
            item.facts = results[str(item.id)]
            written += 1
    await session.commit()
    log.info("facts backfill (apply): wrote facts on %d rows", written)


def _source(item: Item, quote: str) -> str:
    """The outlet whose stored text holds the quote; else the row's outlets (the quote came from
    an article fetched for the batch, which is not stored)."""
    q = facts._norm(quote)
    for s in item.sources:
        if q and q in facts._norm(f"{s.title}\n{s.excerpt or ''}\n{s.body or ''}"):
            return s.source.name
    return "fetched article, one of: " + ", ".join(sorted({s.source.name for s in item.sources}))


async def _report(session, state: dict) -> None:
    """Re-checks the dry run's kept results against the content rules (facts.recheck, with each
    row's displayed CVE as it is now) and logs them for review; nothing is written to items. The
    re-checked results replace state["results"] (what an apply would write); the batch's own stay
    in state["results_original"]. Logs: counts per fact type, what the rules removed, every row
    that would gain POC and every row whose affected or fixed survived, with quotes and sources."""
    original: dict[str, dict] = state.setdefault("results_original", state.get("results") or {})
    ids = [int(k) for k, v in original.items() if v]
    items = {
        i.id: i for i in (
            await session.scalars(
                select(Item).where(Item.id.in_(ids)).options(selectinload(Item.sources).selectinload(ItemSource.source))
            )
        ).all()
    }
    results: dict[str, dict] = {}
    removed_by: dict[str, int] = {}
    for key, found in original.items():
        item = items.get(int(key))
        kept, removed = facts.recheck(found, item.cve_id if item else None)
        results[key] = kept
        for fact, _ in removed:
            removed_by[fact] = removed_by.get(fact, 0) + 1
    state["results"] = results
    rows = {k: v for k, v in results.items() if v}
    counts = {key: sum(1 for v in rows.values() if key in v) for key in ("public_poc", "affected", "fixed", "exploited_in_wild")}
    log.info("facts report: %d rows gain facts: POC %d, affected %d, fixed %d, other (exploited in the wild, not shown) %d",
             len(rows), counts["public_poc"], counts["affected"], counts["fixed"], counts["exploited_in_wild"])
    log.info("facts report: removed by the content rules: %s",
             ", ".join(f"{k} {v}" for k, v in sorted(removed_by.items())) or "none")
    ids = [int(k) for k in rows]

    def describe(tag: str, item_id: int, found: dict) -> None:
        item = items.get(item_id)
        head = item.headline[:90] if item else state.get("headlines", {}).get(str(item_id), "")
        for key, fact in found.items():
            value = fact.get("text") or fact.get("version") or ""
            source = _source(item, fact["quote"]) if item else "row gone"
            log.info("facts report: %s item %d | %s%s | quote %r | source %s | %s",
                     tag, item_id, key, f" = {value!r}" if value else "", fact["quote"][:300], source, head)

    for i in sorted(ids):
        shown = {k: v for k, v in rows[str(i)].items() if k in ("public_poc", "affected", "fixed")}
        if "public_poc" in shown:
            describe("POC", i, {"public_poc": shown.pop("public_poc")})
        if shown:
            describe("affected/fixed", i, shown)


LIVE_SINCE = datetime(2026, 9, 30, 4, 21, tzinfo=UTC)  # the combined summary + facts call went live
LIVE_STATE = "facts_live_check"


async def _live_check(session) -> None:
    """Once: the first 3 rows summarized by the combined call. Each stored summary is run through
    the summary checks again (it must come back unchanged), and each stored fact is logged with
    its quote (verified against the article text when it was written; the fetched text is not
    stored, so here only whether the stored feed text also holds it)."""
    rows = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, Item.first_seen_at >= LIVE_SINCE, Item.facts.is_not(None), Item.summary.is_not(None))
            .options(selectinload(Item.sources).selectinload(ItemSource.source))
            .order_by(Item.first_seen_at, Item.id)
            .limit(3)
        )
    ).all()
    for item in rows:
        # patched=True skips only the fix-claim rule, which needs the fetched article (not
        # stored); it ran when the summary was written. Every other rule runs again here.
        again, why = summaries.review_summary(item.summary, patched=True) if item.summary else (None, "declined")
        verdict = (
            "passes, unchanged (fix-claim rule ran at write time)"
            if item.summary and again == item.summary
            else f"{why}: {again!r}"
        )
        log.info("facts live check: item %d (%s) | summary %s | %r | %s", item.id, item.first_seen_at.isoformat(timespec="minutes"),
                 verdict, (item.summary or "")[:240], item.headline[:80])
        if not item.facts:
            log.info("facts live check: item %d | no facts held up", item.id)
        for key, fact in (item.facts or {}).items():
            value = fact.get("text") or fact.get("version") or ""
            log.info("facts live check: item %d | %s%s | quote %r | in stored feed text: %s", item.id, key,
                     f" = {value!r}" if value else "", fact.get("quote", "")[:300], _source(item, fact.get("quote", "")))


REVALIDATE_STATE = "facts_live_revalidate"
REVALIDATE_VERSION = "1"  # facts.recheck rules of 2026-09-30


async def _revalidate_live(session) -> None:
    """Once per REVALIDATE_VERSION: facts the live path stored before the content rules
    (facts.recheck) are checked against them; any that fail are removed, each removal logged.
    The quotes were already verified against their articles when written."""
    rows = (
        await session.scalars(
            select(Item).where(Item.stream == Stream.main, Item.first_seen_at >= LIVE_SINCE, Item.facts.is_not(None)).order_by(Item.id)
        )
    ).all()
    removed_total = 0
    for item in rows:
        kept, removed = facts.recheck(item.facts, item.cve_id)
        for key, why in removed:
            fact = item.facts[key]
            value = fact.get("text") or fact.get("version") or ""
            log.info("facts revalidate: item %d | removed %s%s (%s) | quote %r | %s", item.id, key,
                     f" = {value!r}" if value else "", why, fact.get("quote", "")[:300], item.headline[:80])
        if removed:
            item.facts = kept
            removed_total += len(removed)
    await session.commit()
    log.info("facts revalidate: %d live rows checked, %d facts removed", len(rows), removed_total)


async def run_once() -> None:
    from app.db import SessionLocal

    key = get_settings().anthropic_api_key
    if not key:
        return
    try:
        async with SessionLocal() as session:
            if await jobstate.get(session, REVALIDATE_STATE) != REVALIDATE_VERSION:
                await _revalidate_live(session)
                await jobstate.put(session, REVALIDATE_STATE, REVALIDATE_VERSION)
                await session.commit()
            if not await jobstate.get(session, LIVE_STATE):
                await _live_check(session)
                await jobstate.put(session, LIVE_STATE, "1")
                await session.commit()
            state = json.loads(await jobstate.get(session, STATE) or "{}")
            if state.get("version") != VERSION:
                state = {"version": VERSION}
            if MODE == "apply":
                if state.get("applied") or not state.get("done"):
                    return
                await _apply(session, state)
                state["applied"] = True
            else:
                if state.get("done"):
                    if state.get("reported") != REPORT_VERSION:
                        await report_and_maybe_apply(session, state)
                        await jobstate.put(session, STATE, json.dumps(state))
                        await session.commit()
                    return
                async with anthropic.AsyncAnthropic(api_key=key, max_retries=3) as client:
                    state |= await _dry_run(session, client, state)
                state.pop("material", None)
            await jobstate.put(session, STATE, json.dumps(state))
            await session.commit()
    except Exception:
        log.exception("facts backfill failed")


def schedule(scheduler) -> None:
    scheduler.add_job(run_once, "date", run_date=datetime.now(UTC) + timedelta(minutes=5), id="facts_backfill")
