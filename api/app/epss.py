"""FIRST EPSS scores for CVEs on the board, batched, refreshed daily."""

import logging
from datetime import UTC, datetime, timedelta
from itertools import batched

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cve, ItemCve

log = logging.getLogger(__name__)

API = "https://api.first.org/data/v1/epss"
BATCH = 100
EVERY = timedelta(hours=24)


async def refresh(session: AsyncSession, client: httpx.AsyncClient) -> int:
    """Score CVEs never scored or scored more than a day ago. Returns CVEs checked."""
    now = datetime.now(UTC)
    due = (
        await session.scalars(
            select(Cve.id)
            .where(Cve.id.in_(select(ItemCve.cve_id)))
            .where(or_(Cve.epss_updated_at.is_(None), Cve.epss_updated_at < now - EVERY))
        )
    ).all()
    checked = 0
    for chunk in batched(due, BATCH):
        try:
            r = await client.get(API, params={"cve": ",".join(chunk)}, timeout=60)
            r.raise_for_status()
            scores = {d["cve"].upper(): d for d in r.json().get("data") or []}
        except (httpx.HTTPError, ValueError) as e:
            log.warning("epss: batch failed: %s", e)
            continue
        for cve_id in chunk:
            d = scores.get(cve_id)
            # CVEs FIRST has not scored yet are marked checked too, and retried tomorrow.
            await session.execute(
                update(Cve)
                .where(Cve.id == cve_id)
                .values(
                    epss=float(d["epss"]) if d else None,
                    epss_percentile=float(d["percentile"]) if d else None,
                    epss_updated_at=now,
                )
            )
        checked += len(chunk)
        await session.commit()
    return checked
