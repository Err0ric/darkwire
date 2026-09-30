"""Two CVE facts the clustering rules need before enrichment has run.

published(): when a CVE was published, for telling a context mention from a current one
(app/article_cves.py). NVD's date as stored; else NVD's API; else CVE.org's record
(cveawg.mitre.org, cveMetadata.datePublished); None when neither has one, which callers treat as
recent. Answers are cached for the life of the process.

pick_pinned(): the CVE a new row displays, among the article's subject CVEs only (the first
linked one when the stored text shows no subject; every CVE of a KEV alert row, row_subjects()): one named in the headline first, then a
KEV-listed one, then the highest CVSS by the scores already stored, then the first mentioned
(rank()). Pins are sticky: set once, when the row gets its first CVE; roll-ups, merges and
re-enrichment never move it. Only an explicit, signed-off re-pin (app/maintenance.py) does.
"""

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import dedupe, nvd
from app.models import Cve, KevEntry
from app.tagging import extract_cves, row_subject_cves

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


def eligible(cves: list[str], subject: set[str]) -> list[str]:
    """The subject CVEs of cves, in order; context CVEs never display. When the stored text shows
    no subject at all, only the first linked CVE (the one that made it a CVE row)."""
    return [c for c in cves if c in subject] or list(cves[:1])


def row_subjects(item, cves: list[str]) -> set[str]:
    """A row's subject CVEs: every CVE of a row a CISA KEV alert started (it holds exactly the
    alert's CVEs); else the subject CVEs of its stored articles, plus the CVEs a KEV alert that
    joined it lists."""
    if dedupe.alert_led(item):
        return set(cves)
    subject = row_subject_cves(item.sources)
    for s in item.sources:
        if dedupe.is_kev_alert(s.title, s.url):
            subject |= set(extract_cves(s.title or "", s.excerpt or "", s.body or "")) & set(cves)
    return subject


def rank(pool: list[str], kev: set[str], scores: dict[str, float | None], headline: str = "") -> str:
    """The displayed CVE of a pool: named in the headline first, then KEV-listed, then the highest
    CVSS, then the first mentioned."""
    named = set(extract_cves(headline))
    return min(pool, key=lambda c: (c not in named, c not in kev, -(scores.get(c) if scores.get(c) is not None else -1), pool.index(c)))


async def kev_listed(session: AsyncSession, cves: list[str]) -> set[str]:
    listed = set(await session.scalars(select(KevEntry.cve_id).where(KevEntry.cve_id.in_(cves))))
    return listed | set(await session.scalars(select(Cve.id).where(Cve.id.in_(cves), Cve.kev.is_(True))))


async def pick_pinned(session: AsyncSession, cves: list[str], subject: set[str], headline: str = "") -> str | None:
    if not cves:
        return None
    pool = eligible(cves, subject)
    scores = dict((await session.execute(select(Cve.id, Cve.base_score).where(Cve.id.in_(pool)))).all())
    return rank(pool, await kev_listed(session, pool), {c: float(s) if s is not None else None for c, s in scores.items()}, headline)
