from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import ServiceHour, ServiceStatus
from app.services import BY_SLUG, DEFAULTS, GROUPS, SERVICES, UNKNOWN

router = APIRouter(tags=["services"])


class Incident(BaseModel):
    title: str | None
    url: str | None
    started_at: datetime | None


class StaleEvent(BaseModel):
    state: str
    title: str | None
    url: str | None
    started_at: datetime | None
    updated_at: datetime | None


class ServiceOut(BaseModel):
    slug: str
    name: str
    group: str
    page: str
    state: str  # operational | degraded | major | unknown
    incident: Incident | None
    checked_at: datetime | None
    changed_at: datetime | None
    hours: list[str]  # 24 UTC hours, oldest first, ending with the current hour; unknown = no data
    stale: list[StaleEvent]  # open events with no vendor update in 72h; never counted in state


class ServicesOut(BaseModel):
    services: list[ServiceOut]
    defaults: list[str]
    groups: list[str]


@router.get("/services", response_model=ServicesOut)
async def services(
    slugs: str | None = Query(None, max_length=1000, description="comma-separated service slugs; 'all' for every one"),
    session: AsyncSession = Depends(get_session),
) -> ServicesOut:
    if slugs == "all":
        wanted = [s.slug for s in SERVICES]
    else:
        wanted = [s for s in (x.strip().lower() for x in (slugs or "").split(",")) if s in BY_SLUG] or DEFAULTS
    now = datetime.now(UTC)
    current = now.replace(minute=0, second=0, microsecond=0)
    hours = [current - timedelta(hours=23 - i) for i in range(24)]

    rows = {r.slug: r for r in (await session.scalars(select(ServiceStatus).where(ServiceStatus.slug.in_(wanted)))).all()}
    history: dict[str, dict[datetime, str]] = {}
    for h in (await session.scalars(select(ServiceHour).where(ServiceHour.slug.in_(wanted), ServiceHour.hour >= hours[0]))).all():
        history.setdefault(h.slug, {})[h.hour] = h.worst

    out = []
    for slug in wanted:
        svc, row = BY_SLUG[slug], rows.get(slug)
        state = row.state if row else UNKNOWN
        out.append(
            ServiceOut(
                slug=slug, name=svc.name, group=svc.group, page=svc.page, state=state,
                incident=Incident(title=row.incident_title, url=row.incident_url or svc.page, started_at=row.incident_started_at)
                if row and row.incident_title
                else None,
                checked_at=row.checked_at if row else None,
                changed_at=row.changed_at if row else None,
                hours=[history.get(slug, {}).get(h, UNKNOWN) for h in hours],
                stale=[StaleEvent(**e) for e in (row.stale or [])] if row else [],
            )
        )
    return ServicesOut(services=out, defaults=DEFAULTS, groups=GROUPS)
