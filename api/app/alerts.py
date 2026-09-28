"""The CVEs a CISA "Adds N Known Exploited Vulnerabilities to Catalog" alert lists.

The feed's excerpt stops before the list, so the alert page is read once (app/fetcher.py:
robots.txt, rate limit, nothing stored but the IDs). When the page cannot be read, the KEV
catalog's entries added on the alert's date are used, only if their number matches the count
in the headline ("Adds Two ..."); on a day with two alerts that is ambiguous, and the alert
gets no CVEs (nothing joins it) rather than another alert's.
"""

import logging
import re
from datetime import date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import fetcher
from app.models import KevEntry
from app.tagging import extract_cves, headline_count

log = logging.getLogger(__name__)

_URL_DATE = re.compile(r"/alerts/(\d{4})/(\d{2})/(\d{2})/")
_ONE = re.compile(r"\bAdds One\b", re.IGNORECASE)


def alert_date(url: str, published: datetime | None) -> date | None:
    """The date in the alert's URL (/alerts/2026/09/25/...), else its publish date."""
    m = _URL_DATE.search(url or "")
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    return published.date() if published else None


def alert_count(title: str) -> int | None:
    """"Adds Two ..." -> 2, "Adds One ..." -> 1."""
    return 1 if _ONE.search(title or "") else headline_count(title)


async def listed_cves(
    session: AsyncSession, client: httpx.AsyncClient | None, title: str, url: str, published: datetime | None,
    *feed_texts: str,
) -> list[str]:
    """The alert's CVEs: from the feed text if it lists them, else its page, else the catalog."""
    found = extract_cves(*feed_texts)
    if found:
        return found
    if client is not None:
        page = await fetcher.article_text(client, url)
        found = extract_cves(page or "")
        if found:
            return found
    day, n = alert_date(url, published), alert_count(title)
    if day is None or not n:
        return []
    added = list(await session.scalars(select(KevEntry.cve_id).where(KevEntry.date_added == day).order_by(KevEntry.cve_id)))
    if len(added) == n:
        return added
    log.info("alerts: %s lists no CVEs we could read (%d catalog entries on %s, headline says %d)", url, len(added), day, n)
    return []
