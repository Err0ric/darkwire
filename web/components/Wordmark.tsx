"use client"

import { useCallback, useEffect, useRef, type CSSProperties } from "react"
import { cn } from "cn"

import type { SyncState } from "@/lib/sync"

/** Every look-and-timing knob of the wordmark. Tune here; the logic below reads only this. */
export const WORDMARK = {
  word: {
    weight: 700,
    tracking: "-0.03em",
  },
  square: {
    /** Stands in for the i's dot, over a dotless ı. */
    size: "0.22em",
    /** From the bottom of the ı's box (leading-none) to the square's bottom edge. */
    bottom: "0.75em",
    /** Horizontal nudge from the ı's center (Geist's ı stem sits a touch left of center). */
    nudge: "0em",
    live: "var(--critical)",
    stale: "var(--accent)",
    staleOpacity: 0.5,
    down: "#525252",
  },
  tech: {
    text: ".tech",
    size: "0.8em",
    color: "#4a4a4a",
    tracking: "-0.04em",
    /** Pulls ".tech" in toward "darkwire": the mono "." sits mid-cell, which reads as a space. */
    gap: "-0.22em",
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
    color: "rgba(74, 74, 74, 0.6)",
    width: "0.55em",
    height: "0.78em",
  },
  blink: {
    /** Cursor and square blink together: opacity 1 -> low -> 1 on a cosine curve. */
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

type Phase = "idle" | "fadeout" | "pause" | "typing" | "blink" | "done"

/**
 * "darkwire" (Geist Sans 700) with a red square for the i's dot, then ".tech" in faint Geist
 * Mono that types in. `state` null means the sync state is not known yet (".tech" stays hidden
 * until it is). Live: types in once on load and again on NEW rows; stale / down: static, the
 * square in its status color. prefers-reduced-motion: static. The animated parts are
 * aria-hidden; the link around it carries aria-label "darkwire.tech".
 */
export function Wordmark({ state, className, techClassName }: { state: SyncState | null; className?: string; techClassName?: string }) {
  const square = useRef<HTMLSpanElement>(null)
  const overlay = useRef<HTMLSpanElement>(null)
  const cursor = useRef<HTMLSpanElement>(null)
  const chars = useRef<(HTMLSpanElement | null)[]>([])
  const bins = useRef<(HTMLSpanElement | null)[]>([])
  const frame = useRef(0)
  const phase = useRef<Phase>("idle")
  const played = useRef(false)
  const queued = useRef(false)
  const stateRef = useRef(state)
  stateRef.current = state

  const text = WORDMARK.tech.text
  const T = WORDMARK.typing
  const B = WORDMARK.blink

  /** Everything shown, nothing moving: the settled mark. */
  const settle = useCallback((showTech: boolean) => {
    cancelAnimationFrame(frame.current)
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
          // One value drives both, so the cursor and the square blink in perfect sync.
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
    }
  }, [play])

  const sq = WORDMARK.square
  const squareStyle: CSSProperties = {
    width: sq.size,
    height: sq.size,
    bottom: sq.bottom,
    marginLeft: sq.nudge,
    background: state === "down" ? sq.down : state === "stale" ? sq.stale : sq.live,
    ...(state === "stale" ? { filter: `opacity(${sq.staleOpacity})` } : {}),
  }

  return (
    <span aria-hidden className={cn("inline-flex items-baseline leading-none whitespace-nowrap text-fg", className)}>
      <span style={{ fontWeight: WORDMARK.word.weight, letterSpacing: WORDMARK.word.tracking }}>
        darkw
        <span className="relative inline-block">
          {"ı"}
          <span ref={square} data-wordmark-square className="absolute left-1/2 -translate-x-1/2" style={squareStyle} />
        </span>
        re
      </span>
      <span
        className={cn("relative inline-block font-mono font-normal", techClassName)}
        style={{ fontSize: WORDMARK.tech.size, letterSpacing: WORDMARK.tech.tracking, color: WORDMARK.tech.color, marginLeft: WORDMARK.tech.gap }}
      >
        {/* The reserve: the full ".tech" plus the cursor, invisible, so nothing shifts. */}
        <span className="invisible">{text}</span>
        <span className="invisible inline-block" style={{ width: WORDMARK.cursor.width }} />
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
            className="ml-[0.06em] inline-block align-baseline"
            style={{ width: WORDMARK.cursor.width, height: WORDMARK.cursor.height, background: WORDMARK.cursor.color, display: "none" }}
          />
        </span>
      </span>
    </span>
  )
}
