"""Clustering rules shared by live ingest, the one-time merge of existing rows and the split
of bad clusters (app/split_clusters.py).

CLAUDE.md: cluster by CVE ID first. A title merge (normalized-title similarity > 0.85, same
vendor; or same vendor + a shared product alias + "zero-day" in both titles; or shared
distinctive words) also needs publish times within 72h AND a shared CVE ID or vendor, so
boilerplate titles alone never merge. CISA's "Adds N Known Exploited Vulnerabilities to
Catalog" alerts never merge with anything: each is its own row, and a news article joins one
only by sharing a CVE the alert lists (the row's CVEs are the alert's own, app/alerts.py).
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import urlsplit

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import jobstate, rowtime
from app.models import Item, ItemCve, ItemSource, Stream
from app.tagging import ZERO_DAY, VendorMatcher

log = logging.getLogger(__name__)

WINDOW = timedelta(hours=48)  # CVE merges of existing rows (merge_existing)
TITLE_WINDOW = timedelta(hours=72)  # title merges: publish times at most this far apart
SIMILARITY = 0.85
_NON_WORD = re.compile(r"[^a-z0-9]+")

KEV_ALERT = re.compile(
    r"^\s*CISA Adds (?:\w+) Known Exploited Vulnerabilit(?:y|ies) to (?:the |Its )?(?:KEV )?Catalog\b",
    re.IGNORECASE,
)


def is_kev_alert(title: str | None, url: str | None) -> bool:
    """CISA's own "Adds N Known Exploited Vulnerabilities to Catalog" alert (on cisa.gov).
    Another outlet's story with the same wording is ordinary news."""
    host = (urlsplit(url or "").hostname or "").lower()
    return bool(KEV_ALERT.match(title or "")) and (host == "cisa.gov" or host.endswith(".cisa.gov"))


def is_alert_row(sources) -> bool:
    """A row holding a CISA KEV alert (sources: anything with .title and .url)."""
    return any(is_kev_alert(s.title, s.url) for s in sources)


def normalize(title: str) -> str:
    return _NON_WORD.sub(" ", title.lower()).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# ---------------------------------------------------------------- distinctive words

