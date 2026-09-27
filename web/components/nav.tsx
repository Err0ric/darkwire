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
  { href: "/cves", label: "CVEs" },
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
  const label = sync.failing ? "Sync unavailable" : minutes !== null ? syncedLabel(minutes) : ""

  return (
    <header data-chrome className="flex h-15 items-center px-4 md:px-12">
      {!home && (
        <Link href={`/${query()}`} className="mr-4 flex items-center gap-2 outline-none focus-visible:outline-1 focus-visible:outline-rule sm:mr-6 md:mr-10">
          <SyncDot state={dot} className="size-1.5" />
          <span className="text-lg leading-none font-bold tracking-[-0.01em] text-fg">darkwire</span>
        </Link>
      )}

      <nav aria-label="Main" className="flex min-w-0 items-center gap-3.5 sm:gap-6">
        {LINKS.map(({ href, label }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`)
          return (
            <Link
              key={href}
              href={`${href}${query()}`}
              aria-current={active ? "page" : undefined}
              className={cn(
                "text-[14px] leading-none outline-none focus-visible:text-fg sm:text-[15px]",
                active ? "text-fg" : "text-muted hover:text-fg-2",
              )}
            >
              {label}
            </Link>
          )
        })}
      </nav>

      <div className="ml-auto flex shrink-0 items-center gap-4 pl-3">
        {now !== null && !OWN_CLOCK.has(pathname) && (
          <time
            dateTime={new Date(now).toISOString()}
            title="Coordinated Universal Time"
            className="hidden font-mono text-xs leading-none text-dim min-[1200px]:block"
          >
            {utcHHMM(new Date(now))} UTC
          </time>
        )}
        <p className="hidden text-[15px] leading-none text-muted sm:block" aria-live="polite">
          {label}
        </p>
        <ThemePicker />
      </div>
    </header>
  )
}
