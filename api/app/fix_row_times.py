"""One-off: put every main row's time on its earliest news source (app/rowtime.py), replacing
older KEV / score-change times and any other drift.

    python -m app.fix_row_times            # dry run: one line per row that would change
    python -m app.fix_row_times --apply    # writes, logging every change (old, new, reason)
    python -m app.fix_row_times --rows 79 [--apply]   # only these row ids (comma-separated)

Uses DATABASE_URL like the app. Never run --apply against production without sign-off.
"""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import dedupe, rowtime
from app.db import SessionLocal
from app.models import Item, Stream


def planned(items) -> list[tuple[object, object, object, str]]:
    """(item, old time, new time, old kind) for every row whose time is not its earliest news
    source. Pure, so it can be tested without a database."""
    out = []
    for item in items:
        new = rowtime.news_time(s.published_at for s in dedupe.time_sources(item.sources))
        if new is None:
            continue  # no dated news source: nothing better to say
        if new != item.last_event_at or item.last_event_kind != rowtime.PUBLISHED:
            out.append((item, item.last_event_at, new, item.last_event_kind))
    return out


async def main(apply: bool, rows: list[int] | None = None) -> None:
    async with SessionLocal() as session:
        query = select(Item).where(Item.stream == Stream.main).options(selectinload(Item.sources))
        if rows:
            query = query.where(Item.id.in_(rows))
        items = (await session.scalars(query)).all()
        changes = planned(items)
        print(f"{'applying' if apply else 'dry run'}: {len(changes)} of {len(items)} rows change")
        for item, old, new, kind in changes:
            print(f"  row {item.id}  {old.isoformat() if old else None} ({kind})  ->  {new.isoformat()}  |  {item.headline[:70]}")
            if apply:
                rowtime.set_row_time(item, new, "one-off fix: earliest news source")
        if apply:
            await session.commit()


def parse_rows(argv: list[str]) -> list[int] | None:
    """The ids after --rows ("79" or "79,93"), else None for every row."""
    if "--rows" not in argv:
        return None
    i = argv.index("--rows")
    if i + 1 >= len(argv):
        raise SystemExit("--rows needs ids, e.g. --rows 79")
    return [int(x) for x in argv[i + 1].split(",") if x.strip()]


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv, parse_rows(sys.argv)))
