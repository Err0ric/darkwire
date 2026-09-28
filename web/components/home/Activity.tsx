"use client"

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"

import type { Activity as ActivityData, ActivityHour, BoardEvent } from "@/lib/api"
import { pad } from "@/lib/clock"

/**
 * Every setting of the landing's activity trace and log line. Tune the look or switch parts off
 * here; the logic below reads only this.
 */
export const ACTIVITY = {
  trace: {
    on: true,
    width: 760, // px, the most it grows to; narrower screens scale it down
    height: 60,
    baseline: 52, // y of the flat line inside the 60px box
    maxSpike: 46, // px, the busiest hour of the 24
    spikeHalfWidth: 5, // px each side of an hour's peak
    scale: "sqrt" as "sqrt" | "linear", // sqrt keeps quiet hours visible next to a busy one
    lineColor: "#3a1414",
    lineWidth: 1,
    hotColor: "var(--critical)", // hours with a Critical, KEV or exploited row
    hotOpacity: 0.6,
  },
  pulse: {
    on: true,
    seconds: 8, // one pass, left to right
    length: 44, // px of bright line
    color: "var(--critical)",
    dot: 4, // px, the head
  },
  log: {
    on: true,
    typingMs: 25, // per character
    cycleMs: 30_000, // no new event for this long: show an older one
    cycleCount: 5, // how far back the cycle goes
    cursorColor: "#4a4a4a",
    cursorFadeMs: 700,
    // The faintest text that clears 4.5:1 on --bg (#555 would be about 2.9:1).
    timeColor: "var(--dim-text)",
    kindColor: "var(--fg-2)",
    detailColor: "var(--dim-text)",
    hotColor: "var(--critical-text)",
    hotWords: /\b(KEV|critical|exploited)\b/i,
    kindWidth: 9, // characters, the type column
  },
}

const HOT_SPLIT = new RegExp(`(${ACTIVITY.log.hotWords.source})`, ACTIVITY.log.hotWords.flags.includes("i") ? "gi" : "g")

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)")
    const on = () => setReduced(q.matches)
    on()
    q.addEventListener("change", on)
    return () => q.removeEventListener("change", on)
  }, [])
  return reduced
}

// ---------------------------------------------------------------- trace

function spikes(hours: ActivityHour[]) {
  const T = ACTIVITY.trace
  const f = T.scale === "sqrt" ? Math.sqrt : (n: number) => n
  const max = Math.max(1, ...hours.map((h) => f(h.items)))
  const slot = T.width / Math.max(1, hours.length)
  return hours.map((h, i) => ({
    x: (i + 0.5) * slot,
    h: h.items ? Math.max(2, (f(h.items) / max) * T.maxSpike) : 0,
    hot: h.critical > 0,
  }))
}

function tracePath(hours: ActivityHour[]): string {
  const T = ACTIVITY.trace
  const d = [`M0 ${T.baseline}`]
  for (const s of spikes(hours)) {
    if (!s.h) continue
    d.push(`L${s.x - T.spikeHalfWidth} ${T.baseline}`, `L${s.x} ${T.baseline - s.h}`, `L${s.x + T.spikeHalfWidth} ${T.baseline}`)
  }
  d.push(`L${T.width} ${T.baseline}`)
  return d.join(" ")
}

