// KEV due dates on collapsed rows: shown from 7 days before the deadline to 7 days after it.
// CISA dates are calendar dates stored at midnight UTC, so days are counted in UTC.

import type { FeedItem } from "@/lib/api"

const DAY_MS = 24 * 3600 * 1000
export const DUE_WINDOW_DAYS = 7
export const URGENT_DAYS = 2

/** Days until the KEV due date (0 = today, negative = overdue), or null outside the window. */
export function kevDueIn(item: Pick<FeedItem, "kev" | "kev_due_date">, nowMs: number): number | null {
  if (!item.kev || !item.kev_due_date) return null
  const today = Math.floor(nowMs / DAY_MS)
  const due = Math.floor(Date.parse(item.kev_due_date) / DAY_MS)
  const days = due - today
  return Math.abs(days) <= DUE_WINDOW_DAYS ? days : null
}

/** What the unseen "!" counts: Critical, KEV (incl. due soon), never an old CVE. */
export function isImportant(item: FeedItem): boolean {
  return !item.stale && (item.severity === "critical" || item.kev || kevDueIn(item, Date.now()) !== null)
}
