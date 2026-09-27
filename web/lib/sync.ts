import type { Status } from "@/lib/api"

// Sync state for the wordmark's square: live (last sync within 30 minutes), stale (older),
// down (the API or the last ingest run failing).

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
