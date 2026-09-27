"use client"

import Link from "next/link"
import { useEffect, useRef, useState, type ReactNode } from "react"
import { cn } from "cn"

import { FeedRow } from "@/components/FeedRow"
import { getFeed, getStatus, type FeedItem, type Status, type Tab } from "@/lib/api"
import { useUnseen } from "@/lib/unseen"

const LATEST = 8
const FEED_POLL_MS = Number(process.env.NEXT_PUBLIC_POLL_SECONDS ?? 900) * 1000
const STATUS_POLL_MS = 60_000

const HOME_TABS: [Tab, string][] = [
  ["all", "All"],
  ["vulnerabilities", "Vulnerabilities"],
  ["breaches", "Breaches"],
  ["kev", "KEV"],
]

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

const hhmm = (d: Date, seconds = false) =>
  d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: seconds ? "2-digit" : undefined, hour12: false })

function zoneName(d: Date): string {
  return new Intl.DateTimeFormat([], { timeZoneName: "short" }).formatToParts(d).find((p) => p.type === "timeZoneName")?.value ?? "UTC"
}

export function HomeBoard({
  initialItems,
  initialStatus,
  initialFailed,
}: {
  initialItems: FeedItem[]
  initialStatus: Status | null
  initialFailed: boolean
}) {
  const [tab, setTab] = useState<Tab>("all")
  const [items, setItems] = useState(initialItems)
  const [fresh, setFresh] = useState<ReadonlySet<number>>(new Set())
  const [status, setStatus] = useState(initialStatus)
  const [failed, setFailed] = useState(initialFailed)
  const tabRef = useRef(tab)
  const itemsRef = useRef(items)
  const request = useRef(0)
  const addUnseen = useUnseen()
  const now = useClock()

  useEffect(() => {
    itemsRef.current = items
  }, [items])

  async function choose(next: Tab) {
    tabRef.current = next
    setTab(next)
    const id = ++request.current
    try {
      const page = await getFeed({ tab: next, limit: LATEST })
      if (id !== request.current) return
      setItems(page.items)
      setFresh(new Set())
      setFailed(false)
    } catch {
      if (id === request.current) setFailed(true)
    }
  }

  // Latest rows every 15 minutes; rows not on screen before fade in and count as unseen.
  useEffect(() => {
    const timer = setInterval(async () => {
      const t = tabRef.current
      try {
        const page = await getFeed({ tab: t, limit: LATEST })
        if (t !== tabRef.current) return
        const known = new Set(itemsRef.current.map((i) => i.id))
        const incoming = page.items.filter((i) => !known.has(i.id))
        setItems(page.items)
        setFresh(new Set(incoming.map((i) => i.id)))
        void addUnseen(incoming.length, incoming.some((i) => i.severity === "critical" || i.kev))
      } catch {
        setFailed(true)
      }
    }, FEED_POLL_MS)
    return () => clearInterval(timer)
  }, [addUnseen])

  useEffect(() => {
    const timer = setInterval(() => {
      getStatus().then(setStatus, () => undefined)
    }, STATUS_POLL_MS)
    return () => clearInterval(timer)
  }, [])

  const counts = status?.counts
  const nextSync = status?.sync.next_run_at ? new Date(status.sync.next_run_at) : null

  return (
    <main className="flex flex-1 flex-col px-4 md:px-12">
      <header className="pt-6 md:pt-[39px]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <h1 className="min-h-7 text-[22px] leading-7 font-medium tracking-[-0.01em] text-fg">
            {now?.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}
          </h1>
          <Link
            href={tab === "all" ? "/wire" : `/wire?tab=${tab}`}
            className="mt-px inline-flex h-[30px] items-center gap-2 rounded-control border border-accent px-[14px] font-mono text-[13px] tracking-[0.04em] text-fg outline-none hover:text-fg focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            OPEN WIRE <span className="text-critical">→</span>
          </Link>
        </div>

        <p className="mt-[6px] flex min-h-5 flex-wrap gap-x-3 font-mono text-[13px] leading-5 text-muted md:gap-x-0" aria-live="off">
          {now && (
            <Part first>
              <span className="tabular-nums">{hhmm(now, true)}</span> {zoneName(now)}
            </Part>
          )}
          {counts && (
            <>
              <Part>
                <span className="text-critical">{counts.critical_24h}</span> critical
              </Part>
              <Part>
                <Num>{counts.high_24h}</Num> high
              </Part>
              <Part>
                <Num>{counts.kev_added_7d}</Num> added to kev / 7d
              </Part>
              <Part>
                <Num>{counts.items_24h}</Num> items / 24h
              </Part>
            </>
          )}
          {status && (
            <Part>
              sources{" "}
              <span className={status.sources_failing ? "text-critical" : "text-fg-2"}>
                {status.sources_ok}/{status.sources_total}
              </span>{" "}
              {status.sources_failing ? `${status.sources_failing} failing` : "ok"}
            </Part>
          )}
          {nextSync && <Part>next sync {hhmm(nextSync)}</Part>}
          {!status && <Part first={!now}>status unavailable</Part>}
        </p>
      </header>

      <div className="mt-[21px] flex items-baseline justify-between border-b border-rule pb-[9px]">
        <nav aria-label="Categories" className="flex gap-6">
          {HOME_TABS.map(([t, label]) => (
            <button
              key={t}
              type="button"
              onClick={() => choose(t)}
              aria-pressed={tab === t}
              className={cn("text-[15px] leading-5 outline-none focus-visible:text-fg", tab === t ? "text-fg" : "text-muted hover:text-fg-2")}
            >
              {label}
            </button>
          ))}
        </nav>
        <p className="hidden text-[13px] text-dim md:block">latest 8 · full feed, filters and detail on the wire</p>
      </div>

      <div>
        {items.map((item) => (
          <FeedRow key={item.id} item={item} fresh={fresh.has(item.id)} />
        ))}
        {items.length === 0 && (
          <p className="py-10 text-[15px] text-muted">
            {failed ? "The feed is unreachable right now. It retries on the next refresh." : "Nothing here in the last 14 days."}
          </p>
        )}
      </div>

      <footer className="mt-auto flex items-baseline justify-between gap-4 pt-16 pb-[30px] text-[13px] text-muted">
        <span>
          Sources: NVD, CISA KEV, vendor PSIRTs, {status?.sources_total ?? "–"} feeds. Refreshes every{" "}
          {status?.sync.interval_minutes ?? 15} minutes.
        </span>
        <span className="shrink-0">darkwire.tech</span>
      </footer>
    </main>
  )
}

function Part({ first = false, children }: { first?: boolean; children: ReactNode }) {
  // Desktop: "·" between parts, as in home.png. Narrow screens wrap, so they use a gap instead.
  return (
    <span className="whitespace-nowrap">
      {!first && (
        <span aria-hidden className="mx-3.5 hidden text-outline-medium md:inline">
          ·
        </span>
      )}
      {children}
    </span>
  )
}

function Num({ children }: { children: ReactNode }) {
  return <span className="text-fg-2">{children}</span>
}
