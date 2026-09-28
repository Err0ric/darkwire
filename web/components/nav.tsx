"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"
import { cn } from "cn"

import { NavServices } from "@/components/NavServices"
import { Wordmark } from "@/components/Wordmark"
import { ThemePicker } from "@/components/ThemePicker"
import { getStatus, type Status } from "@/lib/api"
import { utcHHMM } from "@/lib/clock"
import { usePrefs } from "@/lib/prefs"
import { minutesSinceSync, syncState } from "@/lib/sync"

const LINKS = [
  { href: "/wire", label: "Wire" },
  { href: "/vendors", label: "Vendors" },
]

/** Where the wire puts its compact counts and clock inside the condensed bar (a portal). */
export const CONDENSED_SLOT = "wire-condensed-slot"

const STATUS_POLL_MS = 60_000
const RETRY_MS = 15_000
const CLOCK_TICK_MS = 15_000
// Pages whose own header shows the time: no UTC in the nav there.
const OWN_CLOCK = new Set(["/", "/wire"])

// failing: the API answered but the last ingest run failed. unreachable: the API did not answer;
// the last good data stays on screen and the next poll retries.
type Sync = { status: Status | null; failing: boolean; unreachable: boolean }

function syncedLabel(minutes: number): string {
  if (minutes < 1) return "Synced just now"
  if (minutes < 60) return `Synced ${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  return hours < 24 ? `Synced ${hours}h ago` : `Synced ${Math.floor(hours / 24)}d ago`
}

export function Nav() {
  const pathname = usePathname()
  const { query } = usePrefs()
  const [sync, setSync] = useState<Sync>({ status: null, failing: false, unreachable: false })
  const [now, setNow] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    let retry: ReturnType<typeof setTimeout> | undefined
    const load = () =>
      getStatus()
        .then((status) => !cancelled && setSync({ status, failing: status.sync.last_ok === false, unreachable: false }))
        .catch(() => {
          if (cancelled) return
          setSync((prev) => ({ ...prev, unreachable: true }))
          // Unreachable: try again sooner than the minute poll.
          clearTimeout(retry)
          retry = setTimeout(load, RETRY_MS)
        })
    load()
    const poll = setInterval(load, STATUS_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(poll)
      clearTimeout(retry)
    }
  }, [])

  useEffect(() => {
    const tick = () => setNow(Date.now())
    const first = setTimeout(tick, 0)
    const clock = setInterval(tick, CLOCK_TICK_MS)
    return () => {
      clearTimeout(first)
      clearInterval(clock)
    }
  }, [])

  const minutes = minutesSinceSync(sync.status, now)
  const dot = syncState(sync.status, sync.failing || sync.unreachable, now)
  const ownClock = OWN_CLOCK.has(pathname)
  const wirePage = pathname === "/wire"
  const cvesActive = pathname === "/cves" || pathname.startsWith("/cve/")
  const label = sync.unreachable
    ? "Feed unreachable · retrying"
    : sync.failing
      ? "Sync failing"
      : minutes !== null
        ? syncedLabel(minutes)
        : ""

  // The nav's bottom rule shows only while the page is scrolled (it is sticky).
  useEffect(() => {
    const root = document.documentElement
    const on = () => root.toggleAttribute("data-scrolled", window.scrollY > 0)
    on()
    window.addEventListener("scroll", on, { passive: true })
    return () => {
      window.removeEventListener("scroll", on)
      root.removeAttribute("data-scrolled")
    }
  }, [])

  const wordmark = (tech: string) => (
    <Link
      href={`/${query()}`}
      aria-label="darkwire.tech"
      className="max-md:tap mr-2.5 flex items-center outline-none sm:mr-6 md:mr-10"
    >
      <Wordmark
        state={sync.status || sync.failing || sync.unreachable ? dot : null}
        className="text-base sm:text-lg"
        techClassName={tech}
      />
    </Link>
  )

  // The condensed bar repeats the links in a plain div: one "Main" landmark per page.
  const links = (landmark: boolean) => {
    const Tag = landmark ? "nav" : "div"
    return (
      <Tag aria-label={landmark ? "Main" : undefined} className="flex min-w-0 items-center gap-2.5 sm:gap-6">
        {LINKS.map(({ href, label }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`)
          // Wire is the primary link: a small outlined button in OPEN WIRE's style.
          const wire = href === "/wire"
          return (
            <Link
              key={href}
              href={`${href}${query()}`}
              aria-current={active ? "page" : undefined}
              className={cn(
                "max-md:tap",
                "leading-none outline-none",
                wire
                  ? cn(
                      "rounded-control border px-1.5 py-1 font-mono text-xs font-medium tracking-[0.06em] focus-visible:border-critical sm:px-2.5",
                      active ? "border-critical text-fg" : "border-accent/60 text-fg-2 hover:border-critical",
                    )
                  : cn(
                      "text-[13px] focus-visible:text-fg sm:text-[15px]",
                      active ? "text-fg" : "text-muted hover:text-fg-2",
                    ),
              )}
            >
              {wire ? label.toUpperCase() : label}
            </Link>
          )
        })}
      </Tag>
    )
  }

  const status = (utc: boolean, main: boolean) => (
    // main: the nav proper (its Synced line is the live region); else the condensed bar, which
    // drops Synced under 1400px to fit one line.
    <div className="ml-auto flex shrink-0 items-center gap-3 pl-5 sm:gap-4">
      <NavServices />
      {/* CVEs is a quiet link at the start of the status group. On / and /wire (their own
          clocks show UTC) there is no UTC slot, so CVEs sits right next to "Synced". */}
      <Link
        href={`/cves${query()}`}
        aria-current={cvesActive ? "page" : undefined}
        className={cn(
          "max-md:tap",
          "text-[13px] leading-none outline-none focus-visible:text-fg sm:text-[15px]",
          cvesActive ? "text-fg" : "text-muted hover:text-fg-2",
        )}
      >
        CVEs
      </Link>
      {utc && (
        <>
          <span aria-hidden className="-mx-1.5 hidden text-xs text-dim-text min-[1200px]:block">
            ·
          </span>
          <time
            dateTime={now !== null ? new Date(now).toISOString() : undefined}
            title="Coordinated Universal Time"
            className="hidden w-[70px] font-mono text-xs leading-none text-dim-text min-[1200px]:block"
          >
            {now !== null ? `${utcHHMM(new Date(now))} UTC` : ""}
          </time>
        </>
      )}
      <p
        className={cn(
          "hidden text-[15px] leading-none sm:block",
          !main && "max-[1399px]:hidden!",
          sync.unreachable ? "text-critical-text" : "text-muted",
        )}
        aria-live={main ? "polite" : undefined}
      >
        {label}
      </p>
      <ThemePicker />
    </div>
  )

  return (
    <>
      {/* Sticky on every page, full width so rows never show beside it. On /wire from 900px it
          scrolls away with the page header and the condensed bar below takes over. */}
      <div
        data-chrome
        className={cn(
          // A 1px shadow, not a border, so the nav stays exactly --nav-h tall.
          "sticky top-0 z-30 bg-bg scrolled:shadow-[0_1px_0_var(--color-rule)]",
          wirePage && "min-[900px]:static min-[900px]:shadow-none",
        )}
      >
        <header className="flex h-15 items-center page-frame">
          {/* .tech is hidden under 640px so the nav still fits on one line on a phone. */}
          {wordmark("max-sm:hidden")}
          {links(true)}
          {status(!ownClock, true)}
        </header>
      </div>
      {wirePage && (
        // The wire's condensed bar: shown (150ms fade) once the tabs row reaches it, hidden again
        // at the top. Fixed, so the feed never moves. Its counts and clock are the wire's, put
        // into the slot by a portal. A labelled region, not a second banner or Main nav.
        <div
          data-chrome
          className={cn(
            "invisible fixed inset-x-0 top-0 z-30 h-(--bar-h) border-b border-rule bg-bg opacity-0 transition-[opacity,visibility] duration-150 motion-reduce:transition-none max-[899px]:hidden",
            "wire-stuck:visible wire-stuck:opacity-100",
          )}
        >
          <div role="region" aria-label="Wire summary" className="flex h-full items-center page-frame">
            {wordmark("hidden")}
            {links(false)}
            <div id={CONDENSED_SLOT} className="flex min-w-0 flex-1 items-center justify-between gap-6 pl-8" />
            {status(false, false)}
          </div>
        </div>
      )}
    </>
  )
}
