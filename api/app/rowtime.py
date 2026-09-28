"""A row's time: the earliest publish time among its news sources (the articles in its cluster),
never a CVE, KEV or NVD date. It sorts the wire, groups it by day and drives the age column.

It moves back only when a news source genuinely published earlier, and every change is logged
with the old time, the new time and the reason. Escalations (became KEV, Critical, exploited)
still reach viewers as new through items.changed_at; they never rewrite the row's time.
"""

import logging
from collections.abc import Iterable
from datetime import datetime

log = logging.getLogger(__name__)

PUBLISHED = "published"


def news_time(published: Iterable[datetime | None]) -> datetime | None:
    """The earliest of the news sources' publish times (None when none has one)."""
    times = [t for t in published if t is not None]
    return min(times) if times else None


def after_source_joins(current: datetime | None, source_published: datetime | None) -> datetime | None:
    """The row time once a news source published at `source_published` joins the row: earlier
    only if that source genuinely published earlier, otherwise unchanged."""
    if source_published is None:
        return current
    if current is None or source_published < current:
        return source_published
    return current


def set_row_time(item, new: datetime | None, reason: str) -> bool:
    """Apply a row time (and the "published" kind), logging old -> new with the reason.
    Returns whether anything changed."""
    old, old_kind = item.last_event_at, item.last_event_kind
    if new is None or (new == old and old_kind == PUBLISHED):
        return False
    log.info(
        "row time: item %s %s -> %s (%s)",
        getattr(item, "id", None),
        old.isoformat() if old else None,
        new.isoformat(),
        reason if old_kind in (None, PUBLISHED) else f"{reason}; was a {old_kind} time",
    )
    item.last_event_at, item.last_event_kind = new, PUBLISHED
    return True
