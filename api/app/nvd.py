"""NVD API 2.0: CVSS, CPE ranges and reference tags for CVEs on the board.

New CVEs are fetched one at a time. After that a CVE is only re-read when NVD's change
feed (lastModStartDate / lastModEndDate) says it changed, so nothing is polled blindly.
Rate limits: 5 requests / 30 s without a key, 50 / 30 s with NVD_API_KEY.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import events, jobstate
from app.config import get_settings
from app.models import Cve, Item, ItemCve, PatchStatus, Severity
from app.product_names import display_name
from app.ratelimit import RateLimiter

log = logging.getLogger(__name__)

API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
PAGE_SIZE = 2000
CHANGE_OVERLAP = timedelta(minutes=5)
MAX_WINDOW = timedelta(days=119)  # NVD allows at most 120 days per lastMod query
CHANGES_STATE = "nvd_changes_until"
ANALYZED = {"Analyzed", "Modified"}
# Bump when parse() output changes; the next enrichment pass re-derives every stored CVE
# from its cached NVD record (no API calls).
PARSER_VERSION = "5"


class Nvd:
    def __init__(self, client: httpx.AsyncClient):
        key = get_settings().nvd_api_key
        self.client = client
        self.headers = {"apiKey": key} if key else {}
        # A little under the published limits; NVD also asks for a pause between calls.
        self.limiter = RateLimiter(50, 31) if key else RateLimiter(5, 31)
        self.per_run = 300 if key else 30

    async def get(self, params: dict) -> dict:
        for attempt in range(4):
            await self.limiter.wait()
            try:
                r = await self.client.get(API, params=params, headers=self.headers, timeout=60)
                if r.status_code in (403, 429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as e:
                if attempt == 3:
                    raise
                log.info("nvd: %s, retrying (%s)", e, params)
                await asyncio.sleep(6 * (attempt + 1))
        raise RuntimeError("unreachable")


# ---------------------------------------------------------------- parsing


def _ts(value: str | None) -> datetime | None:
    # NVD timestamps are UTC without an offset: 2026-06-17T07:44:11.533
    return datetime.fromisoformat(value).replace(tzinfo=UTC) if value else None


def _pick_cvss(metrics: dict) -> dict | None:
    """CVSS 3.1 (then 3.0): NVD's own Primary score, else the CNA's Secondary one."""
    for key in ("cvssMetricV31", "cvssMetricV30"):
        found = metrics.get(key) or []
        if found:
            return next((m for m in found if m.get("type") == "Primary"), found[0])
    return None


RANGE_KEYS = ("versionStartIncluding", "versionStartExcluding", "versionEndIncluding", "versionEndExcluding")


def _cpes(cve: dict) -> list[dict]:
    out = []
    for config in cve.get("configurations") or []:
        for node in config.get("nodes") or []:
            for m in node.get("cpeMatch") or []:
                if m.get("vulnerable"):
                    out.append({"criteria": m["criteria"], **{k: m[k] for k in RANGE_KEYS if m.get(k)}})
    return out


def _cpe_product(criteria: str) -> str:
    """The CPE product slug, e.g. "sharepoint_server"."""
    parts = criteria.split(":")
    return parts[4] if len(parts) > 4 else criteria


def _cpe_version(criteria: str) -> str | None:
    parts = criteria.split(":")
    if len(parts) < 6 or parts[5] in ("*", "-", ""):
        return None
    update_ = parts[6] if len(parts) > 6 and parts[6] not in ("*", "-", "") else None
    return f"{parts[5]}-{update_}" if update_ else parts[5]


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _cna_name(name: str) -> str:
    # CNA names are usually well cased; an all-lowercase one gets the CPE treatment.
    return display_name(name.replace(" ", "_")) if name.islower() else name


def _cna_versions(cve: dict):
    for a in cve.get("affected") or []:
        for d in a.get("affectedData") or []:
            for v in d.get("versions") or []:
                if v.get("versionType") != "git":  # kernel-style commit ranges read as noise
                    yield _cna_name(d.get("product") or ""), v


def _format(groups: dict[str, list[str]], limit: int = 3) -> str | None:
    """"PAN-OS 11.2 before 11.2.4-h3, 11.1 before 11.1.6-h1": product once, then its ranges."""
    parts: list[str] = []
    for product, ranges in groups.items():
        for i, r in enumerate(ranges):
            parts.append(f"{product} {r}".strip() if i == 0 else r)
    if not parts:
        return None
    return ", ".join(parts[:limit]) + (f" +{len(parts) - limit}" if len(parts) > limit else "")


def affected_summary(cve: dict, cpes: list[dict]) -> str | None:
    """CPE version ranges; else the CNA's ranges; else a compact list of exact CPE versions.
    Product names: the CNA's own name when it names the same product, else display_name()."""
    names = {_norm(p): p for p, _ in _cna_versions(cve) if p}

    def pretty(criteria: str) -> str:
        slug = _cpe_product(criteria)
        return names.get(_norm(slug), display_name(slug))

    groups: dict[str, list[str]] = {}
    for m in cpes:
        start = m.get("versionStartIncluding") or m.get("versionStartExcluding")
        if m.get("versionEndExcluding"):
            text = f"{start} before {m['versionEndExcluding']}" if start else f"before {m['versionEndExcluding']}"
        elif m.get("versionEndIncluding"):
            text = f"{start} through {m['versionEndIncluding']}" if start else f"through {m['versionEndIncluding']}"
        else:
            continue
        ranges = groups.setdefault(pretty(m["criteria"]), [])
        if text not in ranges:
            ranges.append(text)
    if groups:
        return _format(groups)

    for product, v in _cna_versions(cve):
        if v.get("status") != "affected":
            continue
        start = v.get("version") if v.get("version") not in (None, "", "0", "*", "n/a") else None
        if v.get("lessThan"):
            text = f"{start} before {v['lessThan']}" if start else f"before {v['lessThan']}"
        elif v.get("lessThanOrEqual"):
            text = f"{start} through {v['lessThanOrEqual']}" if start else f"through {v['lessThanOrEqual']}"
        else:
            continue
        ranges = groups.setdefault(product, [])
        if text not in ranges:
            ranges.append(text)
    if groups:
        return _format(groups)

    exact: dict[str, list[str]] = {}
    for m in cpes:
        version = _cpe_version(m["criteria"])
        if version:
            exact.setdefault(pretty(m["criteria"]), []).append(version)
    if exact:
        return _format({p: [vs[0] if len(vs) == 1 else f"({len(vs)} versions)"] for p, vs in exact.items()})
    return None


