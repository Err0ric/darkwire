"use client"

import Link from "next/link"
import { useEffect, useLayoutEffect, useRef, useState } from "react"

import { Activity } from "@/components/home/Activity"
import { Ticker } from "@/components/home/Ticker"
import { PrefsControls } from "@/components/PrefsControls"
import { CURSOR_RESERVE_EM, NEW_ROWS_EVENT, Wordmark } from "@/components/Wordmark"
import { getActivity, getFeed, getStatus, type Activity as ActivityData, type FeedItem, type Status } from "@/lib/api"
import { pad, useMinuteClock, utcHHMM, zoneName } from "@/lib/clock"
import { isImportant } from "@/lib/kev"
import { apply as applyDiff, changedSince, cursorOf, diff, LIVE_POLL_MS } from "@/lib/live"
import { usePrefs } from "@/lib/prefs"
import { syncState, type SyncState } from "@/lib/sync"
import { useUnseen } from "@/lib/unseen"

// Home: a calm landing page. A centered block (the wordmark with its live dot, tagline, one
// date and time line, the activity trace and log line, ticker, OPEN WIRE, stack link) about
// half the viewport tall,
// with black space around it; the footer at the bottom. The clock lives on /wire; counts, KEV
// due dates and services too. Gaps scale with the viewport height; the wordmark with its width.

const STATUS_POLL_MS = 60_000

export interface HomeData {
  activity: ActivityData | null
  latest: FeedItem[]
  status: Status | null
  failed: boolean
}



export function HomeBoard({ initial }: { initial: HomeData }) {
  const [activity, setActivity] = useState(initial.activity)
  const [latest, setLatest] = useState(initial.latest)
  const [status, setStatus] = useState(initial.status)
  const { query } = usePrefs()
  const minute = useMinuteClock()
  const [statusFailed, setStatusFailed] = useState(false)
  const addUnseen = useUnseen()
  const latestRef = useRef(latest)
  const loadedAt = useRef(new Date().toISOString())
  const lastPoll = useRef(0)
  useEffect(() => {
    lastPoll.current = Date.now()
  }, [])
  useEffect(() => {
    latestRef.current = latest
  }, [latest])

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

  // Every 60s, hidden or not: rows with a newer event or any newer change (lib/live.ts), and the
  // activity trace and log. New and escalated rows lead the ticker and count as unseen; in-place
  // changes update silently. A new board event types into the log line.
  useEffect(() => {
    const poll = async () => {
      getActivity()
        .then(setActivity)
        .catch(() => undefined)
      const known = latestRef.current
      const changed = changedSince(lastPoll.current)
      lastPoll.current = Date.now()
      const page = await getFeed({ since: cursorOf(known) ?? loadedAt.current, changed_since: changed, limit: 50 }).catch(
        () => null,
      )
      if (!page) return
      const d = diff(known, page.items)
      setLatest((prev) => applyDiff(prev, d).slice(0, 10))
      if (d.fresh.length) void addUnseen(d.fresh.length, d.fresh.some(isImportant))
      // NEW rows re-type the wordmark's ".tech" (nav and lockup).
      if (d.fresh.length) window.dispatchEvent(new Event(NEW_ROWS_EVENT))
    }
    const live = setInterval(poll, LIVE_POLL_MS)
    return () => clearInterval(live)
  }, [addUnseen])

  return (
    // One screen tall: the block centers in whatever the nav and footer leave.
    <main className="flex min-h-[calc(100dvh/var(--zoom)-var(--nav-h))] flex-col page-frame">
      <div className="mx-auto my-auto flex w-full max-w-[880px] flex-col items-center py-[clamp(24px,5vh,72px)] text-center">
        {/* One block on the page's center axis: the lockup (as in og.png), then the date line. */}
        <div className="flex flex-col items-center">
          <Lockup state={syncState(status, statusFailed || status?.sync.last_ok === false, minute?.getTime() ?? null)} />
          <DateLine now={minute} />
        </div>
        <Activity data={activity} sources={status?.sources_total ?? null} />
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
      </div>

      {/* Just above the footer, centered: at least 48px under the links (mt-12); the block above
          keeps its vertical centering in what is left. */}
      <Link
        href={`/vendors${query()}`}
        className="max-md:tap mx-auto mt-12 shrink-0 text-[13px] text-muted underline decoration-rule underline-offset-[5px] outline-none hover:text-fg-2 focus-visible:text-fg-2"
      >
        Pick your vendors to filter everything to your stack →
      </Link>

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

/** The x of a glyph's right ink edge: its box's left (the glyph origin) plus the font's
 * actualBoundingBoxRight for that character, so side bearings and tracking do not count. */
function inkRight(left: number, ch: string, style: CSSStyleDeclaration): number {
  const ctx = document.createElement("canvas").getContext("2d")
  if (!ctx) return left
  ctx.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
  return left + ctx.measureText(ch).actualBoundingBoxRight
}

/** The landing's centerpiece, the og.png lockup: the nav's wordmark (red i-dot, typing
 * ".tech") at landing size, and "live security news + CVEs" under it, its last glyph's ink
 * ending exactly under the ink of the "h" in ".tech" (measured below). */
function Lockup({ state }: { state: SyncState }) {
  // The cursor's reserved space after ".tech" hangs outside the layout box (negative margin),
  // so the block centers on the visible "darkwire.tech".
  const size = "clamp(40px, 3.2vw, 64px)"
  const lockup = useRef<HTMLDivElement>(null)
  const tagline = useRef<HTMLParagraphElement>(null)

  // Moves the tagline so its last glyph's ink ends exactly where the "h" of ".tech" ends when
  // fully typed (the wordmark's invisible reserve, so typing never moves it). A transform, so
  // the layout does not shift. Re-measured on resize and once fonts are ready.
  useLayoutEffect(() => {
    const box = lockup.current
    const tag = tagline.current
    if (!box || !tag) return
    const place = () => {
      const h = box.querySelector<HTMLElement>("[data-wordmark-last]")
      const text = tag.firstChild
      if (!h || !text || text.nodeType !== Node.TEXT_NODE) return
      tag.style.transform = ""
      const hRight = inkRight(h.getBoundingClientRect().left, h.textContent ?? "h", getComputedStyle(h))
      const content = text.textContent ?? ""
      const range = document.createRange()
      range.setStart(text, content.length - 1)
      range.setEnd(text, content.length)
      const tagRight = inkRight(range.getBoundingClientRect().left, content.slice(-1), getComputedStyle(tag))
      tag.style.transform = `translateX(${hRight - tagRight}px)`
    }
    place()
    const ro = new ResizeObserver(place)
    ro.observe(box)
    document.fonts?.ready.then(place)
    window.addEventListener("resize", place)
    return () => {
      ro.disconnect()
      window.removeEventListener("resize", place)
    }
  }, [])
  return (
    <div ref={lockup} className="inline-flex flex-col items-end">
      <h1 aria-label="darkwire.tech" style={{ fontSize: size, marginRight: `calc(${size} * ${-CURSOR_RESERVE_EM})` }}>
        <Wordmark state={state} />
      </h1>
      <p ref={tagline} className="mt-2 font-mono text-[13px] leading-4 text-muted">live security news + CVEs</p>
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
