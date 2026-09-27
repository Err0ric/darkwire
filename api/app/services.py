"""Third-party service status for the rail's Services block and /outages.

Every POLL_MINUTES each service's official status source is fetched and reduced to one state:
operational, degraded (amber), major (red), or unknown (the source failed or was never read),
plus the current incident's title, link and start. The worst state per UTC hour is kept for
24 hours for the /outages strip.

An open event the vendor has not updated in 72 hours is stale: it is stored and listed on
/outages under "Stale", but never counts toward the state, the rail, the unseen indicator or
the home status line (AWS's long-running Middle East region events, for one).

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

import ast
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

from app import jobstate
from app.db import SessionLocal
from app.models import ServiceHour, ServiceIncident, ServiceStatus

log = logging.getLogger(__name__)

JOB_ID = "services"
POLL_MINUTES = 3
HISTORY = timedelta(hours=24)
INCIDENT_KEEP = timedelta(days=8)  # the /services panel shows 7 days
INCIDENT_HISTORY_EVERY = timedelta(hours=1)  # Statuspage incident history backfill
# An open event the vendor has not updated in this long is stale: listed, never counted.
STALE_AFTER = timedelta(hours=72)
TIMEOUT = 20.0
USER_AGENT = "darkwire/0.1 (+https://darkwire.tech)"

OPERATIONAL, DEGRADED, MAJOR, UNKNOWN = "operational", "degraded", "major", "unknown"
RANK = {UNKNOWN: 0, OPERATIONAL: 1, DEGRADED: 2, MAJOR: 3}


@dataclass
class Reading:
    """One open event (or a page-level rollup) on a status source."""

    state: str
    title: str | None = None
    url: str | None = None
    started_at: datetime | None = None
    # Last time the vendor updated it. None for page-level rollups: always current.
    updated_at: datetime | None = None


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


def split(readings: list[Reading], now: datetime) -> tuple[Reading, list[Reading]]:
    """(the service's current reading, stale events). An event the vendor has not updated in
    STALE_AFTER is set aside: it does not count toward the state, the rail, the unseen
    indicator or the home status line, and /outages lists it under Stale."""
    current = [r for r in readings if r.updated_at is None or now - r.updated_at <= STALE_AFTER]
    stale = [r for r in readings if r.updated_at is not None and now - r.updated_at > STALE_AFTER]
    return _worst(current), sorted(stale, key=lambda r: r.updated_at or now, reverse=True)


# ---------------------------------------------------------------- parsers (one per kind)
# Each returns every open event with its last update; split() decides what counts.


def parse_statuspage(data: dict, svc: Service) -> list[Reading]:
    """Operational when the page's own rollup (status.indicator) says so, whatever incidents
    are open; an incident the vendor rates impact "none" is never an outage. Otherwise one
    reading per open incident, or the rollup itself when no incident explains it."""
    status = data.get("status") or {}
    rollup = {"major": MAJOR, "critical": MAJOR, "minor": DEGRADED}.get(status.get("indicator"))
    if rollup is None:
        return []
    impact = {"critical": MAJOR, "major": MAJOR, "minor": DEGRADED}
    readings = [
        Reading(
            impact[i["impact"]], i.get("name"), i.get("shortlink") or svc.page,
            _ts(i.get("created_at")), _ts(i.get("updated_at")) or _ts(i.get("created_at")),
        )
        for i in data.get("incidents") or []
        if i.get("status") not in ("resolved", "postmortem") and i.get("impact") in impact
    ]
    return readings or [Reading(rollup, status.get("description"), svc.page)]


def parse_aws(raw: bytes, svc: Service) -> list[Reading]:
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    # One reading per (service, summary), naming every region it covers:
    # "Multiple services · Region Availability · UAE, Bahrain".
    groups: dict[tuple[str, str], dict] = {}
    for e in json.loads(text or "[]"):
        state = {"2": DEGRADED, "3": MAJOR}.get(str(e.get("status")))
        if state is None:
            continue  # 0 resolved, 1 informational
        g = groups.setdefault(
            (e.get("service_name") or "", e.get("summary") or ""),
            {"state": state, "regions": [], "started": None, "updated": None},
        )
        if RANK[state] > RANK[g["state"]]:
            g["state"] = state
        if e.get("region_name") and e["region_name"] not in g["regions"]:
            g["regions"].append(e["region_name"])
        started = _ts(e.get("date"))
        if started and (g["started"] is None or started < g["started"]):
            g["started"] = started
        log_ = e.get("event_log") or []
        if isinstance(log_, str):
            try:
                log_ = ast.literal_eval(log_)
            except (ValueError, SyntaxError):
                log_ = []
        stamps = [t for t in (_ts(x.get("timestamp")) for x in log_ if isinstance(x, dict)) if t] or [started]
        latest = max((t for t in stamps if t), default=None)
        if latest and (g["updated"] is None or latest > g["updated"]):
            g["updated"] = latest
    return [
        Reading(
            g["state"], " · ".join(p for p in (name, summary, ", ".join(g["regions"])) if p),
            svc.page, g["started"], g["updated"],
        )
        for (name, summary), g in groups.items()
    ]


_OUTAGE_WORDS = re.compile(r"\b(outage|unavailable|down)\b", re.I)


def parse_rss_incidents(raw: bytes, svc: Service) -> list[Reading]:
    readings = []
    for entry in feedparser.parse(raw).entries:
        title = (entry.get("title") or "").strip()
        # The M365 admin center feed keeps one standing item marked <status>Available</status>.
        if not title or (entry.get("status") or "").strip().lower() in ("available", "operational", "resolved"):
            continue
        p = entry.get("published_parsed")
        u = entry.get("updated_parsed") or p
        started = datetime(*p[:6], tzinfo=UTC) if p else None
        updated = datetime(*u[:6], tzinfo=UTC) if u else None
        state = MAJOR if _OUTAGE_WORDS.search(title) else DEGRADED
        readings.append(Reading(state, title, entry.get("link") or svc.page, started, updated))
    return readings


def parse_m365(data: list, svc: Service) -> list[Reading]:
    readings = []
    for post in data or []:
        status = (post.get("Status") or "").lower()
        if not status or status == "operational":
            continue
        state = MAJOR if "interruption" in status or "outage" in status else DEGRADED
        title = post.get("Title") or f"{post.get('ServiceDisplayName')}: {post.get('Status')}"
        updated = _ts(post.get("LastUpdatedTime"))
        readings.append(Reading(state, title, svc.page, updated, updated))
    return readings


def parse_google(data: list, svc: Service, base: str) -> list[Reading]:
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
        readings.append(Reading(state, title, url, _ts(inc.get("begin")), _ts(inc.get("modified")) or _ts(inc.get("begin"))))
    return readings


def parse_slack(data: dict, svc: Service) -> list[Reading]:
    readings = []
    for inc in data.get("active_incidents") or []:
        kind = inc.get("type")
        if kind == "notice":
            continue
        state = MAJOR if kind == "outage" else DEGRADED
        readings.append(Reading(
            state, inc.get("title"), inc.get("url") or svc.page,
            _ts(inc.get("date_created")), _ts(inc.get("date_updated")) or _ts(inc.get("date_created")),
        ))
    return readings


def parse_statusio(data: dict, svc: Service) -> list[Reading]:
    result = data.get("result") or {}
    overall = result.get("status_overall") or {}
    code = int(overall.get("status_code") or 100)
    if code < 300:
        return []
    incidents = result.get("incidents") or []
    title = incidents[0].get("name") if incidents else overall.get("status")
    started = _ts(incidents[0].get("datetime_open")) if incidents else None
    return [Reading(MAJOR if code >= 400 else DEGRADED, title, svc.page, started, _ts(overall.get("updated")))]


_OKTA_RECORD = re.compile(r'\{"attributes":\{"type":"Incident__c"')


def parse_okta(html: str, svc: Service) -> list[Reading]:
    readings = []
    for m in _OKTA_RECORD.finditer(html):
        record = _balanced_json(html, m.start())
        if not record or (record.get("Status__c") or "").lower() == "resolved":
            continue
        category = record.get("Category__c") or ""
        state = MAJOR if "Service Disruption" in category and "Minor" not in category else DEGRADED
        started = _ts(record.get("Start_Time__c"))
        readings.append(Reading(state, record.get("Incident_Title__c"), svc.page, started,
                                _ts(record.get("Last_Updated__c")) or started))
    return readings


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


async def read(client: httpx.AsyncClient, svc: Service) -> list[Reading]:
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
                return posts + parse_rss_incidents(admin.content, svc)
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


async def store(
    session: AsyncSession, svc: Service, readings: list[Reading] | None, error: str | None, now: datetime
) -> None:
    row = await session.get(ServiceStatus, svc.slug)
    if row is None:
        row = ServiceStatus(slug=svc.slug)
        session.add(row)
    reading, stale = split(readings, now) if readings is not None else (None, [])
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
        row.stale = [
            {
                "state": r.state, "title": r.title, "url": r.url,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in stale
        ]

    hour = _hour(now)
    existing = await session.get(ServiceHour, (svc.slug, hour))
    if existing is None:
        await session.execute(insert(ServiceHour).values(slug=svc.slug, hour=hour, worst=state).on_conflict_do_nothing())
    elif RANK[state] > RANK[existing.worst]:
        existing.worst = state


async def record_incidents(session: AsyncSession, svc: Service, readings: list[Reading] | None, now: datetime) -> None:
    """Keep each open incident (a titled degraded / major reading that is not stale) in
    service_incidents; one that is no longer open gets ended_at. Skipped when the read failed."""
    if readings is None:
        return
    current, _ = split(readings, now)
    open_now = [
        r for r in readings
        if r.title and r.state in (DEGRADED, MAJOR) and (r.updated_at is None or now - r.updated_at <= STALE_AFTER)
    ]
    seen = []
    for r in open_now:
        key = r.url if r.url and r.url != svc.page else f"{r.title}|{r.started_at.isoformat() if r.started_at else ''}"
        if key in seen:
            continue
        seen.append(key)
        existing = await session.scalar(
            select(ServiceIncident).where(ServiceIncident.slug == svc.slug, ServiceIncident.key == key)
        )
        if existing is None:
            session.add(ServiceIncident(
                slug=svc.slug, key=key, title=r.title, state=r.state, url=r.url or svc.page,
                started_at=r.started_at or now, ended_at=None, last_seen_at=now,
            ))
        else:
            existing.title = r.title
            existing.last_seen_at = now
            existing.ended_at = None
            if RANK[r.state] > RANK.get(existing.state, 0):
                existing.state = r.state
    await session.flush()
    stmt = select(ServiceIncident).where(ServiceIncident.slug == svc.slug, ServiceIncident.ended_at.is_(None))
    for inc in (await session.scalars(stmt)).all():
        if inc.key not in seen:
            inc.ended_at = now


async def backfill_statuspage_history(client: httpx.AsyncClient, session: AsyncSession, now: datetime) -> int:
    """Hourly: Statuspage services publish their recent incidents (resolved ones included) at
    /api/v2/incidents.json; import the last 7 days so the panel is not empty on day one."""
    last = await jobstate.get_time(session, "service_history_at")
    if last and now - last < INCIDENT_HISTORY_EVERY:
        return 0
    impact = {"critical": MAJOR, "major": MAJOR, "minor": DEGRADED}
    added = 0
    for svc in (s for s in SERVICES if s.kind == "statuspage"):
        try:
            r = await client.get(svc.source.replace("/summary.json", "/incidents.json"))
            r.raise_for_status()
            incidents = r.json().get("incidents") or []
        except Exception as e:  # one bad page is that service's problem only
            log.info("services: %s history failed: %s", svc.slug, type(e).__name__)
            continue
        for i in incidents:
            started = _ts(i.get("created_at"))
            if not started or now - started > INCIDENT_KEEP or i.get("impact") not in impact:
                continue
            ended = _ts(i.get("resolved_at")) if i.get("status") in ("resolved", "postmortem") else None
            url = i.get("shortlink") or svc.page
            existing = await session.scalar(
                select(ServiceIncident).where(ServiceIncident.slug == svc.slug, ServiceIncident.key == url)
            )
            if existing is None:
                session.add(ServiceIncident(
                    slug=svc.slug, key=url, title=i.get("name"), state=impact[i["impact"]], url=url,
                    started_at=started, ended_at=ended, last_seen_at=now,
                ))
                added += 1
            else:
                existing.title = i.get("name")
                existing.started_at = started
                if ended:
                    existing.ended_at = ended
            await session.flush()
    await jobstate.put(session, "service_history_at", now.isoformat())
    return added


REPAIR_STATE = "service_hours_stale_v1"


async def repair_hours_once(session: AsyncSession) -> None:
    """One time: hours stored before the 72h stale rule were colored by events that were already
    stale. For a service that now reads operational with only stale events open, clear the
    impact from every hour that began 72h or more after the last update of all of them."""
    if await jobstate.get(session, REPAIR_STATE):
        return
    fixed = 0
    for row in (await session.scalars(select(ServiceStatus))).all():
        if row.state != OPERATIONAL or not row.stale:
            continue
        updated = [_ts(e.get("updated_at")) for e in row.stale]
        if any(u is None for u in updated):
            continue
        stale_from = max(updated) + STALE_AFTER
        for h in (
            await session.scalars(
                select(ServiceHour).where(
                    ServiceHour.slug == row.slug, ServiceHour.worst.in_([DEGRADED, MAJOR]), ServiceHour.hour >= _hour(stale_from)
                )
            )
        ).all():
            h.worst = OPERATIONAL
            fixed += 1
    await jobstate.put(session, REPAIR_STATE, datetime.now(UTC).isoformat())
    await session.commit()
    log.info("services: repaired %d hours colored by stale events", fixed)


async def poll() -> None:
    now = datetime.now(UTC)
    async with httpx.AsyncClient(
        timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:

        async def one(svc: Service) -> tuple[Service, list[Reading] | None, str | None]:
            try:
                return svc, await read(client, svc), None
            except Exception as e:  # any bad page is that service's problem only
                return svc, None, f"{type(e).__name__}: {e}"[:300]

        results = await asyncio.gather(*(one(s) for s in SERVICES))

        async with SessionLocal() as session:
            for svc, readings, error in results:
                if error:
                    log.info("services: %s failed: %s", svc.slug, error)
                await store(session, svc, readings, error, now)
                await record_incidents(session, svc, readings, now)
            await session.execute(delete(ServiceHour).where(ServiceHour.hour < _hour(now) - HISTORY))
            await session.execute(delete(ServiceIncident).where(ServiceIncident.last_seen_at < now - INCIDENT_KEEP))
            await session.commit()
            try:
                if added := await backfill_statuspage_history(client, session, now):
                    log.info("services: backfilled %d incidents from Statuspage history", added)
                await session.commit()
            except Exception:
                await session.rollback()
                log.exception("services: incident history backfill failed")
            await repair_hours_once(session)
    impacted = [f"{s.slug}={split(r, now)[0].state}" for s, r, _ in results if r and split(r, now)[0].state != OPERATIONAL]
    log.info("services: polled %d, %s", len(results), ", ".join(impacted) or "all operational")


def schedule(scheduler) -> None:
    scheduler.add_job(
        poll, "interval", minutes=POLL_MINUTES, id=JOB_ID,
        next_run_time=datetime.now(UTC) + timedelta(seconds=10), max_instances=1, coalesce=True,
    )
