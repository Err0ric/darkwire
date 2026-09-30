import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Stream(str, enum.Enum):
    main = "main"
    elsewhere = "elsewhere"
    # Fetched for data only, never becomes rows (e.g. MSRC update guide).
    enrichment = "enrichment"


class Health(str, enum.Enum):
    unknown = "unknown"
    ok = "ok"
    failing = "failing"
    disabled = "disabled"


class Category(str, enum.Enum):
    vulnerability = "vulnerability"
    breach = "breach"
    ransomware = "ransomware"
    advisory = "advisory"
    research = "research"
    news = "news"


class Severity(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    none = "none"


class PatchStatus(str, enum.Enum):
    patched = "patched"
    no_fix = "no_fix"
    workaround = "workaround"
    unverified = "unverified"


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    domain: Mapped[str | None] = mapped_column(String(255))
    logo_path: Mapped[str | None] = mapped_column(String(255))


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    feed_url: Mapped[str] = mapped_column(Text, unique=True)
    site_url: Mapped[str | None] = mapped_column(Text)
    stream: Mapped[Stream] = mapped_column(_enum(Stream, "stream"), default=Stream.main)
    # Set when the feed is a vendor PSIRT. Its articles win primary-source selection.
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    health: Mapped[Health] = mapped_column(
        _enum(Health, "health"), default=Health.unknown, server_default="unknown"
    )
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Conditional GET validators from the last 200 response.
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    # What the last fetch did with each entry: {"entries", "kept", "merged", "seen", "ads",
    # "future", "too_old", "invalid"}. Null until the first fetch after migration 0010.
    last_counts: Mapped[dict | None] = mapped_column(JSONB)

    vendor: Mapped[Vendor | None] = relationship()


class Cve(Base):
    """Raw enrichment for one CVE: NVD, FIRST.org EPSS, CISA KEV."""

    __tablename__ = "cves"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # CVE-2026-12345
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cvss_version: Mapped[str | None] = mapped_column(String(8))
    cvss_vector: Mapped[str | None] = mapped_column(String(128))
    base_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    base_severity: Mapped[Severity | None] = mapped_column(_enum(Severity, "severity"))
    impact_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    exploitability_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    cpes: Mapped[list | None] = mapped_column(JSONB)
    references: Mapped[list | None] = mapped_column(JSONB)
    epss: Mapped[float | None] = mapped_column(Float)
    epss_percentile: Mapped[float | None] = mapped_column(Float)
    epss_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kev: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    kev_added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kev_due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nvd_raw: Mapped[dict | None] = mapped_column(JSONB)
    # When NVD was last fetched for this CVE (also set when NVD has no record yet).
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nvd_status: Mapped[str | None] = mapped_column(String(32))  # Analyzed, Awaiting Analysis, NOT_FOUND, ...
    # Derived on enrichment: human-readable affected ranges and patch status with its link.
    affected: Mapped[str | None] = mapped_column(Text)
    patch_status: Mapped[PatchStatus | None] = mapped_column(_enum(PatchStatus, "patch_status"))
    patch_url: Mapped[str | None] = mapped_column(Text)
    # "What to do": first fixed version per affected range, [{"product", "version"}],
    # and an NVD reference tagged Mitigation.
    fixed_versions: Mapped[list | None] = mapped_column(JSONB)
    workaround_url: Mapped[str | None] = mapped_column(Text)


class Item(Base):
    """One row on the board: a cluster of articles about the same thing."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    headline: Mapped[str] = mapped_column(Text)
    primary_url: Mapped[str] = mapped_column(Text)
    # Copied from the source feed. Elsewhere is assigned per feed, not per article.
    stream: Mapped[Stream] = mapped_column(_enum(Stream, "stream"), default=Stream.main, index=True)
    vendor_id: Mapped[int | None] = mapped_column(
        ForeignKey("vendors.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[Category] = mapped_column(_enum(Category, "category"), default=Category.news)
    # Elsewhere only (app/topics.py): privacy, surveillance, disinfo, courts, policy, rights,
    # cybercrime, "off-topic" (hidden), "" (asked, no usable answer), NULL (not classified yet).
    topic: Mapped[str | None] = mapped_column(String(24))
    # Not unique: coverage of the same CVE more than 48h apart starts a new row.
    cve_id: Mapped[str | None] = mapped_column(
        ForeignKey("cves.id", ondelete="SET NULL"), index=True
    )
    cvss: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    severity: Mapped[Severity | None] = mapped_column(_enum(Severity, "severity"))
    kev: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # A headline says zero-day / actively exploited / in the wild, and no CVE is known yet.
    exploited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Any headline in the cluster is about exploitation (exploit, exploited, zero-day, in the
    # wild, under attack), CVE or not. Keeps an old CVE from being dimmed.
    exploitation: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    epss: Mapped[float | None] = mapped_column(Float)
    patch_status: Mapped[PatchStatus] = mapped_column(
        _enum(PatchStatus, "patch_status"),
        default=PatchStatus.unverified,
        server_default="unverified",
    )
    patch_url: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    # Model-read workaround from the articles, CVE rows only: {"workaround": str | None}.
    # Null until asked; {"workaround": null} when the articles name none.
    action: Mapped[dict | None] = mapped_column(JSONB)
    # What the articles state, read with the summary and checked against their text (app/facts.py):
    # NULL not read yet, {} nothing verified, else {"public_poc"|"exploited_in_wild": {"quote"},
    # "affected": {"text", "quote"}, "fixed": {"version", "quote"}}. Shown only as "per article".
    facts: Mapped[dict | None] = mapped_column(JSONB)
    # How many sources the summary was written from, and when: a row whose sources grew is
    # summarized again, at most every summaries.REGENERATE_AFTER.
    summary_sources: Mapped[int | None] = mapped_column(Integer)
    summarized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Last time anything on the row changed (sources, scores, KEV, flags, summary). Lets
    # /feed?since= return in-place updates too; the client decides what counts as new.
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )
    # Sort key: last significant event (published, kev_added, poc, cvss_changed), not first-seen.
    last_event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    last_event_kind: Mapped[str | None] = mapped_column(String(32))

    vendor: Mapped[Vendor | None] = relationship()
    cve: Mapped[Cve | None] = relationship()
    sources: Mapped[list["ItemSource"]] = relationship(
        back_populates="item", order_by="ItemSource.published_at", cascade="all, delete-orphan"
    )


class ItemCve(Base):
    """Every CVE an item's articles mention. items.cve_id is the one shown on the row."""

    __tablename__ = "item_cves"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    cve_id: Mapped[str] = mapped_column(ForeignKey("cves.id", ondelete="CASCADE"), primary_key=True, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ItemSource(Base):
    """One outlet's article inside a cluster."""

    __tablename__ = "item_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    guid: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    # Plain text of the feed's full content (content:encoded), when the feed carries it.
    body: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped[Item] = relationship(back_populates="sources")
    source: Mapped[Source] = relationship()


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool | None] = mapped_column(Boolean)
    items_added: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    skipped_ads: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)