def fixed_versions(cve: dict, cpes: list[dict], limit: int = 6) -> list[dict]:
    """Explicit fixed versions: CPE versionEndExcluding, else the CNA's "unaffected at"
    versions. versionEndIncluding names the last bad version and a CNA lessThan only bounds the
    affected range, so neither counts as a fix."""
    names = {_norm(p): p for p, _ in _cna_versions(cve) if p}
    out: list[dict] = []

    def add(product: str, version: str | None) -> None:
        if version and version not in ("*", "-", "n/a"):
            entry = {"product": product, "version": version}
            if entry not in out:
                out.append(entry)

    for m in cpes:
        slug = _cpe_product(m["criteria"])
        add(names.get(_norm(slug), display_name(slug)), m.get("versionEndExcluding"))
    if not out:
        for product, v in _cna_versions(cve):
            if v.get("status") != "affected":
                continue
            # "lessThan" only bounds the affected range (it can name a fix not shipped yet);
            # "unaffected at" is the vendor saying where it is fixed.
            for c in v.get("changes") or []:
                if c.get("status") == "unaffected":
                    add(product, c.get("at"))
    return out[:limit]


def patch_status(cve: dict, cpes: list[dict], refs: list[dict]) -> tuple[PatchStatus, str | None]:
    """Per CLAUDE.md: patched / no fix / no fix + workaround / unverified.

    The link is the vendor advisory, else an NVD reference tagged Patch (Mitigation for a
    workaround). It is kept for unverified CVEs too so the row can still link the advisory.
    """
    def tagged(tag: str) -> list[str]:
        return [r["url"] for r in refs if tag in (r.get("tags") or [])]

    advisory, patches, mitigations = tagged("Vendor Advisory"), tagged("Patch"), tagged("Mitigation")
    # Explicit fixes only: NVD's CPE upper bound (set from the vendor's fixed version when NVD
    # analyzes the CVE) or the CNA saying "unaffected at" a version. A CNA "lessThan" alone is
    # the edge of the affected range and can name a fix that has not shipped.
    fix_known = any(m.get("versionEndExcluding") for m in cpes) or any(
        v.get("status") == "affected" and any(c.get("status") == "unaffected" for c in v.get("changes") or [])
        for _, v in _cna_versions(cve)
    )
    if patches or fix_known:
        return PatchStatus.patched, (advisory or patches or [None])[0]
    if mitigations:
        return PatchStatus.workaround, mitigations[0]
    open_ended = cpes and all(
        not any(m.get(k) for k in ("versionEndIncluding", "versionEndExcluding")) and _cpe_version(m["criteria"]) is None
        for m in cpes
    )
    if cve.get("vulnStatus") in ANALYZED and open_ended:
        return PatchStatus.no_fix, (advisory or [None])[0]
    return PatchStatus.unverified, (advisory or [None])[0]


