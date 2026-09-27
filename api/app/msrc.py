"""MSRC Security Update Guide as enrichment, keyed by CVE.

The RSS feed carries one entry per CVE revision (title, link, revision note). Product,
KBs, fixed builds and the exploited flag come from the SUG API, fetched only for CVEs
that are on the board, and again only when MSRC revises them.
"""

import asyncio
import logging
from datetime import UTC, datetime
from itertools import batched

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, MsrcUpdate
from app.tagging import clean_text, extract_cves

log = logging.getLogger(__name__)

RSS_URL = "https://api.msrc.microsoft.com/update-guide/rss"
SUG_API = "https://api.msrc.microsoft.com/sug/v2.0/en-US"
DETAILS_PER_RUN = 40
CONCURRENCY = 4


async def store_entries(session: AsyncSession, entries: list) -> int:
    rows: dict[str, dict] = {}
    for e in entries:
        cves = extract_cves(e.get("id") or "", e.get("title") or "")
        if not cves:
            continue
        t = e.get("published_parsed")
        rows[cves[0]] = {
            "cve_id": cves[0],
            "title": clean_text(e.get("title")),
            "url": e.get("link") or f"https://msrc.microsoft.com/update-guide/vulnerability/{cves[0]}",
            "revision_note": clean_text(e.get("summary")) or None,
            "revised_at": datetime(*t[:6], tzinfo=UTC) if t else None,
        }
    for chunk in batched(rows.values(), 1000):
        stmt = insert(MsrcUpdate).values(list(chunk))
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["cve_id"],
                set_={
                    "title": stmt.excluded.title,
                    "url": stmt.excluded.url,
                    "revision_note": stmt.excluded.revision_note,
                    "revised_at": stmt.excluded.revised_at,
                    "details_fetched_at": None,
                },
                where=MsrcUpdate.revised_at.is_distinct_from(stmt.excluded.revised_at),
            )
        )
    return len(rows)


async def _odata(client: httpx.AsyncClient, path: str, cve_id: str) -> list[dict]:
    url: str | None = f"{SUG_API}/{path}"
    params: dict | None = {"$filter": f"cveNumber eq '{cve_id}'"}  # cve_id is regex-validated
    out: list[dict] = []
    while url:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("value", []))
        url, params = data.get("@odata.nextLink"), None
    return out


def _yes(value) -> bool | None:
    return None if value is None else str(value).strip().lower().startswith("yes")


async def _details(client: httpx.AsyncClient, cve_id: str) -> dict:
    vulns = await _odata(client, "vulnerability", cve_id)
    products = await _odata(client, "affectedProduct", cve_id)
    v = vulns[0] if vulns else {}
    kbs: dict[str, str | None] = {}
    builds: dict[tuple[str, str], None] = {}
    for p in products:
        for kb in p.get("kbArticles") or []:
            if kb.get("articleName"):
                kbs.setdefault(kb["articleName"], kb.get("articleUrl"))
            if kb.get("fixedBuildNumber"):
                builds.setdefault((p.get("product") or "", kb["fixedBuildNumber"]), None)
    return {
        "product": v.get("tag"),
        "severity": v.get("severity"),
        "exploited": _yes(v.get("exploited")),
        "publicly_disclosed": _yes(v.get("publiclyDisclosed")),
        "release": v.get("releaseNumber"),
        "kbs": [{"kb": k, "url": u} for k, u in kbs.items()],
        "fixed_builds": [{"product": p, "build": b} for p, b in builds],
    }


async def fetch_details(session: AsyncSession, client: httpx.AsyncClient) -> int:
    """Fill API details for MSRC entries whose CVE is on the board."""
    pending = (
        await session.scalars(
            select(MsrcUpdate.cve_id)
            .where(
                MsrcUpdate.details_fetched_at.is_(None),
                MsrcUpdate.cve_id.in_(select(Item.cve_id).where(Item.cve_id.is_not(None))),
            )
            .limit(DETAILS_PER_RUN)
        )
    ).all()
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(cve_id: str) -> tuple[str, dict | None]:
        async with sem:
            try:
                return cve_id, await _details(client, cve_id)
            except (httpx.HTTPError, ValueError) as e:
                log.warning("msrc: details for %s failed: %s", cve_id, e)
                return cve_id, None

    now = datetime.now(UTC)
    filled = 0
    for cve_id, details in await asyncio.gather(*(one(c) for c in pending)):
        if details is None:
            continue
        await session.execute(
            update(MsrcUpdate)
            .where(MsrcUpdate.cve_id == cve_id)
            .values(**details, details_fetched_at=now)
        )
        filled += 1
    return filled


ENRICHERS = {RSS_URL: store_entries}
