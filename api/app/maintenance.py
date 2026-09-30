"""One-off, signed-off data changes, run once each from the scheduler (schedule()) and logged.

Each step runs once (job_state key STATE + step name) and logs every change it makes or would
make. Steps that were signed off conditionally ("apply only if the dry run shows exactly X")
check that condition themselves and stop, logging the difference, when it does not hold.
"""

import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import article_cves, facts_backfill, fetcher, ics, jobstate, summaries, versions
from app.config import get_settings
from app.models import Category, Item, ItemCve, ItemSource, PatchStatus, Stream

log = logging.getLogger(__name__)

STATE = "maintenance"

# Signed off 2026-09-30: 834 folds into row 1 (the same ShinyHunters PeopleSoft campaign, both
# about CVE-2026-35273). (merged, survivor).
MERGES = [(834, 1)]

# Signed off 2026-09-30: row 793 (the MikroTrick chain) displays CVE-2026-67279, the KEV-listed CVE
# of the chain, set by hand. (row, CVE); the row must hold the CVE.
REPIN_MANUAL = {793: "CVE-2026-67279"}


async def merges(session, pairs: list[tuple[int, int]] | None = None) -> None:
    """Signed-off merges, (merged, survivor), each logged; MERGES unless `pairs` is given."""
    rows = await article_cves._rows(session, datetime.now(UTC) - timedelta(days=30))
    for merged_id, survivor_id in pairs or MERGES:
        merged, survivor = rows.get(merged_id), rows.get(survivor_id)
        if merged is None or survivor is None:
            log.info("maintenance: merge %d -> %d skipped (row gone: %s)", merged_id, survivor_id,
                     ", ".join(str(i) for i in (merged_id, survivor_id) if i not in rows))
            continue
        await article_cves.merge(session, survivor, merged, "signed off")
        rows.pop(merged_id)
    await session.commit()


async def repin_manual(session) -> None:
    for item_id, cve in REPIN_MANUAL.items():
        item = await session.get(Item, item_id)
        held = set(await session.scalars(select(ItemCve.cve_id).where(ItemCve.item_id == item_id)))
        if item is None or cve not in held:
            log.info("maintenance: repin item %d -> %s skipped (%s)", item_id, cve, "row gone" if item is None else "the row does not hold it")
            continue
        log.info("maintenance: repin item %d %s -> %s (signed off)", item_id, item.cve_id, cve)
        item.cve_id = cve  # the next roll-up copies its score, severity and fix status
    await session.commit()


async def explain_873(session) -> None:
    """For review: row 873's article facts as the batch stored them, and the CISA advisory's own
    sentences about versions and release channels (fetched politely, as the summarizer does)."""
    item = await session.get(Item, 873)
    if item is None:
        log.info("maintenance: explain 873: row gone")
        return
    state = json.loads(await jobstate.get(session, facts_backfill.STATE) or "{}")
    found = (state.get("results_original") or state.get("results") or {}).get("873") or {}
    for key, fact in found.items():
        value = fact.get("text") or fact.get("version") or ""
        log.info("maintenance: explain 873 | stored %s%s | quote %r", key, f" = {value!r}" if value else "", fact.get("quote", ""))
    log.info("maintenance: explain 873 | summary %r", item.summary)
    async with fetcher.client() as client:
        text = await fetcher.article_text(client, item.primary_url)
    if not text:
        log.info("maintenance: explain 873 | the advisory could not be fetched (%s)", item.primary_url)
        return
    pattern = re.compile(r"\b7\.2\d|\bstable\b|long[- ]term|\bchannel|\btesting\b|\bbranch", re.I)
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        if pattern.search(sentence):
            log.info("maintenance: explain 873 | article: %r", sentence.strip()[:300])


