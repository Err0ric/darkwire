"""Scheduled ingest: fetch every feed, cluster articles into rows, drop what is too old.

Enrichment feeds (MSRC) never become rows; they are handed to their handler in ENRICHERS.

No enrichment yet. cvss, severity, kev, epss and patch_status stay null until the
NVD / KEV / EPSS jobs exist.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import feedparser
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import cleanup, dedupe, events, jobstate, msrc
from app.config import get_settings
from app.db import SessionLocal
from app.models import Category, Cve, Health, Item, ItemCve, ItemSource, Source, Stream, SyncRun, Vendor
from app.tagging import (
    VendorMatcher,
    clean_text,
    cluster_cves,
    headline_cves,
    first_paragraph,
    guess_category,
    is_ad,
)

log = logging.getLogger(__name__)

JOB_ID = "ingest"
USER_AGENT = "darkwire/0.1 (+https://darkwire.tech)"
FETCH_TIMEOUT = 15.0
RETENTION = timedelta(days=14)
CVE_CLUSTER_WINDOW = timedelta(hours=48)
FUTURE_TOLERANCE = timedelta(hours=1)
ENRICHERS = {**msrc.ENRICHERS}

scheduler = AsyncIOScheduler(timezone=UTC)


@dataclass
class FetchResult:
    source_id: int
    not_modified: bool = False
    entries: list = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    error: str | None = None


@dataclass
class Stored:
    """What one fetch did with its entries. Every entry lands in exactly one bucket."""

    entries: int = 0
    added: int = 0  # kept: became a new row
    merged: int = 0  # kept: joined an existing row
    seen: int = 0  # already stored from an earlier fetch
    skipped_ads: int = 0
    skipped_future: int = 0
    too_old: int = 0  # older than RETENTION
    invalid: int = 0  # no link or title

    def counts(self) -> dict:
        return {
            "entries": self.entries, "kept": self.added, "merged": self.merged, "seen": self.seen,
            "ads": self.skipped_ads, "future": self.skipped_future, "too_old": self.too_old, "invalid": self.invalid,
        }


@dataclass
class Article:
    url: str
    guid: str | None
    title: str
    excerpt: str
    text: str
    body: str  # full content (content:encoded), plain text; empty when the feed has none
    published_at: datetime


async def fetch(client: httpx.AsyncClient, source: Source, conditional: bool = True) -> FetchResult:
    headers = {}
    if conditional and source.etag:
        headers["If-None-Match"] = source.etag
    if conditional and source.last_modified:
        headers["If-Modified-Since"] = source.last_modified
    try:
        r = await client.get(source.feed_url, headers=headers)
        if r.status_code == 304:
            return FetchResult(source.id, not_modified=True)
        r.raise_for_status()
        parsed = await asyncio.to_thread(feedparser.parse, r.content)
    except httpx.HTTPStatusError as e:
        return FetchResult(source.id, error=f"HTTP {e.response.status_code}")
    except httpx.HTTPError as e:
        return FetchResult(source.id, error=f"{type(e).__name__}: {e}"[:500])
    if parsed.bozo and not parsed.entries:
        return FetchResult(source.id, error=f"parse: {parsed.get('bozo_exception')}"[:500])
    return FetchResult(
        source.id,
        entries=parsed.entries,
        etag=r.headers.get("etag"),
        last_modified=r.headers.get("last-modified"),
    )


def to_article(entry, now: datetime) -> Article | None:
    url = (entry.get("link") or "").strip()
    title = clean_text(entry.get("title"))
    if not url or not title:
        return None
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    published = datetime(*t[:6], tzinfo=UTC) if t else now
    raw = entry.get("summary") or ""
    return Article(
        url=url,
        guid=entry.get("id"),
        title=title,
        excerpt=first_paragraph(raw),
        text=clean_text(raw),
        body=clean_text(" ".join(c.get("value", "") for c in entry.get("content") or []))[:50_000],
        published_at=published,
    )


def _is_better_primary(new: ItemSource, new_source: Source, cur: ItemSource | None) -> bool:
    """Vendor PSIRT beats everyone, otherwise earliest wins."""
    if cur is None:
        return True
    new_psirt, cur_psirt = new_source.vendor_id is not None, cur.source.vendor_id is not None
    if new_psirt != cur_psirt:
        return new_psirt
    far = datetime.max.replace(tzinfo=UTC)
    return (new.published_at or far) < (cur.published_at or far)


async def find_cve_cluster(session: AsyncSession, cves: list[str], published: datetime) -> Item | None:
    if not cves:
        return None
    return await session.scalar(
        select(Item)
        .where(
            Item.stream == Stream.main,
            Item.id.in_(select(ItemCve.item_id).where(ItemCve.cve_id.in_(cves))),
            Item.last_event_at.between(published - CVE_CLUSTER_WINDOW, published + CVE_CLUSTER_WINDOW),
        )
        .options(selectinload(Item.sources).selectinload(ItemSource.source))
        .order_by(Item.last_event_at.desc())
        .limit(1)
    )


async def link_cves(session: AsyncSession, item: Item, cves: list[str]) -> None:
    """Record every CVE an item's articles mention, after the ones it already has."""
    if not cves:
        return
    await session.flush()
    last = await session.scalar(
        select(func.coalesce(func.max(ItemCve.position), -1)).where(ItemCve.item_id == item.id)
    )
    await session.execute(
        insert(ItemCve)
        .values([{"item_id": item.id, "cve_id": c, "position": last + 1 + i} for i, c in enumerate(cves)])
        .on_conflict_do_nothing()
    )