function Trace({ hours, animate }: { hours: ActivityHour[]; animate: boolean }) {
  const T = ACTIVITY.trace
  const P = ACTIVITY.pulse
  const d = useMemo(() => tracePath(hours), [hours])
  const hot = useMemo(() => spikes(hours).filter((s) => s.hot && s.h), [hours])
  const pulse = useRef<SVGPathElement>(null)
  const head = useRef<HTMLSpanElement>(null)

  // The bright segment: a dash of P.length along a copy of the line, moved by time (so a hidden
  // tab, where frames stop, picks up where the clock says on return).
  useEffect(() => {
    const path = pulse.current
    const dot = head.current
    if (!animate || !P.on || !path || !dot) return
    const total = path.getTotalLength()
    path.style.strokeDasharray = `${P.length} ${total + P.length}`
    let frame = 0
    const tick = (t: number) => {
      const at = ((t / 1000) % P.seconds) / P.seconds
      path.style.strokeDashoffset = `${P.length - at * (total + P.length)}`
      const p = path.getPointAtLength(Math.min(total, at * (total + P.length)))
      dot.style.left = `${(p.x / T.width) * 100}%`
      dot.style.top = `${p.y}px`
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [animate, d, P.on, P.length, P.seconds, T.width])

  const all = hours.reduce((n, h) => n + h.items, 0)
  const critical = hours.reduce((n, h) => n + h.critical, 0)
  return (
    <div className="w-full" style={{ maxWidth: T.width }}>
      <div className="relative" style={{ height: T.height }}>
        <svg
          role="img"
          aria-label={`Rows per hour over the last 24 hours: ${all} items, ${critical} critical or KEV`}
          viewBox={`0 0 ${T.width} ${T.height}`}
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full overflow-visible"
        >
          <path d={d} fill="none" vectorEffect="non-scaling-stroke" style={{ stroke: T.lineColor, strokeWidth: T.lineWidth }} />
          {hot.map((s) => (
            <path
              key={s.x}
              d={`M${s.x - T.spikeHalfWidth} ${T.baseline} L${s.x} ${T.baseline - s.h} L${s.x + T.spikeHalfWidth} ${T.baseline}`}
              fill="none"
              vectorEffect="non-scaling-stroke"
              style={{ stroke: T.hotColor, strokeOpacity: T.hotOpacity, strokeWidth: T.lineWidth }}
            />
          ))}
          {animate && P.on && (
            <path
              ref={pulse}
              d={d}
              fill="none"
              vectorEffect="non-scaling-stroke"
              style={{ stroke: P.color, strokeWidth: T.lineWidth + 0.5, strokeLinecap: "round", strokeDashoffset: P.length }}
            />
          )}
        </svg>
        {animate && P.on && (
          // An HTML dot, so the stretched SVG does not squash it into an ellipse.
          <span
            ref={head}
            aria-hidden
            className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ width: P.dot, height: P.dot, background: P.color, left: 0, top: T.baseline }}
          />
        )}
      </div>
      <p className="mt-1.5 flex justify-between font-mono text-[11px] leading-4 text-dim-text">
        <span>-24h</span>
        <span>
          {all} {all === 1 ? "item" : "items"} · {critical} critical/KEV
        </span>
        <span>now</span>
      </p>
    </div>
  )
}

// ---------------------------------------------------------------- log line

type Part = { text: string; color: string }

function lineParts(e: BoardEvent): Part[] {
  const L = ACTIVITY.log
  const at = new Date(e.at)
  const joiner = e.kind === "cluster" || e.kind === "summary" ? " · " : " "
  const detail = `${e.subject}${joiner}${e.detail}`
  return [
    { text: `${pad(at.getHours())}:${pad(at.getMinutes())}  `, color: L.timeColor },
    { text: e.kind.padEnd(L.kindWidth), color: L.kindColor },
    ...detail
      .split(HOT_SPLIT)
      .filter(Boolean)
      .map((text) => ({ text, color: L.hotWords.test(text) ? L.hotColor : L.detailColor })),
  ]
}