def parse(cve: dict, now: datetime) -> dict:
    metric = _pick_cvss(cve.get("metrics") or {})
    data = (metric or {}).get("cvssData") or {}
    cpes = _cpes(cve)
    refs = [{"url": r["url"], "tags": r.get("tags") or []} for r in cve.get("references") or []]
    status, url = patch_status(cve, cpes, refs)
    severity = (data.get("baseSeverity") or "").lower()
    score = data.get("baseScore")
    return {
        "description": next((d["value"] for d in cve.get("descriptions") or [] if d.get("lang") == "en"), None),
        "published_at": _ts(cve.get("published")),
        "last_modified_at": _ts(cve.get("lastModified")),
        "nvd_status": cve.get("vulnStatus"),
        "cvss_version": data.get("version"),
        "cvss_vector": data.get("vectorString"),
        "base_score": Decimal(str(score)) if score is not None else None,
        "base_severity": Severity(severity) if severity in Severity._value2member_map_ else None,
        "impact_score": Decimal(str(metric["impactScore"])) if metric and metric.get("impactScore") is not None else None,
        "exploitability_score": (
            Decimal(str(metric["exploitabilityScore"])) if metric and metric.get("exploitabilityScore") is not None else None
        ),
        "cpes": cpes,
        "references": refs,
        "affected": affected_summary(cve, cpes),
        "patch_status": status,
        "patch_url": url,
        "fixed_versions": fixed_versions(cve, cpes) or None,
        "workaround_url": next((r["url"] for r in refs if "Mitigation" in r["tags"]), None),
        "nvd_raw": cve,
        "fetched_at": now,
    }


# ---------------------------------------------------------------- jobs


async def fetch_new(session: AsyncSession, nvd: Nvd) -> int:
    """CVEs on the board that NVD has never been asked about, newest rows first."""
    latest = (
        select(ItemCve.cve_id, Item.last_event_at)
        .join(Item, Item.id == ItemCve.item_id)
        .join(Cve, Cve.id == ItemCve.cve_id)
        .where(Cve.fetched_at.is_(None))
        .subquery()
    )
    pending = (
        await session.scalars(
            select(latest.c.cve_id)
            .group_by(latest.c.cve_id)
            .order_by(func.max(latest.c.last_event_at).desc())
            .limit(nvd.per_run)
        )
    ).all()

    done = 0
    for cve_id in pending:
        now = datetime.now(UTC)
        try:
            data = await nvd.get({"cveId": cve_id})
        except (httpx.HTTPError, ValueError) as e:
            log.warning("nvd: %s failed: %s", cve_id, e)
            continue
        vulns = data.get("vulnerabilities") or []
        values = parse(vulns[0]["cve"], now) if vulns else {"fetched_at": now, "nvd_status": "NOT_FOUND"}
        await session.execute(update(Cve).where(Cve.id == cve_id).values(**values))
        if values.get("base_score") is not None:
            events.record(session, "nvd", cve_id, events.scored(values))
        await session.commit()
        done += 1
    return done


async def sync_changes(session: AsyncSession, nvd: Nvd) -> int:
    """Re-read CVEs we hold whose lastModified moved, using NVD's change feed."""
    now = datetime.now(UTC)
    since = await jobstate.get_time(session, CHANGES_STATE)
    if since is None:
        # First run: everything on the board is fetched fresh by fetch_new.
        await jobstate.put(session, CHANGES_STATE, now)
        await session.commit()
        return 0
    start = max(since - CHANGE_OVERLAP, now - MAX_WINDOW)
    fmt = lambda t: t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")  # noqa: E731

    rows = (
        await session.execute(select(Cve.id, Cve.last_modified_at, Cve.base_score).where(Cve.fetched_at.is_not(None)))
    ).all()
    known = {r.id: r.last_modified_at for r in rows}
    scores = {r.id: r.base_score for r in rows}
    updated, index = 0, 0
    while True:
        data = await nvd.get(
            {"lastModStartDate": fmt(start), "lastModEndDate": fmt(now), "startIndex": index, "resultsPerPage": PAGE_SIZE}
        )
        for v in data.get("vulnerabilities") or []:
            cve = v["cve"]
            if cve["id"] not in known:
                continue
            modified = _ts(cve.get("lastModified"))
            if known[cve["id"]] is None or (modified and modified > known[cve["id"]]):
                values = parse(cve, now)
                await session.execute(update(Cve).where(Cve.id == cve["id"]).values(**values))
                if values.get("base_score") is not None and values["base_score"] != scores.get(cve["id"]):
                    events.record(session, "nvd", cve["id"], events.scored(values))
                updated += 1
        index += data.get("resultsPerPage") or 0
        if not data.get("resultsPerPage") or index >= (data.get("totalResults") or 0):
            break
    await jobstate.put(session, CHANGES_STATE, now)
    await session.commit()
    return updated


async def reparse_if_changed(session: AsyncSession) -> int | None:
    """Re-derive CVE columns from cached nvd_raw when PARSER_VERSION changed. None when current."""
    if await jobstate.get(session, "nvd_parser_version") == PARSER_VERSION:
        return None
    cves = (await session.scalars(select(Cve).where(Cve.nvd_raw.is_not(None)))).all()
    for c in cves:
        values = parse(c.nvd_raw, c.fetched_at or datetime.now(UTC))
        for key in (
            "affected", "patch_status", "patch_url", "fixed_versions", "workaround_url",
            "base_score", "base_severity", "cvss_vector", "cvss_version",
        ):
            setattr(c, key, values[key])
    await jobstate.put(session, "nvd_parser_version", PARSER_VERSION)
    await session.commit()
    return len(cves)
