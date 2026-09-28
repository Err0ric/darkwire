"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "cn"

import { byImpact, isImpacted } from "@/components/ServiceBits"
import { Tooltip } from "@/components/Tooltip"
import { usePrefs } from "@/lib/prefs"
import { useLiveServices } from "@/lib/services-live"

/** The nav's "Services" link (styled like CVEs), from the same watched set and poll as the
 * wire's rail block. A dot before the word only when something is wrong: amber when any
 * service is degraded, red when any has a major outage (worst wins). Hover and focus show the
 * detail at once ("Cloudflare degraded", "AWS major outage +1", "All services operational");
 * the dot's aria-label says the same. */
export function NavServices() {
  const pathname = usePathname()
  const prefs = usePrefs()
  const data = useLiveServices(prefs.ready ? prefs.services.join(",") : null)
  const active = pathname === "/services"

  const impacted = data ? [...data.services].sort(byImpact).filter(isImpacted) : []
  const worst = impacted[0]
  const more = impacted.length - 1
  const detail = !data
    ? null
    : !worst
      ? "All services operational"
      : worst.state === "major"
        ? `${worst.name} major outage${more ? ` +${more}` : ""}`
        : impacted.length === 1
          ? `${worst.name} degraded`
          : `${impacted.length} services degraded`

  const link = (props: object = {}) => (
    <Link
      href={`/services${prefs.query()}`}
      aria-current={active ? "page" : undefined}
      {...props}
      className={cn(
        "max-md:tap flex items-center gap-1.5 text-[13px] leading-none outline-none focus-visible:text-fg sm:text-[15px]",
        active ? "text-fg" : "text-muted hover:text-fg-2",
      )}
    >
      {worst && (
        <span
          role="img"
          aria-label={detail ?? undefined}
          className={cn("size-1.5 shrink-0 rounded-full", worst.state === "major" ? "bg-critical" : "bg-degraded")}
        />
      )}
      Services
    </Link>
  )

  if (!detail) return link()
  return (
    <Tooltip label={detail} side="bottom">
      {(props) => link(props)}
    </Tooltip>
  )
}
