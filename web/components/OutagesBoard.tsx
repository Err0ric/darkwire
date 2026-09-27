"use client"

import { useEffect, useState } from "react"
import { cn } from "cn"

import { byImpact, HourStrip, isImpacted, StateDot } from "@/components/ServiceBits"
import { SiteFooter } from "@/components/SiteFooter"
import { getServices, type ServiceOut, type ServicesOut } from "@/lib/api"
import { age, useNow } from "@/lib/time"

// /outages: one screen. Header, "Impacted now" (one line per impacted service, with the
// incident), then the four groups as columns of name + 24h strip, then Stale, collapsed.
// 4 columns from 1600px, 2x2 from 1200px, stacked below. No boxes: columns separate by gap.

const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const
const POLL_MS = 3 * 60 * 1000

const STATE_WORD = { major: "major", degraded: "degraded" } as const

export function OutagesBoard({ initial }: { initial: ServicesOut | null }) {
  const [data, setData] = useState(initial)
  const now = useNow()

  useEffect(() => {
    const timer = setInterval(() => {
      getServices("all").then(setData).catch(() => undefined)
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [])

  const all = data?.services ?? []
  const impacted = all.filter(isImpacted)
  const checked = all.map((s) => s.checked_at).filter(Boolean).sort().at(-1) ?? null

  return (
    <main className="flex-1 page-frame pb-16">
      <header className="pt-6 md:pt-[33px]">
        <h1 className="text-[36px] leading-[44px] font-bold tracking-[-0.02em] text-fg">Outages</h1>
        <p className="mt-[3px] text-[15px] leading-5 text-muted">
          {data ? (
            <>
              <span className="text-fg">{all.length}</span> services ·{" "}
              {impacted.length ? (
                <>
                  <span className="text-fg">{impacted.length}</span> impacted
                </>
              ) : (
                "all operational"
              )}
              {checked && now !== null && <> · checked {age(checked, now)} ago</>}
            </>
          ) : (
            "The API is unreachable right now."
          )}
        </p>
      </header>

      {data && <ImpactedNow services={impacted} total={all.length} now={now} />}

      {data && (
        <div className="mt-10 grid gap-x-12 gap-y-10 min-[1200px]:grid-cols-2 min-[1600px]:grid-cols-4">
          {data.groups.map((group) => {
            const rows = all.filter((s) => s.group === group).sort(byImpact)
            return rows.length ? <Group key={group} name={group} services={rows} /> : null
          })}
        </div>
      )}

      <Stale services={all} now={now} />
      <SiteFooter className="mt-12" />
    </main>
  )
}

/** Impacted services, one full-width line each: major first, then the most recent. */
function ImpactedNow({ services, total, now }: { services: ServiceOut[]; total: number; now: number | null }) {
  if (!services.length) {
    return <p className="mt-8 text-[15px] text-muted">All {total} services operational.</p>
  }
  const started = (s: ServiceOut) => (s.incident?.started_at ? Date.parse(s.incident.started_at) : 0)
  const sorted = [...services].sort(
    (a, b) => Number(b.state === "major") - Number(a.state === "major") || started(b) - started(a),
  )
  return (
    <section aria-label="Impacted now" className="mt-8">
      <h2 className="border-b border-rule pb-2.5 text-[13px] font-medium text-fg">Impacted now</h2>
      <ul>
        {sorted.map((s) => (
          <li key={s.slug} className="flex min-h-11 items-baseline gap-x-3 border-b border-hairline py-3 text-[14px]">
            <StateDot state={s.state} className="relative -top-px self-center" />
            <span className="shrink-0 text-fg">{s.name}</span>
            <span className={cn("shrink-0", s.state === "major" ? "text-critical" : "text-degraded")}>
              {s.state === "major" ? STATE_WORD.major : STATE_WORD.degraded}
            </span>
            <a
              href={s.incident?.url ?? s.page}
              {...EXTERNAL}
              className="min-w-0 flex-1 text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
            >
              {s.incident?.title ?? "Status page"} <span aria-hidden className="text-[10px] text-critical">↗</span>
            </a>
            {s.incident?.started_at && now !== null && (
              <span className="shrink-0 font-mono text-xs text-muted">{age(s.incident.started_at, now)}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Group({ name, services }: { name: string; services: ServiceOut[] }) {
  return (
    <section aria-label={name} className="min-w-0">
      <h2 className="border-b border-rule pb-2.5 text-[13px] font-medium text-fg">{name}</h2>
      {/* The strip's axis, once per column. */}
      <div aria-hidden className="mt-2 flex justify-between text-[11px] leading-4 text-dim">
        <span>24h</span>
        <span>now</span>
      </div>
      <ul className="mt-1">
        {services.map((s) => (
          <li key={s.slug} className="py-2">
            <p className="flex items-center gap-2.5 text-[14px] leading-5">
              <StateDot state={s.state} />
              <a href={s.page} {...EXTERNAL} className="truncate text-fg outline-none hover:underline focus-visible:underline">
                {s.name}
              </a>
              {isImpacted(s) && (
                <span className={s.state === "major" ? "text-critical" : "text-degraded"}>
                  {s.state === "major" ? STATE_WORD.major : STATE_WORD.degraded}
                </span>
              )}
            </p>
            <HourStrip hours={s.hours} stretch className="mt-1.5" />
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Events the vendor has not touched in 72h+: kept visible, collapsed, and never counted. */
function Stale({ services, now }: { services: ServiceOut[]; now: number | null }) {
  const events = services.flatMap((s) => s.stale.map((e) => ({ service: s, e })))
  if (!events.length) return null
  return (
    <details className="group mt-10 text-dim">
      <summary className="flex cursor-pointer list-none items-baseline gap-2 border-b border-rule pb-2.5 text-[13px] font-medium outline-none hover:text-muted focus-visible:text-muted">
        <span aria-hidden className="inline-block group-open:rotate-90">
          ›
        </span>
        Stale (no update in 72h+)
        <span className="font-mono text-xs font-normal">{events.length}</span>
      </summary>
      <ul>
        {events.map(({ service, e }, i) => (
          <li key={i} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-hairline py-3 text-[13px]">
            <span className="w-full text-[15px] md:w-[228px] md:shrink-0">{service.name}</span>
            <a
              href={e.url ?? service.page}
              {...EXTERNAL}
              className="min-w-0 flex-1 truncate outline-none hover:text-muted focus-visible:text-muted"
            >
              {e.title ?? "Status page"}
            </a>
            {e.updated_at && now !== null && (
              <span className="shrink-0 font-mono text-xs">last update {age(e.updated_at, now)} ago</span>
            )}
          </li>
        ))}
      </ul>
    </details>
  )
}
