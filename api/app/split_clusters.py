"""One-off: split rows that the old clustering rules merged wrongly around CISA KEV alerts
(alerts chained by their boilerplate titles, stories chained on through the alerts' CVEs),
rebuilding each such row's sources under the current rules (app/dedupe.py plan).

    python -m app.split_clusters            # dry run: each row that would split, and into what
    python -m app.split_clusters --apply    # writes; never against production without sign-off

Every main row holding a KEV alert and at least one other source is replayed through the rules;
a row that comes out as more than one group is split. Other rows are only counted: their merges
were made from the feeds' full text, which is not stored (only the first paragraph is), so a
replay would split some of them wrongly. The group holding the row's primary source keeps the row id; the
others become new rows. Each row's time is its earliest news source (app/rowtime.py), its CVEs
are re-derived (a KEV alert row: the alert's listed CVEs only), and its summary is cleared so it
is written again for the smaller cluster. Scores, KEV and patch status are refilled by the next
enrichment roll-up. Uses DATABASE_URL like the app.
"""

import asyncio
import sys

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from app import alerts, dedupe, fetcher, rowtime
from app.db import SessionLocal
from app.models import Cve, Item, ItemCve, ItemSource, PatchStatus, Stream, Vendor
from app.tagging import VendorMatcher, cluster_cves, guess_category, headline_cves


async def _arts(session, client, item: Item, matcher: VendorMatcher) -> list[dedupe.Art]:
    out = []
    for s in item.sources:
        if s.published_at is None:
            continue
        if dedupe.is_kev_alert(s.title, s.url):
            cves = await alerts.listed_cves(session, client, s.title, s.url, s.published_at, s.excerpt or "", s.body or "")
        else:
            cves = headline_cves(s.title, s.excerpt or "", s.body or "")
        vendor = s.source.vendor_id or matcher.match(s.title, s.excerpt or "")
        out.append(dedupe.Art(s.id, s.title, s.url, s.published_at, vendor, cves, s.excerpt or "", s.body or ""))
    return out


def _primary(group: dedupe.Group, by_id: dict[int, ItemSource]) -> ItemSource:
    """The alert on a row it started; else a vendor PSIRT; else the earliest news article."""
    if group.alert_led:
        return by_id[group.arts[0].key]
    sources = [by_id[a.key] for a in group.arts if not a.alert]
    return min(sources, key=lambda s: (s.source.vendor_id is None, s.published_at, s.id))


def _group_cves(group: dedupe.Group, by_id: dict[int, ItemSource]) -> list[str]:
    if group.alert_led:
        return group.arts[0].cves
    sources = [by_id[a.key] for a in group.arts if not a.alert]
    return cluster_cves([(s.title, s.excerpt or "", s.body or "") for s in sources])


async def main(apply: bool) -> None:
    async with SessionLocal() as session, fetcher.client() as client:
        matcher = VendorMatcher((await session.scalars(select(Vendor))).all())
        multi = select(ItemSource.item_id).group_by(ItemSource.item_id).having(func.count() > 1)
        items = (
            await session.scalars(
                select(Item)
                .where(Item.stream == Stream.main, Item.id.in_(multi))
                .options(selectinload(Item.sources).selectinload(ItemSource.source))
                .order_by(Item.id)
            )
        ).all()
        alert_rows = [i for i in items if dedupe.has_alert(i.sources)]
        splits = []
        for item in alert_rows:
            groups = dedupe.plan(await _arts(session, client, item, matcher), matcher)
            if len(groups) > 1:
                splits.append((item, groups))
        print(
            f"{'applying' if apply else 'dry run'}: {len(splits)} of {len(alert_rows)} multi-source rows holding "
            f"a CISA KEV alert split ({len(items) - len(alert_rows)} other multi-source rows not replayed)"
        )

        for item, groups in splits:
            by_id = {s.id: s for s in item.sources}
            keep = next((g for g in groups if any(by_id[a.key].url == item.primary_url for a in g.arts)), groups[0])
            print(f"\nrow {item.id}  {item.last_event_at.isoformat()} ({item.last_event_kind})  {len(item.sources)} sources  |  {item.headline[:80]}")
            for g in sorted(groups, key=lambda g: g.time):
                primary = _primary(g, by_id)
                cves = _group_cves(g, by_id)
                label = f"row {item.id} (kept)" if g is keep else "new row"
                kind = "KEV alert" if g.alert_led else ("news + KEV alert" if g.has_alert else "news")
                print(f"  -> {label}  {g.time.isoformat()}  {kind}  cves={','.join(cves) or '-'}  |  {primary.title[:80]}")
                for a in sorted(g.arts, key=lambda a: a.published):
                    s = by_id[a.key]
                    print(f"       {a.published.isoformat()}  {s.source.name:<18} {s.title[:70]}")
            if apply:
                await _apply(session, item, groups, keep, by_id)
        if apply:
            await session.commit()


async def _apply(session, item: Item, groups: list[dedupe.Group], keep: dedupe.Group, by_id: dict[int, ItemSource]) -> None:
    await session.execute(delete(ItemCve).where(ItemCve.item_id == item.id))
    for g in groups:
        primary = _primary(g, by_id)
        cves = _group_cves(g, by_id)
        category = guess_category(primary.title, primary.excerpt or "", bool(cves))
        if cves:  # placeholder CVE rows first, so items.cve_id and item_cves hold
            await session.execute(insert(Cve).values([{"id": c} for c in cves]).on_conflict_do_nothing())
        if g is keep:
            row = item
        else:
            row = Item(stream=Stream.main, last_event_at=g.time, last_event_kind=rowtime.PUBLISHED)
            session.add(row)
        row.headline, row.primary_url = primary.title, primary.url
        row.vendor_id = None if g.alert_led else g.vendor_id
        row.category = category
        row.cve_id = cves[0] if cves else None
        # Refilled by enrichment (roll_up) for rows with CVEs; cleared for rows without.
        row.cvss = row.severity = row.epss = row.patch_url = None
        row.exploited = row.exploitation = False
        row.kev = g.has_alert
        row.patch_status = PatchStatus.unverified
        row.summary = row.action = None
        row.changed_at = func.now()
        for a in g.arts:
            by_id[a.key].item = row
        await session.flush()
        rowtime.set_row_time(row, g.time, f"split from item {item.id}")
        if cves:
            await session.execute(
                insert(ItemCve).values([{"item_id": row.id, "cve_id": c, "position": i} for i, c in enumerate(cves)])
                .on_conflict_do_nothing()
            )
    await session.flush()


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
