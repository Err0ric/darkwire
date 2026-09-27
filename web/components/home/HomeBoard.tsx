"use client"

import Link from "next/link"
import { useEffect, useState, type ReactNode } from "react"
import { cn } from "cn"

import { PrefsControls } from "@/components/PrefsControls"
import { byImpact, isImpacted } from "@/components/ServiceBits"
import { getFeed, getServices, getStatus, type FeedItem, type ServicesOut, type Status } from "@/lib/api"
import { kevDueIn } from "@/lib/kev"
import { usePrefs } from "@/lib/prefs"
import { age, useNow } from "@/lib/time"

// Home: a landing page. Centered block (date, clock, status line, Right now, ticker, OPEN WIRE,
// stack link), footer at the bottom. Sized in em off one clamp() on the block, so it scales
// with the viewport instead of jumping at breakpoints, and fits 1920x1080 and 2560x1440
// without scrolling.

const STATUS_POLL_MS = 60_000
const FEED_POLL_MS = 60_000
const SERVICES_POLL_MS = 3 * 60_000
const TICKER_MS = 8_000
const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const

export interface HomeData {
  rightNow: FeedItem[]
  latest: FeedItem[]
  status: Status | null
  services: ServicesOut | null
  failed: boolean
}

/** Wall clock in the viewer's zone, ticking every second. Null until mounted (no server time). */
function useClock(): Date | null {
  const [now, setNow] = useState<Date | null>(null)
  useEffect(() => {
    const tick = () => setNow(new Date())
    const first = setTimeout(tick, 0)
    const timer = setInterval(tick, 1000)
    return () => {
      clearTimeout(first)
      clearInterval(timer)
    }
  }, [])
  return now
}

function zoneName(d: Date): string {
  return new Intl.DateTimeFormat([], { timeZoneName: "short" }).formatToParts(d).find((p) => p.type === "timeZoneName")?.value ?? "UTC"
}

const pad = (n: number) => String(n).padStart(2, "0")

export function HomeBoard({ initial }: { initial: HomeData }) {
  const [rightNow, setRightNow] = useState(initial.rightNow)
  const [latest, setLatest] = useState(initial.latest)
  const [status, setStatus] = useState(initial.status)
  const [services, setServices] = useState(initial.services)
  const { query, services: watched, ready } = usePrefs()
  const clock = useClock()

  useEffect(() => {
    const timer = setInterval(() => getStatus().then(setStatus).catch(() => undefined), STATUS_POLL_MS)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    const load = () => {
      getFeed({ pinned: true, limit: 5 }).then((p) => setRightNow(p.items)).catch(() => undefined)
      getFeed({ limit: 10 }).then((p) => setLatest(p.items)).catch(() => undefined)
    }
    const timer = setInterval(load, FEED_POLL_MS)
    return () => clearInterval(timer)
  }, [])

  const slugs = ready ? watched.join(",") : null
  useEffect(() => {
    if (slugs === null) return
    const load = () => getServices(slugs || undefined).then(setServices).catch(() => undefined)
    if (slugs) void load()
    const timer = setInterval(load, SERVICES_POLL_MS)
    return () => clearInterval(timer)
  }, [slugs])

  return (
    // One screen tall: the block centers in whatever the nav and footer leave.
    <main className="flex min-h-[calc(100dvh/var(--zoom)-var(--nav-h))] flex-col px-4 md:px-12">
      <div
        className="mx-auto my-auto flex w-full max-w-[62em] flex-col items-center py-[2.5em] text-center"
        style={{ fontSize: "clamp(14px, calc(0.6vw + 0.55vh), 22px)" }}
      >
        <Clock now={clock} />
        <StatusLine status={status} services={services} query={query} />
        <RightNow items={rightNow} failed={initial.failed && !rightNow.length} />
        <Ticker items={latest} />

        <Link
          href={`/wire${query()}`}
          className="mt-[2.4em] inline-flex h-[2.8em] items-center gap-[0.8em] rounded-control border border-accent px-[1.9em] font-mono text-[0.95em] font-medium tracking-[0.08em] text-fg outline-none hover:border-critical focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          OPEN WIRE <span className="text-critical">→</span>
        </Link>
        <nav aria-label="More" className="mt-[1.1em] flex gap-[1.7em] text-[0.88em] text-muted">
          {[
            ["/cves", "CVEs"],
            ["/vendors", "Vendors"],
            ["/outages", "Outages"],
          ].map(([href, label]) => (
            <Link key={href} href={`${href}${query()}`} className="outline-none hover:text-fg-2 focus-visible:text-fg-2">
              {label}
            </Link>
          ))}
        </nav>
        <Link
          href={`/vendors${query()}`}
          className="mt-[2.4em] text-[0.88em] text-muted underline decoration-rule underline-offset-[0.35em] outline-none hover:text-fg-2 focus-visible:text-fg-2"
        >
          Pick your vendors to filter everything to your stack →
        </Link>
      </div>

      <footer className="flex shrink-0 flex-col gap-2 pt-6 pb-[30px] text-[13px] text-muted sm:flex-row sm:items-baseline sm:justify-between sm:gap-6">
        <span>
          {status
            ? `Aggregated from NVD, CISA KEV, vendor PSIRTs and ${status.sources_total} feeds. No accounts, no tracking.`
            : "Aggregated from NVD, CISA KEV and vendor PSIRTs. No accounts, no tracking."}
        </span>
        <span className="flex shrink-0 flex-wrap items-baseline gap-x-6">
          <PrefsControls />
          <span>darkwire.tech</span>
        </span>
      </footer>
    </main>
  )
}

