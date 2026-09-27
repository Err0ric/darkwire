"use client"

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { cn } from "cn"

import { FeedRow } from "@/components/FeedRow"
import { Input } from "@/components/ui/input"
import { SiteFooter } from "@/components/SiteFooter"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { AddedToKev, Elsewhere, LastSevenDays, MostActive, SourcesLine } from "@/components/wire/Rail"
import { Services } from "@/components/wire/Services"
import { WireClock } from "@/components/wire/WireClock"
import { useFitCount } from "@/lib/fit"
import {
  getElsewhere,
  getFeed,
  getKev,
  getServices,
  getStatus,
  getVendors,
  type FeedItem,
  type Severity,
} from "@/lib/api"
import { useDots } from "@/lib/dots"
import { useStickyTop } from "@/lib/sticky"
import { usePrefs } from "@/lib/prefs"
import { isImportant } from "@/lib/kev"
import { apply as applyDiff, changedSince, cursorOf, diff, LIVE_POLL_MS } from "@/lib/live"
import { groupByDay, useNow } from "@/lib/time"
import { useUnseen } from "@/lib/unseen"
import { feedQuery, stackCriticalQuery, TABS, type Filters, type WireData, type WireTab } from "@/lib/wire"

const PAGE = 50
// Rows: every 60s (lib/live.ts). The slower rail sections: every 15 minutes.
const RAIL_POLL_MS = 15 * 60 * 1000
// Scrolled further than this: new rows wait behind the "N new ↑" button instead of shifting the page.
const SCROLLED_PX = 160
// The API reads status pages every 3 minutes.
const SERVICES_POLL_MS = 3 * 60 * 1000
const SEARCH_DEBOUNCE_MS = 250
const ALL_VENDORS = "all"

// Filters live in the URL next to whatever else is there (?stack=, ?theme=).
function syncUrl(f: Filters) {
  const url = new URL(window.location.href)
  const set = (k: string, v: string) => (v ? url.searchParams.set(k, v) : url.searchParams.delete(k))
  set("tab", f.tab === "all" ? "" : f.tab)
  set("vendor", f.vendor)
  set("q", f.q)
  set("severity", f.severity)
  set("window", f.severity ? f.window : "")
  window.history.replaceState(null, "", url.pathname + url.search.replace(/%2C/gi, ",") + url.hash)
}

