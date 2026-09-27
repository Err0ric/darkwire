"""Tiny key/value store for scheduled jobs (last KEV fetch, NVD change window, ...)."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobState


async def get(session: AsyncSession, name: str) -> str | None:
    return await session.scalar(select(JobState.value).where(JobState.name == name))


async def get_time(session: AsyncSession, name: str) -> datetime | None:
    value = await get(session, name)
    return datetime.fromisoformat(value) if value else None


async def put(session: AsyncSession, name: str, value: str | datetime | None) -> None:
    text = value.isoformat() if isinstance(value, datetime) else value
    stmt = insert(JobState).values(name=name, value=text)
    await session.execute(
        stmt.on_conflict_do_update(index_elements=["name"], set_={"value": text, "updated_at": func.now()})
    )
