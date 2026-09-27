"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"

import { parseStack } from "@/lib/stack"

// Personal preferences with no accounts: your stack of vendors (and, later, a theme).
// - The URL is the source of truth: ?stack=cisco,fortinet. It always wins.
// - "Remember on this browser" is off by default. When on, localStorage keeps only
//   { stack, theme } under one key; nothing else, no feed data, no service worker.
// - A stack that arrives in a shared URL is shown but never written to storage; only
//   the viewer's own changes are remembered.

const STORE = "darkwire.prefs"

export interface Stored {
  stack?: string[]
  theme?: string
}

export interface Prefs {
  /** False until the URL and storage have been read on the client. */
  ready: boolean
  stack: string[]
  remember: boolean
  setStack: (stack: string[]) => void
  toggleVendor: (slug: string) => void
  setRemember: (on: boolean) => void
  reset: () => void
  /** "?stack=a,b" (plus any other kept params) for links, or "". */
  query: (extra?: Record<string, string | undefined>) => string
}

export function readStored(): Stored | null {
  try {
    const raw = window.localStorage.getItem(STORE)
    return raw ? (JSON.parse(raw) as Stored) : null
  } catch {
    return null
  }
}

export function writeStored(value: Stored | null) {
  try {
    if (value) window.localStorage.setItem(STORE, JSON.stringify(value))
    else window.localStorage.removeItem(STORE)
  } catch {
    // Storage blocked (private window): remembering silently does nothing.
  }
}

/** Set or drop one query param in the current URL without navigating. */
export function setUrlParam(name: string, value: string | null) {
  const url = new URL(window.location.href)
  if (value) url.searchParams.set(name, value)
  else url.searchParams.delete(name)
  window.history.replaceState(null, "", url.pathname + (url.search ? url.search.replace(/%2C/gi, ",") : "") + url.hash)
}

const PrefsContext = createContext<Prefs | null>(null)

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [stack, setStackState] = useState<string[]>([])
  const [remember, setRememberState] = useState(false)
  const [ready, setReady] = useState(false)

  // Client only: read the URL, then storage if the viewer opted in. URL wins.
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("stack")
    const stored = readStored()
    const next = fromUrl !== null ? parseStack(fromUrl) : parseStack(stored?.stack?.join(","))
    const load = () => {
      setRememberState(stored !== null)
      setStackState(next)
      // A remembered stack goes into the URL too, so what's on screen is what a copied link shows.
      if (fromUrl === null && next.length) setUrlParam("stack", next.join(","))
      setReady(true)
    }
    load()
  }, [])

  const setStack = useCallback(
    (next: string[]) => {
      const clean = parseStack(next.join(","))
      setStackState(clean)
      setUrlParam("stack", clean.length ? clean.join(",") : null)
      if (remember) writeStored({ ...readStored(), stack: clean })
    },
    [remember],
  )

  const toggleVendor = useCallback(
    (slug: string) => setStack(stack.includes(slug) ? stack.filter((s) => s !== slug) : [...stack, slug]),
    [stack, setStack],
  )

  const setRemember = useCallback(
    (on: boolean) => {
      setRememberState(on)
      if (on) writeStored({ ...readStored(), stack })
      else writeStored(null)
    },
    [stack],
  )

  const reset = useCallback(() => {
    writeStored(null)
    setRememberState(false)
  }, [])

  const query = useCallback(
    (extra: Record<string, string | undefined> = {}) => {
      const params = new URLSearchParams()
      for (const [k, v] of Object.entries(extra)) if (v) params.set(k, v)
      // Always carried, remembered or not, so every URL stays shareable.
      if (stack.length) params.set("stack", stack.join(","))
      const qs = params.toString().replace(/%2C/gi, ",")
      return qs ? `?${qs}` : ""
    },
    [stack],
  )

  const value = useMemo(
    () => ({ ready, stack, remember, setStack, toggleVendor, setRemember, reset, query }),
    [ready, stack, remember, setStack, toggleVendor, setRemember, reset, query],
  )
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>
}

export function usePrefs(): Prefs {
  const prefs = useContext(PrefsContext)
  if (!prefs) throw new Error("usePrefs outside PrefsProvider")
  return prefs
}