STOPWORDS = set("""
a an the and or but nor of in on at to for from by with without into onto over under after before about against
between through during as is are was were be been being has have had do does did it its this that these those
their there here who whom whose which what when where why how than then so not no yes can could may might will
would should must shall up down out off new now more most less least very just still also all any some each
every both few many much such via per vs amid says said say says report reports reported warns warned
""".split())
GENERIC = set("""
attack attacker hack hacker hacked hacking flaw bug issue vulnerability vulnerabilities vuln exploit exploited
exploiting exploitation zero day zeroday cyber cyberattack cybersecurity security secure breach leak leaked data
patch patched update fix fixed critical severe active actively ransomware malware threat actor campaign researcher
research user customer company firm government agency warning alert advisory possible potential million billion
""".split())
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:['.&][A-Za-z0-9]+)*")
_MIXED = re.compile(r"[a-z][A-Z]|[A-Za-z]\d|\d[A-Za-z]")


def _stem(word: str) -> str:
    w = word.lower().removesuffix("'s")
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _tokens(title: str) -> list[str]:
    return _TOKEN.findall(title)


def _sentence_case(tokens: list[str]) -> bool:
    words = [t for t in tokens[1:] if t[:1].isalpha() and len(t) > 3]
    return bool(words) and sum(t[:1].isupper() for t in words) / len(words) < 0.5


def distinctive(title: str) -> dict[str, list[str]]:
    """Stem -> the original spellings, for words that say something about this story."""
    out: dict[str, list[str]] = {}
    for t in _tokens(title):
        stem = _stem(t)
        if len(stem) < 3 or stem.isdigit() or stem in STOPWORDS or stem in GENERIC or t.lower() in GENERIC:
            continue
        out.setdefault(stem, []).append(t)
    return out


def _proper(stem: str, a: str, b: str, da: dict, db: dict) -> bool:
    spellings = da[stem] + db[stem]
    if any(_MIXED.search(s) or (s.isupper() and len(s) > 1) for s in spellings):
        return True  # NetScaler, x47.c, CISA
    if not all(s[:1].isupper() for s in spellings):
        return False
    # Capitalized everywhere, and at least one title is sentence case, where capitals mean something.
    return _sentence_case(_tokens(a)) or _sentence_case(_tokens(b))


def shared_story(a: str, b: str) -> bool:
    """At least 3 distinctive words in common, one of them a proper noun or product name."""
    da, db = distinctive(a), distinctive(b)
    shared = da.keys() & db.keys()
    return len(shared) >= 3 and any(_proper(s, a, b, da, db) for s in shared)


def titles_match(a: str, b: str, vendor_a: int | None, vendor_b: int | None, matcher: VendorMatcher) -> bool:
    if vendor_a is not None and vendor_b is not None and vendor_a != vendor_b:
        return False
    if vendor_a is not None and vendor_a == vendor_b:
        if similarity(a, b) > SIMILARITY:
            return True
        if ZERO_DAY.search(a) and ZERO_DAY.search(b) and matcher.products(vendor_a, a) & matcher.products(vendor_a, b):
            return True
        return False
    # At least one side has no vendor: fall back to shared distinctive words.
    return shared_story(a, b)


def title_merge_ok(
    title: str, published: datetime | None, vendor_id: int | None, cves,
    other_title: str, other_published: datetime | None, other_vendor_id: int | None, other_cves,
    matcher: VendorMatcher,
) -> bool:
    """A title merge: publish times within 72h, a shared CVE ID or the same vendor, and the
    titles match. Boilerplate titles alone ("CISA Adds Two ...") never merge."""
    if published is None or other_published is None or abs(published - other_published) > TITLE_WINDOW:
        return False
    same_vendor = vendor_id is not None and vendor_id == other_vendor_id
    if not same_vendor and not (set(cves) & set(other_cves)):
        return False
    return titles_match(title, other_title, vendor_id, other_vendor_id, matcher)


async def find_title_cluster(
    session: AsyncSession, title: str, vendor_id: int | None, published: datetime, matcher: VendorMatcher,
    cves: list[str] = (),
) -> Item | None:
    """A row with a source published within 72h whose title matches this one (title_merge_ok).
    Rows holding a CISA KEV alert are never joined by title."""
    compatible = [] if vendor_id is None else [or_(Item.vendor_id == vendor_id, Item.vendor_id.is_(None))]
    near = select(ItemSource.item_id).where(
        ItemSource.published_at.between(published - TITLE_WINDOW, published + TITLE_WINDOW)
    )
    candidates = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, *compatible, Item.id.in_(near))
            .options(selectinload(Item.sources).selectinload(ItemSource.source))
            .order_by(Item.last_event_at.desc())
        )
    ).all()
    if not candidates:
        return None
    row_cves: dict[int, set[str]] = {}
    ids = [i.id for i in candidates]
    for item_id, cve_id in (
        await session.execute(select(ItemCve.item_id, ItemCve.cve_id).where(ItemCve.item_id.in_(ids)))
    ).all():
        row_cves.setdefault(item_id, set()).add(cve_id)
    for item in candidates:
        if is_alert_row(item.sources):
            continue
        theirs = row_cves.get(item.id, set())
        if any(
            title_merge_ok(title, published, vendor_id, cves, s.title, s.published_at, item.vendor_id, theirs, matcher)
            for s in item.sources
        ):
            return item
    return None


# ---------------------------------------------------------------- the rules as a pure plan


@dataclass
class Art:
    """One article as the clustering rules see it."""

    key: object  # item_sources.id, or anything unique in tests
    title: str
    url: str
    published: datetime
    vendor_id: int | None = None
    cves: list[str] = field(default_factory=list)  # tied to its headline; for an alert, the ones it lists

    @property
    def alert(self) -> bool:
        return is_kev_alert(self.title, self.url)


@dataclass
class Group:
    arts: list[Art]
    cves: set[str]
    vendor_id: int | None

    @property
    def alert(self) -> bool:
        return any(a.alert for a in self.arts)

    @property
    def time(self) -> datetime:
        return min(a.published for a in self.arts)


