from datetime import date, datetime

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
    kev_due_date: datetime | None  # CISA remediation deadline when the row's CVE is in KEV
    exploited: bool  # headline says exploited / zero-day and no CVE is known yet
    patch_status: PatchStatus  # rolled up from vendor / NVD data; "no fix yet" on home
    stale: bool  # CVE >90 days old, not in KEV, no exploitation headline: dimmed, left out of totals
    epss: float | None
    sources: list[SourceLink]
    last_event_at: datetime
    last_event_kind: str | None


class FeedPage(BaseModel):
    items: list[FeedItem]
    total: int


class FixedVersion(BaseModel):
    product: str
    version: str


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
    # When enrichment last ran. Null means kev / scores are defaults, not checked facts.
    fetched_at: datetime | None
    nvd_status: str | None
    affected: str | None  # "PAN-OS 10.2.0 before 10.2.9-h1, ..." from CPE, else the CNA's ranges
    patch_status: PatchStatus | None
    patch_url: str | None
    fixed_versions: list["FixedVersion"] | None
    workaround_url: str | None
    kev_due_date: datetime | None  # CISA's remediation deadline for federal agencies


class MsrcDetail(ORM):
    url: str
    title: str
    revision_note: str | None
    revised_at: datetime | None
    product: str | None
    severity: str | None
    exploited: bool | None
    publicly_disclosed: bool | None
    release: str | None
    kbs: list | None
    fixed_builds: list | None


class Action(BaseModel):
    """Model-read from the articles. Workaround sentence only: fixed versions, CVSS, KEV and
    patch status never come from the model."""

    workaround: str | None = None


class ItemDetail(FeedItem):
    summary: str | None
    action: Action | None  # model-read from the articles, CVE rows only
    patch_url: str | None
    first_seen_at: datetime
    cve: CveDetail | None
    msrc: MsrcDetail | None


class CveRow(BaseModel):
    id: str
    vendor: VendorRef | None
    product: str | None
    cvss: float | None
    severity: Severity | None
    epss: float | None
    kev: bool
    patch_status: PatchStatus | None
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
    # Last fetch: {"entries", "kept", "merged", "seen", "ads", "future", "too_old", "invalid"},
    # or {"not_modified": true} / {"error": ...}. Null before the first fetch.
    last_counts: dict | None


class SummariesStatus(BaseModel):
    state: str  # ok | auth_failing | quota | error | no_key | pending
    at: datetime | None
    detail: str | None


class SyncStatus(BaseModel):
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_ok: bool | None
    skipped_ads: int | None
    next_run_at: datetime | None
    interval_minutes: int


class Counts(BaseModel):
    critical_24h: int
    high_24h: int
    medium_24h: int
    low_24h: int
    items_24h: int
    articles_24h: int  # main-stream articles published in the last 24h (rows can hold several)
    kev_added_7d: int
    kev_due_7d: int  # CVEs on the board whose CISA KEV due date falls in the next 7 days
    critical_7d: int
    high_7d: int
    medium_7d: int
    low_7d: int


class KevRow(BaseModel):
    cve_id: str
    vendor: str | None
    product: str | None
    date_added: date
    item_id: int | None  # a row on the board for this CVE, if any


class Status(BaseModel):
    now: datetime
    sync: SyncStatus
    # total / ok / failing count enabled sources only. Disabled ones are listed, not counted.
    sources_total: int
    sources_ok: int
    sources_failing: int
    sources_disabled: int
    sources: list[SourceStatus]
    counts: Counts
    summaries: SummariesStatus