async def ingest_source(
    session: AsyncSession, source: Source, entries: list, matcher: VendorMatcher, now: datetime
) -> Stored:
    stored = Stored(entries=len(entries))
    articles = []
    for a in (to_article(e, now) for e in entries):
        if a is None:
            stored.invalid += 1
        elif a.published_at < now - RETENTION:
            stored.too_old += 1
        elif a.published_at > now + FUTURE_TOLERANCE:
            stored.skipped_future += 1
        elif is_ad(a.title, a.url, a.excerpt):
            stored.skipped_ads += 1
        else:
            articles.append(a)
    if not articles:
        return stored
    seen = set(
        await session.scalars(select(ItemSource.url).where(ItemSource.url.in_([a.url for a in articles])))
    )

    for a in articles:
        if a.url in seen:
            stored.seen += 1
            continue
        seen.add(a.url)
        link = ItemSource(
            source=source, url=a.url, guid=a.guid, title=a.title,
            excerpt=a.excerpt or None, body=a.body or None, published_at=a.published_at,
        )

        if source.stream == Stream.elsewhere:
            session.add(Item(
                stream=Stream.elsewhere, headline=a.title, primary_url=a.url,
                category=Category.news, last_event_at=a.published_at,
                last_event_kind="published", sources=[link],
            ))
            stored.added += 1
            continue

        cves = headline_cves(a.title, a.excerpt, a.text, a.body)
        if cves:
            # Placeholder rows so the FKs hold. Enrichment fills them in.
            await session.execute(insert(Cve).values([{"id": c} for c in cves]).on_conflict_do_nothing())
        vendor_id = source.vendor_id or matcher.match(a.title, a.excerpt)
        category = guess_category(a.title, a.excerpt, bool(cves))

        cluster = await find_cve_cluster(session, cves, a.published_at) or await dedupe.find_title_cluster(
            session, a.title, vendor_id, a.published_at, matcher
        )
        if cluster is not None:
            current = next((s for s in cluster.sources if s.url == cluster.primary_url), None)
            if _is_better_primary(link, source, current):
                cluster.headline, cluster.primary_url = a.title, a.url
            cluster.sources.append(link)
            cluster.last_event_at = min(cluster.last_event_at, a.published_at)
            if source.vendor_id is not None or cluster.vendor_id is None:
                cluster.vendor_id = vendor_id or cluster.vendor_id
            if cluster.category == Category.news:
                cluster.category = category
            # The cluster's count can tie more IDs than this article alone ("2 zero-days" in one
            # headline, the bulletin list in another).
            texts = [(s.title, s.excerpt or "", s.body or "") for s in cluster.sources if s is not link]
            cves = cluster_cves([*texts, (a.title, a.excerpt or "", " ".join(t or "" for t in (a.text, a.body)))])
            if cves:
                await session.execute(insert(Cve).values([{"id": c} for c in cves]).on_conflict_do_nothing())
            await link_cves(session, cluster, cves)
            cluster.changed_at = func.now()  # a new source alone does not touch the row's columns
            events.record(session, "cluster", cluster.headline, f"{len(cluster.sources)} sources", cluster.id)
            stored.merged += 1
        else:
            # cve_id starts as the first CVE mentioned; enrichment re-points it at the highest-scored one.
            item = Item(
                stream=Stream.main, headline=a.title, primary_url=a.url,
                vendor_id=vendor_id, category=category, cve_id=cves[0] if cves else None,
                last_event_at=a.published_at, last_event_kind="published", sources=[link],
            )
            session.add(item)
            await link_cves(session, item, cves)
            stored.added += 1
        # Flush per article so the next one can cluster onto it.
        await session.flush()
    return stored


