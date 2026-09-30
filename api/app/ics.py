"""CISA ICS advisory rows: the fallback summary built from stored fields. The model summarizes
them like any row (app/summaries.py); this template is used when its summary fails a check
(version consistency included), or with no model key.

CISA's ICS advisory titles are the vendor and product ("Siemens Mendix Runtime (Update A)"), and
the rest comes from the row's own data: how many CVEs it holds (item_cves), the highest CVSS and
its severity (items.cvss / items.severity, rolled up from NVD), and the fix status
(items.patch_status). Nothing missing is ever written out: no score, no count, no "unverified".

    python -m app.ics            # dry run: ICS rows with no summary (or ours), stored and new summary
    python -m app.ics --apply    # writes; never against production without sign-off

Each enrich pass refreshes the rows this module wrote (they start with PREFIX) when a score or
fix status changes, and with no model key fills ICS rows with no summary yet. Rows the model summarized before this module
keep their summary. Rows it declined ("") are rewritten once per BACKFILL_VERSION (set only with
sign-off); the dry run lists exactly those.
Uses DATABASE_URL like the app.
"""

import asyncio
import logging
import re
import sys

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import jobstate
from app.config import get_settings
from app.models import Item, ItemCve, PatchStatus, Severity, Stream

log = logging.getLogger(__name__)

PREFIX = "CISA industrial control systems advisory for "
BACKFILL_STATE = "ics_backfill"
BACKFILL_VERSION = "1"  # 2026-09-30, signed off: the 9 declined rows (81, 96-103). Empty: off.

# icsa-26-272-01 (ICS) and icsma-26-...(medical); not CISA's other pages under /ics-advisories.
_ICS_URL = re.compile(r"cisa\.gov/.*/ics-(?:medical-)?advisories/icsm?a-\d", re.I)
_ICS_SQL = r"cisa\.gov/.*/ics-(medical-)?advisories/icsm?a-[0-9]"
_UPDATE = re.compile(r"\s*\(Update ([A-Z])\)\s*$")

_FIX = {
    PatchStatus.patched: "Vendor data lists a fix.",
    PatchStatus.no_fix: "Vendor data lists no fix yet.",
    PatchStatus.workaround: "Vendor data lists a workaround but no fix yet.",
}


def is_ics_advisory(url: str | None) -> bool:
    return bool(url and _ICS_URL.search(url))


def ics_sql():
    """SQL condition: the row is a CISA ICS advisory (its primary source is the advisory)."""
    return Item.primary_url.regexp_match(_ICS_SQL, "i")


def ics_summary(
    headline: str, cve_count: int, cvss: float | None, severity: Severity | str | None, patch: PatchStatus | str | None
) -> str:
    """Two short sentences at most, from stored fields only."""
    m = _UPDATE.search(headline)
    subject = _UPDATE.sub("", headline).strip()
    update = f" (update {m.group(1)})" if m else ""

    sev = Severity(severity) if severity else None
    rated = f"CVSS {cvss:.1f}" if cvss is not None else ""
    if rated and sev and sev != Severity.none:
        rated += f" ({sev.value.capitalize()})"
    if cve_count == 1:
        covering = f"1 CVE rated {rated}" if rated else "1 CVE"
    elif cve_count > 1:
        covering = f"{cve_count} CVEs, the highest rated {rated}" if rated else f"{cve_count} CVEs"
    else:
        covering = ""
    first = f"{PREFIX}{subject}{update}" + (f", covering {covering}." if covering else ".")

    fix = _FIX.get(PatchStatus(patch)) if patch else None
    return f"{first} {fix}" if fix else first


async def _rows(session: AsyncSession, backfill: bool, fill_new: bool = True) -> list[tuple[Item, int]]:
    counts = (
        select(ItemCve.item_id, func.count().label("n")).group_by(ItemCve.item_id).subquery()
    )
    stmt = (
        select(Item, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.item_id == Item.id)
        .where(Item.stream == Stream.main, ics_sql())
        .order_by(Item.id)
    )
    # Never a model-written summary; declined ("") rows only in a backfill.
    no_summary = or_(Item.summary.is_(None), Item.summary == "") if backfill else Item.summary.is_(None)
    ours = Item.summary.startswith(PREFIX, autoescape=True)
    stmt = stmt.where(or_(no_summary, ours) if fill_new or backfill else ours)
    return list((await session.execute(stmt)).all())


async def summarize(session: AsyncSession) -> int:
    """Fill or refresh ICS advisory summaries; once per BACKFILL_VERSION, also the declined ones.
    Returns how many summaries changed."""
    backfill = bool(BACKFILL_VERSION) and await jobstate.get(session, BACKFILL_STATE) != BACKFILL_VERSION
    changed = 0
    # With a model key, rows with no summary go to the model first (app/summaries.py).
    for item, n in await _rows(session, backfill, fill_new=not get_settings().anthropic_api_key):
        text = ics_summary(item.headline, n, float(item.cvss) if item.cvss is not None else None, item.severity, item.patch_status)
        if item.summary != text:
            if backfill:
                log.info("ics: backfill item %d: %r -> %r", item.id, item.summary, text)
            item.summary = text
            changed += 1
    if backfill:
        await jobstate.put(session, BACKFILL_STATE, BACKFILL_VERSION)
        log.info("ics: backfill v%s rewrote %d rows", BACKFILL_VERSION, changed)
    await session.commit()
    return changed


async def main(apply: bool) -> None:
    from app.db import SessionLocal

    async with SessionLocal() as session:
        rows = await _rows(session, backfill=True)
        for item, n in rows:
            text = ics_summary(item.headline, n, float(item.cvss) if item.cvss is not None else None, item.severity, item.patch_status)
            mark = "  " if item.summary == text else "->"
            print(f"row {item.id}  {n} CVE  |  {item.headline}\n   was: {item.summary!r}\n   {mark}  {text}")
            if apply:
                item.summary = text
        print(f"\n{len(rows)} ICS advisory rows" + ("; written" if apply else "; dry run, nothing written"))
        if apply:
            await session.commit()


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
