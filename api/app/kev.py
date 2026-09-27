"""CISA Known Exploited Vulnerabilities catalog, refreshed hourly."""

import logging
from datetime import UTC, date, datetime, timedelta
from itertools import batched

import httpx
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import jobstate
from app.models import KevEntry

log = logging.getLogger(__name__)

URLS = [
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
    # CISA's own GitHub mirror, for networks where cisa.gov answers 403.
    "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json",
]
EVERY = timedelta(hours=1)  # CISA adds entries through the day


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


async def refresh(session: AsyncSession, client: httpx.AsyncClient, force: bool = False) -> int | None:
    """Replace kev_entries with the current catalog. None when skipped or unreachable."""
    now = datetime.now(UTC)
    last = await jobstate.get_time(session, "kev_fetched_at")
    if not force and last and now - last < EVERY:
        return None

    payload = None
    for url in URLS:
        try:
            r = await client.get(url, timeout=60)
            r.raise_for_status()
            payload = r.json()
            break
        except (httpx.HTTPError, ValueError) as e:
            log.warning("kev: %s failed: %s", url, e)
    if payload is None:
        return None

    rows = {
        v["cveID"].upper(): {
            "cve_id": v["cveID"].upper(),
            "vendor": v.get("vendorProject"),
            "product": v.get("product"),
            "name": v.get("vulnerabilityName"),
            "date_added": _date(v["dateAdded"]),
            "due_date": _date(v.get("dueDate")),
            "ransomware": v.get("knownRansomwareCampaignUse"),
        }
        for v in payload.get("vulnerabilities") or []
        if v.get("cveID") and v.get("dateAdded")
    }
    if not rows:
        log.warning("kev: empty catalog, keeping the previous one")
        return None
    for chunk in batched(rows.values(), 1000):
        stmt = insert(KevEntry).values(list(chunk))
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["cve_id"],
                set_={c: stmt.excluded[c] for c in ("vendor", "product", "name", "date_added", "due_date", "ransomware")},
            )
        )
    await session.execute(delete(KevEntry).where(KevEntry.cve_id.not_in(list(rows))))
    await jobstate.put(session, "kev_fetched_at", now)
    await jobstate.put(session, "kev_catalog_version", payload.get("catalogVersion"))
    await session.commit()
    return len(rows)