def plan(arts: list[Art], matcher: VendorMatcher, cve_window: timedelta = timedelta(hours=48)) -> list[Group]:
    """Cluster articles the way live ingest does, oldest first: a KEV alert always starts its
    own row; otherwise join by a shared CVE (the newest such row within cve_window of its time;
    an alert row only by one of the alert's CVEs, which are all it holds), else by title
    (title_merge_ok, never an alert row), else start a row."""
    groups: list[Group] = []
    for a in sorted(arts, key=lambda a: (a.published, str(a.key))):
        if a.alert:
            groups.append(Group([a], set(a.cves), None))
            continue
        by_cve = [g for g in groups if set(a.cves) & g.cves and abs(a.published - g.time) <= cve_window]
        target = max(by_cve, key=lambda g: g.time) if by_cve else None
        if target is None:
            for g in sorted(groups, key=lambda g: g.time, reverse=True):
                if not g.alert and any(
                    title_merge_ok(a.title, a.published, a.vendor_id, a.cves, b.title, b.published, g.vendor_id, g.cves, matcher)
                    for b in g.arts
                ):
                    target = g
                    break
        if target is None:
            groups.append(Group([a], set(a.cves), a.vendor_id))
            continue
        target.arts.append(a)
        if not target.alert:  # an alert row keeps only the alert's CVEs
            target.cves |= set(a.cves)
            if target.vendor_id is None:
                target.vendor_id = a.vendor_id
    return groups


async def refresh_exploited(session: AsyncSession) -> None:
    """items.exploited: a headline in the cluster says zero-day / actively exploited / in the
    wild, and the row has no CVE. Recomputed for every main row, so it clears once a CVE lands.
    items.exploitation: any headline is about exploitation at all, CVE or not (staleness)."""
    await session.execute(text(r"""
        UPDATE items i SET exploited = f.flagged, exploitation = f.about, changed_at = now()
        FROM (
            SELECT i2.id,
                   NOT EXISTS (SELECT 1 FROM item_cves c WHERE c.item_id = i2.id)
                   AND EXISTS (
                       SELECT 1 FROM item_sources s WHERE s.item_id = i2.id
                       AND s.title ~* '\y(zero[- ]days?|0-days?|actively exploited|in the wild)\y'
                   ) AS flagged,
                   EXISTS (
                       SELECT 1 FROM item_sources s WHERE s.item_id = i2.id
                       AND s.title ~* '\y(zero[- ]days?|0-days?|exploit(s|ed|ing|ation)?|in the wild|under attack|under active attack)\y'
                   ) AS about
            FROM items i2 WHERE i2.stream = 'main'
        ) f
        WHERE f.id = i.id AND (i.exploited IS DISTINCT FROM f.flagged OR i.exploitation IS DISTINCT FROM f.about)
    """))


# ---------------------------------------------------------------- one-time merge


async def merge_existing(session: AsyncSession, matcher: VendorMatcher) -> int:
    """Replay both clustering rules over existing rows, oldest first. A row folds into an
    earlier row that it would have joined at ingest. Returns rows merged."""
    rows = (
        await session.execute(text("""
            SELECT i.id, i.last_event_at, i.last_event_kind, i.first_seen_at, i.vendor_id, i.category::text AS category,
                   i.summary, i.kev, i.cvss, i.exploited,
                   (SELECT min(published_at) FROM item_sources s WHERE s.item_id = i.id) AS first_pub
            FROM items i WHERE i.stream = 'main'
        """))
    ).mappings().all()
    cves: dict[int, set[str]] = {}
    for item_id, cve_id in (await session.execute(text("SELECT item_id, cve_id FROM item_cves"))).all():
        cves.setdefault(item_id, set()).add(cve_id)
    titles: dict[int, set[str]] = {}
    alerts: set[int] = set()
    for item_id, title, url in (await session.execute(text("SELECT item_id, title, url FROM item_sources"))).all():
        titles.setdefault(item_id, set()).add(title)
        if is_kev_alert(title, url):
            alerts.add(item_id)

    order = sorted((dict(r) for r in rows), key=lambda r: (r["first_pub"] or r["last_event_at"], r["id"]))
    survivors: list[dict] = []
    merged = 0
    for n in order:
        pub = n["first_pub"] or n["last_event_at"]

        def joins(o: dict) -> bool:
            if n["id"] in alerts:  # a KEV alert never joins another row
                return False
            shared = cves.get(o["id"], set()) & cves.get(n["id"], set())
            if shared and abs(pub - o["last_event_at"]) <= WINDOW:
                return True
            if o["id"] in alerts:  # joined only by one of the alert's CVEs
                return False
            same_vendor = n["vendor_id"] is not None and n["vendor_id"] == o["vendor_id"]
            if abs(pub - o["last_event_at"]) > TITLE_WINDOW or not (shared or same_vendor):
                return False
            return any(
                titles_match(a, b, n["vendor_id"], o["vendor_id"], matcher)
                for a in titles.get(n["id"], ())
                for b in titles.get(o["id"], ())
            )

        candidates = [o for o in survivors if joins(o)]
        if not candidates:
            survivors.append(n)
            continue
        o = max(candidates, key=lambda r: r["last_event_at"])
        await _merge(session, o, n, pub)
        cves.setdefault(o["id"], set()).update(cves.pop(n["id"], set()))
        titles.setdefault(o["id"], set()).update(titles.pop(n["id"], set()))
        merged += 1
    await session.commit()
    return merged


