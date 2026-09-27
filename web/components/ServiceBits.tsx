"use client"

import { cn } from "cn"

import type { ServiceOut, ServiceState } from "@/lib/api"
import { useNow } from "@/lib/time"

// Shared by the rail's Services block and /services: one visual language for service state,
// the same as the CVSS bar (5x10px cells, 2px gap): gray ok, amber degraded, red major,
// --rule where there is no data.

export const STATE_LABEL: Record<ServiceState, string> = {
  operational: "operational",
  degraded: "degraded",
  major: "major outage",
  unknown: "not reporting",
}

const DOT: Record<ServiceState, string> = {
  operational: "bg-medium",
  degraded: "bg-degraded",
  major: "bg-critical",
  unknown: "bg-rule",
}

// Operational hours are a flat quiet line; hours before polling began are only outlined.
const CELL: Record<ServiceState, string> = {
  operational: "bg-strip-ok",
  degraded: "bg-degraded",
  major: "bg-critical",
  unknown: "bg-transparent ring-1 ring-inset ring-rule",
}

const CELL_WORD: Record<ServiceState, string> = {
  operational: "operational",
  degraded: "degraded",
  major: "major",
  unknown: "no data",
}

/** "13:00–14:00 PDT" for the cell `back` hours before the current one (local zone). */
function hourRange(back: number, nowMs: number): string {
  const start = new Date(Math.floor(nowMs / 3_600_000) * 3_600_000 - back * 3_600_000)
  const end = new Date(start.getTime() + 3_600_000)
  const hm = (d: Date) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
  const zone = new Intl.DateTimeFormat([], { timeZoneName: "short" }).formatToParts(start).find((p) => p.type === "timeZoneName")?.value ?? ""
  return `${hm(start)}–${hm(end)} ${zone}`.trim()
}

export function StateDot({ state, className }: { state: ServiceState; className?: string }) {
  return (
    <span
      role="img"
      aria-label={STATE_LABEL[state]}
      title={STATE_LABEL[state]}
      className={cn("inline-block size-1.5 shrink-0 rounded-full", DOT[state], className)}
    />
  )
}

/** 24 cells, one per hour, oldest on the left. `stretch` spreads them over the full width. */
export function HourStrip({ hours, stretch = false, className }: { hours: ServiceState[]; stretch?: boolean; className?: string }) {
  const now = useNow()
  const impacted = hours.filter((h) => h === "degraded" || h === "major").length
  return (
    <span
      role="img"
      aria-label={impacted ? `${impacted} of the last 24 hours impacted` : "No impact in the last 24 hours"}
      className={cn("flex shrink-0 gap-0.5", className)}
    >
      {hours.map((h, i) => (
        <span
          key={i}
          title={now === null ? undefined : `${hourRange(hours.length - 1 - i, now)} · ${CELL_WORD[h]}`}
          className={cn("h-2.5", stretch ? "min-w-0 flex-1" : "w-[5px]", CELL[h])}
        />
      ))}
    </span>
  )
}

const RANK: Record<ServiceState, number> = { major: 0, degraded: 1, unknown: 2, operational: 3 }

/** Major first, then degraded, then by name. */
export function byImpact(a: ServiceOut, b: ServiceOut) {
  return RANK[a.state] - RANK[b.state] || a.name.localeCompare(b.name)
}

export const isImpacted = (s: ServiceOut) => s.state === "major" || s.state === "degraded"