async def summary_versions(session) -> None:
    """Existing summaries that state a fix version inside their own affected range: an ICS
    advisory row gets its deterministic summary (it never goes to the model); any other row is
    regenerated once without version numbers, else its versions are stripped. Each one logged."""
    rows = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, Item.summary.is_not(None), Item.summary != "",
                   Item.last_event_at >= datetime.now(UTC) - timedelta(days=14))
            .options(selectinload(Item.sources).selectinload(ItemSource.source))
        )
    ).all()
    hits = [i for i in rows if versions.summary_conflict(i.summary)]
    log.info("maintenance: summary versions: %d of %d summaries state a fix inside their affected range", len(hits), len(rows))
    for item in hits:
        before = item.summary
        if ics.is_ics_advisory(item.primary_url):
            n = len(set(await session.scalars(select(ItemCve.cve_id).where(ItemCve.item_id == item.id))))
            item.summary = ics.ics_summary(item.headline, n, float(item.cvss) if item.cvss is not None else None, item.severity, item.patch_status)
        elif get_settings().anthropic_api_key:
            fetched = await summaries._fetch_articles([item])
            material = summaries._articles(item, fetched.get(item.id))
            text, _ = await summaries.without_version_conflict(item.id, before, material, False)
            item.summary = text or ""
        else:
            log.info("maintenance: summary versions: item %d left as is (no model key)", item.id)
            continue
        log.info("maintenance: summary versions: item %d %r -> %r", item.id, before, item.summary)
    await session.commit()


async def resummarize_933(session) -> None:
    """Row 933's summary lost its version phrases mid-sentence ("Affected versions are; ...") under
    the first stripping rule; it is summarized again by the next pass (versions.strip now drops
    whole sentences)."""
    item = await session.get(Item, 933)
    if item is None:
        log.info("maintenance: resummarize 933: row gone")
        return
    log.info("maintenance: resummarize 933: %r -> queued", item.summary)
    item.summary = None
    await session.commit()


async def refresh_873(session) -> None:
    """Row 873 (CISA's MikroTik RouterOS advisory, corrected from "7.23 or later" to "7.24 or
    later"): the advisory read again and the combined summary + facts call run once on it
    (advisories.refresh). Signed off 2026-09-30; v2: the model summary replaces the template when it passes."""
    from app import advisories

    item = await session.scalar(
        select(Item).where(Item.id == 873)
        .options(selectinload(Item.sources).selectinload(ItemSource.source), selectinload(Item.vendor))
    )
    if item is None:
        log.info("maintenance: refresh 873: row gone")
        return
    src = next((s for s in item.sources if s.url == item.primary_url), item.sources[0])
    async with fetcher.client() as client:
        text = await fetcher.article_text(client, src.url)
    if not text:
        log.info("maintenance: refresh 873: the advisory could not be read (%s)", src.url)
        return
    log.info("maintenance: refresh 873: advisory fix/affected sentences: %s", " | ".join(advisories.fix_sentences(text)))
    if src.advisory_read_at is None:
        src.advisory_read_at, src.advisory_digest = datetime.now(UTC), advisories.digest(text)
    await advisories.refresh(session, item, {src.id: text}, "corrected CISA advisory, signed off")


async def recheck_930(session) -> None:
    """Row 930's stored summary kept a passive fix claim through the workaround exemption ("... as
    no workaround exists"); it is checked again under the current rules, no model call."""
    item = await session.get(Item, 930)
    if item is None or not item.summary:
        log.info("maintenance: recheck 930: nothing to check")
        return
    before = item.summary
    text, why = summaries.review_summary(before, patched=item.patch_status == PatchStatus.patched)
    if text:
        item.summary = text
    log.info("maintenance: recheck 930 (%s): %r -> %r", why, before, item.summary)
    await session.commit()


# Summarized again under the vendor-backed fix rule (summaries.fix_vendor), through the "sources
# grew" path so the current summary stays if the new attempt fails. The result is logged by
# summaries ("written again ..." / "kept its summary").
RESUMMARIZE = [930]


async def resummarize(session, ids: list[int] | None = None) -> None:
    for item_id in ids or RESUMMARIZE:
        item = await session.get(Item, item_id)
        if item is None:
            log.info("maintenance: resummarize %d: row gone", item_id)
            continue
        log.info("maintenance: resummarize %d: %r -> queued", item_id, item.summary)
        item.summary_sources, item.summarized_at = 0, datetime(2000, 1, 1, tzinfo=UTC)
    await session.commit()


async def strip_headline_emoji(session) -> None:
    """Stored headlines and article titles (wire and Elsewhere) without emoji, as ingest now
    writes them (tagging.strip_emoji). Each change logged."""
    from app.tagging import strip_emoji

    rows = changed = 0
    for model, column in ((Item, Item.headline), (ItemSource, ItemSource.title)):
        for obj in (await session.scalars(select(model))).all():
            rows += 1
            before = getattr(obj, column.key)
            after = strip_emoji(before)
            if after and after != before:
                log.info("maintenance: emoji: %s %d %r -> %r", model.__tablename__, obj.id, before, after)
                setattr(obj, column.key, after)
                changed += 1
    await session.commit()
    log.info("maintenance: emoji: %d of %d headlines and titles changed", changed, rows)


