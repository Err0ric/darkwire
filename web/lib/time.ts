"use client"

import { useSyncExternalStore } from "react"

// One shared minute ticker for every relative timestamp on the page.
const TICK_MS = 60_000
let now = Date.now()
const listeners = new Set<() => void>()
let timer: ReturnType<typeof setInterval> | null = null

function subscribe(listener: () => void) {
  listeners.add(listener)
  if (!timer) {
    now = Date.now()
    timer = setInterval(() => {
      now = Date.now()
      listeners.forEach((l) => l())
    }, TICK_MS)
  }
  return () => {
    listeners.delete(listener)
    if (!listeners.size && timer) {
      clearInterval(timer)
      timer = null
    }
  }
}

/** Current time, updated every minute. Null during server render and hydration. */
export function useNow(): number | null {
  return useSyncExternalStore(
    subscribe,
    () => now,
    () => null,
  )
}

/** "12m", "5h", "3d". Mono, no "ago": the column says it. */
export function age(iso: string, nowMs: number): string {
  const minutes = Math.max(0, Math.floor((nowMs - Date.parse(iso)) / 60_000))
  if (minutes < 60) return `${Math.max(1, minutes)}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}
