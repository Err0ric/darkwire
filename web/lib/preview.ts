import type { FeedItem } from "@/lib/api"

// /wire?preview=unseen: two fake new rows, built here in the browser and handed to the same code
// path a poll's new rows take (title count, favicon, dots), so the unseen indicators can be seen
// by switching tabs. Nothing is fetched or stored; the rows exist in this tab only, have negative
// ids (no real row has one, and the poll ignores them), link nowhere, and say "Preview" plainly.

export const PREVIEW_PARAM = "unseen"
export const PREVIEW_DELAY_MS = 10_000

export function isPreviewRow(item: FeedItem): boolean {
  return item.id < 0
}

export function previewRows(): FeedItem[] {
  const now = Date.now()
  const base = {
    vendor: null,
    cve_id: null,
    kev_due_date: null,
    exploited: false,
    patch_status: "unverified",
    stale: false,
    epss: null,
    expandable: false,
    summary: null,
    last_event_kind: "published",
  } as const
  const source = (at: number) => [{ name: "preview", url: "#preview", published_at: new Date(at).toISOString() }]
  return [
    {
      ...base,
      id: -2,
      headline: "Preview: a Critical KEV row (not real)",
      primary_url: "#preview",
      category: "vulnerability",
      cvss: 9.8,
      severity: "critical",
      kev: true,
      sources: source(now),
      last_event_at: new Date(now).toISOString(),
    },
    {
      ...base,
      id: -1,
      headline: "Preview: a new row (not real)",
      primary_url: "#preview",
      category: "news",
      cvss: null,
      severity: null,
      kev: false,
      sources: source(now - 1000),
      last_event_at: new Date(now - 1000).toISOString(),
    },
  ] as FeedItem[]
}
