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
import random
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
REPORT_VERSION = "1"  # once the dry run is done: log its results for review, once per version
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
                .options(selectinload(Item.sources))
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
    """Logs the dry run's kept results for review (nothing is written to items): counts per fact
    type, every row that would gain POC with its quote and source, and 10 other rows at random
    (seeded) with their facts and quotes."""
    results: dict[str, dict] = state.get("results") or {}
    rows = {k: v for k, v in results.items() if v}
    counts = {key: sum(1 for v in rows.values() if key in v) for key in ("public_poc", "affected", "fixed", "exploited_in_wild")}
    log.info("facts report: %d rows gain facts: POC %d, affected %d, fixed %d, other (exploited in the wild) %d",
             len(rows), counts["public_poc"], counts["affected"], counts["fixed"], counts["exploited_in_wild"])
    ids = [int(k) for k in rows]
    items = {
        i.id: i for i in (
            await session.scalars(
                select(Item).where(Item.id.in_(ids)).options(selectinload(Item.sources).selectinload(ItemSource.source))
            )
        ).all()
    }

    def describe(tag: str, item_id: int, found: dict) -> None:
        item = items.get(item_id)
        head = item.headline[:90] if item else state.get("headlines", {}).get(str(item_id), "")
        for key, fact in found.items():
            value = fact.get("text") or fact.get("version") or ""
            source = _source(item, fact["quote"]) if item else "row gone"
            log.info("facts report: %s item %d | %s%s | quote %r | source %s | %s",
                     tag, item_id, key, f" = {value!r}" if value else "", fact["quote"][:300], source, head)

    poc = sorted(i for i in ids if "public_poc" in rows[str(i)])
    for i in poc:
        describe("POC", i, rows[str(i)])
    others = sorted(set(ids) - set(poc))
    for i in sorted(random.Random(20260930).sample(others, min(10, len(others)))):
        describe("sample", i, rows[str(i)])


async def run_once() -> None:
    from app.db import SessionLocal

    key = get_settings().anthropic_api_key
    if not key:
        return
    try:
        async with SessionLocal() as session:
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
                        await _report(session, state)
                        state["reported"] = REPORT_VERSION
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
