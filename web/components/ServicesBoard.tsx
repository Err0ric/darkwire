"use client"

import { useEffect, useRef, useState } from "react"
import { cn } from "cn"

import { PageHeader } from "@/components/PageHeader"
import { byImpact, isImpacted, StateDot } from "@/components/ServiceBits"
import { SiteFooter } from "@/components/SiteFooter"
import { getServices, type ServiceOut, type ServicesOut, type ServiceState } from "@/lib/api"
import { age, useNow } from "@/lib/time"

// /services: one screen. Header and a legend, "Impacted now" (one line per impacted service,
// with the incident), then the four groups as columns: each service's name line (state dot,
// name that opens its last 7 days of incidents, a summary on the right) over its 24-hour strip
// with an instant tooltip per hour; then Stale, collapsed. 4 columns from 1600px, 2x2 from
// 1200px, stacked below. No boxes: columns separate by gap.

const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const
const POLL_MS = 3 * 60 * 1000

const STATE_WORD = { major: "major", degraded: "degraded" } as const

export function ServicesBoard({ initial, open = null }: { initial: ServicesOut | null; open?: string | null }) {
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
      <PageHeader title="Services">
        {data ? (
          <>
            <span className="text-fg">{all.length}</span> tracked · <span className="text-fg">{impacted.length}</span> impacted
            {checked && now !== null && <> · checked {age(checked, now)} ago</>}
          </>
        ) : (
          "The API is unreachable right now."
        )}
      </PageHeader>
      {data && <Legend />}

      {data && <ImpactedNow services={impacted} total={all.length} now={now} />}

      {data && (
        <div className="mt-10 grid gap-x-12 gap-y-10 min-[1200px]:grid-cols-2 min-[1600px]:grid-cols-4">
          {data.groups.map((group) => {
            const rows = all.filter((s) => s.group === group).sort(byImpact)
            return rows.length ? <Group key={group} name={group} services={rows} open={open} /> : null
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
          <li key={s.slug} className="flex min-h-11 items-baseline gap-x-3 border-b border-hairline py-3 text-[15px] hover:bg-surface">
            <StateDot state={s.state} className="relative -top-px self-center" />
            <span className="shrink-0 text-fg">{s.name}</span>
            <span className={cn("shrink-0", s.state === "major" ? "text-critical-text" : "text-degraded")}>
              {s.state === "major" ? STATE_WORD.major : STATE_WORD.degraded}
            </span>
            <a
              href={s.incident?.url ?? s.page}
              {...EXTERNAL}
              className="max-md:tap min-w-0 flex-1 text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
            >
              {s.incident?.title ?? "Status page"} <span aria-hidden className="text-[11px] text-critical-text">↗</span>
            </a>
            {/* The age slot is reserved from the first render: filling it in after mount must not
                narrow the title (on a phone that re-wraps it and shifts the grid below). */}
            {s.incident?.started_at && (
              <span className="w-[4ch] shrink-0 text-right font-mono text-xs text-muted">
                {now !== null ? age(s.incident.started_at, now) : ""}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

const SWATCH: [string, string][] = [
  ["bg-strip-ok", "operational"],
  ["bg-degraded", "degraded"],
  ["bg-critical", "major"],
  ["bg-transparent ring-1 ring-inset ring-rule", "no data"],
]

/** What the strips mean, once, under the header. */
function Legend() {
  return (
    <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] leading-4 text-muted">
      {SWATCH.map(([cls, label]) => (
        <span key={label} className="inline-flex items-center gap-1.5">
          <span aria-hidden className={cn("inline-block h-2.5 w-[5px]", cls)} />
          {label}
        </span>
      ))}
      <span className="text-dim-text">each block = 1 hour, your local time</span>
    </p>
  )
}

function Group({ name, services, open }: { name: string; services: ServiceOut[]; open: string | null }) {
  return (
    <section aria-label={name} className="min-w-0">
      <h2 className="border-b border-rule pb-2.5 text-[13px] font-medium text-fg">{name}</h2>
      {/* The strips' time axis, once per column: -24h at the first cell, -12h at the 13th
          (12 hours before the current one), now at the end. */}
      <div aria-hidden className="relative mt-2 h-4 font-mono text-[11px] leading-4 text-dim-text">
        <span className="absolute left-0">-24h</span>
        <span className="absolute" style={{ left: "calc((100% + 2px) * 12 / 24)" }}>
          -12h
        </span>
        <span className="absolute right-0">now</span>
      </div>
      <ul className="mt-1">
        {services.map((s) => (
          <ServiceLine key={s.slug} s={s} startOpen={open === s.slug} />
        ))}
      </ul>
    </section>
  )
}

const HOUR = 3_600_000
const hm = (d: Date) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`

/** Start of cell i (hours are oldest first, the last one is the current hour). */
function cellStart(i: number, count: number, nowMs: number): Date {
  return new Date(Math.floor(nowMs / HOUR) * HOUR - (count - 1 - i) * HOUR)
}

/** Impacted now: only the impacted hours in the state's color ("6h of 24h", or "6h since 11:00"
 * when tracking covers less than 24 hours). Otherwise "100%" when every tracked hour was
 * operational, else "major 2h · degraded 6h", plus "since 16:00" for a shorter window. */
function Summary({ hours, now, state }: { hours: ServiceState[]; now: number | null; state: ServiceState }) {
  const major = hours.filter((h) => h === "major").length
  const degraded = hours.filter((h) => h === "degraded").length
  const first = hours.findIndex((h) => h !== "unknown")
  const since = now !== null && first > 0 ? hm(cellStart(first, hours.length, now)) : null
  if (first < 0) return <span className="ml-auto shrink-0 pl-2 font-mono text-xs text-dim-text">no data</span>
  // Impacted now: the name line already says the state, so only how long, in its color.
  if (state === "major" || state === "degraded") {
    const hrs = major + degraded
    return (
      <span className={cn("ml-auto shrink-0 pl-2 font-mono text-xs whitespace-nowrap", state === "major" ? "text-critical-text" : "text-degraded")}>
        {since ? `${hrs}h since ${since}` : `${hrs}h of 24h`}
      </span>
    )
  }
  return (
    <span className="ml-auto shrink-0 pl-2 font-mono text-xs whitespace-nowrap">
      {major > 0 && <span className="text-critical-text">major {major}h</span>}
      {major > 0 && degraded > 0 && <span className="text-dim-text"> · </span>}
      {degraded > 0 && <span className="text-degraded">degraded {degraded}h</span>}
      {major === 0 && degraded === 0 && <span className="text-dim-text">100%</span>}
      {since && <span className="text-dim-text"> · since {since}</span>}
    </span>
  )
}

const CELL_WORD: Record<ServiceState, string> = { operational: "operational", degraded: "degraded", major: "major", unknown: "no data" }
const CELL: Record<ServiceState, string> = {
  operational: "bg-strip-ok",
  degraded: "bg-degraded",
  major: "bg-critical",
  unknown: "bg-transparent ring-1 ring-inset ring-rule",
}

/** The 24-hour strip with an instant tooltip: hover a cell, or focus the strip and move with
 * the arrow keys (Home / End jump to the ends). */
function Strip({ hours, name }: { hours: ServiceState[]; name: string }) {
  const now = useNow()
  const [active, setActive] = useState<number | null>(null)
  const label = (i: number) => {
    if (now === null) return CELL_WORD[hours[i]]
    const start = cellStart(i, hours.length, now)
    return `${hm(start)}–${hm(new Date(start.getTime() + HOUR))} · ${CELL_WORD[hours[i]]}`
  }
  const impacted = hours.filter((h) => h === "degraded" || h === "major").length
  return (
    <div
      role="group"
      tabIndex={0}
      aria-label={`${name}, last 24 hours: ${impacted ? `${impacted} hours impacted` : "no impact"}. Arrow keys read each hour.`}
      onFocus={() => setActive((a) => a ?? hours.length - 1)}
      onBlur={() => setActive(null)}
      onMouseLeave={() => setActive(null)}
      onKeyDown={(e) => {
        const last = hours.length - 1
        const at = active ?? last
        const next =
          e.key === "ArrowLeft" ? Math.max(0, at - 1) : e.key === "ArrowRight" ? Math.min(last, at + 1) : e.key === "Home" ? 0 : e.key === "End" ? last : null
        if (next !== null) {
          e.preventDefault()
          setActive(next)
        }
      }}
      className="relative mt-1.5 flex gap-0.5 outline-none max-md:tap max-md:mt-5"
    >
      {hours.map((h, i) => (
        <span
          key={i}
          onMouseEnter={() => setActive(i)}
          className={cn("h-2.5 min-w-0 flex-1", CELL[h], active === i && "outline outline-1 outline-fg-2")}
        />
      ))}
      {active !== null && (
        <span
          role="tooltip"
          aria-live="polite"
          className="pointer-events-none absolute bottom-full z-20 mb-1.5 -translate-x-1/2 rounded-control border border-rule bg-surface px-2 py-1 font-mono text-[11px] leading-4 whitespace-nowrap text-fg-2"
          style={{ left: `calc((100% + 2px) * ${(active + 0.5) / hours.length} - 1px)` }}
        >
          {label(active)}
        </span>
      )}
    </div>
  )
}

function duration(ms: number): string {
  const m = Math.max(1, Math.round(ms / 60_000))
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return m % 60 ? `${h}h ${m % 60}m` : `${h}h`
  return `${Math.floor(h / 24)}d ${h % 24}h`
}

function when(iso: string): string {
  const d = new Date(iso)
  return `${d.toLocaleDateString([], { month: "short", day: "numeric" })} ${hm(d)}`
}

/** A service's name line (the name opens its incidents of the last 7 days) and its strip. */
function ServiceLine({ s, startOpen }: { s: ServiceOut; startOpen: boolean }) {
  const now = useNow()
  const [open, setOpen] = useState(startOpen)
  const row = useRef<HTMLLIElement>(null)
  const panel = `svc-${s.slug}-incidents`
  // Opened from a link (?open=slug): scroll it into view.
  useEffect(() => {
    if (startOpen) row.current?.scrollIntoView({ block: "center" })
  }, [startOpen])
  const incidents = s.incidents ?? []
  return (
    <li ref={row} className="-mx-2 px-2 py-2 hover:bg-surface max-md:py-3">
      <p className="flex items-center gap-2.5 text-[15px] leading-5">
        <StateDot state={s.state} />
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls={panel}
          className="max-md:tap min-w-0 truncate text-left text-fg outline-none hover:underline focus-visible:underline"
        >
          {s.name}
        </button>
        {isImpacted(s) && (
          <span className={s.state === "major" ? "text-critical-text" : "text-degraded"}>
            {s.state === "major" ? STATE_WORD.major : STATE_WORD.degraded}
          </span>
        )}
        <Summary hours={s.hours} now={now} state={s.state} />
      </p>
      <Strip hours={s.hours} name={s.name} />
      {open && (
        <div id={panel} className="mt-2.5 border-t border-hairline pt-2 text-[12px] leading-5">
          {incidents.length === 0 ? (
            <p className="text-muted">No incidents in the last 7 days.</p>
          ) : (
            <ul>
              {incidents.map((inc, i) => (
                <li key={i} className="flex items-baseline gap-2">
                  <span className={cn("w-10 shrink-0 font-mono", inc.state === "major" ? "text-critical-text" : "text-degraded")}>
                    {inc.state === "major" ? "major" : "degr."}
                  </span>
                  <a
                    href={inc.url ?? s.page}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="max-md:tap min-w-0 flex-1 truncate text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
                  >
                    {inc.title ?? "Incident"}
                  </a>
                  {inc.started_at && (
                    <span className="shrink-0 font-mono text-dim-text">
                      {when(inc.started_at)}–{inc.ended_at ? hm(new Date(inc.ended_at)) : "now"}
                      {now !== null && <> · {duration((inc.ended_at ? Date.parse(inc.ended_at) : now) - Date.parse(inc.started_at))}</>}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          <a
            href={s.page}
            target="_blank"
            rel="noopener noreferrer"
            className="max-md:tap mt-1 inline-block text-muted outline-none hover:text-fg-2 focus-visible:text-fg-2"
          >
            Status page <span aria-hidden className="text-[11px] text-critical-text">↗</span>
          </a>
        </div>
      )}
    </li>
  )
}

/** Events the vendor has not touched in 72h+: kept visible, collapsed, and never counted. */
function Stale({ services, now }: { services: ServiceOut[]; now: number | null }) {
  const events = services.flatMap((s) => s.stale.map((e) => ({ service: s, e })))
  if (!events.length) return null
  return (
    <details className="group mt-10 text-dim-text">
      <summary className="max-md:tap flex cursor-pointer list-none items-baseline gap-2 border-b border-rule pb-2.5 text-[13px] font-medium outline-none hover:text-muted focus-visible:text-muted">
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
              className="max-md:tap min-w-0 flex-1 truncate outline-none hover:text-muted focus-visible:text-muted"
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
