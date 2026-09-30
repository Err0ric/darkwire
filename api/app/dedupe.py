"""Clustering rules shared by live ingest, the one-time merge of existing rows and the split
of bad clusters (app/split_clusters.py).

CLAUDE.md: cluster by CVE ID first. Title merges need publish times within 72h: with the same
vendor, normalized-title similarity > 0.85, or a shared product alias and "zero-day" in both
titles; with no vendor on one side, the same tests on the titles with boilerplate removed
(CISA, adds, known, exploited, vulnerability, catalog, KEV, warns, patches, flaw, zero-day,
critical, actively, attacks and stopwords): similarity > 0.85 on at least 3 remaining words, or
3 shared distinctive words with a proper noun among them.

CISA's "Adds N Known Exploited Vulnerabilities to Catalog" alerts (app/alerts.py lists their
CVEs): when every CVE an alert lists belongs to one existing row, and to no other row covering
them all, the alert joins that row as a source (the row keeps its headline and time and gets
KEV). Otherwise it starts its own row, which holds only the alert's CVEs and which a news article
joins only by sharing one of them. Alerts never merge with each other or by title, and never
pull stories in by chaining.
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
from app.tagging import ZERO_DAY, VendorMatcher, cluster_cves

log = logging.getLogger(__name__)

WINDOW = timedelta(hours=48)  # CVE merges of existing rows (merge_existing)

# Row pairs that never merge, either way, whatever the rules say: a signed-off decision, like
# tagging.CATEGORY_OVERRIDES. Every merge of existing rows checks it (merge_existing here, and
# article_cves.merge_target for the re-check after fetching and the re-merge). Each with the reason.
MERGE_EXCLUSIONS: frozenset[frozenset[int]] = frozenset({
    frozenset({819, 1}),  # 819, an arrest story, only mentions row 1's PeopleSoft CVE (2026-09-30)
})


def excluded(a: int, b: int) -> bool:
    return frozenset({a, b}) in MERGE_EXCLUSIONS
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


def has_alert(sources) -> bool:
    """A row with a CISA KEV alert among its sources (anything with .title and .url)."""
    return any(is_kev_alert(s.title, s.url) for s in sources)


def alert_led(item) -> bool:
    """A row started by a KEV alert: the alert is its primary source. Such a row holds only the
    alert's CVEs and is joined only through them. A row an alert joined stays a news row."""
    return is_kev_alert(getattr(item, "headline", None), getattr(item, "primary_url", None))


def alert_row_takes(row_cves: set[str], article_cves: set[str]) -> bool:
    """Whether news sharing a CVE with a row a KEV alert started may join it: the row holds one
    CVE, or the article holds every CVE the row does. One shared CVE of a multi-CVE alert would
    gather unrelated stories under one "CISA Adds ..." row."""
    return len(row_cves) <= 1 or row_cves <= article_cves


def time_sources(sources, led_by_alert: bool = False) -> list:
    """The sources a row's time comes from (app/rowtime.py). On a row a KEV alert started, all of
    them, the alert included. On a news row an alert joined, the news articles only: the row
    keeps its own time."""
    if led_by_alert:
        return list(sources)
    news = [s for s in sources if not is_kev_alert(getattr(s, "title", None), getattr(s, "url", None))]
    return news or list(sources)


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
# Words every KEV / advisory headline has; removed before titles are compared, so boilerplate
# alone ("CISA Adds Two Known Exploited Vulnerabilities to Catalog") never matches.
BOILERPLATE = set("""
cisa add adds known exploited vulnerability vulnerabilities catalog kev warn warns patch patches flaw flaws
zero day zeroday critical actively attack attacks
""".split())
GENERIC |= BOILERPLATE
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


def stripped(title: str) -> list[str]:
    """The title's words without stopwords, boilerplate and bare numbers."""
    return [
        w for w in normalize(title).split()
        if w not in STOPWORDS and w not in BOILERPLATE and _stem(w) not in BOILERPLATE and not w.isdigit()
    ]


def stripped_similar(a: str, b: str) -> bool:
    """Similarity > 0.85 on what is left once boilerplate is removed, with at least 3 words left."""
    wa, wb = stripped(a), stripped(b)
    if min(len(wa), len(wb)) < 3:
        return False
    return SequenceMatcher(None, " ".join(wa), " ".join(wb)).ratio() > SIMILARITY


def titles_match(a: str, b: str, vendor_a: int | None, vendor_b: int | None, matcher: VendorMatcher) -> bool:
    if vendor_a is not None and vendor_b is not None and vendor_a != vendor_b:
        return False
    if vendor_a is not None and vendor_a == vendor_b:
        if similarity(a, b) > SIMILARITY:
            return True
        if ZERO_DAY.search(a) and ZERO_DAY.search(b) and matcher.products(vendor_a, a) & matcher.products(vendor_a, b):
            return True
        return False
    # At least one side has no vendor: the boilerplate-free titles.
    return stripped_similar(a, b) or shared_story(a, b)


def title_merge_ok(
    title: str, published: datetime | None, vendor_id: int | None,
    other_title: str, other_published: datetime | None, other_vendor_id: int | None,
    matcher: VendorMatcher,
) -> bool:
    """A title merge: publish times within 72h and the titles match (titles_match)."""
    if published is None or other_published is None or abs(published - other_published) > TITLE_WINDOW:
        return False
    return titles_match(title, other_title, vendor_id, other_vendor_id, matcher)


