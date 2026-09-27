from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import Category, Health, PatchStatus, Severity, Stream


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VendorRef(ORM):
    slug: str
    name: str
    logo_path: str | None


class VendorOut(VendorRef):
    id: int
    aliases: list[str]
    domain: str | None
    items_7d: int = 0


class SourceLink(BaseModel):
    name: str
    url: str
    published_at: datetime | None


class FeedItem(BaseModel):
    id: int
    headline: str
    primary_url: str
    vendor: VendorRef | None
    category: Category
    cve_id: str | None
    cvss: float | None
    severity: Severity | None
    kev: bool
    epss: float | None
    sources: list[SourceLink]
    last_event_at: datetime
    last_event_kind: str | None


class FeedPage(BaseModel):
    items: list[FeedItem]
    total: int


class CveDetail(ORM):
    id: str
    description: str | None
    published_at: datetime | None
    cvss_version: str | None
    cvss_vector: str | None
    base_score: float | None
    base_severity: Severity | None
    impact_score: float | None
    exploitability_score: float | None
    cpes: list | None
    references: list | None
    epss: float | None
    epss_percentile: float | None
    kev: bool
    kev_added_at: datetime | None


class ItemDetail(FeedItem):
    summary: str | None
    patch_status: PatchStatus
    patch_url: str | None
    first_seen_at: datetime
    cve: CveDetail | None


class CveRow(BaseModel):
    id: str
    vendor: VendorRef | None
    product: str | None
    cvss: float | None
    severity: Severity | None
    epss: float | None
    kev: bool
    published_at: datetime | None
    item_id: int | None


class ElsewhereItem(BaseModel):
    id: int
    headline: str
    url: str
    source: str
    published_at: datetime | None


class SourceStatus(ORM):
    name: str
    stream: Stream
    health: Health
    last_ok_at: datetime | None
    last_error: str | None


class SyncStatus(BaseModel):
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_ok: bool | None
    next_run_at: datetime | None
    interval_minutes: int


class Counts(BaseModel):
    critical_24h: int
    high_24h: int
    medium_24h: int
    low_24h: int
    items_24h: int
    kev_added_7d: int


class Status(BaseModel):
    now: datetime
    sync: SyncStatus
    sources_total: int
    sources_ok: int
    sources_failing: int
    sources: list[SourceStatus]
    counts: Counts
