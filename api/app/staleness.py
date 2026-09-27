"""Old CVEs: published more than 90 days ago and not added to KEV in the last 14 days.

Such rows still show, but their score, bar and badge are dimmed and they do not count
toward severity totals or pinning. Computed at query time, since rows age into it.
"""

from datetime import datetime, timedelta

from sqlalchemy import exists, or_, select

from app.models import Cve, Item

MAX_AGE = timedelta(days=90)
KEV_RECENT = timedelta(days=14)


def is_stale(cve: Cve | None, now: datetime) -> bool:
    if cve is None or cve.published_at is None or cve.published_at >= now - MAX_AGE:
        return False
    return not (cve.kev_added_at and cve.kev_added_at >= now - KEV_RECENT)


def not_stale(now: datetime):
    """SQL condition on Item: the row's CVE (if any) is not stale."""
    return ~exists(
        select(Cve.id).where(
            Cve.id == Item.cve_id,
            Cve.published_at < now - MAX_AGE,
            or_(Cve.kev_added_at.is_(None), Cve.kev_added_at < now - KEV_RECENT),
        )
    )
