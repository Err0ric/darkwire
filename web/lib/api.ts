// Typed client for the darkwire API. Types mirror api/app/schemas.py; keep them in sync.
// Datetimes arrive as ISO 8601 strings (UTC).

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "")

export type Stream = "main" | "elsewhere" | "enrichment"
export type Health = "unknown" | "ok" | "failing" | "disabled"
export type Category = "vulnerability" | "breach" | "ransomware" | "advisory" | "research" | "news"
export type Severity = "critical" | "high" | "medium" | "low" | "none"
export type PatchStatus = "patched" | "no_fix" | "workaround" | "unverified"
export type Tab = "all" | "vulnerabilities" | "breaches" | "ransomware" | "advisories" | "research" | "kev"

export interface VendorRef {
  slug: string
  name: string
  logo_path: string | null
}

export interface VendorOut extends VendorRef {
  id: number
  aliases: string[]
  domain: string | null
  items_7d: number
}

export interface SourceLink {
  name: string
  url: string
  published_at: string | null
}

export interface FeedItem {
  id: number
  headline: string
  primary_url: string
  vendor: VendorRef | null
  category: Category
  cve_id: string | null
  cvss: number | null
  severity: Severity | null
  kev: boolean
  epss: number | null
  sources: SourceLink[]
  last_event_at: string
  last_event_kind: string | null
}

export interface FeedPage {
  items: FeedItem[]
  total: number
}

export interface CveDetail {
  id: string
  description: string | null
  published_at: string | null
  cvss_version: string | null
  cvss_vector: string | null
  base_score: number | null
  base_severity: Severity | null
  impact_score: number | null
  exploitability_score: number | null
  cpes: unknown[] | null
  references: unknown[] | null
  epss: number | null
  epss_percentile: number | null
  kev: boolean
  kev_added_at: string | null
}

export interface MsrcDetail {
  url: string
  title: string
  revision_note: string | null
  revised_at: string | null
  product: string | null
  severity: string | null
  exploited: boolean | null
  publicly_disclosed: boolean | null
  release: string | null
  kbs: { kb: string; url: string | null }[] | null
  fixed_builds: { product: string; build: string }[] | null
}

export interface ItemDetail extends FeedItem {
  summary: string | null
  patch_status: PatchStatus
  patch_url: string | null
  first_seen_at: string
  cve: CveDetail | null
  msrc: MsrcDetail | null
}

export interface CveRow {
  id: string
  vendor: VendorRef | null
  product: string | null
  cvss: number | null
  severity: Severity | null
  epss: number | null
  kev: boolean
  published_at: string | null
  item_id: number | null
}

export interface ElsewhereItem {
  id: number
  headline: string
  url: string
  source: string
  published_at: string | null
}

export interface SourceStatus {
  name: string
  stream: Stream
  health: Health
  last_ok_at: string | null
  last_error: string | null
}

export interface SyncStatus {
  last_started_at: string | null
  last_finished_at: string | null
  last_ok: boolean | null
  skipped_ads: number | null
  next_run_at: string | null
  interval_minutes: number
}

export interface Counts {
  critical_24h: number
  high_24h: number
  medium_24h: number
  low_24h: number
  items_24h: number
  kev_added_7d: number
}

export interface Status {
  now: string
  sync: SyncStatus
  // total / ok / failing count enabled sources only; disabled ones are listed, not counted.
  sources_total: number
  sources_ok: number
  sources_failing: number
  sources_disabled: number
  sources: SourceStatus[]
  counts: Counts
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
  ) {
    super(`API ${status} on ${path}`)
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

async function get<T>(path: string, query: Query = {}, init?: RequestInit): Promise<T> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value))
  }
  const qs = params.size ? `?${params}` : ""
  const res = await fetch(`${API_URL}${path}${qs}`, { cache: "no-store", ...init })
  if (!res.ok) throw new ApiError(res.status, path)
  return res.json() as Promise<T>
}

export interface FeedQuery {
  tab?: Tab
  vendor?: string
  q?: string
  limit?: number
  since?: string
}

export const getFeed = (query: FeedQuery = {}, init?: RequestInit) =>
  get<FeedPage>("/feed", { ...query }, init)

export const getItem = (id: number, init?: RequestInit) => get<ItemDetail>(`/items/${id}`, {}, init)

export interface CvesQuery {
  sort?: "published" | "cvss" | "epss" | "cve"
  order?: "asc" | "desc"
  vendor?: string
  kev?: boolean
  q?: string
  limit?: number
  offset?: number
}

export const getCves = (query: CvesQuery = {}, init?: RequestInit) =>
  get<CveRow[]>("/cves", { ...query }, init)

export const getVendors = (sort: "name" | "active" = "name", init?: RequestInit) =>
  get<VendorOut[]>("/vendors", { sort }, init)

export const getElsewhere = (limit = 5, init?: RequestInit) =>
  get<ElsewhereItem[]>("/elsewhere", { limit }, init)

export const getStatus = (init?: RequestInit) => get<Status>("/status", {}, init)
