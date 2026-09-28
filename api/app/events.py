"""Board events for the landing's activity log (models.BoardEvent, GET /activity).

record() adds one to the caller's session; it is committed with the caller's own changes, so
an event exists only when what it describes does. Kept KEEP days (prune(), run by ingest)."""

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BoardEvent

KEEP = timedelta(days=7)
KINDS = ("ingest", "kev", "nvd", "cluster", "services", "summary")


def record(session: AsyncSession, kind: str, subject: str, detail: str, item_id: int | None = None) -> None:
    assert kind in KINDS, kind
    session.add(BoardEvent(kind=kind, subject=subject[:300], detail=detail[:120], item_id=item_id))


async def prune(session: AsyncSession, now: datetime) -> int:
    result = await session.execute(delete(BoardEvent).where(BoardEvent.at < now - KEEP))
    return result.rowcount or 0