def _mark(source: Source, result: FetchResult, now: datetime) -> None:
    source.last_fetched_at = now
    if result.error:
        source.health = Health.failing
        source.last_error = result.error
        source.consecutive_failures += 1
        return
    source.health = Health.ok
    source.last_ok_at = now
    source.last_error = None
    source.consecutive_failures = 0
    if not result.not_modified:
        source.etag, source.last_modified = result.etag, result.last_modified


REEXTRACT_STATE = "reextract_v1"


async def reextract_once(
    session: AsyncSession, client: httpx.AsyncClient, sources: list[Source], matcher: VendorMatcher, now: datetime
) -> int | None:
    """One time: re-read every main feed in full, store article bodies and link any CVEs found
    in them to rows we already hold, then merge rows under both clustering rules. Only articles
    still present in a feed can be re-read. None when already done."""
    if await jobstate.get(session, REEXTRACT_STATE):
        return None
    main = [s for s in sources if s.stream == Stream.main]
    results = await asyncio.gather(*(fetch(client, s, conditional=False) for s in main))
    touched = 0
    for result in results:
        for entry in result.entries:
            a = to_article(entry, now)
            if a is None:
                continue
            link = await session.scalar(select(ItemSource).where(ItemSource.url == a.url))
            if link is None:
                continue
            link.body = a.body or link.body
            cves = headline_cves(a.title, a.excerpt, a.text, a.body)
            if cves:
                await session.execute(insert(Cve).values([{"id": c} for c in cves]).on_conflict_do_nothing())
                item = await session.get(Item, link.item_id)
                await link_cves(session, item, cves)
            touched += 1
    await session.commit()
    merged = await dedupe.merge_existing(session, matcher)
    await jobstate.put(session, REEXTRACT_STATE, now)
    await session.commit()
    log.info("ingest: re-extracted %d articles, merged %d rows", touched, merged)
    return touched


async def prune(session: AsyncSession, now: datetime) -> int:
    dropped = await session.execute(delete(Item).where(Item.last_event_at < now - RETENTION))
    await session.execute(delete(Cve).where(~exists().where(ItemCve.cve_id == Cve.id)))
    return dropped.rowcount or 0


