"""Board events for the landing's activity log (models.BoardEvent, GET /activity).

record() adds one to the caller's session; it is committed with the caller's own changes, so
an event exists only when what it describes does. Kept KEEP days (prune(), run by ingest)."""

from datetime import UTC, datetime, time, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BoardEvent, Cve, ItemSource, KevEntry, ServiceIncident, Source, Stream

KEEP = timedelta(days=7)
KINDS = ("ingest", "kev", "nvd", "cluster", "services", "summary")


def scored(values: dict) -> str:
    """An nvd event's detail: "scored 9.8 critical"."""
    severity = values.get("base_severity")
    severity = str(getattr(severity, "value", severity) or "").lower()
    return f"scored {values['base_score']}" + (f" {severity}" if severity and severity != "none" else "")


def record(session: AsyncSession, kind: str, subject: str, detail: str, item_id: int | None = None) -> None:
    assert kind in KINDS, kind
    session.add(BoardEvent(kind=kind, subject=subject[:300], detail=detail[:120], item_id=item_id))


async def prune(session: AsyncSession, now: datetime) -> int:
    result = await session.execute(delete(BoardEvent).where(BoardEvent.at < now - KEEP))
    return result.rowcount or 0


async def derived_events(session: AsyncSession, since: datetime, now: datetime) -> list[dict]:
    """Board events rebuilt from the data itself, for the window since..now, so the landing's
    log has real lines before (or without) recorded ones: ingest (a main feed's articles per
    ingest batch, from item_sources.fetched_at), kev (CISA catalog entries by dateAdded, at the
    start of that UTC day), nvd (scored CVEs on the board, at NVD's lastModified), services
    (incident starts and ends). Dicts with at, kind, subject, detail, item_id."""
    from app.services import BY_SLUG  # here: services records events itself (circular import)

    out: list[dict] = []

    batch = func.date_trunc("minute", ItemSource.fetched_at)
    for name, n, at in (
        await session.execute(
            select(Source.name, func.count(), func.max(ItemSource.fetched_at))
            .join(Source, Source.id == ItemSource.source_id)
            .where(Source.stream == Stream.main, ItemSource.fetched_at >= since)
            .group_by(Source.name, batch)
        )
    ).all():
        out.append({"at": at, "kind": "ingest", "subject": name, "detail": f"+{n} {'item' if n == 1 else 'items'}", "item_id": None})

    for cve_id, added in (
        await session.execute(select(KevEntry.cve_id, KevEntry.date_added).where(KevEntry.date_added >= since.date()))
    ).all():
        at = datetime.combine(added, time.min, tzinfo=UTC)
        if since <= at <= now:
            out.append({"at": at, "kind": "kev", "subject": cve_id, "detail": "added", "item_id": None})

    for cve in (
        await session.scalars(select(Cve).where(Cve.base_score.is_not(None), Cve.last_modified_at >= since, Cve.last_modified_at <= now))
    ).all():
        detail = scored({"base_score": cve.base_score, "base_severity": cve.base_severity})
        out.append({"at": cve.last_modified_at, "kind": "nvd", "subject": cve.id, "detail": detail, "item_id": None})

    for inc in (
        await session.scalars(
            select(ServiceIncident).where(or_(ServiceIncident.started_at >= since, ServiceIncident.ended_at >= since))
        )
    ).all():
        svc = BY_SLUG.get(inc.slug)
        if svc is None:
            continue
        if inc.started_at and since <= inc.started_at <= now:
            word = "major outage" if inc.state == "major" else "degraded"
            out.append({"at": inc.started_at, "kind": "services", "subject": svc.name, "detail": word, "item_id": None})
        if inc.ended_at and since <= inc.ended_at <= now:
            out.append({"at": inc.ended_at, "kind": "services", "subject": svc.name, "detail": "operational", "item_id": None})
    return out
