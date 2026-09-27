import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
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


class Health(str, enum.Enum):
    unknown = "unknown"
    ok = "ok"
    failing = "failing"


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
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    # Not unique: coverage of the same CVE more than 48h apart starts a new row.
    cve_id: Mapped[str | None] = mapped_column(
        ForeignKey("cves.id", ondelete="SET NULL"), index=True
    )
    cvss: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    severity: Mapped[Severity | None] = mapped_column(_enum(Severity, "severity"))
    kev: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    epss: Mapped[float | None] = mapped_column(Float)
    patch_status: Mapped[PatchStatus] = mapped_column(
        _enum(PatchStatus, "patch_status"),
        default=PatchStatus.unverified,
        server_default="unverified",
    )
    patch_url: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
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
    error: Mapped[str | None] = mapped_column(Text)