async def recategorize_trends(session, apply: bool = False) -> dict[int, tuple[str, str]]:
    """Rows of the last 7 days that the trend rule (tagging.guess_category, trend and industry
    pieces are not Vulnerability) re-derives. A row changes only when the rule before it, on the
    same primary article, gives the row's current category, and the new one differs: categories set
    another way (a merge, another article in the cluster) are left alone. Dry run unless `apply`;
    each change logged. {row: (now, new)}."""
    from app.tagging import guess_category

    rows = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, Item.last_event_at >= datetime.now(UTC) - timedelta(days=7))
            .options(selectinload(Item.sources))
            .order_by(Item.id)
        )
    ).all()
    changes: dict[int, tuple[str, str]] = {}
    for item in rows:
        primary = next((s for s in item.sources if s.url == item.primary_url), item.sources[0] if item.sources else None)
        if primary is None:
            continue
        has_cve = await session.scalar(select(ItemCve.cve_id).where(ItemCve.item_id == item.id).limit(1)) is not None
        old = guess_category(primary.title, primary.excerpt or "", has_cve, trends=False)
        new = guess_category(primary.title, primary.excerpt or "", has_cve)
        if old == item.category and new != old:
            changes[item.id] = (old.value, new.value)
            log.info("maintenance: trends (%s): item %d %s -> %s | %s", "apply" if apply else "dry run",
                     item.id, old.value, new.value, item.headline[:100])
            if apply:
                item.category = new
    if apply:
        await session.commit()
    log.info("maintenance: trends (%s): %d of %d rows change", "apply" if apply else "dry run", len(changes), len(rows))
    return changes


async def category_rules_dry_run(session) -> dict[int, tuple[str, str]]:
    """Dry run, writes nothing: rows of the last 7 days whose category differs from what the rules
    alone give (tagging.guess_category on the primary article, the trend pre-filter included), or
    that a manual override will set. The summary call's category verdicts are log-only, so they
    account for none of it. {row: (now, rules or override)}."""
    from app.tagging import CATEGORY_OVERRIDES, guess_category

    rows = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, Item.last_event_at >= datetime.now(UTC) - timedelta(days=7))
            .options(selectinload(Item.sources))
            .order_by(Item.id)
        )
    ).all()
    out: dict[int, tuple[str, str]] = {}
    for item in rows:
        if item.id in CATEGORY_OVERRIDES:
            if item.category.value != CATEGORY_OVERRIDES[item.id]:
                out[item.id] = (item.category.value, CATEGORY_OVERRIDES[item.id])
                log.info("maintenance: category rules (dry run): item %d %s -> %s (manual override) | %s",
                         item.id, item.category.value, CATEGORY_OVERRIDES[item.id], item.headline[:100])
            continue
        primary = next((s for s in item.sources if s.url == item.primary_url), item.sources[0] if item.sources else None)
        if primary is None:
            continue
        has_cve = await session.scalar(select(ItemCve.cve_id).where(ItemCve.item_id == item.id).limit(1)) is not None
        rules = guess_category(primary.title, primary.excerpt or "", has_cve)
        if rules != item.category:
            out[item.id] = (item.category.value, rules.value)
            log.info("maintenance: category rules (dry run): item %d is %s, its primary article alone gives %s | %s",
                     item.id, item.category.value, rules.value, item.headline[:100])
    overrides = sum(1 for k in out if k in CATEGORY_OVERRIDES)
    log.info("maintenance: category rules (dry run): %d of %d rows differ (%d manual overrides, %d other); nothing written",
             len(out), len(rows), overrides, len(out) - overrides)
    return out


# Signed off 2026-09-30: under the single-CVE subject rule (article_cves.row_subject), apply the
# 7-day re-merge only if it is exactly this pair, (merged, survivor): the OpenSSL DTLS rows.
REMERGE_EXPECTED = {(910, 907)}


