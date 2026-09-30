// Shared by the /wire server page and the client board (plain values cannot cross the
// "use client" boundary, so they live here).

import type { ElsewhereItem, FeedPage, FeedQuery, KevRow, ServicesOut, Severity, Status, Tab, VendorOut } from "@/lib/api"

/** "stack" is the My stack tab: every category, only the viewer's vendors. "elsewhere" lists
 * the Elsewhere stream (policy, privacy, courts) of the last 7 days instead of the feed. */
export type WireTab = Tab | "stack" | "elsewhere"

export interface Filters {
  tab: WireTab
  vendor: string // slug, "" for all
  q: string
  /** ?severity=: this severity over the last 7 days; "" for none. Combines with tab/vendor/stack. */
  severity: Severity | ""
  /** Severity window: "24h" from the header counts, "" = 7 days from the rail. */
  window: "24h" | ""
}

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"]

export function parseSeverity(raw: string | undefined): Severity | "" {
  return SEVERITIES.find((s) => s === raw) ?? ""
}

export interface WireData {
  filters: Filters
  feed: FeedPage
  status: Status | null
  vendors: VendorOut[] // by activity this week
  elsewhere: ElsewhereItem[]
  kev: KevRow[]
  services: ServicesOut | null
  error: boolean
  /** Stack in the request URL (?stack=); storage is read on the client. */
  stack: string[]
  /** Critical/KEV rows for the stack in the last 24h, null without a stack. */
  stackCritical: number | null
}

export const DAY_MS = 24 * 3600 * 1000

/** API query for the wire's filters. My stack is the All tab narrowed to the stack's vendors. */
export function feedQuery(f: Filters, stack: string[]): FeedQuery {
  const base = {
    vendor: f.vendor || undefined,
    q: f.q || undefined,
    severity: f.severity || undefined,
    window: f.severity && f.window ? f.window : undefined,
  }
  if (f.tab === "stack") return { ...base, tab: "all", vendors: stack.join(",") || undefined }
  if (f.tab === "elsewhere") return { ...base, tab: "all" } // the tab shows Elsewhere items, not this feed
  return { ...base, tab: f.tab }
}

/** Anything Critical or KEV for these vendors today? */
export const stackCriticalQuery = (stack: string[]) => ({
  vendors: stack.join(","),
  critical: true,
  since: new Date(Date.now() - DAY_MS).toISOString(),
  limit: 1,
})

export const TABS: [WireTab, string][] = [
  ["all", "All"],
  ["vulnerabilities", "Vulnerabilities"],
  ["breaches", "Breaches"],
  ["ransomware", "Ransomware"],
  ["advisories", "Advisories"],
  ["research", "Research"],
  ["kev", "KEV"],
  ["elsewhere", "Elsewhere"],
]
