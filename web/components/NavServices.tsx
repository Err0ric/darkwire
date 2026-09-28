"use client"

import Link from "next/link"
import { cn } from "cn"

import { byImpact, isImpacted } from "@/components/ServiceBits"
import { usePrefs } from "@/lib/prefs"
import { useLiveServices } from "@/lib/services-live"

/** The nav's services status, from the same watched set and poll as the wire's rail block:
 * "All services operational" (quiet), "Cloudflare degraded" / "3 services degraded" (amber
 * dot), or the worst major outage first, "AWS major outage +1" (red dot). Links to /services.
 * Hidden under 900px; the rail and /services still show it. */
export function NavServices({ className }: { className?: string }) {
  const prefs = usePrefs()
  const data = useLiveServices(prefs.ready ? prefs.services.join(",") : null)
  if (!data) return null
  const list = [...data.services].sort(byImpact)
  const impacted = list.filter(isImpacted)
  if (!impacted.length && !list.some((s) => s.state === "operational")) return null

  const worst = impacted[0]
  const more = impacted.length - 1
  const label = !worst
    ? "All services operational"
    : worst.state === "major"
      ? `${worst.name} major outage${more ? ` +${more}` : ""}`
      : impacted.length === 1
        ? `${worst.name} degraded`
        : `${impacted.length} services degraded`

  return (
    <Link
      href={`/services${prefs.query()}`}
      className={cn(
        "hidden items-center gap-2 text-[15px] leading-none whitespace-nowrap outline-none min-[900px]:flex",
        worst ? "text-fg-2 hover:text-fg focus-visible:text-fg" : "text-muted hover:text-fg-2 focus-visible:text-fg-2",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-1.5 shrink-0 rounded-full",
          !worst ? "bg-muted" : worst.state === "major" ? "bg-critical" : "bg-degraded",
        )}
      />
      {label}
    </Link>
  )
}
