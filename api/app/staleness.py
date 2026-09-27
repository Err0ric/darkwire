"""Old CVEs: published more than 90 days ago, not in KEV, and no headline in the row is
about exploitation (items.exploitation).

Such rows still show, but their score, bar and badge are dimmed and they do not count
toward severity totals or pinning. Computed at query time, since rows age into it.
"""

from datetime import datetime, timedelta

from sqlalchemy import exists, or_, select

from app.models import Cve, Item

MAX_AGE = timedelta(days=90)


def is_stale(item: Item, now: datetime) -> bool:
    cve = item.cve
    if cve is None or cve.published_at is None or cve.published_at >= now - MAX_AGE:
        return False
    return not (cve.kev or item.kev or item.exploited or item.exploitation)


def not_stale(now: datetime):
    """SQL condition on Item: the row is not stale."""
    return or_(
        Item.kev.is_(True),
        Item.exploited.is_(True),
        Item.exploitation.is_(True),
        ~exists(
            select(Cve.id).where(Cve.id == Item.cve_id, Cve.published_at < now - MAX_AGE, Cve.kev.is_not(True))
        ),
    )