async def run_ingest() -> None:
    async with SessionLocal() as session:
        run = SyncRun(started_at=datetime.now(UTC))
        session.add(run)
        await session.commit()

        try:
            sources = (await session.scalars(select(Source).where(Source.enabled))).all()
            matcher = VendorMatcher((await session.scalars(select(Vendor))).all())
            async with httpx.AsyncClient(
                timeout=FETCH_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
            ) as client:
                results = await asyncio.gather(*(fetch(client, s) for s in sources))

                now = datetime.now(UTC)
                by_id = {s.id: s for s in sources}
                for result in results:
                    source = by_id[result.source_id]
                    stored = Stored()
                    note = ""
                    if not result.error and not result.not_modified:
                        try:
                            # Savepoint: a bad feed rolls back its own rows, not the whole run.
                            async with session.begin_nested():
                                if source.stream == Stream.enrichment:
                                    handler = ENRICHERS.get(source.feed_url)
                                    if handler is None:
                                        raise LookupError(f"no enrichment handler for {source.feed_url}")
                                    note = f", {await handler(session, result.entries)} enrichment rows"
                                else:
                                    stored = await ingest_source(session, source, result.entries, matcher, now)
                        except Exception as e:
                            log.exception("ingest: %s failed while storing", source.name)
                            stored = Stored()
                            result.error = f"store: {type(e).__name__}: {e}"[:500]
                    _mark(source, result, now)
                    if result.error:
                        source.last_counts = {"error": result.error}
                    elif result.not_modified:
                        source.last_counts = {"not_modified": True}
                    elif source.stream != Stream.enrichment:
                        source.last_counts = stored.counts()
                    if stored.added and source.stream == Stream.main:
                        events.record(session, "ingest", source.name, f"+{stored.added} {'item' if stored.added == 1 else 'items'}")
                    await session.commit()
                    run.items_added += stored.added
                    run.skipped_ads += stored.skipped_ads
                    status = result.error or ("304" if result.not_modified else f"{len(result.entries)} entries")
                    log.info(
                        "ingest: %s: %s, %d new, %d merged, %d seen, %d ads, %d future, %d too old%s",
                        source.name, status, stored.added, stored.merged, stored.seen,
                        stored.skipped_ads, stored.skipped_future, stored.too_old, note,
                    )

                details = await msrc.fetch_details(session, client)
                await session.commit()

            # One-time maintenance, each in its own session: a failure here must not roll
            # back (and expire) this run's objects. Retried next run until it succeeds.
            try:
                async with SessionLocal() as once, httpx.AsyncClient(
                    timeout=FETCH_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
                ) as client:
                    await reextract_once(once, client, sources, matcher, now)
            except Exception:
                log.exception("ingest: re-extraction failed, retried next run")
            try:
                async with SessionLocal() as once:
                    await cleanup.retag_once(once, matcher)
            except Exception:
                log.exception("ingest: cleanup failed, retried next run")
            try:
                async with SessionLocal() as once:
                    await cleanup.relink_cves_once(once)
            except Exception:
                log.exception("ingest: CVE relink failed, retried next run")
            try:
                async with SessionLocal() as once:
                    # v2: vendorless stories that share distinctive words (Kiteworks-style pairs).
                    await dedupe.merge_once(once, matcher, "merge_v2")
            except Exception:
                log.exception("ingest: merge failed, retried next run")
            await dedupe.refresh_exploited(session)
            dropped = await prune(session, now)
            await events.prune(session, now)
            failing = [by_id[r.source_id].name for r in results if r.error]
            run.ok = True
            run.error = f"failing: {', '.join(failing)}" if failing else None
            log.info(
                "ingest: run %d done, %d new, %d ads skipped, %d msrc details, %d pruned, %d failing",
                run.id, run.items_added, run.skipped_ads, details, dropped, len(failing),
            )
        except Exception as e:
            log.exception("ingest: run failed")
            await session.rollback()
            run = await session.get(SyncRun, run.id)
            run.ok = False
            run.error = f"{type(e).__name__}: {e}"[:500]
        run.finished_at = datetime.now(UTC)
        await session.commit()


def start_scheduler() -> None:
    interval = get_settings().ingest_interval_minutes
    scheduler.add_job(
        run_ingest,
        "interval",
        minutes=interval,
        id=JOB_ID,
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("scheduler: ingest every %d min", interval)


def next_run_at() -> datetime | None:
    job = scheduler.get_job(JOB_ID) if scheduler.running else None
    return job.next_run_time if job else None
