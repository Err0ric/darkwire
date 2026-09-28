"use client"

import { useCallback, useEffect, useLayoutEffect, useRef, type CSSProperties } from "react"
import type React from "react"
import { cn } from "cn"

import type { SyncState } from "@/lib/sync"

/** Every look-and-timing knob of the wordmark. Tune here; the logic below reads only this. */
export const WORDMARK = {
  word: {
    weight: 700,
    tracking: "-0.03em",
  },
  tittle: {
    /** The real Geist Sans 700 "i" is drawn twice: white, then a copy in the status color clipped
     *  to everything above clipAbove (em above the baseline), so only its dot turns red and keeps
     *  Geist's own shape, size and gap. Measured: the stem tops out at 0.536em and the tittle
     *  starts at 0.602em, so the clip line sits in the gap. */
    clipAbove: 0.57,
    live: "var(--critical)",
    stale: "var(--accent)",
    staleOpacity: 0.5,
    down: "#525252",
  },
  tech: {
    text: ".tech",
    /** Of the wordmark size; baseline-aligned with "darkwire". */
    size: 0.55,
    color: "#4a4a4a",
    tracking: "-0.04em",
    /** Pulls ".tech" in toward "darkwire" (the mono "." sits mid-cell, which reads as a space),
     *  but not so far that the first binary digit runs into the "e". */
    gap: "-0.05em",
  },
  typing: {
    /** One character every charMs. */
    charMs: 700,
    /** Each character starts as a dim red binary digit that changes once at flipMs... */
    binaryColor: "#3d1a1a",
    flipMs: 175,
    /** ...then fades into the real character over fadeMs, ending at charMs. */
    fadeMs: 350,
  },
  cursor: {
    /** A faint hint, not a block: 0.4em wide and the mono x-height tall (em of ".tech"). */
    color: "rgba(74, 74, 74, 0.4)",
    width: 0.4,
    height: 0.53,
    /** Space between the last character and the cursor, em of ".tech". */
    gap: 0.06,
  },
  blink: {
    /** Cursor and the red dot blink together: opacity 1 -> low -> 1 on a cosine curve. */
    count: 2,
    durationMs: 1800,
    low: 0.25,
  },
  rerun: {
    /** A re-run (new rows): ".tech" fades out, pauses, then types in again. */
    fadeOutMs: 800,
    pauseMs: 300,
  },
} as const

/** Fired by a poll that found NEW rows (lib/dots.tsx); every mounted wordmark re-runs. */
export const NEW_ROWS_EVENT = "darkwire:new-rows"

/** The cursor's reserved space after ".tech", in em of the wordmark size. The landing lockup
 * subtracts it so the tagline and the centering use the visible end of ".tech". */
export const CURSOR_RESERVE_EM = WORDMARK.tech.size * (WORDMARK.cursor.width + WORDMARK.cursor.gap)

type Phase = "idle" | "fadeout" | "pause" | "typing" | "blink" | "done"

/** Clip the red copy of the "i" at the x-height: measure the baseline (a zero-height
 * inline-block's bottom edge) and the copy's box, and keep only what is above clipAbove.
 * Re-runs on resize and when fonts load; returns the cleanup. Server render: an em estimate. */
function watchTittle(a: HTMLSpanElement | null, l: HTMLSpanElement | null): (() => void) | undefined {
  if (!a || !l) return
  const place = () => {
    const fs = parseFloat(getComputedStyle(a).fontSize)
    if (!fs) return
    const base = a.getBoundingClientRect().bottom
    const box = l.getBoundingClientRect()
    const keep = Math.max(0, base - WORDMARK.tittle.clipAbove * fs - box.top)
    l.style.clipPath = `inset(0 0 ${Math.max(0, box.height - keep)}px 0)`
  }
  place()
  const ro = new ResizeObserver(place)
  ro.observe(a.parentElement ?? a)
  document.fonts?.ready.then(place)
  window.addEventListener("resize", place)
  return () => {
    ro.disconnect()
    window.removeEventListener("resize", place)
  }
}

/**
 * "darkwire" (Geist Sans 700) with the i's dot in red (the real glyph, recolored above the x-height), then ".tech" in faint Geist
 * Mono that types in. `state` null means the sync state is not known yet (".tech" stays hidden
 * until it is). Live: types in once on load and again on NEW rows; stale / down: static, the
 * square in its status color. prefers-reduced-motion: static. The animated parts are
 * aria-hidden; the link around it carries aria-label "darkwire.tech".
 */