async def _merge(session: AsyncSession, o: dict, n: dict, n_pub: datetime) -> None:
    oid, nid = o["id"], n["id"]
    await session.execute(text("UPDATE item_sources SET item_id = :o WHERE item_id = :n"), {"o": oid, "n": nid})
    await session.execute(
        text("""
            INSERT INTO item_cves (item_id, cve_id, position)
            SELECT :o, cve_id, (SELECT coalesce(max(position), -1) + 1 FROM item_cves WHERE item_id = :o) + position
            FROM item_cves WHERE item_id = :n
            ON CONFLICT DO NOTHING
        """),
        {"o": oid, "n": nid},
    )
    # Row time: the earliest of the merged row's news sources (app/rowtime.py), logged.
    earliest = await session.scalar(text("SELECT min(published_at) FROM item_sources WHERE item_id = :o"), {"o": oid})
    event, kind = earliest or min(o["last_event_at"], n_pub), rowtime.PUBLISHED
    if event != o["last_event_at"] or o["last_event_kind"] != rowtime.PUBLISHED:
        log.info(
            "row time: item %s %s -> %s (merged item %s into it)",
            oid, o["last_event_at"].isoformat(), event.isoformat(), nid,
        )

    primary = (
        await session.execute(
            text("""
                SELECT s.url, s.title, src.vendor_id FROM item_sources s JOIN sources src ON src.id = s.source_id
                WHERE s.item_id = :o
                ORDER BY (src.vendor_id IS NULL), s.published_at NULLS LAST, s.id LIMIT 1
            """),
            {"o": oid},
        )
    ).mappings().one()
    scores = [x for x in (o["cvss"], n["cvss"]) if x is not None]
    values = {
        "vendor_id": primary["vendor_id"] or o["vendor_id"] or n["vendor_id"],
        "category": n["category"] if o["category"] == "news" else o["category"],
        "summary": o["summary"] or n["summary"],
        # Kept at the pair's max so the next roll-up does not see a change and resurface it.
        "kev": bool(o["kev"] or n["kev"]),
        "cvss": max(scores) if scores else None,
        "exploited": bool(o["exploited"] or n["exploited"]),
        "last_event_at": event,
        "last_event_kind": kind,
        "first_seen_at": min(o["first_seen_at"], n["first_seen_at"]),
    }
    await session.execute(
        text("""
            UPDATE items SET headline = :headline, primary_url = :url, vendor_id = :vendor_id,
                   category = CAST(:category AS category), summary = :summary, kev = :kev, cvss = :cvss,
                   exploited = :exploited, last_event_at = :last_event_at, last_event_kind = :last_event_kind,
                   first_seen_at = :first_seen_at
            WHERE id = :o
        """),
        {"o": oid, "headline": primary["title"], "url": primary["url"], **values},
    )
    await session.execute(text("DELETE FROM items WHERE id = :n"), {"n": nid})
    o.update(values)


async def merge_once(session: AsyncSession, matcher: VendorMatcher, key: str) -> int | None:
    """merge_existing once per rules version (job_state key). None when already done."""
    if await jobstate.get(session, key):
        return None
    merged = await merge_existing(session, matcher)
    await jobstate.put(session, key, str(merged))
    await session.commit()
    log.info("dedupe: %s merged %d rows", key, merged)
    return merged
