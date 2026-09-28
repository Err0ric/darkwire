"""Enrichment pass: KEV (hourly), NVD (new CVEs + change feed), EPSS (daily), then roll the
results up onto items. Runs on its own schedule, separate from RSS ingest."""

import logging
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import dedupe, epss, events, kev, nvd, summaries, topics
from app.config import get_settings
from app.db import SessionLocal
from app.models import Cve, Item, ItemCve, KevEntry, MsrcUpdate, PatchStatus, Stream
from app.tagging import says_unpatched

log = logging.getLogger(__name__)

JOB_ID = "enrich"
USER_AGENT = "darkwire/0.1 (+https://darkwire.tech)"


async def apply_kev(session: AsyncSession) -> None:
    """cves.kev from the catalog. KEV overrides MSRC's exploited flag."""
    if not await session.scalar(select(KevEntry.cve_id).limit(1)):
        return  # catalog never loaded: leave kev untouched rather than clear it
    rows = {r.cve_id: r for r in (await session.execute(select(KevEntry.cve_id, KevEntry.date_added, KevEntry.due_date))).all()}
    at = lambda d: datetime.combine(d, time.min, tzinfo=UTC) if d else None  # noqa: E731
    cves = (await session.scalars(select(Cve))).all()
    for c in cves:
        row = rows.get(c.id)
        kev_at, due_at = (at(row.date_added), at(row.due_date)) if row else (None, None)
        if c.kev != bool(row) or c.kev_added_at != kev_at or c.kev_due_date != due_at:
            if row and not c.kev:
                events.record(session, "kev", c.id, "added")
            c.kev, c.kev_added_at, c.kev_due_date = bool(row), kev_at, due_at
    await session.execute(
        update(MsrcUpdate)
        .where(MsrcUpdate.cve_id.in_(select(KevEntry.cve_id)), MsrcUpdate.exploited.is_not(True))
        .values(exploited=True)
    )
    await session.commit()


async def roll_up(session: AsyncSession) -> int:
    """Copy CVE facts onto items. Returns how many escalated (KEV added, score changed); the
    row's time is never touched here."""
    links = (
        await session.execute(
            select(ItemCve.item_id, ItemCve.position, Cve)
            .join(Cve, Cve.id == ItemCve.cve_id)
            .join(Item, Item.id == ItemCve.item_id)
            .where(Item.stream == Stream.main)
            .order_by(ItemCve.item_id, ItemCve.position)
        )
    ).all()
    by_item: dict[int, list[Cve]] = defaultdict(list)
    for item_id, _, cve in links:
        by_item[item_id].append(cve)
    if not by_item:
        return 0
    items = {
        i.id: i
        for i in (
            await session.scalars(select(Item).where(Item.id.in_(list(by_item))).options(selectinload(Item.sources)))
        ).all()
    }
    msrc = {
        m.cve_id: m
        for m in (
            await session.scalars(select(MsrcUpdate).where(MsrcUpdate.cve_id.in_({c.id for cs in by_item.values() for c in cs})))
        ).all()
    }

    escalated = 0
    for item_id, cves in by_item.items():
        item = items[item_id]
        scored = [c for c in cves if c.base_score is not None]
        # Highest score wins; ties go to the CVE mentioned first. Unscored rows keep the first mention.
        primary = max(scored, key=lambda c: (c.base_score, -cves.index(c))) if scored else cves[0]
        kev_dates = [c.kev_added_at for c in cves if c.kev and c.kev_added_at]

        status, url = primary.patch_status, primary.patch_url
        m = msrc.get(primary.id)
        if m and m.kbs and status in (None, PatchStatus.unverified, PatchStatus.no_fix):
            status, url = PatchStatus.patched, m.url  # Microsoft shipped a KB for it
        url = url or (m.url if m else None)

        # KEV or score changes never move the row's time (app/rowtime.py: its news sources only).
        # They still reach viewers as escalations through items.changed_at; counted for the log.
        if (kev_dates and not item.kev) or (
            item.cvss is not None and primary.base_score is not None and primary.base_score != item.cvss
        ):
            escalated += 1

        # Coverage override: when a headline or lead paragraph in the cluster says unpatched / no
        # patch, nothing in it is "patched". With no explicit vendor fix it is "no fix"; with one
        # (coverage and vendor disagree) it is "unverified" until they agree.
        if says_unpatched(*(t for s in item.sources for t in (s.title, s.excerpt))):
            status = PatchStatus.unverified if status == PatchStatus.patched else PatchStatus.no_fix
            for c in cves:
                c.patch_status = PatchStatus.unverified if c.patch_status == PatchStatus.patched else PatchStatus.no_fix

        item.cve_id = primary.id
        item.cvss = primary.base_score
        item.severity = primary.base_severity
        # A CISA KEV alert on the row counts before the hourly catalog poll catches up.
        item.kev = bool(kev_dates) or any(c.kev for c in cves) or dedupe.has_alert(item.sources)
        item.epss = primary.epss
        item.patch_status = status or PatchStatus.unverified
        item.patch_url = url
    await session.commit()
    return escalated


async def run_enrich() -> None:
    started = datetime.now(UTC)
    counts: dict[str, int | None] = {}
    async with SessionLocal() as session, httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30
    ) as client:
        client_nvd = nvd.Nvd(client)
        steps = [
            ("kev", lambda: kev.refresh(session, client)),
            ("nvd_new", lambda: nvd.fetch_new(session, client_nvd)),
            ("nvd_changed", lambda: nvd.sync_changes(session, client_nvd)),
            ("nvd_reparse", lambda: nvd.reparse_if_changed(session)),
            ("epss", lambda: epss.refresh(session, client)),
        ]
        for name, step in steps:
            try:
                counts[name] = await step()
            except Exception:
                log.exception("enrich: %s failed", name)
                await session.rollback()
                counts[name] = None
        try:
            await apply_kev(session)
            counts["escalated"] = await roll_up(session)
        except Exception:
            log.exception("enrich: roll-up failed")
            await session.rollback()
        try:
            counts["summaries"] = await summaries.summarize_pending(session)
            counts["actions"] = await summaries.actions_pending(session)
            counts["topics"] = await topics.classify_pending(session)
        except Exception:
            log.exception("enrich: summaries failed")
            await session.rollback()
    log.info(
        "enrich: done in %.0fs: %s",
        (datetime.now(UTC) - started).total_seconds(),
        ", ".join(f"{k}={v}" for k, v in counts.items()),
    )


def schedule(scheduler) -> None:
    interval = get_settings().enrich_interval_minutes
    scheduler.add_job(
        run_enrich,
        "interval",
        minutes=interval,
        id=JOB_ID,
        # Give the first ingest a head start so there are CVEs to enrich.
        next_run_time=datetime.now(UTC) + timedelta(seconds=45),
        max_instances=1,
        coalesce=True,
    )
    log.info("scheduler: enrich every %d min", interval)
