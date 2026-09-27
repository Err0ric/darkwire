"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"
import { cn } from "cn"

import { getStatus, type Status } from "@/lib/api"
import { usePrefs } from "@/lib/prefs"

const LINKS = [
  { href: "/wire", label: "Wire" },
  { href: "/cves", label: "CVEs" },
  { href: "/vendors", label: "Vendors" },
]

const STATUS_POLL_MS = 60_000
const CLOCK_TICK_MS = 15_000
const STALE_AFTER_MIN = 30

type Sync = { status: Status | null; failing: boolean }

function lastSyncAt(status: Status | null): number | null {
  const at = status?.sync.last_finished_at ?? status?.sync.last_started_at
  return at ? Date.parse(at) : null
}

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

  const syncedAt = lastSyncAt(sync.status)
  const minutes = syncedAt !== null && now !== null ? Math.max(0, Math.floor((now - syncedAt) / 60_000)) : null
  const dot = sync.failing ? "down" : minutes !== null && minutes <= STALE_AFTER_MIN ? "live" : "stale"
  const label = sync.failing ? "Sync unavailable" : minutes !== null ? syncedLabel(minutes) : ""

  return (
    <header data-chrome className="flex h-15 items-center px-4 md:px-12">
      <Link href={`/${query()}`} className="flex items-center gap-2 outline-none focus-visible:outline-1 focus-visible:outline-rule">
        <span
          aria-hidden
          className={cn(
            "size-1.5 rounded-full",
            dot === "down" ? "bg-dim" : "bg-accent",
            dot === "live" && "animate-pulse-dot",
          )}
        />
        <span className="text-lg leading-none font-bold tracking-[-0.01em] text-fg">darkwire</span>
      </Link>

      <nav aria-label="Main" className="ml-6 flex items-center gap-6 md:ml-10">
        {LINKS.map(({ href, label }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`)
          return (
            <Link
              key={href}
              href={`${href}${query()}`}
              aria-current={active ? "page" : undefined}
              className={cn(
                "text-[15px] leading-none outline-none focus-visible:text-fg",
                active ? "text-fg" : "text-muted hover:text-fg-2",
              )}
            >
              {label}
            </Link>
          )
        })}
      </nav>

      <p className="ml-auto hidden text-[15px] leading-none text-muted sm:block" aria-live="polite">
        {label}
      </p>
    </header>
  )
}