function Clock({ now }: { now: Date | null }) {
  // Heights are reserved so nothing moves when the client fills the time in.
  return (
    <div>
      <p className="h-[1.4em] text-[1.3em] leading-[1.4em] text-fg-2">
        {now?.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}
      </p>
      <p
        className="h-[1.05em] font-mono leading-[1.05em] font-normal tracking-[-0.02em] text-fg tabular-nums"
        style={{ fontSize: "clamp(52px, min(10.5vh, 13vw), 200px)" }}
      >
        {now && (
          <time dateTime={now.toISOString()}>
            {pad(now.getHours())}:{pad(now.getMinutes())}
            <span className="text-dim">:{pad(now.getSeconds())}</span>
          </time>
        )}
      </p>
      <p className="mt-[0.5em] h-[1.2em] font-mono text-[0.72em] tracking-[0.08em] text-dim">{now && zoneName(now)}</p>
    </div>
  )
}

function StatusLine({
  status,
  services,
  query,
}: {
  status: Status | null
  services: ServicesOut | null
  query: (extra?: Record<string, string | undefined>) => string
}) {
  const parts: ReactNode[] = []
  const critical = status?.counts.critical_24h ?? 0
  const kevDue = status?.counts.kev_due_7d ?? 0
  const impacted = (services?.services ?? []).filter(isImpacted).sort(byImpact)
  if (critical)
    parts.push(
      <Part key="c" dot="bg-critical" href={`/wire${query({ severity: "critical", window: "24h" })}`}>
        <span className="text-fg">{critical}</span> critical
      </Part>,
    )
  if (kevDue)
    parts.push(
      <Part key="k" dot="bg-critical" href={`/wire${query({ tab: "kev" })}`}>
        <span className="text-fg">{kevDue}</span> KEV due this week
      </Part>,
    )
  if (impacted.length) {
    const worst = impacted[0]
    parts.push(
      <Part key="s" dot={worst.state === "major" ? "bg-critical" : "bg-degraded"} href={`/outages${query()}`}>
        {worst.name} {worst.state === "major" ? "major outage" : "degraded"}
        {impacted.length > 1 && <span className="text-muted"> +{impacted.length - 1}</span>}
      </Part>,
    )
  }
  return (
    <div className="mt-[2em] flex min-h-[1.5em] flex-wrap items-center justify-center gap-x-[1.1em] gap-y-[0.4em] text-[1.05em] text-fg-2">
      {parts.length ? (
        parts.map((p, i) => (
          <span key={i} className="flex items-center gap-x-[1.1em]">
            {i > 0 && (
              // Narrow screens wrap the parts; a separator would start the second line.
              <span aria-hidden className="hidden text-dim sm:inline">
                ·
              </span>
            )}
            {p}
          </span>
        ))
      ) : status ? (
        <span className="text-muted">All quiet</span>
      ) : null}
    </div>
  )
}

function Part({ dot, href, children }: { dot: string; href: string; children: ReactNode }) {
  return (
    <Link href={href} className="flex items-center gap-[0.5em] outline-none hover:text-fg focus-visible:text-fg">
      <span aria-hidden className={cn("size-[0.4em] rounded-full", dot)} />
      <span>{children}</span>
    </Link>
  )
}

// ---------------------------------------------------------------- Right now

function RightNow({ items, failed }: { items: FeedItem[]; failed: boolean }) {
  return (
    <section aria-label="Right now" className="mt-[2.2em] w-full text-left">
      <div className="flex items-baseline gap-[1em] border-b border-rule pb-[0.6em]">
        <h2 className="text-[0.85em] font-medium text-fg">Right now</h2>
        <span className="text-[0.75em] text-muted">critical, KEV and exploited · last 48h</span>
      </div>
      {items.length ? (
        <ul>
          {items.slice(0, 5).map((item) => (
            <RightNowRow key={item.id} item={item} />
          ))}
        </ul>
      ) : (
        <p className="border-b border-hairline py-[1em] text-[0.9em] text-muted">
          {failed ? "The feed is unreachable right now." : "Nothing critical in the last 48h."}
        </p>
      )}
    </section>
  )
}

const BADGE: Record<string, string> = {
  critical: "border-critical bg-critical text-on-critical",
  high: "border-accent text-fg",
  medium: "border-outline-medium text-fg-2",
  low: "border-outline-muted text-muted",
  exploited: "border-accent text-critical",
}