class MsrcUpdate(Base):
    """MSRC Security Update Guide, keyed by CVE. RSS fields for every entry;
    API details (product, KBs, builds, exploited) only for CVEs on the board."""

    __tablename__ = "msrc_updates"

    cve_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    revision_note: Mapped[str | None] = mapped_column(Text)
    revised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    product: Mapped[str | None] = mapped_column(String(255))
    severity: Mapped[str | None] = mapped_column(String(32))
    exploited: Mapped[bool | None] = mapped_column(Boolean)
    publicly_disclosed: Mapped[bool | None] = mapped_column(Boolean)
    release: Mapped[str | None] = mapped_column(String(16))  # 2026-Sep
    kbs: Mapped[list | None] = mapped_column(JSONB)  # [{"kb": "5126052", "url": ...}]
    fixed_builds: Mapped[list | None] = mapped_column(JSONB)  # [{"product": ..., "build": ...}]
    # Null means "fetch details next run". Reset when MSRC revises the entry.
    details_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KevEntry(Base):
    """CISA Known Exploited Vulnerabilities catalog, the whole list."""

    __tablename__ = "kev_entries"

    cve_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    vendor: Mapped[str | None] = mapped_column(String(255))
    product: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(Text)
    date_added: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    ransomware: Mapped[str | None] = mapped_column(String(32))  # Known / Unknown


class JobState(Base):
    """Small key/value store for scheduled jobs: last KEV fetch, NVD change window, ..."""

    __tablename__ = "job_state"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceStatus(Base):
    """Latest state of one third-party service (app/services.py). state: operational,
    degraded, major, or unknown (never checked, or its status page failed)."""

    __tablename__ = "service_status"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), default="unknown", server_default="unknown")
    incident_title: Mapped[str | None] = mapped_column(Text)
    incident_url: Mapped[str | None] = mapped_column(Text)
    incident_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    # Open events with no vendor update in 72h: [{state, title, url, started_at, updated_at}].
    stale: Mapped[list | None] = mapped_column(JSONB)


class ServiceIncident(Base):
    """An incident on a third-party status page, kept 8 days for the /services panel: recorded
    from each poll while it is open (ended_at set when it is gone) and, for Statuspage services,
    backfilled from the page's incident history."""

    __tablename__ = "service_incidents"
    __table_args__ = (UniqueConstraint("slug", "key", name="uq_service_incidents_slug_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(Text)  # the incident URL, else title + start
    title: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16))  # degraded | major (worst seen)
    url: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ServiceHour(Base):
    """Worst state seen per service per UTC hour, kept for 24h (the /outages strip)."""

    __tablename__ = "service_hours"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    worst: Mapped[str] = mapped_column(String(16))


class BoardEvent(Base):
    """What the board just did, for the landing's one-line log (GET /activity): ingest (a feed
    added rows), kev (a CVE on the board entered KEV), nvd (a CVE got or changed its score),
    cluster (another outlet joined a story), services (a service changed state), summary (a
    row got its summary). Public facts only; kept 7 days."""

    __tablename__ = "board_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str] = mapped_column(Text)  # source name, CVE ID, headline or service name
    detail: Mapped[str] = mapped_column(Text)  # "+3 items", "added", "scored 9.8", "4 sources", ...
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"))
