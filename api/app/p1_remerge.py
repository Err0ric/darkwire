"""One-time re-merge of the P1 dedupe misses (WIRE_FIXES.md P1), under the rules as they now stand.

Only the rows in SCOPE are read, planned or touched; nothing outside it merges. The plan:

1. Vendor tags: a row in scope with no vendor takes the one its headline matches now (Arista was
   seeded after its rows came in). A tagged row is never re-tagged.
2. Subject flags: each row's articles are fetched again (app/fetcher.py, as the summarizer does)
   and the CVEs the row already holds that are subjects of them (tagging.subject_cves, with the
   "tracked as" rule) are flagged on item_cves. No CVE is added or removed.
3. Merges, oldest row first, as dedupe.merge_existing replays them: a row folds into the most
   recent earlier row within 72h that takes it on a shared subject CVE (article_cves.takes) or by
   title (dedupe.titles_match; never into or out of a row holding a KEV alert), unless
   MERGE_EXCLUSIONS says no.
4. KEV alerts: a row a KEV alert started joins the one row now holding all its CVEs
   (article_cves.alert_home).
5. Breach shadow pairs (dedupe.breach_victims) are logged only.

Stop conditions (nothing is written, exit code 1): a SCOPE row is missing, the "arista" vendor is
not seeded, the plan has a merge not in EXPECTED, or more than MAX_MERGES merges. --apply also
needs SIGNED_OFF to equal the plan exactly; it is empty until the dry run is signed off. After an
apply the same plan runs again as a dry run and must find no merge.

    python -m app.p1_remerge            # dry run: logs the plan, writes nothing
    python -m app.p1_remerge --apply    # only with SIGNED_OFF filled in from a signed-off dry run
"""

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import article_cves, dedupe, fetcher
from app.article_cves import MERGE_WINDOW, Row
from app.models import Vendor
from app.tagging import VendorMatcher, subject_cves

log = logging.getLogger(__name__)

# Prod row ids of the P1 stories (2026-10-25).
SCOPE: frozenset[int] = frozenset({
    1871, 1891, 1908, 1944, 1951,  # Arista VeloCloud
    1948, 1952,  # Popcorn Time
    1760, 1766, 1796, 1814, 1836, 1839, 1927, 1940, 1945, 1964,  # PHP2Shell
    1893, 1905, 1906, 1915,  # Capcom, Quest Diagnostics
})
# What the in-memory dry run over the prod rows found (WIRE_FIXES.md P1): (kind, merged, survivor).
# 1908's text could not be read locally, so it may come in by CVE or by title; both are listed.
EXPECTED: frozenset[tuple[str, int, int]] = frozenset({
    ("cve", 1766, 1760), ("cve", 1836, 1760), ("cve", 1891, 1871), ("cve", 1952, 1948),
    ("title", 1908, 1871), ("cve", 1908, 1871), ("alert", 1944, 1871),
})
SIGNED_OFF: frozenset[tuple[str, int, int]] = frozenset()  # filled in only from a signed-off dry run
MAX_MERGES = 8


@dataclass
class Plan:
    vendors: dict[int, int] = field(default_factory=dict)  # item -> vendor id
    flags: dict[int, set[str]] = field(default_factory=dict)  # item -> CVEs to flag as subjects
    merges: list[tuple[str, int, int]] = field(default_factory=list)  # (kind, merged, survivor)
    breach: list[tuple[int, int, list[str]]] = field(default_factory=list)
    stop: list[str] = field(default_factory=list)


@dataclass
class Info:
    """What the plan needs beyond article_cves.Row."""

    headline: str
    vendor_id: int | None
    category: str
    titles: list[str]  # its news articles' titles (not KEV alerts)


