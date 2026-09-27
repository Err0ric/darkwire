// Shared by the /wire server page and the client board (plain values cannot cross the
// "use client" boundary, so they live here).

import type { ElsewhereItem, FeedPage, KevRow, Status, Tab, VendorOut } from "@/lib/api"

export interface Filters {
  tab: Tab
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
}

export const TABS: [Tab, string][] = [
  ["all", "All"],
  ["vulnerabilities", "Vulnerabilities"],
  ["breaches", "Breaches"],
  ["ransomware", "Ransomware"],
  ["advisories", "Advisories"],
  ["research", "Research"],
  ["kev", "KEV"],
]
