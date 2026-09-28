"use client"

import { useCallback, useSyncExternalStore } from "react"

import { getServices, type ServicesOut } from "@/lib/api"

// One services poll for the whole page: the nav's status link and the wire's rail block read
// the same data, fetched every 3 minutes while anything is subscribed. `key` is the API's slugs
// parameter ("all" for every tracked service, "" for its default set); a new key starts over.

const POLL_MS = 180_000

let key: string | null = null
let data: ServicesOut | null = null
let at = 0
let inflight = false
let timer: ReturnType<typeof setInterval> | undefined
const subs = new Set<() => void>()

function publish(k: string, d: ServicesOut) {
  if (k !== key) return
  data = d
  at = Date.now()
  subs.forEach((fn) => fn())
}

function load() {
  if (inflight || key === null) return
  const k = key
  inflight = true
  getServices(k || undefined)
    .then((d) => publish(k, d))
    .catch(() => {})
    .finally(() => {
      inflight = false
    })
}

function use(k: string) {
  if (k !== key) {
    key = k
    data = null
    at = 0
    clearInterval(timer)
    timer = undefined
  }
  timer ??= setInterval(load, POLL_MS)
  if (Date.now() - at > POLL_MS) load()
}

/** Live services for the API slugs `k` (null: not yet). `initial` is server-rendered data for
 * that same set; it seeds the store so nothing refetches at once. */
export function useLiveServices(k: string | null, initial: ServicesOut | null = null): ServicesOut | null {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (k === null) return () => {}
      if (initial && (k !== key || at === 0)) {
        key = k
        data = initial
        at = Date.now()
      }
      subs.add(onChange)
      use(k)
      return () => {
        subs.delete(onChange)
        if (!subs.size) {
          clearInterval(timer)
          timer = undefined
        }
      }
    },
    [k, initial],
  )
  return useSyncExternalStore(
    subscribe,
    () => (k !== null && key === k && data) || initial,
    () => initial,
  )
}
