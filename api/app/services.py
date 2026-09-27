"""Third-party service status for the rail's Services block and /outages.

Every POLL_MINUTES each service's official status source is fetched and reduced to one state:
operational, degraded (amber), major (red), or unknown (the source failed or was never read),
plus the current incident's title, link and start. The worst state per UTC hour is kept for
24 hours for the /outages strip.

Sources, all public and official:
- Statuspage (/api/v2/summary.json): Cloudflare, GitHub, DigitalOcean, Akamai, Duo, 1Password,
  Ping Identity, Zoom, Atlassian, Dropbox, npm, Docker, PyPI, Vercel.
  indicator minor -> degraded, major/critical -> major; maintenance is not an outage.
- AWS Health public events (health.aws.amazon.com/public/currentevents, UTF-16 JSON):
  event status 2 -> degraded, 3 -> major; the region is named in the title.
- Azure status RSS: an item is an active incident; "outage" / "unavailable" -> major.
- Microsoft 365: status.cloud.microsoft consumer posts plus the admin center RSS.
- Google Cloud and Google Workspace incidents.json: open incidents (no "end");
  SERVICE_OUTAGE -> major, SERVICE_DISRUPTION -> degraded.
- Slack (slack-status.com API v2): outage -> major, incident -> degraded, notices ignored.
- GitLab (status.io): status_code 300 -> degraded, 400+ -> major.
- Okta: status.okta.com has no API; its page embeds the incident records as JSON, and an
  incident not marked Resolved is active. Service Disruption categories -> major, others
  -> degraded.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import feedparser
import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import ServiceHour, ServiceStatus

log = logging.getLogger(__name__)

JOB_ID = "services"
POLL_MINUTES = 3
HISTORY = timedelta(hours=24)
TIMEOUT = 20.0
USER_AGENT = "darkwire/0.1 (+https://darkwire.tech)"

OPERATIONAL, DEGRADED, MAJOR, UNKNOWN = "operational", "degraded", "major", "unknown"
RANK = {UNKNOWN: 0, OPERATIONAL: 1, DEGRADED: 2, MAJOR: 3}


@dataclass
class Reading:
    state: str
    title: str | None = None
    url: str | None = None
    started_at: datetime | None = None


@dataclass(frozen=True)
class Service:
    slug: str
    name: str
    group: str  # Cloud, Identity, Collaboration, Dev
    page: str  # public status page, linked when there is no incident link
    kind: str  # statuspage, aws, azure, m365, google, slack, statusio, okta
    source: str  # the URL that is fetched


def _sp(slug: str, name: str, group: str, host: str) -> Service:
    return Service(slug, name, group, f"https://{host}", "statuspage", f"https://{host}/api/v2/summary.json")


SERVICES: list[Service] = [
    Service("aws", "AWS", "Cloud", "https://health.aws.amazon.com/health/status", "aws",
            "https://health.aws.amazon.com/public/currentevents"),
    Service("azure", "Azure", "Cloud", "https://azure.status.microsoft/en-us/status", "azure",
            "https://azure.status.microsoft/en-us/status/feed/"),
    Service("gcp", "Google Cloud", "Cloud", "https://status.cloud.google.com", "google",
            "https://status.cloud.google.com/incidents.json"),
    _sp("cloudflare", "Cloudflare", "Cloud", "www.cloudflarestatus.com"),
    _sp("digitalocean", "DigitalOcean", "Cloud", "status.digitalocean.com"),
    _sp("akamai", "Akamai", "Cloud", "www.akamaistatus.com"),
    Service("okta", "Okta", "Identity", "https://status.okta.com", "okta", "https://status.okta.com/"),
    _sp("duo", "Duo", "Identity", "status.duo.com"),
    _sp("1password", "1Password", "Identity", "status.1password.com"),
    _sp("ping", "Ping Identity", "Identity", "status.pingidentity.com"),
    Service("m365", "Microsoft 365", "Collaboration", "https://status.cloud.microsoft", "m365",
            "https://status.cloud.microsoft/api/posts/m365Consumer"),
    Service("google-workspace", "Google Workspace", "Collaboration", "https://www.google.com/appsstatus/dashboard/",
            "google", "https://www.google.com/appsstatus/dashboard/incidents.json"),
    Service("slack", "Slack", "Collaboration", "https://slack-status.com", "slack",
            "https://slack-status.com/api/v2.0.0/current"),
    _sp("zoom", "Zoom", "Collaboration", "www.zoomstatus.com"),
    _sp("atlassian", "Atlassian", "Collaboration", "status.atlassian.com"),
    _sp("dropbox", "Dropbox", "Collaboration", "status.dropbox.com"),
    _sp("github", "GitHub", "Dev", "www.githubstatus.com"),
    Service("gitlab", "GitLab", "Dev", "https://status.gitlab.com", "statusio",
            "https://status.gitlab.com/1.0/status/5b36dc6502d06804c08349f7"),
    _sp("npm", "npm", "Dev", "status.npmjs.org"),
    _sp("docker", "Docker", "Dev", "www.dockerstatus.com"),
    _sp("pypi", "PyPI", "Dev", "status.python.org"),
    _sp("vercel", "Vercel", "Dev", "www.vercel-status.com"),
]
BY_SLUG = {s.slug: s for s in SERVICES}
DEFAULTS = ["aws", "azure", "m365", "gcp", "cloudflare", "github", "slack", "okta"]
GROUPS = ["Cloud", "Identity", "Collaboration", "Dev"]
M365_ADMIN_RSS = "https://status.office365.com/api/feed/mac"


def _ts(value) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, int | float) or (isinstance(value, str) and value.isdigit()):
            return datetime.fromtimestamp(int(value), UTC)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _worst(readings: list[Reading]) -> Reading:
    return max(readings, key=lambda r: (RANK[r.state], r.started_at or datetime.min.replace(tzinfo=UTC)),
               default=Reading(OPERATIONAL))


# ---------------------------------------------------------------- parsers (one per kind)


def parse_statuspage(data: dict, svc: Service) -> Reading:
    """The page's own rollup (status.indicator) decides the state; the worst open incident
    only supplies the title and link. An incident the vendor rates impact "none", or one open
    while the page still says All Systems Operational, is not an outage here."""
    status = data.get("status") or {}
    indicator = status.get("indicator")
    state = {"major": MAJOR, "critical": MAJOR, "minor": DEGRADED}.get(indicator)
    if state is None:
        return Reading(OPERATIONAL)
    rank = {"critical": 3, "major": 2, "minor": 1}
    open_ = [
        i for i in data.get("incidents") or []
        if i.get("status") not in ("resolved", "postmortem") and i.get("impact") in rank
    ]
    if not open_:
        return Reading(state, status.get("description"), svc.page)
    inc = max(open_, key=lambda i: (rank[i["impact"]], i.get("created_at") or ""))
    return Reading(state, inc.get("name"), inc.get("shortlink") or svc.page, _ts(inc.get("created_at")))


def parse_aws(raw: bytes, svc: Service) -> Reading:
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    # One reading per (service, summary), naming every region it covers:
    # "Multiple services · Region Availability · UAE, Bahrain".
    groups: dict[tuple[str, str], dict] = {}
    for e in json.loads(text or "[]"):
        state = {"2": DEGRADED, "3": MAJOR}.get(str(e.get("status")))
        if state is None:
            continue  # 0 resolved, 1 informational
        g = groups.setdefault(
            (e.get("service_name") or "", e.get("summary") or ""), {"state": state, "regions": [], "started": None}
        )
        if RANK[state] > RANK[g["state"]]:
            g["state"] = state
        if e.get("region_name") and e["region_name"] not in g["regions"]:
            g["regions"].append(e["region_name"])
        started = _ts(e.get("date"))
        if started and (g["started"] is None or started < g["started"]):
            g["started"] = started
    readings = [
        Reading(g["state"], " · ".join(p for p in (name, summary, ", ".join(g["regions"])) if p), svc.page, g["started"])
        for (name, summary), g in groups.items()
    ]
    return _worst(readings)


_OUTAGE_WORDS = re.compile(r"\b(outage|unavailable|down)\b", re.I)


def parse_rss_incidents(raw: bytes, svc: Service) -> Reading:
    readings = []
    for entry in feedparser.parse(raw).entries:
        title = (entry.get("title") or "").strip()
        # The M365 admin center feed keeps one standing item marked <status>Available</status>.
        if not title or (entry.get("status") or "").strip().lower() in ("available", "operational", "resolved"):
            continue
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        started = datetime(*t[:6], tzinfo=UTC) if t else None
        state = MAJOR if _OUTAGE_WORDS.search(title) else DEGRADED
        readings.append(Reading(state, title, entry.get("link") or svc.page, started))
    return _worst(readings)


def parse_m365(data: list, svc: Service) -> Reading:
    readings = []
    for post in data or []:
        status = (post.get("Status") or "").lower()
        if not status or status == "operational":
            continue
        state = MAJOR if "interruption" in status or "outage" in status else DEGRADED
        title = post.get("Title") or f"{post.get('ServiceDisplayName')}: {post.get('Status')}"
        readings.append(Reading(state, title, svc.page, _ts(post.get("LastUpdatedTime"))))
    return _worst(readings)


def parse_google(data: list, svc: Service, base: str) -> Reading:
    readings = []
    for inc in data or []:
        if inc.get("end"):
            continue
        impact = inc.get("status_impact")
        if impact == "SERVICE_OUTAGE":
            state = MAJOR
        elif impact == "SERVICE_DISRUPTION":
            state = DEGRADED
        else:
            continue
        title = (inc.get("external_desc") or inc.get("service_name") or "").strip()
        url = f"{base}/{inc['uri']}" if inc.get("uri") else svc.page
        readings.append(Reading(state, title, url, _ts(inc.get("begin"))))
    return _worst(readings)


def parse_slack(data: dict, svc: Service) -> Reading:
    readings = []
    for inc in data.get("active_incidents") or []:
        kind = inc.get("type")
        if kind == "notice":
            continue
        state = MAJOR if kind == "outage" else DEGRADED
        readings.append(Reading(state, inc.get("title"), inc.get("url") or svc.page, _ts(inc.get("date_created"))))
    return _worst(readings)


def parse_statusio(data: dict, svc: Service) -> Reading:
    result = data.get("result") or {}
    code = int((result.get("status_overall") or {}).get("status_code") or 100)
    incidents = result.get("incidents") or []
    title = incidents[0].get("name") if incidents else (result.get("status_overall") or {}).get("status")
    started = _ts(incidents[0].get("datetime_open")) if incidents else None
    if code >= 400:
        return Reading(MAJOR, title, svc.page, started)
    if code >= 300:
        return Reading(DEGRADED, title, svc.page, started)
    return Reading(OPERATIONAL)


_OKTA_RECORD = re.compile(r'\{"attributes":\{"type":"Incident__c"')


def parse_okta(html: str, svc: Service) -> Reading:
    readings = []
    for m in _OKTA_RECORD.finditer(html):
        record = _balanced_json(html, m.start())
        if not record or (record.get("Status__c") or "").lower() == "resolved":
            continue
        category = record.get("Category__c") or ""
        state = MAJOR if "Service Disruption" in category and "Minor" not in category else DEGRADED
        readings.append(Reading(state, record.get("Incident_Title__c"), svc.page, _ts(record.get("Start_Time__c"))))
    return _worst(readings)


def _balanced_json(text: str, start: int) -> dict | None:
    depth, in_str, escape = 0, False, False
    for j in range(start, min(len(text), start + 200_000)):
        c = text[j]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : j + 1])
                except ValueError:
                    return None
    return None


# ---------------------------------------------------------------- fetching


async def read(client: httpx.AsyncClient, svc: Service) -> Reading:
    r = await client.get(svc.source)
    r.raise_for_status()
    match svc.kind:
        case "statuspage":
            return parse_statuspage(r.json(), svc)
        case "aws":
            return parse_aws(r.content, svc)
        case "azure":
            return parse_rss_incidents(r.content, svc)
        case "m365":
            posts = parse_m365(r.json(), svc)
            try:
                admin = await client.get(M365_ADMIN_RSS)
                admin.raise_for_status()
                return _worst([posts, parse_rss_incidents(admin.content, svc)])
            except httpx.HTTPError:
                return posts
        case "google":
            return parse_google(r.json(), svc, svc.source.rsplit("/", 1)[0])
        case "slack":
            return parse_slack(r.json(), svc)
        case "statusio":
            return parse_statusio(r.json(), svc)
        case "okta":
            return parse_okta(r.text, svc)
    raise ValueError(f"unknown kind {svc.kind}")


def _hour(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


async def store(session: AsyncSession, svc: Service, reading: Reading | None, error: str | None, now: datetime) -> None:
    row = await session.get(ServiceStatus, svc.slug)
    if row is None:
        row = ServiceStatus(slug=svc.slug)
        session.add(row)
    state = reading.state if reading else UNKNOWN
    # A failed read keeps the last known state for up to 15 minutes before turning unknown.
    if reading is None and row.checked_at and now - row.checked_at < timedelta(minutes=15):
        row.error = error
        return
    if row.state != state:
        row.changed_at = now
    row.state = state
    row.incident_title = reading.title if reading and state in (DEGRADED, MAJOR) else None
    row.incident_url = reading.url if reading and state in (DEGRADED, MAJOR) else None
    row.incident_started_at = reading.started_at if reading and state in (DEGRADED, MAJOR) else None
    row.error = error
    if reading is not None:
        row.checked_at = now

    hour = _hour(now)
    existing = await session.get(ServiceHour, (svc.slug, hour))
    if existing is None:
        await session.execute(insert(ServiceHour).values(slug=svc.slug, hour=hour, worst=state).on_conflict_do_nothing())
    elif RANK[state] > RANK[existing.worst]:
        existing.worst = state


async def poll() -> None:
    now = datetime.now(UTC)
    async with httpx.AsyncClient(
        timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:

        async def one(svc: Service) -> tuple[Service, Reading | None, str | None]:
            try:
                return svc, await read(client, svc), None
            except Exception as e:  # any bad page is that service's problem only
                return svc, None, f"{type(e).__name__}: {e}"[:300]

        results = await asyncio.gather(*(one(s) for s in SERVICES))

    async with SessionLocal() as session:
        for svc, reading, error in results:
            if error:
                log.info("services: %s failed: %s", svc.slug, error)
            await store(session, svc, reading, error, now)
        await session.execute(delete(ServiceHour).where(ServiceHour.hour < _hour(now) - HISTORY))
        await session.commit()
    impacted = [f"{s.slug}={r.state}" for s, r, _ in results if r and r.state != OPERATIONAL]
    log.info("services: polled %d, %s", len(results), ", ".join(impacted) or "all operational")


def schedule(scheduler) -> None:
    scheduler.add_job(
        poll, "interval", minutes=POLL_MINUTES, id=JOB_ID,
        next_run_time=datetime.now(UTC) + timedelta(seconds=10), max_instances=1, coalesce=True,
    )
