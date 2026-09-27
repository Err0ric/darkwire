"""Scheduled ingest: fetch every feed, cluster articles into rows, drop what is too old.

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
from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import SessionLocal
from app.models import Category, Cve, Health, Item, ItemSource, Source, Stream, SyncRun, Vendor
from app.tagging import VendorMatcher, clean_text, extract_cves, first_paragraph, guess_category

log = logging.getLogger(__name__)

JOB_ID = "ingest"
USER_AGENT = "darkwire/0.1 (+https://darkwire.tech)"
FETCH_TIMEOUT = 15.0
RETENTION = timedelta(days=14)
CVE_CLUSTER_WINDOW = timedelta(hours=48)

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
class Article:
    url: str
    guid: str | None
    title: str
    excerpt: str
    text: str
    published_at: datetime


async def fetch(client: httpx.AsyncClient, source: Source) -> FetchResult:
    headers = {}
    if source.etag:
        headers["If-None-Match"] = source.etag
    if source.last_modified:
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
        published_at=min(published, now),  # some feeds post-date entries
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
            Item.cve_id.in_(cves),
            Item.last_event_at.between(published - CVE_CLUSTER_WINDOW, published + CVE_CLUSTER_WINDOW),
        )
        .options(selectinload(Item.sources).selectinload(ItemSource.source))
        .order_by(Item.last_event_at.desc())
        .limit(1)
    )


async def ingest_source(
    session: AsyncSession, source: Source, entries: list, matcher: VendorMatcher, now: datetime
) -> int:
    articles = [a for a in (to_article(e, now) for e in entries) if a and a.published_at >= now - RETENTION]
    if not articles:
        return 0
    seen = set(
        await session.scalars(select(ItemSource.url).where(ItemSource.url.in_([a.url for a in articles])))
    )

    added = 0
    for a in articles:
        if a.url in seen:
            continue
        seen.add(a.url)
        link = ItemSource(
            source=source, url=a.url, guid=a.guid, title=a.title,
            excerpt=a.excerpt or None, published_at=a.published_at,
        )

        if source.stream == Stream.elsewhere:
            session.add(Item(
                stream=Stream.elsewhere, headline=a.title, primary_url=a.url,
                category=Category.news, last_event_at=a.published_at,
                last_event_kind="published", sources=[link],
            ))
            added += 1
            continue

        cves = extract_cves(a.title, a.text)
        vendor_id = source.vendor_id or matcher.match(a.title, a.excerpt)
        category = guess_category(a.title, a.excerpt, bool(cves))

        cluster = await find_cve_cluster(session, cves, a.published_at)
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
        else:
            if cves:
                # Placeholder rows so the FK holds. Enrichment fills them later.
                await session.execute(
                    insert(Cve).values([{"id": c} for c in cves]).on_conflict_do_nothing()
                )
            session.add(Item(
                stream=Stream.main, headline=a.title, primary_url=a.url,
                vendor_id=vendor_id, category=category, cve_id=cves[0] if cves else None,
                last_event_at=a.published_at, last_event_kind="published", sources=[link],
            ))
            added += 1
        # Flush per article so the next one can cluster onto it.
        await session.flush()
    return added


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


async def prune(session: AsyncSession, now: datetime) -> int:
    dropped = await session.execute(delete(Item).where(Item.last_event_at < now - RETENTION))
    await session.execute(delete(Cve).where(~exists().where(Item.cve_id == Cve.id)))
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
                added = 0
                if not result.error and not result.not_modified:
                    try:
                        # Savepoint: a bad feed rolls back its own rows, not the whole run.
                        async with session.begin_nested():
                            added = await ingest_source(session, source, result.entries, matcher, now)
                    except Exception as e:
                        log.exception("ingest: %s failed while storing", source.name)
                        added = 0
                        result.error = f"store: {type(e).__name__}: {e}"[:500]
                _mark(source, result, now)
                await session.commit()
                run.items_added += added
                status = result.error or ("304" if result.not_modified else f"{len(result.entries)} entries")
                log.info("ingest: %s: %s, %d new", source.name, status, added)

            dropped = await prune(session, now)
            failing = [by_id[r.source_id].name for r in results if r.error]
            run.ok = True
            run.error = f"failing: {', '.join(failing)}" if failing else None
            log.info("ingest: run %d done, %d new, %d pruned, %d failing", run.id, run.items_added, dropped, len(failing))
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
