"""Two CVE facts the clustering rules need before enrichment has run.

published(): when a CVE was published, for telling a context mention from a current one
(app/article_cves.py). NVD's date as stored; else NVD's API; else CVE.org's record
(cveawg.mitre.org, cveMetadata.datePublished); None when neither has one, which callers treat as
recent. Answers are cached for the life of the process.

pick_pinned(): the CVE a new row displays (enrich.roll_up never moves it afterwards), among the
article's subject CVEs (all of them when none is a subject): a KEV-listed one first, then the
highest CVSS by the scores already stored, then the first mentioned (rank()).
"""

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import nvd
from app.models import Cve, KevEntry

log = logging.getLogger(__name__)

CVE_ORG = "https://cveawg.mitre.org/api/cve/{}"
USER_AGENT = "darkwire/0.1 (+https://darkwire.tech)"

_cache: dict[str, datetime | None] = {}


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


async def published(session: AsyncSession, http: httpx.AsyncClient, cves: list[str]) -> dict[str, datetime | None]:
    stored = dict((await session.execute(select(Cve.id, Cve.published_at).where(Cve.id.in_(cves)))).all())
    out: dict[str, datetime | None] = {}
    client = None
    for c in cves:
        if stored.get(c) is not None:
            out[c] = stored[c]
            continue
        if c in _cache:
            out[c] = _cache[c]
            continue
        date = None
        try:
            client = client or nvd.Nvd(http)
            vulns = (await client.get({"cveId": c})).get("vulnerabilities") or []
            date = _ts(vulns[0]["cve"].get("published")) if vulns else None
        except (httpx.HTTPError, ValueError, KeyError) as e:
            log.info("cve facts: NVD %s: %s", c, e)
        if date is None:
            try:
                r = await http.get(CVE_ORG.format(c), headers={"User-Agent": USER_AGENT}, timeout=15)
                if r.status_code == 200:
                    date = _ts((r.json().get("cveMetadata") or {}).get("datePublished"))
            except (httpx.HTTPError, ValueError) as e:
                log.info("cve facts: CVE.org %s: %s", c, e)
        _cache[c] = out[c] = date
    return out


def rank(pool: list[str], kev: set[str], scores: dict[str, float | None]) -> str:
    """The displayed CVE of a pool: KEV-listed first, then the highest CVSS, then the first mentioned."""
    return min(pool, key=lambda c: (c not in kev, -(scores.get(c) if scores.get(c) is not None else -1), pool.index(c)))


async def kev_listed(session: AsyncSession, cves: list[str]) -> set[str]:
    listed = set(await session.scalars(select(KevEntry.cve_id).where(KevEntry.cve_id.in_(cves))))
    return listed | set(await session.scalars(select(Cve.id).where(Cve.id.in_(cves), Cve.kev.is_(True))))


async def pick_pinned(session: AsyncSession, cves: list[str], subject: set[str]) -> str | None:
    if not cves:
        return None
    pool = [c for c in cves if c in subject] or list(cves)
    scores = dict((await session.execute(select(Cve.id, Cve.base_score).where(Cve.id.in_(pool)))).all())
    return rank(pool, await kev_listed(session, pool), {c: float(s) if s is not None else None for c, s in scores.items()})