export function Wordmark({ state, className, techClassName }: { state: SyncState | null; className?: string; techClassName?: string }) {
  const square = useRef<HTMLSpanElement>(null)
  const anchor = useRef<HTMLSpanElement>(null)
  useEffect(() => watchTittle(anchor.current, square.current), [])
  const overlay = useRef<HTMLSpanElement>(null)
  const cursor = useRef<HTMLSpanElement>(null)
  const chars = useRef<(HTMLSpanElement | null)[]>([])
  const bins = useRef<(HTMLSpanElement | null)[]>([])
  const frame = useRef(0)
  const fallback = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const phase = useRef<Phase>("idle")
  const played = useRef(false)
  const queued = useRef(false)
  const stateRef = useRef(state)
  useLayoutEffect(() => {
    stateRef.current = state
  }, [state])

  const text = WORDMARK.tech.text
  const T = WORDMARK.typing
  const B = WORDMARK.blink

  /** Everything shown, nothing moving: the settled mark. */
  const settle = useCallback((showTech: boolean) => {
    cancelAnimationFrame(frame.current)
    clearTimeout(fallback.current)
    phase.current = "done"
    if (overlay.current) overlay.current.style.opacity = showTech ? "1" : "0"
    chars.current.forEach((c) => {
      if (!c) return
      c.style.display = "inline-block"
      c.style.opacity = "1"
    })
    bins.current.forEach((b) => b && (b.style.opacity = "0"))
    if (cursor.current) cursor.current.style.display = "none"
    if (square.current) square.current.style.opacity = ""
  }, [])

  const run = useCallback(
    (rerun: boolean) => {
      const o = overlay.current
      const sq = square.current
      const cur = cursor.current
      if (!o || !sq || !cur) return
      cancelAnimationFrame(frame.current)
      const digits = [...text].map(() => [Math.random() < 0.5 ? "0" : "1", Math.random() < 0.5 ? "0" : "1"])
      digits.forEach((d) => d[1] === d[0] && (d[1] = d[0] === "0" ? "1" : "0")) // it must change once
      const typeStart = rerun ? WORDMARK.rerun.fadeOutMs + WORDMARK.rerun.pauseMs : 0
      const typeEnd = typeStart + text.length * T.charMs
      const blinkEnd = typeEnd + B.count * B.durationMs
      let start = 0
      let reset = !rerun
      // Frames can stop mid-animation (a background or occluded window) and leave the cursor up
      // until they resume. A timer, which keeps running there, settles the mark when the
      // animation should have ended, so the cursor never stays.
      clearTimeout(fallback.current)
      fallback.current = setTimeout(() => settle(true), blinkEnd + 400)

      const hideChars = () => {
        chars.current.forEach((c) => c && (c.style.display = "none"))
        bins.current.forEach((b) => b && (b.style.opacity = "0"))
      }
      if (!rerun) {
        hideChars()
        o.style.opacity = "1"
        cur.style.display = "inline-block"
        cur.style.opacity = "1"
      }

      const step = (t: number) => {
        if (!start) start = t
        const e = t - start
        if (e < typeStart) {
          // Re-run: fade the old ".tech" out, then a pause.
          phase.current = e < WORDMARK.rerun.fadeOutMs ? "fadeout" : "pause"
          o.style.opacity = String(Math.max(0, 1 - e / WORDMARK.rerun.fadeOutMs))
        } else if (e < typeEnd) {
          phase.current = "typing"
          if (!reset) {
            reset = true
            hideChars()
            o.style.opacity = "1"
            cur.style.display = "inline-block"
            cur.style.opacity = "1"
          }
          const te = e - typeStart
          ;[...text].forEach((_, i) => {
            const c = chars.current[i]
            const b = bins.current[i]
            if (!c || !b) return
            const local = te - i * T.charMs
            if (local < 0) {
              c.style.display = "none"
              return
            }
            c.style.display = "inline-block"
            const fade = Math.min(1, Math.max(0, (local - (T.charMs - T.fadeMs)) / T.fadeMs))
            b.textContent = local < T.flipMs ? digits[i][0] : digits[i][1]
            b.style.opacity = String(1 - fade)
            c.style.opacity = String(fade)
          })
        } else if (e < blinkEnd) {
          if (phase.current !== "blink") {
            phase.current = "blink"
            chars.current.forEach((c) => c && ((c.style.display = "inline-block"), (c.style.opacity = "1")))
            bins.current.forEach((b) => b && (b.style.opacity = "0"))
          }
          // One value drives both, so the cursor and the red dot blink in perfect sync.
          const f = ((e - typeEnd) % B.durationMs) / B.durationMs
          const v = B.low + (1 - B.low) * (0.5 + 0.5 * Math.cos(2 * Math.PI * f))
          cur.style.opacity = String(v)
          sq.style.opacity = String(v)
        } else {
          settle(true)
          return
        }
        frame.current = requestAnimationFrame(step)
      }
      frame.current = requestAnimationFrame(step)
    },
    [settle, text, T, B],
  )

  const play = useCallback(
    (rerun: boolean) => {
      if (stateRef.current !== "live") return
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        settle(true)
        return
      }
      if (document.hidden) {
        queued.current = true
        return
      }
      queued.current = false
      run(rerun)
    },
    [run, settle],
  )

  // First known state: live plays once; anything else shows the static mark.
  useEffect(() => {
    if (state === null) return
    if (state !== "live" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      settle(true)
      return
    }
    if (!played.current) {
      played.current = true
      play(false)
    }
  }, [state, play, settle])

  // New rows re-run it (queued while the tab is hidden, played once on return).
  useEffect(() => {
    const onNew = () => {
      if (!played.current || stateRef.current !== "live") return
      // Mid-animation: let it finish rather than restart.
      if (phase.current !== "done" && phase.current !== "idle") return
      play(true)
    }
    const onVisible = () => {
      if (!document.hidden && queued.current) play(played.current && phase.current === "done")
    }
    window.addEventListener(NEW_ROWS_EVENT, onNew)
    document.addEventListener("visibilitychange", onVisible)
    return () => {
      window.removeEventListener(NEW_ROWS_EVENT, onNew)
      document.removeEventListener("visibilitychange", onVisible)
      cancelAnimationFrame(frame.current)
      clearTimeout(fallback.current)
    }
  }, [play])

  const t = WORDMARK.tittle
  const tittleStyle: CSSProperties = {
    color: state === "down" ? t.down : state === "stale" ? t.stale : t.live,
    // Server render: keep about the top 0.29em of the line box (Geist's metrics at line-height 1).
    clipPath: "inset(0 0 calc(100% - 0.29em) 0)",
    ...(state === "stale" ? { filter: `opacity(${t.staleOpacity})` } : {}),
  }

  return (
    <span aria-hidden className={cn("inline-flex items-baseline leading-none whitespace-nowrap text-fg", className)}>
      <span style={{ fontWeight: WORDMARK.word.weight, letterSpacing: WORDMARK.word.tracking }}>
        darkw
        <span className="relative inline-block">
          {/* Baseline anchor: zero height, so its bottom edge is the baseline. */}
          <span ref={anchor} className="inline-block h-0 w-0 align-baseline" />
          i
          {/* The same "i" in the status color, clipped to its dot. */}
          <span ref={square} data-wordmark-square className="absolute inset-0" style={tittleStyle}>
            i
          </span>
        </span>
        re
      </span>
      <span
        className={cn("relative inline-block font-mono font-normal", techClassName)}
        style={{ fontSize: `${WORDMARK.tech.size}em`, letterSpacing: WORDMARK.tech.tracking, color: WORDMARK.tech.color, marginLeft: WORDMARK.tech.gap }}
      >
        {/* The reserve: the full ".tech" plus the cursor, invisible, so nothing shifts. Its last
            character marks where the fully typed "h" ends (the landing aligns its tagline to it). */}
        <span className="invisible">
          {text.slice(0, -1)}
          <span data-wordmark-last>{text.slice(-1)}</span>
        </span>
        <span className="invisible inline-block" style={{ width: `${WORDMARK.cursor.width + WORDMARK.cursor.gap}em` }} />
        <span ref={overlay} data-wordmark-tech className="absolute inset-0 text-left whitespace-pre" style={{ opacity: state === null ? 0 : undefined }}>
          {[...text].map((ch, i) => (
            <span
              key={i}
              ref={(el) => {
                chars.current[i] = el
              }}
              className="relative inline-block"
            >
              <span
                ref={(el) => {
                  bins.current[i] = el
                }}
                className="absolute inset-0"
                style={{ color: T.binaryColor, opacity: 0 }}
              />
              {ch}
            </span>
          ))}
          <span
            ref={cursor}
            data-wordmark-cursor
            className="inline-block align-baseline"
            style={{
              marginLeft: `${WORDMARK.cursor.gap}em`,
              width: `${WORDMARK.cursor.width}em`,
              height: `${WORDMARK.cursor.height}em`,
              background: WORDMARK.cursor.color,
              display: "none",
            }}
          />
        </span>
      </span>
    </span>
  )
}