export function WireBoard({ initial }: { initial: WireData }) {
  const [filters, setFilters] = useState(initial.filters)
  const [query, setQuery] = useState(initial.filters.q)
  const [items, setItems] = useState(initial.feed.items)
  const [total, setTotal] = useState(initial.feed.total)
  const [fresh, setFresh] = useState<ReadonlySet<number>>(new Set())
  const [status, setStatus] = useState(initial.status)
  const [vendors, setVendors] = useState(initial.vendors)
  const [elsewhere, setElsewhere] = useState(initial.elsewhere)
  const [kev, setKev] = useState(initial.kev)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(initial.error)
  const [stackCritical, setStackCritical] = useState(initial.stackCritical)
  const [services, setServices] = useState(initial.services)
  const prefs = usePrefs()
  // Until the provider has read the URL, the server's stack is the truth.
  const stack = prefs.ready ? prefs.stack : initial.stack

  const filtersRef = useRef(filters)
  const itemsRef = useRef(items)
  const stackRef = useRef(initial.stack)
  const request = useRef(0)
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null)
  const addUnseen = useUnseen()
  const list = useRef<HTMLDivElement>(null)
  const fit = useFitCount(list)
  const { dots, add: addDots, clear: clearDot } = useDots()
  // Rails stick while the feed scrolls (lib/sticky.ts). Under 1200px the rail stacks below the
  // feed and is not sticky (no position: sticky there), so its computed top does nothing.
  const leftRail = useRef<HTMLElement>(null)
  const rightRail = useRef<HTMLElement>(null)
  useStickyTop(leftRail)
  useStickyTop(rightRail)
  const now = useNow()
  // New rows found while scrolled down, waiting for "N new ↑" or a scroll back to the top.
  const [pending, setPending] = useState<FeedItem[]>([])
  const pendingRef = useRef<FeedItem[]>([])
  // Cursor for an empty list: rows newer than the moment it loaded.
  const loadedAt = useRef(new Date().toISOString())
  const lastPoll = useRef(0)
  useEffect(() => {
    lastPoll.current = Date.now()
  }, [])

  useEffect(() => {
    itemsRef.current = items
  }, [items])

  const load = useCallback(async (f: Filters) => {
    const id = ++request.current
    setLoading(true)
    try {
      const page = await getFeed({ ...feedQuery(f, stackRef.current), limit: PAGE })
      if (id !== request.current) return
      setItems(page.items)
      setTotal(page.total)
      setFresh(new Set())
      pendingRef.current = []
      setPending([])
      loadedAt.current = new Date().toISOString()
      setFailed(false)
    } catch {
      if (id === request.current) setFailed(true)
    } finally {
      if (id === request.current) setLoading(false)
    }
  }, [])

  const apply = useCallback(
    (next: Partial<Filters>) => {
      const f = { ...filtersRef.current, ...next }
      filtersRef.current = f
      setFilters(f)
      syncUrl(f)
      void load(f)
    },
    [load],
  )

  function onSearch(value: string) {
    setQuery(value)
    if (debounce.current) clearTimeout(debounce.current)
    debounce.current = setTimeout(() => apply({ q: value.trim() }), SEARCH_DEBOUNCE_MS)
  }

  async function showMore() {
    const f = filtersRef.current
    try {
      const page = await getFeed({ ...feedQuery(f, stackRef.current), limit: PAGE, offset: itemsRef.current.length })
      if (f !== filtersRef.current) return
      setItems((prev) => {
        const seen = new Set(prev.map((p) => p.id))
        return [...prev, ...page.items.filter((i) => !seen.has(i.id))]
      })
      setTotal(page.total)
    } catch {
      setFailed(true)
    }
  }

  // Services: every 3 minutes, and at once when a remembered ?services= set differs from the
  // server's. A service newly in a major outage fires the unseen indicator like a Critical row.
  const watched = prefs.ready ? prefs.services.join(",") : null
  const majors = useRef(new Set((initial.services?.services ?? []).filter((s) => s.state === "major").map((s) => s.slug)))
  useEffect(() => {
    if (watched === null) return
    let cancelled = false
    const load = async () => {
      const next = await getServices(watched || undefined).catch(() => null)
      if (cancelled || !next) return
      setServices(next)
      const nowMajor = new Set(next.services.filter((s) => s.state === "major").map((s) => s.slug))
      const fresh = [...nowMajor].filter((s) => !majors.current.has(s))
      majors.current = nowMajor
      if (fresh.length) void addUnseen(fresh.length, true)
    }
    const serverSet = (initial.services?.services ?? []).map((s) => s.slug).join(",")
    const defaults = (initial.services?.defaults ?? []).join(",")
    if ((watched || defaults) !== serverSet) void load()
    const timer = setInterval(load, SERVICES_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [watched, addUnseen, initial.services])

  // The stack can change after first paint: restored from storage, or edited in another page.
  // Refetch what depends on it; a URL asking for tab=stack gets it once a stack exists.
  useEffect(() => {
    const key = stack.join(",")
    if (key === stackRef.current.join(",")) return
    stackRef.current = stack
    const refresh = async () => {
      setStackCritical(stack.length ? (await getFeed(stackCriticalQuery(stack)).catch(() => null))?.total ?? null : null)
    }
    void refresh()
    const wantsStack = new URLSearchParams(window.location.search).get("tab") === "stack"
    if (!stack.length && filtersRef.current.tab === "stack") apply({ tab: "all" })
    else if (stack.length && (filtersRef.current.tab === "stack" || wantsStack)) apply({ tab: "stack" })
  }, [stack, apply])

  // Put queued rows on top and give them their dots.
  const flush = useCallback(() => {
    const queued = pendingRef.current
    if (!queued.length) return
    pendingRef.current = []
    setPending([])
    setItems((prev) => applyDiff(prev, { fresh: queued, updated: new Map() }))
    setFresh(new Set(queued.map((i) => i.id)))
    addDots(queued.map((i) => i.id))
  }, [addDots])

  // Every 60s, hidden or not (the unseen count depends on it): rows with a newer event or any
  // newer change. New and escalated rows go on top with a dot and count as unseen; anything
  // else updates in place, silently. Scrolled down, new rows wait behind "N new ↑".
  useEffect(() => {
    const poll = async () => {
      const f = filtersRef.current
      const mine = stackRef.current
      const current = [...itemsRef.current, ...pendingRef.current]
      const since = cursorOf(current) ?? loadedAt.current
      const changed = changedSince(lastPoll.current)
      lastPoll.current = Date.now()
      const [feed, st, crit] = await Promise.allSettled([
        getFeed({ ...feedQuery(f, mine), limit: PAGE, since, changed_since: changed }),
        getStatus(),
        mine.length ? getFeed(stackCriticalQuery(mine)).then((p) => p.total) : Promise.resolve(null),
      ])
      if (crit.status === "fulfilled" && mine === stackRef.current) setStackCritical(crit.value)
      if (st.status === "fulfilled") setStatus(st.value)
      if (feed.status !== "fulfilled" || f !== filtersRef.current) return

      const d = diff(current, feed.value.items)
      if (d.updated.size) {
        setItems((prev) => prev.map((i) => d.updated.get(i.id) ?? i))
        pendingRef.current = pendingRef.current.map((i) => d.updated.get(i.id) ?? i)
      }
      if (d.added) setTotal((t) => t + d.added)
      if (!d.fresh.length) return

      // With a stack, only its rows count toward the unseen title and dot.
      const counted = mine.length ? d.fresh.filter((i) => i.vendor && mine.includes(i.vendor.slug)) : d.fresh
      void addUnseen(counted.length, counted.some(isImportant))

      const ids = new Set(d.fresh.map((i) => i.id))
      pendingRef.current = [...d.fresh, ...pendingRef.current.filter((i) => !ids.has(i.id))]
      if (window.scrollY > SCROLLED_PX) setPending(pendingRef.current)
      else flush()
    }
    const timer = setInterval(poll, LIVE_POLL_MS)
    return () => clearInterval(timer)
  }, [addUnseen, flush])

  // Back at the top: queued rows go in directly.
  useEffect(() => {
    const onScroll = () => {
      if (window.scrollY <= SCROLLED_PX && pendingRef.current.length) flush()
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [flush])

  // The slower rail sections.
  useEffect(() => {
    const poll = async () => {
      const [els, act, kv] = await Promise.allSettled([getElsewhere(5), getVendors("active"), getKev(7, 8)])
      if (els.status === "fulfilled") setElsewhere(els.value)
      if (act.status === "fulfilled") setVendors(act.value)
      if (kv.status === "fulfilled") setKev(kv.value)
    }
    const timer = setInterval(poll, RAIL_POLL_MS)
    return () => clearInterval(timer)
  }, [])

  // Tall displays: keep at least a screenful of rows loaded.
  const loadedRef = useRef(0)
  useEffect(() => {
    if (fit === null || items.length >= total || fit <= items.length || loadedRef.current >= fit) return
    loadedRef.current = fit
    const f = filtersRef.current
    getFeed({ ...feedQuery(f, stackRef.current), limit: Math.min(100, fit), offset: 0 })
      .then((page) => {
        if (f !== filtersRef.current) return
        setItems((prev) => (page.items.length > prev.length ? page.items : prev))
        setTotal(page.total)
      })
      .catch(() => undefined)
  }, [fit, items.length, total])

  // Header counts are 24h numbers, so their filter uses a 24h window; again clears it.
  // The rail's Last 7 days rows: 7-day window; clicking the active row clears it.
  const railSeverity = filters.window === "24h" ? "" : filters.severity
  const onRailSeverity = (s: Severity) =>
    apply(filters.severity === s && !filters.window ? { severity: "", window: "" } : { severity: s, window: "" })
  const toggle24h = (s: "critical" | "high"): Partial<Filters> =>
    filters.severity === s && filters.window === "24h" ? { severity: "", window: "" } : { severity: s, window: "24h" }
  const windowText = filters.severity ? (filters.window === "24h" ? "24 hours" : "7 days") : "14 days"

  const byName = [...vendors].sort((a, b) => a.name.localeCompare(b.name))
  const active = vendors.filter((v) => v.items_7d > 0).slice(0, 5)
  const counts = status?.counts
  const tabs: [WireTab, string][] = stack.length ? [["stack", "My stack"], ...TABS] : TABS

  return (
    <main className="flex-1 page-frame pb-24">
      {/* Rail beside the feed from 1000px, stacked below it under that; three columns
          (feed | Elsewhere | stats) from 2200px. The feed is fluid; no page cap. */}
      {/* Under 1200px: feed, then the rail stacked below it. 1200-2199px: feed plus one 340px
          rail on the right, 48px apart. 2200px+: one centered block (page-frame), stats rail 300
          | 64 | feed (max 1100) | 64 | Services and Elsewhere 300. Rails are sticky and start level
          with the tabs row. The rail sections are placed with CSS order per range. */}
      <div className="min-[1200px]:flex min-[1200px]:items-start min-[1200px]:gap-12 min-[2200px]:gap-16">
        <aside
          ref={leftRail}
          data-chrome
          aria-label="This week"
          className="sticky mt-[133px] hidden w-[300px] shrink-0 text-[13px] min-[2200px]:block"
        >
          <div className="flex flex-col gap-10">
            <LastSevenDays status={status} severity={railSeverity} onSeverity={onRailSeverity} />
            <AddedToKev kev={kev} query={prefs.query()} />
            <MostActive active={active} onVendor={(slug) => apply({ vendor: slug })} />
            <SourcesLine status={status} />
          </div>
        </aside>

        <div className="@container min-w-0 flex-1 min-[2200px]:max-w-[1100px]">
          <header className="pt-6 md:pt-[33px]">
            {/* The live clock is the heading; the date and UTC line sits on its baseline. */}
            <WireClock />
            <p className="mt-[3px] flex flex-wrap gap-x-4 text-[15px] leading-5 text-muted md:gap-x-0">
              {counts ? (
                <>
                  <Count
                    n={counts.critical_24h}
                    active={filters.severity === "critical" && filters.window === "24h"}
                    onClick={() => apply(toggle24h("critical"))}
                  >
                    critical
                  </Count>
                  <Count
                    n={counts.high_24h}
                    slash
                    active={filters.severity === "high" && filters.window === "24h"}
                    onClick={() => apply(toggle24h("high"))}
                  >
                    high
                  </Count>
                  <Count n={counts.kev_added_7d} slash>
                    added to KEV this week
                  </Count>
                  <Count n={counts.articles_24h} slash>
                    articles in the last 24h
                  </Count>
                </>
              ) : (
                <span className="text-dim">Counts unavailable.</span>
              )}
            </p>
            {stack.length > 0 && stackCritical === 0 && (
              <p className="mt-1 text-[13px] leading-5 text-muted">Nothing critical in your stack today.</p>
            )}
            {/* Rail stacked under the feed (< 1200px): Services moves up here so an outage is seen. */}
            <div data-chrome className="mt-6 max-w-[640px] text-[13px] min-[1200px]:hidden">
              <Services data={services} />
            </div>
          </header>

          {/* Tabs and filters share a line only when the feed column is wide enough for both;
              My stack adds a tab, so the split moves out. */}
          <div
            className={cn(
              "mt-8 flex flex-col-reverse border-b border-rule md:mt-[32px]",
              stack.length
                ? "@min-[1060px]:flex-row @min-[1060px]:items-end @min-[1060px]:justify-between"
                : "@min-[940px]:flex-row @min-[940px]:items-end @min-[940px]:justify-between",
            )}
          >
            <nav aria-label="Categories" className="-mb-px flex gap-6 overflow-x-auto [scrollbar-width:none]">
              {tabs.map(([tab, label]) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => apply({ tab })}
                  aria-pressed={filters.tab === tab}
                  className={cn(
                    "relative shrink-0 pb-[18px] text-[15px] leading-5 whitespace-nowrap outline-none focus-visible:text-fg",
                    filters.tab === tab ? "text-fg" : "text-muted hover:text-fg-2",
                  )}
                >
                  {label}
                  {filters.tab === tab && <span aria-hidden className="absolute inset-x-0 bottom-[6px] h-px bg-fg" />}
                </button>
              ))}
            </nav>
            <div
              className={cn(
                "mb-4 flex items-center gap-5",
                stack.length ? "@min-[1060px]:mb-[10px] @min-[1060px]:shrink-0" : "@min-[940px]:mb-[10px] @min-[940px]:shrink-0",
              )}
            >
              <Select
                value={filters.vendor || ALL_VENDORS}
                onValueChange={(v) => apply({ vendor: v === ALL_VENDORS ? "" : v })}
              >
                <SelectTrigger aria-label="Vendor" className="h-[30px] px-0 text-[15px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-80">
                  <SelectItem value={ALL_VENDORS}>All vendors</SelectItem>
                  {byName.map((v) => (
                    <SelectItem key={v.slug} value={v.slug}>
                      {v.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                type="search"
                value={query}
                onChange={(e) => onSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && onSearch("")}
                placeholder="Search or CVE ID"
                aria-label="Search headlines or CVE IDs"
                className={cn(
                  "h-[30px] min-w-0 flex-1",
                  stack.length ? "@min-[1060px]:w-[200px] @min-[1060px]:flex-none" : "@min-[940px]:w-[200px] @min-[940px]:flex-none",
                )}
              />
            </div>
          </div>

          {pending.length > 0 && (
            // Pinned under the tabs while scrolled; nothing above the viewer moves until asked.
            <div className="sticky top-3 z-10 flex h-0 justify-center">
              <button
                type="button"
                onClick={() => {
                  window.scrollTo({ top: 0 })
                  flush()
                }}
                className="mt-2 h-7 rounded-control border border-rule bg-bg px-3 font-mono text-xs text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
              >
                {pending.length} new ↑
              </button>
            </div>
          )}

          <div ref={list} className={cn(loading && "opacity-60")} aria-busy={loading}>
            {/* One section per local day of last_event_at (the sort key, also what the age column
                uses). The day label pins to the top while its rows scroll past; the next day's
                section pushes it out. Labels are not rows: no dot, not counted, not <article>. */}
            {(now === null ? [{ key: "all", name: "", date: "", today: true, items }] : groupByDay(items, now)).map((g, gi) => (
              <section key={g.key} aria-label={g.name || undefined} className={cn("[&>article:last-child]:border-b-0", gi > 0 && "mt-8")}>
                {g.name && (
                  <div
                    role="separator"
                    aria-label={`${g.name}, ${g.items.length} rows`}
                    className={cn(
                      "sticky top-0 z-[5] flex h-9 items-center border-t bg-bg text-[13px]",
                      // The tabs row's rule is already right above the first label.
                      gi === 0 ? "border-transparent" : "border-rule",
                    )}
                  >
                    <span className="font-semibold text-fg-2">{g.name}</span>
                    <span className="text-dim">
                      {g.name !== g.date && <>&nbsp;· {g.date}</>}&nbsp;· {g.items.length} {g.items.length === 1 ? "item" : "items"}
                    </span>
                  </div>
                )}
                {g.items.map((item) => (
                  <FeedRow
                    key={item.id}
                    item={item}
                    fresh={fresh.has(item.id)}
                    dot={dots.get(item.id)}
                    onSeen={() => clearDot(item.id)}
                    clockAge={!g.today}
                    inStack={filters.tab !== "stack" && !!item.vendor && stack.includes(item.vendor.slug)}
                  />
                ))}
              </section>
            ))}
          </div>

          {failed && items.length === 0 ? (
            <p className="py-10 text-[15px] text-muted">The feed is unreachable right now. It retries on the next refresh.</p>
          ) : items.length === 0 && !loading ? (
            <p className="py-10 text-[15px] text-muted">Nothing here in the last {windowText}.</p>
          ) : (
            <div className="flex items-baseline justify-between pt-6 text-[15px]">
              <span className="text-muted">
                {items.length} of {total} in the last {windowText}
              </span>
              {items.length < total && (
                <button type="button" onClick={showMore} className="text-fg-2 outline-none hover:text-fg focus-visible:text-fg">
                  Show more
                </button>
              )}
            </div>
          )}
        </div>

        <aside
          data-chrome
          aria-label="Context"
          ref={rightRail}
          className="mt-16 text-[13px] min-[1200px]:sticky min-[1200px]:mt-[133px] min-[1200px]:w-[340px] min-[1200px]:shrink-0 min-[2200px]:w-[300px]"
        >
          {/* Orders: under 1200 Elsewhere, Most active, Added to KEV, Last 7 days, Sources (Services
              sits above the feed). 1200-2199 Services, Added to KEV, Last 7 days, Elsewhere, Most
              active, Sources. 2200+ Services, Elsewhere; the rest is in the left rail. */}
          <div className="flex max-w-[640px] flex-col gap-10 min-[1200px]:max-w-none">
            <div className="hidden min-[1200px]:order-1 min-[1200px]:block">
              <Services data={services} />
            </div>
            <div className="order-3 min-[1200px]:order-2 min-[2200px]:hidden">
              <AddedToKev kev={kev} query={prefs.query()} />
            </div>
            <div className="order-4 min-[1200px]:order-3 min-[2200px]:hidden">
              <LastSevenDays status={status} severity={railSeverity} onSeverity={onRailSeverity} />
            </div>
            <div className="order-1 min-[1200px]:order-4 min-[2200px]:order-2">
              <Elsewhere elsewhere={elsewhere} />
            </div>
            <div className="order-2 min-[1200px]:order-5 min-[2200px]:hidden">
              <MostActive active={active} onVendor={(slug) => apply({ vendor: slug })} />
            </div>
            <div className="order-6 min-[2200px]:hidden">
              <SourcesLine status={status} />
            </div>
          </div>
        </aside>
      </div>
      <SiteFooter data-chrome className="mt-16" />
    </main>
  )
}

function Count({
  n,
  slash = false,
  active = false,
  onClick,
  children,
}: {
  n: number
  slash?: boolean
  active?: boolean
  /** Critical and high filter the wire to that severity (last 7 days); again clears it. */
  onClick?: () => void
  children: ReactNode
}) {
  // Desktop: "/" between counts, as in wire.png. Narrow screens wrap, so they use a gap instead.
  const body = (
    <>
      <span className="text-fg">{n}</span> {children}
    </>
  )
  return (
    <span className="whitespace-nowrap">
      {slash && (
        <span aria-hidden className="mx-[13px] hidden text-outline-medium md:inline">
          /
        </span>
      )}
      {onClick ? (
        <button
          type="button"
          onClick={onClick}
          aria-pressed={active}
          title={active ? "Clear the severity filter" : "Show this severity over the last 7 days"}
          className={cn(
            "relative outline-none hover:text-fg-2 focus-visible:text-fg-2",
            active && "after:absolute after:inset-x-0 after:-bottom-1 after:h-px after:bg-fg",
          )}
        >
          {body}
        </button>
      ) : (
        body
      )}
    </span>
  )
}