const BAR_FILL: Record<string, string> = { critical: "bg-critical", high: "bg-accent", medium: "bg-medium", low: "bg-dim" }

function RightNowRow({ item }: { item: FeedItem }) {
  const { query } = usePrefs()
  const now = useNow()
  const severity = item.severity && item.severity !== "none" ? item.severity : null
  const badge = severity ?? (item.exploited ? "exploited" : null)

  // Right side tag: KEV due / KEV, else "no fix yet" when vendor data says there is none.
  const due = now === null ? null : kevDueIn(item, now)
  const tag =
    due !== null ? (
      <span className="text-critical">{due < 0 ? "KEV overdue" : due === 0 ? "KEV due today" : `KEV due in ${due}d`}</span>
    ) : item.kev ? (
      <span className="text-critical">KEV</span>
    ) : item.patch_status === "no_fix" ? (
      <span className="text-muted">no fix yet</span>
    ) : null

  const score = item.cvss !== null && (
    <span className={cn("font-mono text-[0.95em] font-medium", item.cvss >= 7 ? "text-fg" : "text-fg-2")}>
      {item.cvss.toFixed(1)}
    </span>
  )
  const badgeEl = badge && (
    <span
      className={cn(
        "inline-flex h-[1.4em] w-[7em] shrink-0 items-center justify-center rounded-badge border font-mono text-[0.66em] font-medium tracking-[0.04em] uppercase",
        BADGE[badge],
      )}
    >
      {badge}
    </span>
  )

  return (
    <li className="border-b border-hairline">
      <Link
        href={`/item/${item.id}${query()}`}
        className="group block py-[0.8em] outline-none focus-visible:bg-surface sm:flex sm:h-[3.35em] sm:items-center sm:py-0"
      >
        {/* Wide: score · bar · badge · headline · tag · age on one line. Narrow: headline, then the rest, no bar. */}
        <span className="hidden w-[2.8em] shrink-0 pl-[0.4em] sm:block">{score}</span>
        <span className="hidden w-[6em] shrink-0 sm:block">
          {item.cvss !== null && (
            <span className="flex gap-[0.12em]" aria-label={`CVSS ${item.cvss}`}>
              {Array.from({ length: 10 }, (_, i) => (
                <span
                  key={i}
                  className={cn("h-[0.6em] w-[0.3em]", i < Math.round(item.cvss ?? 0) ? BAR_FILL[severity ?? "medium"] : "bg-rule")}
                />
              ))}
            </span>
          )}
        </span>
        <span className="hidden w-[6.4em] shrink-0 sm:block">{badgeEl}</span>
        <span className="block min-w-0 flex-1 text-[1em] leading-[1.35em] font-medium tracking-[-0.01em] text-fg group-hover:underline sm:truncate">
          {item.headline}
        </span>
        <span className="mt-[0.4em] flex items-center gap-[0.8em] sm:mt-0 sm:ml-[1.5em] sm:gap-0">
          <span className="sm:hidden">{badgeEl}</span>
          <span className="sm:hidden">{score}</span>
          <span className="font-mono text-[0.72em] whitespace-nowrap sm:w-[9em] sm:text-right">{tag}</span>
          <span className="ml-auto font-mono text-[0.72em] text-muted sm:ml-0 sm:w-[4em] sm:text-right">
            {now !== null && age(item.last_event_at, now)}
          </span>
        </span>
      </Link>
    </li>
  )
}

// ---------------------------------------------------------------- ticker

/** The latest headline, crossfading to the next every 8s through the last 10. Not a marquee:
 * nothing scrolls. Under prefers-reduced-motion it stays on the newest. */
function Ticker({ items }: { items: FeedItem[] }) {
  const now = useNow()
  const [index, setIndex] = useState(0)
  const list = items.slice(0, 10)

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || list.length < 2) return
    const timer = setInterval(() => setIndex((i) => i + 1), TICKER_MS)
    return () => clearInterval(timer)
  }, [list.length])

  if (!list.length) return null
  const active = index % list.length
  return (
    <div className="relative mt-[2.2em] h-[1.5em] w-full">
      {list.map((item, i) => (
        <p
          key={item.id}
          aria-hidden={i !== active}
          className={cn(
            "absolute inset-0 flex items-baseline justify-center gap-[0.8em] transition-opacity duration-700 motion-reduce:transition-none",
            i === active ? "opacity-100" : "pointer-events-none opacity-0",
          )}
        >
          <span aria-hidden className="text-critical">
            ›
          </span>
          <a
            href={item.primary_url}
            {...EXTERNAL}
            tabIndex={i === active ? 0 : -1}
            className="min-w-0 truncate text-[1em] text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
          >
            {item.headline}
          </a>
          <span className="hidden shrink-0 font-mono text-[0.68em] text-dim sm:inline">
            {item.sources[0]?.name}
            {now !== null && <> · {age(item.last_event_at, now)}</>}
          </span>
        </p>
      ))}
    </div>
  )
}