async def remerge(session, expected: set[tuple[int, int]] | None = None, apply: bool = True) -> list[tuple[int, int]]:
    """Dry run of the merge rules over the rows of the last 7 days, in publish order, as the live
    re-check makes them (article_cves.merge_target); a row with CVEs of 2+ vendors counts as
    multi-story. Every pair logged with both headlines; applied only when the pairs are exactly
    REMERGE_EXPECTED, else STOP and nothing written. [(merged, survivor)]."""
    rows = await article_cves._rows(session, datetime.now(UTC) - timedelta(days=7))
    for row in rows.values():
        if len(row.cves) >= 2 and len(set((await article_cves.cve_vendors(session, sorted(row.cves))).values())) >= 2:
            row.multi_story = True
    headlines = dict((await session.execute(select(Item.id, Item.headline).where(Item.id.in_(list(rows))))).all())
    live = dict(rows)
    pairs: list[tuple[int, int]] = []
    for n in sorted(rows.values(), key=lambda r: (r.first_pub, r.id)):
        if n.id not in live:
            continue
        target = article_cves.merge_target(n, [r for r in live.values() if r.id != n.id])
        if target is None:
            continue
        pairs.append((n.id, target.id))
        log.info("maintenance: remerge (dry run): item %d into item %d (shared %s) | %s | %s", n.id, target.id,
                 ",".join(sorted(n.cves & target.cves)), headlines.get(n.id, "")[:90], headlines.get(target.id, "")[:90])
        target.cves |= n.cves
        target.subject |= n.subject
        live.pop(n.id)
    expected = REMERGE_EXPECTED if expected is None else expected
    if set(pairs) != expected:
        log.info("maintenance: remerge (dry run): %d merges; STOP: not exactly %s; nothing written", len(pairs), sorted(expected))
        return pairs
    if not apply:
        log.info("maintenance: remerge (dry run): exactly the expected %s; logs only, nothing written", sorted(expected))
        return pairs
    fresh = await article_cves._rows(session, datetime.now(UTC) - timedelta(days=7))
    for merged_id, survivor_id in pairs:
        await article_cves.merge(session, fresh[survivor_id], fresh[merged_id], "signed off: single-CVE subject rule")
        fresh.pop(merged_id)
    await session.commit()
    log.info("maintenance: remerge applied: %s", ", ".join(f"item {m} into item {s}" for m, s in pairs))
    return pairs


# Signed off 2026-09-30, single rows: {row: vendor slug}.
VENDOR_FIXES = {902: "signal"}  # "Signal adds encypted local backup support to iOS, desktop apps" was Apple


async def vendor_fixes(session) -> None:
    from app.models import Vendor

    for item_id, slug in VENDOR_FIXES.items():
        item = await session.get(Item, item_id)
        vendor = await session.scalar(select(Vendor).where(Vendor.slug == slug))
        if item is None or vendor is None:
            log.info("maintenance: vendor fix item %d -> %s skipped (%s)", item_id, slug, "row gone" if item is None else "no such vendor")
            continue
        old = await session.scalar(select(Vendor.slug).where(Vendor.id == item.vendor_id)) if item.vendor_id else None
        log.info("maintenance: vendor fix item %d %s -> %s (signed off) | %s", item_id, old, slug, item.headline[:100])
        item.vendor_id = vendor.id
    await session.commit()


async def apply_category_overrides(session) -> None:
    """tagging.CATEGORY_OVERRIDES written to their rows, each change logged. Runs once per version
    of the table (its step name carries a digest of it)."""
    from app.tagging import CATEGORY_OVERRIDES

    for item_id, value in sorted(CATEGORY_OVERRIDES.items()):
        item = await session.get(Item, item_id)
        if item is None:
            log.info("maintenance: category override: item %d gone", item_id)
            continue
        log.info("maintenance: category override: item %d %s -> %s | %s", item_id, item.category.value, value, item.headline[:100])
        item.category = Category(value)
    await session.commit()


async def recategorize_breach(session) -> None:
    """Rows of the last 14 days tagged Breach, re-derived under the incident rule
    (tagging.guess_category); each change logged. Other categories are left alone."""
    from app.tagging import guess_category

    rows = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, Item.category == Category.breach,
                   Item.last_event_at >= datetime.now(UTC) - timedelta(days=14))
            .options(selectinload(Item.sources))
        )
    ).all()
    changed = 0
    for item in rows:
        primary = next((s for s in item.sources if s.url == item.primary_url), item.sources[0] if item.sources else None)
        if primary is None:
            continue
        has_cve = await session.scalar(select(ItemCve.cve_id).where(ItemCve.item_id == item.id).limit(1)) is not None
        category = guess_category(primary.title, primary.excerpt or "", has_cve)
        if category != item.category:
            log.info("maintenance: recategorize item %d breach -> %s | %s", item.id, category.value, item.headline[:90])
            item.category = category
            changed += 1
    await session.commit()
    log.info("maintenance: recategorize: %d of %d breach rows changed", changed, len(rows))


