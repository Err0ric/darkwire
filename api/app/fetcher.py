"""Article text for the summary model (and a CISA KEV alert's CVE list, app/alerts.py),
fetched on demand and never stored.

For summarization only: the article URL is fetched server-side, its main text extracted
(trafilatura) and cut to about ARTICLE_CHARS, then handed to the model in memory. Nothing
fetched is written to the database or shown; only the model's summary is kept.

Manners: robots.txt is honored (read per domain, cached for a day; a robots.txt that cannot
be read allows, as the robots standard says, except a 401/403 which disallows), requests say
who we are (USER_AGENT), at most one request per domain every DOMAIN_GAP seconds (robots.txt
included), a TIMEOUT per request, and responses over MAX_BYTES are dropped. Any failure means
the caller falls back to the RSS excerpt. Per-domain outcomes are counted and logged.
"""

import asyncio
import logging
import time
import urllib.robotparser
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; darkwire.tech summarizer; +https://darkwire.tech/sources)"
ROBOTS_AGENT = "darkwire.tech summarizer"
DOMAIN_GAP = 5.0
TIMEOUT = 10.0
MAX_BYTES = 3_000_000
ARTICLE_CHARS = 4000
ROBOTS_TTL = 24 * 3600

_last: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_robots: dict[str, tuple[float, urllib.robotparser.RobotFileParser | None]] = {}
# domain -> {"ok", "blocked", "failed", "empty"}; since the process started.
stats: dict[str, dict[str, int]] = defaultdict(lambda: {"ok": 0, "blocked": 0, "failed": 0, "empty": 0})


def _domain(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host.removeprefix("www.")


@dataclass
class _Page:
    status: int
    content_type: str
    text: str
    final_url: str


async def _polite_get(client: httpx.AsyncClient, url: str) -> _Page:
    """One GET, spaced DOMAIN_GAP seconds from the last request to the same domain."""
    domain = _domain(url)
    async with _locks[domain]:
        wait = _last.get(domain, 0) + DOMAIN_GAP - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with client.stream("GET", url) as r:
                chunks, size = [], 0
                async for chunk in r.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise httpx.HTTPError("response too large")
                    chunks.append(chunk)
                body = b"".join(chunks)
                return _Page(r.status_code, r.headers.get("content-type", ""), body.decode(r.encoding or "utf-8", "replace"), str(r.url))
        finally:
            _last[domain] = time.monotonic()


async def _allowed(client: httpx.AsyncClient, url: str) -> bool:
    parts = urlsplit(url)
    domain = _domain(url)
    cached = _robots.get(domain)
    if not cached or time.time() - cached[0] > ROBOTS_TTL:
        parser: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
        try:
            r = await _polite_get(client, f"{parts.scheme}://{parts.netloc}/robots.txt")
            if r.status in (401, 403):
                parser.disallow_all = True
            elif r.status >= 400:
                parser.allow_all = True
            else:
                parser.parse(r.text.splitlines())
            log.debug("robots %s: HTTP %d", domain, r.status)
            parser.modified()  # can_fetch() answers False until a read time is set
        except httpx.HTTPError as e:
            log.debug("robots %s failed: %s", domain, e)
            parser = None  # unknown this time: do not fetch, ask again next time
        _robots[domain] = (time.time() if parser else 0, parser)
        cached = _robots[domain]
    parser = cached[1]
    return bool(parser and parser.can_fetch(ROBOTS_AGENT, url))


async def article_text(client: httpx.AsyncClient, url: str) -> str | None:
    """The article's main text, at most ARTICLE_CHARS (cut at a sentence end when one is
    near), or None when blocked, failing or empty."""
    domain = _domain(url)
    try:
        if not await _allowed(client, url):
            stats[domain]["blocked"] += 1
            return None
        r = await _polite_get(client, url)
        # A redirect to another site would skip that site's robots.txt: treat it as a failure.
        if _domain(r.final_url) != domain:
            stats[domain]["failed"] += 1
            return None
        if r.status != 200 or "html" not in r.content_type:
            stats[domain]["failed"] += 1
            return None
        try:
            # Imported here: where its lxml cannot load, fetching fails and callers fall back.
            import trafilatura
        except ImportError as e:
            log.warning("fetch: trafilatura unavailable: %s", e)
            stats[domain]["failed"] += 1
            return None
        text = await asyncio.to_thread(
            trafilatura.extract, r.text, url=url, include_comments=False, include_tables=False, favor_precision=True
        )
    except (httpx.HTTPError, ValueError) as e:
        log.debug("fetch %s failed: %s", url, e)
        stats[domain]["failed"] += 1
        return None
    text = " ".join((text or "").split())
    if len(text) < 200:
        stats[domain]["empty"] += 1
        return None
    stats[domain]["ok"] += 1
    if len(text) > ARTICLE_CHARS:
        cut = text.rfind(". ", 0, ARTICLE_CHARS)
        text = text[: cut + 1] if cut > ARTICLE_CHARS * 0.7 else text[:ARTICLE_CHARS]
    return text


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
    )


def log_stats() -> None:
    """Per-domain success rates since the process started, one line."""
    if not stats:
        return
    parts = []
    for domain, s in sorted(stats.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(s.values())
        extra = ", ".join(f"{k} {v}" for k, v in s.items() if k != "ok" and v)
        parts.append(f"{domain} {s['ok']}/{total} ok" + (f" ({extra})" if extra else ""))
    log.info("fetch: %s", "; ".join(parts))
