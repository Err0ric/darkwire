"use client"

import Link from "next/link"
import { useEffect, useRef, useState } from "react"

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
      const now = Date.now()
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
        <Activity data={activity} />
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
