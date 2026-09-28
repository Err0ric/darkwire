"use client"

import Link from "next/link"
import { useEffect, useRef, useState } from "react"
import { cn } from "cn"

import { Ticker } from "@/components/home/Ticker"
import { PrefsControls } from "@/components/PrefsControls"
import { CURSOR_RESERVE_EM, NEW_ROWS_EVENT, Wordmark } from "@/components/Wordmark"
import { Expanded, type Detail } from "@/components/FeedRow"
import { getFeed, getItem, getStatus, type FeedItem, type Status } from "@/lib/api"
import { pad, useMinuteClock, utcHHMM, zoneName } from "@/lib/clock"
import { NewDot, useDots, type DotState } from "@/lib/dots"
import { isImportant, kevDueIn } from "@/lib/kev"
import { apply as applyDiff, changedSince, cursorOf, diff, LIVE_POLL_MS } from "@/lib/live"
import { usePrefs } from "@/lib/prefs"
import { syncState, type SyncState } from "@/lib/sync"
import { age, useNow } from "@/lib/time"
import { useUnseen } from "@/lib/unseen"

// Home: a calm landing page. A centered block (the wordmark with its live dot, tagline, one
// date and time line, Right now, ticker, OPEN WIRE, stack link) about half the viewport tall,
// with black space around it; the footer at the bottom. The clock lives on /wire; counts, KEV
// due dates and services too. Gaps scale with the viewport height; the wordmark with its width.

const STATUS_POLL_MS = 60_000
// Right now is also re-read in full now and then, quietly, for rows the since-poll cannot place.
const RESYNC_MS = 5 * 60_000
const RIGHT_NOW_MS = 48 * 3600_000
const RIGHT_NOW_ROWS = 3

export interface HomeData {
  rightNow: FeedItem[]
  latest: FeedItem[]
  status: Status | null
  failed: boolean
}



/** Belongs in Right now: Critical, KEV or EXPLOITED, not an old CVE, event in the last 48h. */
function rightNowWorthy(i: FeedItem, now: number): boolean {
  return (
    !i.stale &&
    (i.severity === "critical" || i.kev || i.exploited) &&
    now - Date.parse(i.last_event_at) <= RIGHT_NOW_MS
  )
}

