import { cn } from "cn"

import type { ServiceOut, ServiceState } from "@/lib/api"

// Shared by the rail's Services block and /outages: one visual language for service state,
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

const CELL: Record<ServiceState, string> = {
  operational: "bg-medium",
  degraded: "bg-degraded",
  major: "bg-critical",
  unknown: "bg-rule",
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

/** 24 cells, one per hour, oldest on the left. */
export function HourStrip({ hours, className }: { hours: ServiceState[]; className?: string }) {
  const impacted = hours.filter((h) => h === "degraded" || h === "major").length
  return (
    <span
      role="img"
      aria-label={impacted ? `${impacted} of the last 24 hours impacted` : "No impact in the last 24 hours"}
      className={cn("flex shrink-0 gap-0.5", className)}
    >
      {hours.map((h, i) => (
        <span key={i} className={cn("h-2.5 w-[5px]", CELL[h])} />
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
