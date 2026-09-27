// Shared by the /wire server page and the client board (plain values cannot cross the
// "use client" boundary, so they live here).

import type { ElsewhereItem, FeedPage, FeedQuery, KevRow, Status, Tab, VendorOut } from "@/lib/api"

/** "stack" is the My stack tab: every category, only the viewer's vendors. */
export type WireTab = Tab | "stack"

export interface Filters {
  tab: WireTab
  vendor: string // slug, "" for all
  q: string
}

export interface WireData {
  filters: Filters
  feed: FeedPage
  status: Status | null
  vendors: VendorOut[] // by activity this week
  elsewhere: ElsewhereItem[]
  kev: KevRow[]
  error: boolean
  /** Stack in the request URL (?stack=); storage is read on the client. */
  stack: string[]
  /** Critical/KEV rows for the stack in the last 24h, null without a stack. */
  stackCritical: number | null
}

export const DAY_MS = 24 * 3600 * 1000

/** API query for the wire's filters. My stack is the All tab narrowed to the stack's vendors. */
export function feedQuery(f: Filters, stack: string[]): FeedQuery {
  const base = { vendor: f.vendor || undefined, q: f.q || undefined }
  if (f.tab === "stack") return { ...base, tab: "all", vendors: stack.join(",") || undefined }
  return { ...base, tab: f.tab }
}

/** Anything Critical or KEV for these vendors today? */
export const stackCriticalQuery = (stack: string[]) => ({
  vendors: stack.join(","),
  critical: true,
  since: new Date(Date.now() - DAY_MS).toISOString(),
  limit: 1,
})

export const TABS: [Tab, string][] = [
  ["all", "All"],
  ["vulnerabilities", "Vulnerabilities"],
  ["breaches", "Breaches"],
  ["ransomware", "Ransomware"],
  ["advisories", "Advisories"],
  ["research", "Research"],
  ["kev", "KEV"],
]
