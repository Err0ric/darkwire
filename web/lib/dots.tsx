"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { cn } from "cn"

// The new-row dot (CLAUDE.md Motion): a 6px --critical dot just left of the headline.
// - arrive: fades in over 300ms, pulses 1 -> 0.3 -> 1 three times on the 2.4s cycle, then
//   holds at 60%.
// - waiting: arrived while the tab was hidden; sits solid, pulses when the tab is shown.
// - solid: beyond the first 5 of one poll; fades in to 60%, no pulse.
// At 10 minutes it fades out over 1s. Expanding the row clears it at once. Nothing on screen
// at page load gets a dot. prefers-reduced-motion: the global rule stops the animations, so
// the dot is simply solid at 60% and disappears at 10 minutes.

export type DotMode = "arrive" | "waiting" | "return" | "solid"

export interface DotState {
  mode: DotMode
  at: number
  fading: boolean
  /** Restarts the animation when a waiting dot starts pulsing. */
  key: number
}

const LIFETIME_MS = 10 * 60_000
const FADE_MS = 1_000
const MAX_PULSING = 5

export function useDots() {
  const [dots, setDots] = useState<ReadonlyMap<number, DotState>>(new Map())
  const seq = useRef(0)

  /** Rows that just arrived, top first. Only the top 5 pulse. */
  const add = useCallback((ids: number[]) => {
    if (!ids.length) return
    const hidden = document.hidden
    const now = Date.now()
    setDots((prev) => {
      const next = new Map(prev)
      ids.forEach((id, i) => {
        const mode: DotMode = i >= MAX_PULSING ? "solid" : hidden ? "waiting" : "arrive"
        next.set(id, { mode, at: now, fading: false, key: ++seq.current })
      })
      return next
    })
  }, [])

  const clear = useCallback((id: number) => {
    setDots((prev) => {
      if (!prev.has(id)) return prev
      const next = new Map(prev)
      next.delete(id)
      return next
    })
  }, [])

  // Waiting dots pulse when the viewer comes back.
  useEffect(() => {
    const onVisible = () => {
      if (document.hidden) return
      setDots((prev) => {
        if (![...prev.values()].some((d) => d.mode === "waiting")) return prev
        const next = new Map(prev)
        for (const [id, d] of next) if (d.mode === "waiting") next.set(id, { ...d, mode: "return", key: ++seq.current })
        return next
      })
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => document.removeEventListener("visibilitychange", onVisible)
  }, [])

  // Ten minutes, then a 1s fade, then gone.
  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now()
      setDots((prev) => {
        let changed = false
        const next = new Map(prev)
        for (const [id, d] of next) {
          if (now - d.at >= LIFETIME_MS + FADE_MS) {
            next.delete(id)
            changed = true
          } else if (!d.fading && now - d.at >= LIFETIME_MS) {
            next.set(id, { ...d, fading: true })
            changed = true
          }
        }
        return changed ? next : prev
      })
    }, 1_000)
    return () => clearInterval(timer)
  }, [])

  return { dots, add, clear }
}

// Resting opacity 60%; a waiting dot is fully solid until it can pulse.
const ANIMATION: Record<DotMode, string> = {
  arrive: "opacity-60 animate-dot-arrive",
  return: "opacity-60 animate-dot-return",
  solid: "opacity-60 animate-dot-solid",
  waiting: "opacity-100",
}

/** Absolutely placed in the gutter left of a `relative` headline box. */
export function NewDot({ state, className }: { state: DotState; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "pointer-events-none absolute size-1.5 transition-opacity duration-1000",
        state.fading ? "opacity-0" : "opacity-100",
        className,
      )}
    >
      <span key={state.key} className={cn("block size-full rounded-full bg-critical", ANIMATION[state.mode])} />
    </span>
  )
}
