import { cn } from "cn"

import type { Status } from "@/lib/api"

// The wordmark's dot: pulses (2.4s) while live, solid when the last sync is over 30 minutes
// old, gray when fetching fails. Shared by the nav and the landing wordmark.

export type SyncState = "live" | "stale" | "down"

const STALE_AFTER_MIN = 30

export function lastSyncAt(status: Status | null): number | null {
  const at = status?.sync.last_finished_at ?? status?.sync.last_started_at
  return at ? Date.parse(at) : null
}

export function minutesSinceSync(status: Status | null, now: number | null): number | null {
  const at = lastSyncAt(status)
  return at !== null && now !== null ? Math.max(0, Math.floor((now - at) / 60_000)) : null
}

export function syncState(status: Status | null, failing: boolean, now: number | null): SyncState {
  const minutes = minutesSinceSync(status, now)
  return failing ? "down" : minutes !== null && minutes <= STALE_AFTER_MIN ? "live" : "stale"
}

export function SyncDot({ state, className }: { state: SyncState; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("rounded-full", state === "down" ? "bg-dim" : "bg-accent", state === "live" && "animate-pulse-dot", className)}
    />
  )
}
