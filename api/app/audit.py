"""Feed audit: what happened to every entry of every feed's current fetch.

    python -m app.audit                      # all feeds, against the local API
    AUDIT_TOKEN=... python -m app.audit --api https://api.darkwire.tech --feed "Dark Reading" -v

The API caps public requests at 100 rows and refuses all_sources without the audit token, so
this sends X-Audit-Token from the AUDIT_TOKEN environment variable (the same value as the
Railway variable). Locally, with no token set on either side, the local API still answers:
set AUDIT_TOKEN for both.

Re-fetches each feed (unconditionally), parses it exactly as ingest does, and labels each
entry with the same rules, in the same order: invalid, too old, future-dated, ad. Entries that
pass are looked up by URL in the board the API serves: kept (the row's primary article), merged
(joined another row), elsewhere (rail), or not on board. Reads only; writes nothing.
"""

import argparse
import asyncio
import os
from collections import Counter
from datetime import UTC, datetime

import feedparser
import httpx

from app.ingest import FETCH_TIMEOUT, FUTURE_TOLERANCE, RETENTION, USER_AGENT, to_article
from app.models import Stream
from app.seed import SOURCES
from app.tagging import is_ad


async def board(client: httpx.AsyncClient, api: str) -> tuple[dict[str, bool], set[str]]:
    """URL -> is-primary for every main row in the retention window, and every Elsewhere URL."""
    urls: dict[str, bool] = {}
    offset = 0
    while True:
        page = (await client.get(f"{api}/feed", params={"limit": 200, "offset": offset, "all_sources": "true"})).json()
        for item in page["items"]:
            for s in item["sources"]:
                urls[s["url"]] = s["url"] == item["primary_url"]
            urls.setdefault(item["primary_url"], True)
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            break
    elsewhere = {e["url"] for e in (await client.get(f"{api}/elsewhere", params={"limit": 500})).json()}
    return urls, elsewhere


def fate(entry, now: datetime, urls: dict[str, bool], elsewhere: set[str]) -> tuple[str, object]:
    a = to_article(entry, now)
    if a is None:
        return "invalid", None
    if a.published_at < now - RETENTION:
        return "too old", a
    if a.published_at > now + FUTURE_TOLERANCE:
        return "future", a
    if is_ad(a.title, a.url, a.excerpt):
        return "ad", a
    if a.url in elsewhere:
        return "elsewhere", a
    if a.url in urls:
        return ("kept" if urls[a.url] else "merged"), a
    return "not on board", a


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--feed", help="only this feed (name)")
    parser.add_argument("-v", "--verbose", action="store_true", help="print every entry")
    args = parser.parse_args()

    now = datetime.now(UTC)
    feeds = [s for s in SOURCES if s["stream"] != Stream.enrichment and (not args.feed or s["name"] == args.feed)]
    headers = {"User-Agent": USER_AGENT}
    if os.environ.get("AUDIT_TOKEN"):
        headers["X-Audit-Token"] = os.environ["AUDIT_TOKEN"]
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT * 2, follow_redirects=True, headers=headers) as client:
        urls, elsewhere = await board(client, args.api)
        zero = []
        for src in feeds:
            try:
                r = await client.get(src["feed_url"])
                r.raise_for_status()
            except httpx.HTTPError as e:
                print(f"\n{src['name']}: fetch failed: {e}")
                continue
            parsed = feedparser.parse(r.content)
            tally: Counter = Counter()
            rows = []
            for entry in parsed.entries:
                what, a = fate(entry, now, urls, elsewhere)
                tally[what] += 1
                rows.append((entry.get("published") or entry.get("updated") or "(no date)", a, what, entry.get("title", "")))
            kept = tally["kept"] + tally["merged"] + tally["elsewhere"]
            if kept == 0:
                zero.append(src["name"])
            summary = ", ".join(f"{k} {v}" for k, v in tally.most_common())
            print(f"\n{src['name']} ({src["stream"].value}): {len(parsed.entries)} entries: {summary}")
            if args.verbose:
                for raw, a, what, title in rows:
                    parsed_at = a.published_at.strftime("%Y-%m-%d %H:%M UTC") if a else "-"
                    print(f"  {what:13} {parsed_at:21} {raw[:31]:31}  {title[:70]}")
        print(f"\nfeeds with nothing kept: {', '.join(zero) or 'none'}")


if __name__ == "__main__":
    asyncio.run(main())
