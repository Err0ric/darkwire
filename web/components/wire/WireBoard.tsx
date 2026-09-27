"use client"

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { cn } from "cn"

import { FeedRow } from "@/components/FeedRow"
import { Input } from "@/components/ui/input"
import { SiteFooter } from "@/components/SiteFooter"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Elsewhere, Stats } from "@/components/wire/Rail"
import { useFitCount } from "@/lib/fit"
import {
  getElsewhere,
  getFeed,
  getKev,
  getStatus,
  getVendors,
  type FeedItem,
} from "@/lib/api"
import { usePrefs } from "@/lib/prefs"
import { useUnseen } from "@/lib/unseen"
import { feedQuery, stackCriticalQuery, TABS, type Filters, type WireData, type WireTab } from "@/lib/wire"

const PAGE = 50
// 15 minutes. Overridable at build time for local testing only.
const POLL_MS = Number(process.env.NEXT_PUBLIC_POLL_SECONDS ?? 900) * 1000
const SEARCH_DEBOUNCE_MS = 250
const ALL_VENDORS = "all"

// Filters live in the URL next to whatever else is there (?stack=, ?theme=).
function syncUrl(f: Filters) {
  const url = new URL(window.location.href)
  const set = (k: string, v: string) => (v ? url.searchParams.set(k, v) : url.searchParams.delete(k))
  set("tab", f.tab === "all" ? "" : f.tab)
  set("vendor", f.vendor)
  set("q", f.q)
  window.history.replaceState(null, "", url.pathname + url.search.replace(/%2C/gi, ",") + url.hash)
}

function mergeNewest(prev: FeedItem[], incoming: FeedItem[]): FeedItem[] {
  const ids = new Set(incoming.map((i) => i.id))
  return [...incoming, ...prev.filter((p) => !ids.has(p.id))]
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

  // Every 15 minutes: rows with an event newer than the top row, plus counts and rail.
  useEffect(() => {
    const poll = async () => {
      const f = filtersRef.current
      const mine = stackRef.current
      const newest = itemsRef.current[0]?.last_event_at
      const [feed, st, els, act, kv, crit] = await Promise.allSettled([
        getFeed({ ...feedQuery(f, mine), limit: PAGE, since: newest }),
        getStatus(),
        getElsewhere(5),
        getVendors("active"),
        getKev(7, 8),
        mine.length ? getFeed(stackCriticalQuery(mine)).then((p) => p.total) : Promise.resolve(null),
      ])
      if (crit.status === "fulfilled" && mine === stackRef.current) setStackCritical(crit.value)
      if (st.status === "fulfilled") setStatus(st.value)
      if (els.status === "fulfilled") setElsewhere(els.value)
      if (act.status === "fulfilled") setVendors(act.value)
      if (kv.status === "fulfilled") setKev(kv.value)
      if (feed.status !== "fulfilled" || f !== filtersRef.current) return
      const incoming = newest ? feed.value.items : []
      if (!incoming.length) return
      const known = new Set(itemsRef.current.map((i) => i.id))
      setItems((prev) => mergeNewest(prev, incoming))
      setTotal((t) => t + incoming.filter((i) => !known.has(i.id)).length)
      setFresh(new Set(incoming.map((i) => i.id)))
      // With a stack, only its rows count toward the unseen title and dot.
      const counted = mine.length ? incoming.filter((i) => i.vendor && mine.includes(i.vendor.slug)) : incoming
      void addUnseen(counted.length, counted.some((i) => !i.stale && (i.severity === "critical" || i.kev)))
    }
    const timer = setInterval(poll, POLL_MS)
    return () => clearInterval(timer)
  }, [addUnseen])

  // Tall displays: keep at least a screenful of rows loaded.
  const loadedRef = useRef(0)
  useEffect(() => {
    if (fit === null || items.length >= total || fit <= items.length || loadedRef.current >= fit) return
    loadedRef.current = fit
    const f = filtersRef.current
    getFeed({ ...feedQuery(f, stackRef.current), limit: Math.min(200, fit), offset: 0 })
      .then((page) => {
        if (f !== filtersRef.current) return
        setItems((prev) => (page.items.length > prev.length ? page.items : prev))
        setTotal(page.total)
      })
      .catch(() => undefined)
  }, [fit, items.length, total])

  const byName = [...vendors].sort((a, b) => a.name.localeCompare(b.name))
  const active = vendors.filter((v) => v.items_7d > 0).slice(0, 5)
  const counts = status?.counts
  const tabs: [WireTab, string][] = stack.length ? [["stack", "My stack"], ...TABS] : TABS

  return (
    <main className="flex-1 px-4 pb-24 md:px-12">
      {/* Rail beside the feed from 1000px, stacked below it under that; three columns
          (feed | Elsewhere | stats) from 2200px. The feed is fluid; no page cap. */}
      <div className="min-[1200px]:flex min-[1200px]:gap-16">
        {/* Feed: basis and cap 1200px so the data columns stay near the headline; the rail
            takes whatever is left (at least 280px). */}
        <div className="@container min-w-0 flex-1 min-[1200px]:max-w-[1200px] min-[1200px]:flex-[1_1_1200px]">
          <header className="pt-6 md:pt-[33px]">
            <h1 className="text-[36px] leading-[44px] font-bold tracking-[-0.02em] text-fg">Today</h1>
            <p className="mt-[3px] flex flex-wrap gap-x-4 text-[15px] leading-5 text-muted md:gap-x-0">
              {counts ? (
                <>
                  <Count n={counts.critical_24h}>critical</Count>
                  <Count n={counts.high_24h} slash>
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

          <div ref={list} className={cn(loading && "opacity-60")} aria-busy={loading}>
            {items.map((item) => (
              <FeedRow
                key={item.id}
                item={item}
                fresh={fresh.has(item.id)}
                inStack={filters.tab !== "stack" && !!item.vendor && stack.includes(item.vendor.slug)}
              />
            ))}
          </div>

          {failed && items.length === 0 ? (
            <p className="py-10 text-[15px] text-muted">The feed is unreachable right now. It retries on the next refresh.</p>
          ) : items.length === 0 && !loading ? (
            <p className="py-10 text-[15px] text-muted">Nothing here in the last 14 days.</p>
          ) : (
            <div className="flex items-baseline justify-between pt-6 text-[15px]">
              <span className="text-muted">
                {items.length} of {total} in the last 14 days
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
          className="@container/rail mt-16 text-[13px] min-[1200px]:mt-0 min-[1200px]:min-w-[280px] min-[1200px]:flex-[1_1_280px] min-[1200px]:pt-[133px]"
        >
          {/* A wide rail splits into Elsewhere | stats, and each flows into more columns. */}
          <div className="flex flex-col gap-10 @min-[600px]/rail:flex-row @min-[600px]/rail:gap-16">
          <div className="@container min-w-0 flex-1">
            <Elsewhere elsewhere={elsewhere} />
          </div>
          <div className="@container min-w-0 flex-1">
            <Stats active={active} kev={kev} status={status} onVendor={(slug) => apply({ vendor: slug })} />
          </div>
          </div>
        </aside>
      </div>
      <SiteFooter data-chrome className="mt-16" />
    </main>
  )
}

function Count({ n, slash = false, children }: { n: number; slash?: boolean; children: ReactNode }) {
  // Desktop: "/" between counts, as in wire.png. Narrow screens wrap, so they use a gap instead.
  return (
    <span className="whitespace-nowrap">
      {slash && (
        <span aria-hidden className="mx-[13px] hidden text-outline-medium md:inline">
          /
        </span>
      )}
      <span className="text-fg">{n}</span> {children}
    </span>
  )
}