function LogLine({ events, animate }: { events: BoardEvent[]; animate: boolean }) {
  const L = ACTIVITY.log
  const [shown, setShown] = useState<BoardEvent | null>(events[0] ?? null)
  const [typed, setTyped] = useState<number | null>(null) // null: fully shown
  const [cursor, setCursor] = useState(false)
  const newest = useRef(events[0]?.id ?? 0)
  const cycle = useRef(0)
  const eventsRef = useRef(events)
  const lastChange = useRef(0)
  useLayoutEffect(() => {
    eventsRef.current = events
  })

  // Types `e` in (or shows it at once under reduced motion).
  const typeIn = useRef<(e: BoardEvent) => void>(() => undefined)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    typeIn.current = (e: BoardEvent) => {
      clearTimeout(timer)
      setShown(e)
      lastChange.current = Date.now()
      if (!animate) {
        setTyped(null)
        return
      }
      const length = lineParts(e).reduce((n, p) => n + p.text.length, 0)
      let n = 0
      setCursor(true)
      const step = () => {
        n += 1
        setTyped(n)
        if (n < length) timer = setTimeout(step, L.typingMs)
        else {
          setTyped(null)
          timer = setTimeout(() => setCursor(false), 400)
        }
      }
      step()
    }
    return () => clearTimeout(timer)
  }, [animate, L.typingMs])

  // A new event (the poll brought one): type it in now, or on return when the tab is hidden.
  useEffect(() => {
    const top = events[0]
    if (!top || top.id <= newest.current) return
    newest.current = top.id
    cycle.current = 0
    if (!document.hidden) typeIn.current(top)
    else {
      const onShow = () => {
        if (document.hidden) return
        document.removeEventListener("visibilitychange", onShow)
        typeIn.current(eventsRef.current[0])
      }
      document.addEventListener("visibilitychange", onShow)
      return () => document.removeEventListener("visibilitychange", onShow)
    }
  }, [events])

  // Quiet for L.cycleMs: step back through the last L.cycleCount events, one per interval.
  useEffect(() => {
    if (!animate || !L.on) return
    lastChange.current = Date.now()
    const timer = setInterval(() => {
      const list = eventsRef.current.slice(0, L.cycleCount)
      if (document.hidden || list.length < 2 || Date.now() - lastChange.current < L.cycleMs) return
      cycle.current = (cycle.current + 1) % list.length
      typeIn.current(list[cycle.current])
    }, 1000)
    return () => clearInterval(timer)
  }, [animate, L.on, L.cycleCount, L.cycleMs])

  const parts = shown ? lineParts(shown) : []
  let left = typed ?? Infinity
  const visible = parts.map((p) => {
    const text = p.text.slice(0, Math.max(0, left))
    left -= p.text.length
    return { ...p, text }
  })
  return (
    <div className="mt-3 w-full" style={{ maxWidth: ACTIVITY.trace.width }}>
      {/* The typed line is for the eye (it changes a character at a time); screen readers get
          the whole event in plain text. */}
      <p aria-hidden className="h-[18px] overflow-hidden text-left font-mono text-[12.5px] leading-[18px] text-ellipsis whitespace-pre">
        {visible.map((p, i) => (
          <span key={i} style={{ color: p.color }}>
            {p.text}
          </span>
        ))}
        {animate && (
          <span
            className="ml-px inline-block h-[13px] w-[7px] align-[-2px]"
            style={{ background: L.cursorColor, opacity: cursor ? 1 : 0, transition: `opacity ${L.cursorFadeMs}ms` }}
          />
        )}
      </p>
      {shown && (
        <p className="sr-only">
          Latest board event: {parts.map((p) => p.text).join("").replace(/\s+/g, " ")}
        </p>
      )}
    </div>
  )
}

/** The landing's activity: a 24-hour trace of rows per hour and one line of the board's log.
 * Heights are fixed from the first render, so nothing moves when data arrives. */
export function Activity({ data }: { data: ActivityData | null }) {
  const reduced = useReducedMotion()
  const animate = !reduced
  return (
    <section aria-label="Activity" className="mt-[clamp(28px,4.4vh,56px)] flex w-full flex-col items-center">
      {ACTIVITY.trace.on && <Trace hours={data?.hours ?? []} animate={animate} />}
      {ACTIVITY.log.on && <LogLine events={data?.events ?? []} animate={animate} />}
    </section>
  )
}
