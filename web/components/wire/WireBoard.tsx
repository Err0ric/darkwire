"use client"

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { cn } from "cn"

import { FeedRow } from "@/components/FeedRow"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Rail } from "@/components/wire/Rail"
import {
  getElsewhere,
  getFeed,
  getKev,
  getStatus,
  getVendors,
  type FeedItem,
} from "@/lib/api"
import { useUnseen } from "@/lib/unseen"
import { TABS, type Filters, type WireData } from "@/lib/wire"

const PAGE = 50
// 15 minutes. Overridable at build time for local testing only.
const POLL_MS = Number(process.env.NEXT_PUBLIC_POLL_SECONDS ?? 900) * 1000
const SEARCH_DEBOUNCE_MS = 250
const ALL_VENDORS = "all"


function feedQuery(f: Filters) {
  return { tab: f.tab, vendor: f.vendor || undefined, q: f.q || undefined }
}

function syncUrl(f: Filters) {
  const params = new URLSearchParams()
  if (f.tab !== "all") params.set("tab", f.tab)
  if (f.vendor) params.set("vendor", f.vendor)
  if (f.q) params.set("q", f.q)
  const qs = params.toString()
  window.history.replaceState(null, "", qs ? `/wire?${qs}` : "/wire")
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

  const filtersRef = useRef(filters)
  const itemsRef = useRef(items)
  const request = useRef(0)
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null)
  const addUnseen = useUnseen()

  useEffect(() => {
    itemsRef.current = items
  }, [items])

  const load = useCallback(async (f: Filters) => {
    const id = ++request.current
    setLoading(true)
    try {
      const page = await getFeed({ ...feedQuery(f), limit: PAGE })
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
      const page = await getFeed({ ...feedQuery(f), limit: PAGE, offset: itemsRef.current.length })
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

  // Every 15 minutes: rows with an event newer than the top row, plus counts and rail.
  useEffect(() => {
    const poll = async () => {
      const f = filtersRef.current
      const newest = itemsRef.current[0]?.last_event_at
      const [feed, st, els, act, kv] = await Promise.allSettled([
        getFeed({ ...feedQuery(f), limit: PAGE, since: newest }),
        getStatus(),
        getElsewhere(5),
        getVendors("active"),
        getKev(7, 8),
      ])
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
      void addUnseen(incoming.length, incoming.some((i) => i.severity === "critical" || i.kev))
    }
    const timer = setInterval(poll, POLL_MS)
    return () => clearInterval(timer)
  }, [addUnseen])

  const byName = [...vendors].sort((a, b) => a.name.localeCompare(b.name))
  const active = vendors.filter((v) => v.items_7d > 0).slice(0, 5)
  const counts = status?.counts

  return (
    <main className="flex-1 px-4 pb-24 md:px-12">
      <div className="lg:flex lg:gap-16">
        <div className="min-w-0 max-w-[1060px] flex-1">
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
          </header>

          <div className="mt-8 flex flex-col-reverse border-b border-rule md:mt-[32px] md:flex-row md:items-end md:justify-between">
            <nav aria-label="Categories" className="-mb-px flex gap-6 overflow-x-auto [scrollbar-width:none]">
              {TABS.map(([tab, label]) => (
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
            <div className="mb-4 flex items-center gap-5 md:mb-[10px] md:shrink-0">
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
                className="h-[30px] min-w-0 flex-1 md:w-[200px] md:flex-none"
              />
            </div>
          </div>

          <div className={cn(loading && "opacity-60")} aria-busy={loading}>
            {items.map((item) => (
              <FeedRow key={item.id} item={item} fresh={fresh.has(item.id)} />
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

        <div className="mt-16 lg:mt-0 lg:w-[220px] lg:shrink-0 lg:pt-[133px]">
          <Rail elsewhere={elsewhere} active={active} kev={kev} status={status} onVendor={(slug) => apply({ vendor: slug })} />
        </div>
      </div>
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
