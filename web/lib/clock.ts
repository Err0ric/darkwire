"use client"

import { useEffect, useState } from "react"

// Wall clocks in the viewer's zone. Null until mounted: the server does not know the zone.

export const pad = (n: number) => String(n).padStart(2, "0")

/** Ticks every second. */
export function useClock(): Date | null {
  const [now, setNow] = useState<Date | null>(null)
  useEffect(() => {
    const tick = () => setNow(new Date())
    const first = setTimeout(tick, 0)
    const timer = setInterval(tick, 1000)
    return () => {
      clearTimeout(first)
      clearInterval(timer)
    }
  }, [])
  return now
}

/** Ticks on each minute boundary. */
export function useMinuteClock(): Date | null {
  const [now, setNow] = useState<Date | null>(null)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    const tick = () => {
      setNow(new Date())
      timer = setTimeout(tick, 60_000 - (Date.now() % 60_000) + 50)
    }
    timer = setTimeout(tick, 0)
    return () => clearTimeout(timer)
  }, [])
  return now
}

export function zoneName(d: Date): string {
  return new Intl.DateTimeFormat([], { timeZoneName: "short" }).formatToParts(d).find((p) => p.type === "timeZoneName")?.value ?? "UTC"
}

/** "19:08", 24-hour UTC. */
export function utcHHMM(d: Date): string {
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
}

/** "PDT · 19:08 UTC", or just "UTC" when the viewer is on UTC. */
export function zoneAndUtc(d: Date): string {
  const zone = zoneName(d)
  return zone === "UTC" ? "UTC" : `${zone} · ${utcHHMM(d)} UTC`
}

/** "12:20:07" local, 24-hour. */
export function hms(d: Date): [string, string] {
  return [`${pad(d.getHours())}:${pad(d.getMinutes())}`, `:${pad(d.getSeconds())}`]
}
