"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"
import { cn } from "cn"

import { minutesSinceSync, SyncDot, syncState } from "@/components/SyncDot"
import { ThemePicker } from "@/components/ThemePicker"
import { getStatus, type Status } from "@/lib/api"
import { utcHHMM } from "@/lib/clock"
import { usePrefs } from "@/lib/prefs"

const LINKS = [
  { href: "/wire", label: "Wire" },
  { href: "/vendors", label: "Vendors" },
  { href: "/outages", label: "Outages" },
]

const STATUS_POLL_MS = 60_000
const CLOCK_TICK_MS = 15_000
// Pages whose own header shows the time: no UTC in the nav there.
const OWN_CLOCK = new Set(["/", "/wire"])

type Sync = { status: Status | null; failing: boolean }

function syncedLabel(minutes: number): string {
  if (minutes < 1) return "Synced just now"
  if (minutes < 60) return `Synced ${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  return hours < 24 ? `Synced ${hours}h ago` : `Synced ${Math.floor(hours / 24)}d ago`
}

export function Nav() {
  const pathname = usePathname()
  const { query } = usePrefs()
  const [sync, setSync] = useState<Sync>({ status: null, failing: false })
  const [now, setNow] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = () =>
      getStatus()
        .then((status) => !cancelled && setSync({ status, failing: status.sync.last_ok === false }))
        .catch(() => !cancelled && setSync((prev) => ({ ...prev, failing: true })))
    load()
    const poll = setInterval(load, STATUS_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(poll)
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
  const dot = syncState(sync.status, sync.failing, now)
  // Home leads with a large wordmark of its own; the nav's would repeat it.
  const home = pathname === "/"
  const ownClock = OWN_CLOCK.has(pathname)
  const cvesActive = pathname === "/cves" || pathname.startsWith("/cve/")
  const label = sync.failing ? "Sync unavailable" : minutes !== null ? syncedLabel(minutes) : ""

  return (
    <header data-chrome className="flex h-15 items-center page-frame">
      {!home && (
        <Link href={`/${query()}`} className="mr-2.5 flex items-center gap-1.5 outline-none focus-visible:outline-1 focus-visible:outline-rule sm:mr-6 md:mr-10">
          <SyncDot state={dot} className="size-1.5" />
          <span className="text-base leading-none font-bold tracking-[-0.01em] text-fg sm:text-lg">darkwire</span>
        </Link>
      )}

      <nav aria-label="Main" className="flex min-w-0 items-center gap-2.5 sm:gap-6">
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
                "leading-none outline-none",
                wire
                  ? cn(
                      "rounded-control border px-1.5 py-1 font-mono text-xs font-medium tracking-[0.06em] focus-visible:border-critical sm:px-2.5",
                      active ? "border-critical text-fg" : "border-accent/60 text-fg-2 hover:border-critical",
                    )
                  : cn("text-[14px] focus-visible:text-fg sm:text-[15px]", active ? "text-fg" : "text-muted hover:text-fg-2"),
              )}
            >
              {wire ? label.toUpperCase() : label}
            </Link>
          )
        })}
      </nav>

      <div className="ml-auto flex shrink-0 items-center gap-3 pl-5 sm:gap-4">
        {/* CVEs is a quiet link at the start of the status group. The UTC slot keeps its width on
            pages with their own clock (/ and /wire), so CVEs sits in the same spot everywhere. */}
        <Link
          href={`/cves${query()}`}
          aria-current={cvesActive ? "page" : undefined}
          className={cn(
            "text-[14px] leading-none outline-none focus-visible:text-fg sm:text-[15px]",
            cvesActive ? "text-fg" : "text-muted hover:text-fg-2",
          )}
        >
          CVEs
        </Link>
        <span aria-hidden className={cn("-mx-1.5 hidden text-dim min-[1200px]:block", ownClock && "invisible")}>
          ·
        </span>
        <time
          dateTime={now !== null ? new Date(now).toISOString() : undefined}
          title="Coordinated Universal Time"
          aria-hidden={ownClock || undefined}
          className={cn("hidden w-[70px] font-mono text-xs leading-none text-dim min-[1200px]:block", ownClock && "invisible")}
        >
          {now !== null ? `${utcHHMM(new Date(now))} UTC` : ""}
        </time>
        <p className="hidden text-[15px] leading-none text-muted sm:block" aria-live="polite">
          {label}
        </p>
        <ThemePicker />
      </div>
    </header>
  )
}
