// Live updates (CLAUDE.md "Live updates"): /wire and / poll /feed?since=<newest last_event_at>
// every 60s. The API returns rows with a newer event or any newer change; this decides what
// each one means for the screen.
//
// NEW: a row that was not on screen and is newer than everything on screen, or an on-screen
// row that escalated (became KEV, became Critical, or got the EXPLOITED flag). New rows go to
// the top, count toward the unseen title and dot, and get the new-row dot.
// Everything else (a source added, a summary filled in, EPSS moved) replaces the row in place,
// silently. A row that is not on screen and not newer belongs further down the list: ignored.

import type { FeedItem } from "@/lib/api"

export const LIVE_POLL_MS = 60_000
// Changes are asked for since the previous poll, with room for clock skew and a slow poll.
const CHANGE_MARGIN_MS = 3 * 60_000

/** ?changed_since= for a poll: the previous poll's time, less a margin. */
export function changedSince(lastPoll: number): string {
  return new Date(lastPoll - CHANGE_MARGIN_MS).toISOString()
}

export function escalated(prev: FeedItem, next: FeedItem): boolean {
  return (
    (!prev.kev && next.kev) ||
    (prev.severity !== "critical" && next.severity === "critical") ||
    (!prev.exploited && next.exploited)
  )
}

/** Newest event on screen: the ?since= cursor. */
export function cursorOf(items: FeedItem[]): string | undefined {
  let best: string | undefined
  for (const i of items) if (!best || i.last_event_at > best) best = i.last_event_at
  return best
}

export interface Diff {
  /** New and escalated rows, newest first: they go to the top. */
  fresh: FeedItem[]
  /** Of those, how many were not on screen at all (for the list's total). */
  added: number
  /** On-screen rows that changed without escalating: replace in place. */
  updated: Map<number, FeedItem>
}

export function diff(current: FeedItem[], incoming: FeedItem[]): Diff {
  const byId = new Map(current.map((i) => [i.id, i]))
  const newest = cursorOf(current)
  const fresh: FeedItem[] = []
  const updated = new Map<number, FeedItem>()
  let added = 0
  for (const next of incoming) {
    const prev = byId.get(next.id)
    if (!prev) {
      if (!newest || next.last_event_at > newest) {
        fresh.push(next)
        added += 1
      }
    } else if (escalated(prev, next)) {
      fresh.push(next)
    } else if (JSON.stringify(prev) !== JSON.stringify(next)) {
      updated.set(next.id, next)
    }
  }
  fresh.sort((a, b) => (a.last_event_at < b.last_event_at ? 1 : -1))
  return { fresh, added, updated }
}

/** Apply a diff: fresh rows on top, the rest in place with their updates. */
export function apply(current: FeedItem[], d: Pick<Diff, "fresh" | "updated">): FeedItem[] {
  const top = new Set(d.fresh.map((i) => i.id))
  return [...d.fresh, ...current.filter((i) => !top.has(i.id)).map((i) => d.updated.get(i.id) ?? i)]
}