def plan_merges(rows: dict[int, Row], info: dict[int, Info], matcher: VendorMatcher) -> tuple[list[tuple[str, int, int]], dict[int, Row]]:
    """Steps 3 and 4 over in-memory rows (mutated: survivors gain what folds into them)."""
    steps: list[tuple[str, int, int]] = []
    survivors: list[Row] = []
    for n in sorted(rows.values(), key=lambda r: (r.first_pub, r.id)):
        if n.led:
            survivors.append(n)
            continue

        def why(o: Row) -> str | None:
            if (o.first_pub, o.id) >= (n.first_pub, n.id) or abs(n.first_pub - o.last_event_at) > MERGE_WINDOW:
                return None
            if dedupe.excluded(n.id, o.id) or n.alert or n.roundup or o.roundup:
                return None
            if article_cves.takes(o, n):
                return "cve"
            if o.alert:
                return None
            vo, vn = info[o.id].vendor_id, info[n.id].vendor_id
            if any(dedupe.titles_match(a, b, vn, vo, matcher) for a in info[n.id].titles for b in info[o.id].titles):
                return "title"
            return None

        found = [(o, k) for o in survivors if (k := why(o))]
        if not found:
            survivors.append(n)
            continue
        o, kind = max(found, key=lambda f: f[0].last_event_at)
        steps.append((kind, n.id, o.id))
        o.cves |= n.cves
        o.subject |= n.subject
        o.alert = o.alert or n.alert
        info[o.id].titles += info[n.id].titles
        info[o.id].vendor_id = info[o.id].vendor_id or info[n.id].vendor_id
    left = {r.id: r for r in survivors}
    for a in sorted((r for r in survivors if r.led), key=lambda r: r.id):
        home = article_cves.alert_home(a, list(left.values()))
        if home is not None:
            steps.append(("alert", a.id, home.id))
            home.alert = True
            left.pop(a.id)
    return steps, left


async def build(session: AsyncSession, scope: frozenset[int], fetched: dict[int, str] | None = None) -> tuple[Plan, dict[int, Row], dict[int, Info]]:
    """Read the scope rows and make the plan. `fetched` (source id -> article text) skips the
    network (tests)."""
    plan = Plan()
    vendors = (await session.scalars(select(Vendor))).all()
    if not any(v.slug == "arista" for v in vendors):
        plan.stop.append('vendor "arista" is not seeded')
    matcher = VendorMatcher(vendors)
    since = datetime(2026, 1, 1, tzinfo=UTC)
    rows = {i: r for i, r in (await article_cves._rows(session, since)).items() if i in scope}
    missing = sorted(scope - rows.keys())
    if missing:
        plan.stop.append(f"rows missing: {missing}")

    got = (await session.execute(
        text("SELECT id, headline, vendor_id, category::text AS category FROM items WHERE id = ANY(:ids)"), {"ids": list(rows)}
    )).mappings().all()
    info = {r["id"]: Info(r["headline"], r["vendor_id"], r["category"], []) for r in got}
    sources = (await session.execute(
        text("SELECT id, item_id, title, url, excerpt FROM item_sources WHERE item_id = ANY(:ids) ORDER BY published_at, id"),
        {"ids": list(rows)},
    )).mappings().all()

    # 1. Vendor tags for untagged rows, from the headline.
    for i, x in info.items():
        if x.vendor_id is None:
            found = matcher.match(x.headline, "")
            if found is not None:
                plan.vendors[i] = found
                x.vendor_id = found

    # 2. Subject flags from the fetched articles.
    if fetched is None:
        fetched = {}
        async with fetcher.client() as client:
            for s in sources:
                if not dedupe.is_kev_alert(s["title"], s["url"]):
                    body = await fetcher.article_text(client, s["url"])
                    if body:
                        fetched[s["id"]] = body
        fetcher.log_stats()
    for s in sources:
        if dedupe.is_kev_alert(s["title"], s["url"]):
            continue
        info[s["item_id"]].titles.append(s["title"])
        r = rows[s["item_id"]]
        subj = subject_cves(s["title"], s["excerpt"] or "", fetched.get(s["id"], "")) & r.cves
        new = subj - r.subject
        if new:
            plan.flags.setdefault(r.id, set()).update(new)
        r.subject |= subj

    # Multi-story: the row's CVEs belong to 2+ vendors by KEV, CPE or CNA data.
    for r in rows.values():
        if len(r.cves) > 1 and len(set((await article_cves.cve_vendors(session, sorted(r.cves))).values())) >= 2:
            r.multi_story = True

    # 3 and 4.
    plan.merges, _ = plan_merges(rows, info, matcher)
    unexpected = [m for m in plan.merges if m not in EXPECTED]
    if unexpected:
        plan.stop.append(f"merges not in EXPECTED: {unexpected}")
    if len(plan.merges) > MAX_MERGES:
        plan.stop.append(f"{len(plan.merges)} merges, more than {MAX_MERGES}")

    # 5. Breach shadow, logged only.
    breach = sorted(i for i, x in info.items() if x.category == "breach")
    for k, a in enumerate(breach):
        for b in breach[k + 1:]:
            if abs(rows[a].first_pub - rows[b].first_pub) <= dedupe.TITLE_WINDOW:
                shared = sorted({w for ta in info[a].titles for tb in info[b].titles for w in dedupe.breach_victims(ta, tb)})
                if shared:
                    plan.breach.append((a, b, shared))
    return plan, rows, info