# v1 moved 25 and 896 (incidents named in their titles) off Breach as well as 922; the incident
# check now reads the title too. These rows are re-derived once more, each change logged.
RECATEGORIZE_ROWS = [25, 896, 922]


async def recategorize_rows(session) -> None:
    from app.tagging import guess_category

    for item_id in RECATEGORIZE_ROWS:
        item = await session.scalar(select(Item).where(Item.id == item_id).options(selectinload(Item.sources)))
        if item is None or not item.sources:
            log.info("maintenance: recategorize item %d: row gone", item_id)
            continue
        primary = next((s for s in item.sources if s.url == item.primary_url), item.sources[0])
        has_cve = await session.scalar(select(ItemCve.cve_id).where(ItemCve.item_id == item.id).limit(1)) is not None
        category = guess_category(primary.title, primary.excerpt or "", has_cve)
        log.info("maintenance: recategorize item %d %s -> %s | %s", item.id, item.category.value, category.value, item.headline[:90])
        item.category = category
    await session.commit()


async def restore_25(session) -> None:
    """Row 25 (a $351M crypto heist) was Breach from another article in its cluster; the v1
    re-derivation read only its primary article and moved it to News. Back to Breach."""

    item = await session.get(Item, 25)
    if item is None:
        log.info("maintenance: restore 25: row gone")
        return
    log.info("maintenance: restore 25: %s -> breach | %s", item.category.value, item.headline[:90])
    item.category = Category.breach
    await session.commit()


STEPS = [
    ("merge_834_1", merges),
    ("repin_793", repin_manual),
    ("explain_873_v1", explain_873),
    ("summary_versions_v1", summary_versions),
    ("resummarize_933_v1", resummarize_933),
    ("recategorize_breach_v1", recategorize_breach),
    ("recategorize_rows_v2", recategorize_rows),
    ("restore_25_breach", restore_25),
    ("resummarize_930_v1", resummarize),
    ("refresh_873_v1", refresh_873),
    ("resummarize_930_v2", resummarize),
    ("recheck_930_v1", recheck_930),
    # Row 747: patched since its summary ("Two unpatched ... zero-days") was written.
    ("resummarize_747_v1", lambda session: resummarize(session, [747])),
    # Row 873 again: an ICS advisory now takes the model summary when it passes every check.
    ("refresh_873_v2", refresh_873),
    ("strip_headline_emoji_v1", strip_headline_emoji),
    ("recategorize_trends_dry_run_v1", recategorize_trends),
    # The dry run (2026-09-30 19:16 UTC) changed 1 of 164 rows: 926 vulnerability -> research.
    ("recategorize_trends_apply_v1", lambda session: recategorize_trends(session, apply=True)),
    # The summary call's category verdicts became log-only (2026-09-30): what differs from the rules.
    ("category_rules_dry_run_v1", category_rules_dry_run),
    ("remerge_single_cve_v1", remerge),
    # Signed off 2026-09-30: only the OpenSSL pair; 906 -> 747 and 819 -> 1 are not merged.
    ("merge_910_907", lambda session: merges(session, [(910, 907)])),
    ("remerge_check_v2", lambda session: remerge(session, expected={(906, 747)}, apply=False)),
    ("vendor_fix_902", vendor_fixes),
]


def _override_step() -> list:
    """The manual category overrides as a step named for the table's contents: it runs again
    whenever the table changes."""
    from app.tagging import CATEGORY_OVERRIDES

    if not CATEGORY_OVERRIDES:
        return []
    digest = hashlib.sha256(json.dumps(sorted(CATEGORY_OVERRIDES.items())).encode()).hexdigest()[:12]
    return [(f"category_overrides_{digest}", apply_category_overrides)]


async def run_once() -> None:
    from app.db import SessionLocal

    for name, step in [*STEPS, *_override_step()]:
        key = f"{STATE}_{name}"
        try:
            async with SessionLocal() as session:
                if await jobstate.get(session, key):
                    continue
                await step(session)
                await jobstate.put(session, key, datetime.now(UTC).isoformat())
                await session.commit()
        except Exception:
            log.exception("maintenance: %s failed", name)


def schedule(scheduler) -> None:
    scheduler.add_job(run_once, "date", run_date=datetime.now(UTC) + timedelta(minutes=2), id="maintenance")