export function HomeBoard({ initial }: { initial: HomeData }) {
  const [rightNow, setRightNow] = useState(initial.rightNow)
  const [latest, setLatest] = useState(initial.latest)
  const [status, setStatus] = useState(initial.status)
  const { query } = usePrefs()
  const minute = useMinuteClock()
  const [statusFailed, setStatusFailed] = useState(false)
  const addUnseen = useUnseen()
  const { dots, add: addDots } = useDots()
  const rightNowRef = useRef(rightNow)
  const latestRef = useRef(latest)
  const loadedAt = useRef(new Date().toISOString())
  const lastPoll = useRef(0)
  useEffect(() => {
    lastPoll.current = Date.now()
  }, [])
  useEffect(() => {
    rightNowRef.current = rightNow
    latestRef.current = latest
  }, [rightNow, latest])

  useEffect(() => {
    const load = () =>
      getStatus()
        .then((s) => {
          setStatus(s)
          setStatusFailed(s.sync.last_ok === false)
        })
        .catch(() => setStatusFailed(true))
    const timer = setInterval(load, STATUS_POLL_MS)
    return () => clearInterval(timer)
  }, [])

  // Every 60s, hidden or not: rows with a newer event or any newer change (lib/live.ts). New
  // and escalated rows lead the ticker, join Right now when they qualify (with a dot) and count
  // as unseen; in-place changes update silently.
  useEffect(() => {
    const poll = async () => {
      const known = [...latestRef.current, ...rightNowRef.current]
      const changed = changedSince(lastPoll.current)
      lastPoll.current = Date.now()
      const page = await getFeed({ since: cursorOf(known) ?? loadedAt.current, changed_since: changed, limit: 50 }).catch(
        () => null,
      )
      if (!page) return
      const d = diff(known, page.items)
      const now = Date.now()
      setLatest((prev) => applyDiff(prev, d).slice(0, 10))
      const worthy = d.fresh.filter((i) => rightNowWorthy(i, now))
      setRightNow((prev) => applyDiff(prev, { fresh: worthy, updated: d.updated }).filter((i) => rightNowWorthy(i, now)).slice(0, RIGHT_NOW_ROWS))
      addDots(worthy.slice(0, RIGHT_NOW_ROWS).map((i) => i.id))
      if (d.fresh.length) void addUnseen(d.fresh.length, d.fresh.some(isImportant))
      // NEW rows re-type the wordmark's ".tech" (nav and lockup).
      if (d.fresh.length) window.dispatchEvent(new Event(NEW_ROWS_EVENT))
    }
    const resync = () => getFeed({ pinned: true, limit: RIGHT_NOW_ROWS }).then((p) => setRightNow(p.items)).catch(() => undefined)
    const live = setInterval(poll, LIVE_POLL_MS)
    const full = setInterval(resync, RESYNC_MS)
    return () => {
      clearInterval(live)
      clearInterval(full)
    }
  }, [addDots, addUnseen])

  return (
    // One screen tall: the block centers in whatever the nav and footer leave.
    <main className="flex min-h-[calc(100dvh/var(--zoom)-var(--nav-h))] flex-col page-frame">
      <div className="mx-auto my-auto flex w-full max-w-[880px] flex-col items-center py-[clamp(24px,5vh,72px)] text-center">
        {/* One block on the page's center axis: the lockup (as in og.png), then the date line. */}
        <div className="flex flex-col items-center">
          <Lockup state={syncState(status, statusFailed || status?.sync.last_ok === false, minute?.getTime() ?? null)} />
          <DateLine now={minute} />
        </div>
        <RightNow items={rightNow.slice(0, RIGHT_NOW_ROWS)} dots={dots} failed={initial.failed && !rightNow.length} />
        <Ticker items={latest} />

        <Link
          href={`/wire${query()}`}
          className="max-md:tap mt-[clamp(24px,3.6vh,48px)] inline-flex h-10 items-center gap-2.5 rounded-control border border-accent px-6 font-mono text-[13px] font-medium tracking-[0.08em] text-fg outline-none hover:border-critical focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          OPEN WIRE <span className="text-critical-text">→</span>
        </Link>
        <nav aria-label="More" className="mt-3.5 flex gap-6 text-[13px] text-muted">
          {[
            ["/cves", "CVEs"],
            ["/vendors", "Vendors"],
            ["/services", "Services"],
          ].map(([href, label]) => (
            <Link key={href} href={`${href}${query()}`} className="max-md:tap outline-none hover:text-fg-2 focus-visible:text-fg-2">
              {label}
            </Link>
          ))}
        </nav>
        <Link
          href={`/vendors${query()}`}
          className="max-md:tap mt-[clamp(20px,3vh,36px)] text-[13px] text-muted underline decoration-rule underline-offset-[5px] outline-none hover:text-fg-2 focus-visible:text-fg-2"
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

/** The landing's centerpiece, the og.png lockup: the nav's wordmark (red i-dot, typing
 * ".tech") at landing size, and "live security news + CVEs" under it, right-aligned to the
 * reserved end of ".tech". */
function Lockup({ state }: { state: SyncState }) {
  // The cursor's reserved space after ".tech" hangs outside the layout box (negative margin),
  // so the block centers on the visible "darkwire.tech" and the tagline ends under the "h".
  const size = "clamp(40px, 3.2vw, 64px)"
  return (
    <div className="inline-flex flex-col items-end">
      <h1 aria-label="darkwire.tech" style={{ fontSize: size, marginRight: `calc(${size} * ${-CURSOR_RESERVE_EM})` }}>
        <Wordmark state={state} />
      </h1>
      <p className="mt-2 font-mono text-[13px] leading-4 text-muted">live security news + CVEs</p>
    </div>
  )
}

/** "Sunday, Sep 27 · 14:09 PDT · 21:09 UTC": date in sans, times in mono, dots dim. UTC viewers
 * see only UTC. Each minute. */
function DateLine({ now }: { now: Date | null }) {
  const dot = <span className="text-dim-text"> · </span>
  const utcOnly = now !== null && zoneName(now) === "UTC"
  return (
    <p className="mt-5 h-5 text-[15px] leading-5 text-fg-2">
      {now && (
        <>
          {now.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" })}
          {!utcOnly && (
            <>
              {dot}
              <span className="font-mono">
                {pad(now.getHours())}:{pad(now.getMinutes())} {zoneName(now)}
              </span>
            </>
          )}
          {dot}
          <span className="font-mono">{utcHHMM(now)} UTC</span>
        </>
      )}
    </p>
  )
}

// ---------------------------------------------------------------- Right now

function RightNow({ items, dots, failed }: { items: FeedItem[]; dots: ReadonlyMap<number, DotState>; failed: boolean }) {
  return (
    <section aria-label="Right now" className="mt-[clamp(28px,4.4vh,56px)] w-full text-left">
      <div className="flex items-baseline gap-3 border-b border-rule pb-2">
        <h2 className="text-[13px] font-medium text-fg">Right now</h2>
        <span className="text-xs text-muted">critical, KEV and exploited · last 48h</span>
      </div>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <RightNowRow key={item.id} item={item} dot={dots.get(item.id)} />
          ))}
        </ul>
      ) : (
        <p className="flex h-11 items-center border-b border-hairline text-[13px] text-muted">
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
  exploited: "border-critical text-critical-text",
  kev: "border-critical text-critical-text",
}

const BAR_FILL: Record<string, string> = { critical: "bg-critical", high: "bg-accent", medium: "bg-medium", low: "bg-dim" }

function RightNowRow({ item, dot }: { item: FeedItem; dot?: DotState }) {
  const { query } = usePrefs()
  const now = useNow()
  const severity = item.severity && item.severity !== "none" ? item.severity : null
  // No CVSS score: the badge column still says why the row is here, EXPLOITED or else KEV
  // (outlined red), so the columns line up with the scored rows.
  const badge = item.cvss === null ? (item.exploited ? "exploited" : item.kev ? "kev" : severity) : (severity ?? (item.exploited ? "exploited" : null))

  // Right side tag: KEV due / KEV, else "no fix yet" when vendor data says there is none.
  const due = now === null ? null : kevDueIn(item, now)
  const tag =
    due !== null ? (
      <span className="text-critical-text">{due < 0 ? "KEV overdue" : due === 0 ? "KEV due today" : `KEV due in ${due}d`}</span>
    ) : item.kev && badge !== "kev" ? (
      <span className="text-critical-text">KEV</span>
    ) : item.patch_status === "no_fix" ? (
      <span className="text-muted">no fix yet</span>
    ) : null

  const score = item.cvss !== null && (
    <span className={cn("font-mono text-[13px] font-medium", item.cvss >= 7 ? "text-fg" : "text-fg-2")}>
      {item.cvss.toFixed(1)}
    </span>
  )
  const badgeEl = badge && (
    <span
      className={cn(
        "inline-flex h-[18px] w-[72px] shrink-0 items-center justify-center rounded-badge border font-mono text-[11px] font-medium tracking-[0.04em] uppercase",
        BADGE[badge],
      )}
    >
      {badge}
    </span>
  )

  // Only the headline is a link (to the article); a click anywhere else on the row, or Enter /
  // Space while it has focus, opens the wire's expanded view under it.
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<Detail>({ state: "idle" })
  const detailId = `rightnow-${item.id}-detail`
  function toggle() {
    const next = !open
    setOpen(next)
    if (next && (detail.state === "idle" || detail.state === "error")) {
      setDetail({ state: "loading" })
      getItem(item.id)
        .then((d) => setDetail({ state: "ready", item: d }))
        .catch(() => setDetail({ state: "error" }))
    }
  }

  return (
    <li className={cn("border-b border-hairline", open ? "bg-surface" : "hover:bg-surface")}>
      <div
        role="group"
        tabIndex={0}
        aria-label={`${item.headline}. ${open ? "Collapse" : "Expand"} details`}
        onClick={(e) => {
          if ((e.target as HTMLElement).closest("a, button")) return
          toggle()
        }}
        onKeyDown={(e) => {
          if (e.target !== e.currentTarget || (e.key !== "Enter" && e.key !== " ")) return
          e.preventDefault()
          toggle()
        }}
        className="block cursor-pointer py-3 outline-offset-[-1px] sm:flex sm:h-11 sm:items-center sm:py-0"
      >
        {/* Wide: score · bar · badge · headline · tag · age on one line. Narrow: headline, then the rest, no bar. */}
        <span className="hidden w-10 shrink-0 pl-1 sm:block">{score}</span>
        <span className="hidden w-[84px] shrink-0 sm:block">
          {item.cvss !== null && (
            <span className="flex gap-0.5" role="img" aria-label={`CVSS ${item.cvss}`}>
              {Array.from({ length: 10 }, (_, i) => (
                <span
                  key={i}
                  className={cn("h-2.5 w-[5px]", i < Math.round(item.cvss ?? 0) ? BAR_FILL[severity ?? "medium"] : "bg-rule")}
                />
              ))}
            </span>
          )}
        </span>
        <span className="hidden w-24 shrink-0 sm:block">{badgeEl}</span>
        {/* The wrapper is not clipped, so the dot can sit in the gutter left of the headline. */}
        <span className="relative block min-w-0 flex-1">
          {dot && <NewDot state={dot} className="top-[7px] -left-[10px] sm:-left-[15px]" />}
          <span className="block text-[15px] leading-5 font-medium tracking-[-0.01em] text-fg sm:truncate">
            <a
              href={item.primary_url}
              target="_blank"
              rel="noopener noreferrer"
              className="max-md:tap outline-none hover:underline focus-visible:underline"
            >
              {item.headline}
            </a>
          </span>
        </span>
        <span className="mt-1.5 flex items-center gap-3 sm:mt-0 sm:ml-5 sm:gap-0">
          <span className="sm:hidden">{badgeEl}</span>
          <span className="sm:hidden">{score}</span>
          <span className="font-mono text-xs whitespace-nowrap sm:w-[120px] sm:text-right">{tag}</span>
          <span className="ml-auto font-mono text-xs text-muted sm:ml-0 sm:w-12 sm:text-right">
            {now !== null && age(item.last_event_at, now)}
          </span>
        </span>
      </div>
      {open && (
        <div id={detailId} className="pb-5 text-left" aria-busy={detail.state === "loading"}>
          {detail.state === "ready" && <Expanded item={detail.item} detail={detail} />}
          {detail.state === "error" && <p className="text-[13px] text-muted">Could not load this row. Try again.</p>}
          <Link href={`/item/${item.id}${query()}`} className="max-md:tap mt-3 inline-block text-[13px] text-muted outline-none hover:text-fg-2 focus-visible:text-fg-2">
            Permalink
          </Link>
        </div>
      )}
    </li>
  )
}