async def find_title_cluster(
    session: AsyncSession, title: str, vendor_id: int | None, published: datetime, matcher: VendorMatcher
) -> Item | None:
    """A row with a source published within 72h whose title matches this one (title_merge_ok).
    Rows started by a KEV alert are never joined by title, nor are the alerts inside a row."""
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
    for item in candidates:
        if alert_led(item):
            continue
        if any(
            title_merge_ok(title, published, vendor_id, s.title, s.published_at, item.vendor_id, matcher)
            for s in item.sources
            if not is_kev_alert(s.title, s.url)
        ):
            return item
    return None


def alert_home_of(alert_cves, rows) -> object | None:
    """The one row an alert joins: rows are (row, its CVEs, whether it holds an alert). The row
    must hold every CVE the alert lists and no alert of its own, and be the only row holding
    them all. None: the alert starts its own row."""
    wanted = set(alert_cves)
    if not wanted:
        return None
    covering = [(row, alerts) for row, cves, alerts in rows if wanted <= set(cves)]
    if len(covering) != 1 or covering[0][1]:
        return None
    return covering[0][0]


async def find_alert_home(session: AsyncSession, alert_cves: list[str]) -> Item | None:
    """alert_home_of over the board's main rows."""
    if not alert_cves:
        return None
    touching = select(ItemCve.item_id).where(ItemCve.cve_id.in_(alert_cves))
    items = (
        await session.scalars(
            select(Item)
            .where(Item.stream == Stream.main, Item.id.in_(touching))
            .options(selectinload(Item.sources).selectinload(ItemSource.source))
        )
    ).all()
    if not items:
        return None
    cves: dict[int, set[str]] = {}
    for item_id, cve_id in (
        await session.execute(select(ItemCve.item_id, ItemCve.cve_id).where(ItemCve.item_id.in_([i.id for i in items])))
    ).all():
        cves.setdefault(item_id, set()).add(cve_id)
    return alert_home_of(alert_cves, [(i, cves.get(i.id, set()), has_alert(i.sources)) for i in items])


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
    lead: str = ""  # for the cluster's CVEs (cluster_cves), as ingest links them
    body: str = ""

    @property
    def alert(self) -> bool:
        return is_kev_alert(self.title, self.url)


@dataclass
class Group:
    arts: list[Art]
    cves: set[str]
    vendor_id: int | None

    @property
    def alert_led(self) -> bool:
        return self.arts[0].alert

    @property
    def has_alert(self) -> bool:
        return any(a.alert for a in self.arts)

    @property
    def time(self) -> datetime:
        return min(a.published for a in time_sources(self.arts, self.alert_led))


def plan(arts: list[Art], matcher: VendorMatcher, cve_window: timedelta = timedelta(hours=48)) -> list[Group]:
    """Cluster articles the way live ingest does, oldest first. A KEV alert joins the one group
    holding all its CVEs (alert_home_of), else starts its own. A news article joins by a shared
    CVE (the newest such group within cve_window; an alert-led group holds only the alert's
    CVEs), else by title (title_merge_ok against the group's news articles; never an alert-led
    group), else starts a group."""
    groups: list[Group] = []
    for a in sorted(arts, key=lambda a: (a.published, str(a.key))):
        if a.alert:
            home = alert_home_of(a.cves, [(g, g.cves, g.has_alert) for g in groups])
            if home is not None:
                home.arts.append(a)
            else:
                groups.append(Group([a], set(a.cves), None))
            continue
        by_cve = [g for g in groups if set(a.cves) & g.cves and abs(a.published - g.time) <= cve_window]
        target = max(by_cve, key=lambda g: g.time) if by_cve else None
        if target is None:
            for g in sorted(groups, key=lambda g: g.time, reverse=True):
                if not g.alert_led and any(
                    title_merge_ok(a.title, a.published, a.vendor_id, b.title, b.published, g.vendor_id, matcher)
                    for b in g.arts
                    if not b.alert
                ):
                    target = g
                    break
        if target is None:
            groups.append(Group([a], set(a.cves), a.vendor_id))
            continue
        target.arts.append(a)
        if not target.alert_led:  # an alert-led group keeps only the alert's CVEs
            # As ingest links them: each article's CVEs, plus the cluster's count filled from
            # another outlet's list ("Two ... Zero-Days" and a bulletin naming both).
            news = [b for b in target.arts if not b.alert]
            target.cves |= set(a.cves) | set(cluster_cves([(b.title, b.lead, b.body) for b in news]))
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
            if n["id"] in alerts or excluded(n["id"], o["id"]):  # a KEV alert never joins another row
                return False
            shared = cves.get(o["id"], set()) & cves.get(n["id"], set())
            if shared and abs(pub - o["last_event_at"]) <= WINDOW:
                return True
            if o["id"] in alerts:  # joined only by one of the alert's CVEs
                return False
            if abs(pub - o["last_event_at"]) > TITLE_WINDOW:
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
    times = (await session.execute(text("SELECT title, url, published_at FROM item_sources WHERE item_id = :o"), {"o": oid})).all()
    head = (await session.execute(text("SELECT headline, primary_url FROM items WHERE id = :o"), {"o": oid})).mappings().one()
    led = is_kev_alert(head["headline"], head["primary_url"])
    earliest = rowtime.news_time(t.published_at for t in time_sources(times, led))
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