def report(plan: Plan, info: dict[int, Info], tag: str) -> None:
    p = f"p1 remerge ({tag}): "
    for i, v in sorted(plan.vendors.items()):
        log.info("%sitem %d vendor -> %d | %s", p, i, v, info[i].headline[:90])
    for i, cves in sorted(plan.flags.items()):
        log.info("%sitem %d flag subject %s", p, i, ",".join(sorted(cves)))
    for kind, m, s in plan.merges:
        log.info("%s%s: item %d -> item %d | %s | %s", p, kind, m, s, info[m].headline[:70], info[s].headline[:70])
    planned = {(m, s) for _, m, s in plan.merges}
    for m, s in sorted({(m, s) for _, m, s in EXPECTED} - planned):
        log.info("%sexpected but not planned: item %d -> item %d", p, m, s)
    for a, b, shared in plan.breach:
        log.info("%sbreach shadow (log only): item %d / item %d (shared %s) | %s | %s",
                 p, a, b, ",".join(shared), info[a].headline[:70], info[b].headline[:70])
    for s in plan.stop:
        log.info("%sSTOP: %s", p, s)
    log.info("%s%d vendor tags, %d rows flagged, %d merges, %d breach pairs logged, %d stop conditions",
             p, len(plan.vendors), len(plan.flags), len(plan.merges), len(plan.breach), len(plan.stop))


async def apply(session: AsyncSession, plan: Plan, rows: dict[int, Row]) -> None:
    for i, v in plan.vendors.items():
        await session.execute(text("UPDATE items SET vendor_id = :v WHERE id = :i AND vendor_id IS NULL"), {"v": v, "i": i})
    for i, cves in plan.flags.items():
        await session.execute(
            text("UPDATE item_cves SET subject = true WHERE item_id = :i AND cve_id = ANY(:c)"), {"i": i, "c": sorted(cves)}
        )
    for kind, m, s in plan.merges:
        if kind == "alert":
            await article_cves.join_alert(session, rows[s], rows[m], "p1 re-merge")
        else:
            await article_cves.merge(session, rows[s], rows[m], f"p1 re-merge ({kind})")
    await session.commit()


async def run(session: AsyncSession, do_apply: bool, scope: frozenset[int] = SCOPE, fetched: dict[int, str] | None = None) -> Plan:
    plan, rows, info = await build(session, scope, fetched)
    report(plan, info, "apply" if do_apply else "dry run")
    if not do_apply:
        return plan
    if plan.stop:
        raise SystemExit("p1 remerge: stop conditions hold, nothing written")
    if not SIGNED_OFF or set(plan.merges) != SIGNED_OFF:
        raise SystemExit("p1 remerge: the plan is not the signed-off one (SIGNED_OFF), nothing written")
    await apply(session, plan, rows)
    log.info("p1 remerge: applied; verification dry run follows")
    after, _, info = await build(session, frozenset(i for i in scope if i not in {m for _, m, _ in plan.merges}), fetched)
    report(after, info, "verification")
    return plan


async def main(do_apply: bool) -> int:
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    async with SessionLocal() as session:
        plan = await run(session, do_apply)
    return 1 if plan.stop else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--apply" in sys.argv)))
