"use client"

import Link from "next/link"
import { cn } from "cn"

import { byImpact, isImpacted } from "@/components/ServiceBits"
import { Tooltip } from "@/components/Tooltip"
import type { ServiceOut, ServicesOut } from "@/lib/api"
import { usePrefs } from "@/lib/prefs"
import { age, useNow } from "@/lib/time"

/** The rail's Services block, every tracked service, compact. Impacted services first (major,
 * then degraded), one line each: dot, name, state, age; the incident title in an instant
 * tooltip. Then every other service in a 2-column grid: a small dim dot and the name. Services
 * the viewer picked (?services= or remembered) lead the grid in --fg-2, above a thin rule. Each
 * name opens that service on /services, expanded. `compact`: only the impacted lines (or one
 * "all operational" line), for the top of the feed under 1024px. `part` splits the block for the
 * single rail (1024-1599px), which puts other sections between the halves: "impacted" (nothing
 * when no service is impacted) and "list" (the grid of every other service). */
export function Services({
  data,
  compact = false,
  part = "all",
}: {
  data: ServicesOut | null
  compact?: boolean
  part?: "all" | "impacted" | "list"
}) {
  const now = useNow()
  const prefs = usePrefs()
  if (!data || !data.services.length) return null

  const open = (slug: string) => {
    const q = prefs.query()
    return `/services${q ? `${q}&` : "?"}open=${slug}`
  }
  const impacted = data.services.filter(isImpacted).sort(byImpact)
  const rest = data.services.filter((s) => !isImpacted(s))
  const picked = new Set(prefs.services)
  const mine = rest.filter((s) => picked.has(s.slug))
  const others = rest.filter((s) => !picked.has(s.slug))

  const lines = impacted.length > 0 && (
    <ul className={cn("flex flex-col gap-1", !compact && "mt-3")}>
      {impacted.map((s) => (
        <ImpactedLine key={s.slug} s={s} href={open(s.slug)} now={now} />
      ))}
    </ul>
  )
  const allLink = (
    <Link href={`/services${prefs.query()}`} className="max-md:tap text-[12px] text-dim-text outline-none hover:text-fg-2 focus-visible:text-fg-2">
      all services
    </Link>
  )

  if (compact) {
    // Its own name: under 1200px the full block is on the page too, and landmarks must differ.
    return (
      <section aria-label="Services, impacted now">
        {lines || (
          <p className="flex items-baseline justify-between gap-3 leading-5 text-muted">
            <span>
              <span className="font-medium text-fg-2">Services</span> · all {rest.length} operational
            </span>
            {allLink}
          </p>
        )}
      </section>
    )
  }

  if (part === "impacted") {
    return lines ? (
      <section aria-label="Services, impacted now">
        <div className="flex items-baseline justify-between">
          <h2 className="text-[13px] font-medium text-fg-2">Services</h2>
          {allLink}
        </div>
        {lines}
      </section>
    ) : null
  }

  return (
    <section aria-label={part === "list" ? "All services" : "Services"}>
      <div className="flex items-baseline justify-between">
        <h2 className="text-[13px] font-medium text-fg-2">{part === "list" && impacted.length ? "All services" : "Services"}</h2>
        {allLink}
      </div>
      {part === "all" && lines}
      <ul className="mt-3 grid grid-cols-2 gap-x-4 text-[12px] leading-[18px]">
        {mine.map((s) => (
          <GridItem key={s.slug} s={s} href={open(s.slug)} picked />
        ))}
        {mine.length > 0 && others.length > 0 && <li aria-hidden className="col-span-2 my-1.5 h-px bg-rule" />}
        {others.map((s) => (
          <GridItem key={s.slug} s={s} href={open(s.slug)} />
        ))}
      </ul>
    </section>
  )
}

function ImpactedLine({ s, href, now }: { s: ServiceOut; href: string; now: number | null }) {
  const major = s.state === "major"
  const word = major ? "major outage" : "degraded"
  return (
    <li>
      <Tooltip label={s.incident?.title ?? word} side="bottom" className="flex w-full" tipClassName="max-w-[min(440px,80vw)] whitespace-normal">
        {(props) => (
          <Link
            href={href}
            {...props}
            className="max-md:tap flex w-full min-w-0 items-center gap-2 text-[13px] leading-5 outline-none hover:bg-surface focus-visible:bg-surface"
          >
            <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", major ? "bg-critical" : "bg-degraded")} />
            <span className="min-w-0 truncate text-fg-2">{s.name}</span>
            <span className={cn("shrink-0", major ? "text-critical-text" : "text-degraded")}>{word}</span>
            <span className="ml-auto shrink-0 pl-2 font-mono text-[12px] text-dim-text">
              {now !== null && s.incident?.started_at ? age(s.incident.started_at, now) : ""}
            </span>
          </Link>
        )}
      </Tooltip>
    </li>
  )
}

function GridItem({ s, href, picked = false }: { s: ServiceOut; href: string; picked?: boolean }) {
  const silent = s.state === "unknown"
  return (
    <li className="min-w-0">
      <Link
        href={href}
        className={cn(
          "max-md:tap flex min-w-0 items-center gap-1.5 outline-none hover:text-fg-2 focus-visible:text-fg-2",
          picked ? "text-fg-2" : "text-muted",
        )}
      >
        <span
          aria-hidden
          className={cn("size-[5px] shrink-0 rounded-full", silent ? "ring-1 ring-dim ring-inset" : "bg-dim")}
        />
        <span className="truncate">{s.name}</span>
        {silent && <span className="sr-only"> (not reporting)</span>}
      </Link>
    </li>
  )
}
