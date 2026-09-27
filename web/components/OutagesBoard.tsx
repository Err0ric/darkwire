"use client"

import { useEffect, useState } from "react"

import { byImpact, HourStrip, isImpacted, StateDot, STATE_LABEL } from "@/components/ServiceBits"
import { SiteFooter } from "@/components/SiteFooter"
import { getServices, type ServiceOut, type ServicesOut } from "@/lib/api"
import { age, useNow } from "@/lib/time"

const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const
const POLL_MS = 3 * 60 * 1000

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
  const impacted = all.filter(isImpacted).length
  const checked = all.map((s) => s.checked_at).filter(Boolean).sort().at(-1) ?? null

  return (
    <main className="flex-1 px-4 pb-24 md:px-12">
      <div className="min-[1200px]:max-w-[1200px]">
        <header className="pt-6 md:pt-[33px]">
          <h1 className="text-[36px] leading-[44px] font-bold tracking-[-0.02em] text-fg">Outages</h1>
          <p className="mt-[3px] text-[15px] leading-5 text-muted">
            {data ? (
              <>
                <span className="text-fg">{all.length}</span> services ·{" "}
                {impacted ? (
                  <>
                    <span className="text-fg">{impacted}</span> impacted
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

        {data?.groups.map((group) => {
          const rows = all.filter((s) => s.group === group).sort(byImpact)
          if (!rows.length) return null
          return (
            <section key={group} aria-label={group} className="mt-10 md:mt-12">
              <div className="flex items-baseline border-b border-rule pb-2.5">
                <h2 className="text-[13px] font-medium text-fg md:w-[228px]">{group}</h2>
                <span className="hidden w-[166px] justify-between text-[11px] text-dim md:flex" aria-hidden>
                  <span>24h</span>
                  <span>now</span>
                </span>
              </div>
              <ul>
                {rows.map((s) => (
                  <ServiceRow key={s.slug} s={s} now={now} />
                ))}
              </ul>
            </section>
          )
        })}
        <Stale services={all} now={now} />
        <SiteFooter className="mt-16" />
      </div>
    </main>
  )
}

function ServiceRow({ s, now }: { s: ServiceOut; now: number | null }) {
  const hit = isImpacted(s)
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-hairline py-3 md:h-12 md:flex-nowrap md:gap-x-0 md:py-0">
      <span className="flex w-full items-center gap-3 md:w-[228px] md:shrink-0">
        <StateDot state={s.state} />
        <a href={s.page} {...EXTERNAL} className="truncate text-[15px] text-fg outline-none hover:underline focus-visible:underline">
          {s.name}
        </a>
      </span>
      <HourStrip hours={s.hours} className="ml-[18px] md:ml-0" />
      <span className="flex min-w-0 flex-1 items-baseline gap-3 text-[13px] md:ml-8">
        {hit ? (
          <>
            <a
              href={s.incident?.url ?? s.page}
              {...EXTERNAL}
              className="min-w-0 truncate text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
            >
              {s.incident?.title ?? "Status page"} <span aria-hidden className="text-[10px] text-critical">↗</span>
            </a>
            {s.incident?.started_at && now !== null && (
              <span className="ml-auto shrink-0 font-mono text-xs text-muted">{age(s.incident.started_at, now)}</span>
            )}
          </>
        ) : (
          <span className="text-dim">{STATE_LABEL[s.state]}</span>
        )}
      </span>
    </li>
  )
}

/** Events the vendor has not touched in 72h+: kept visible, collapsed, and never counted. */
function Stale({ services, now }: { services: ServiceOut[]; now: number | null }) {
  const events = services.flatMap((s) => s.stale.map((e) => ({ service: s, e })))
  if (!events.length) return null
  return (
    <details className="group mt-10 text-dim md:mt-12">
      <summary className="flex cursor-pointer list-none items-baseline gap-2 border-b border-rule pb-2.5 text-[13px] font-medium outline-none hover:text-muted focus-visible:text-muted">
        <span aria-hidden className="inline-block transition-none group-open:rotate-90">›</span>
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
