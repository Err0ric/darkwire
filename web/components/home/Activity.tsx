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
    minSpike: 3, // px, the smallest non-zero hour, so a quiet hour is still a visible bump
    spikeHalfWidth: 5, // px each side of an hour's peak
    scale: "sqrt" as "sqrt" | "linear", // sqrt of the count (capped at the max): one busy hour does not flatten the rest
    // What a full-height spike means: the busiest single hour of the last 7 days (a quiet day draws
    // small blips, a busy one tall spikes), or of the 24 hours shown.
    scaleBasis: "7d" as "7d" | "24h",
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
    // Only these kinds: no article headlines on the landing (cluster and summary events are still
    // recorded, and shown nowhere else yet).
    kinds: ["ingest", "kev", "nvd", "services"] as string[],
    lines: 3, // newest on the bottom
    lineHeight: 18, // px
    // Older lines are dimmer, bottom (newest) to top. Text must clear 4.5:1 on --bg (axe), which
    // rules out opacity on text (50% of even --fg-2 fails), so they step down through the text
    // tokens instead: the middle line's type column goes --muted, the top line is all
    // --dim-text. lineOpacity stays 1; lower it only if that contrast rule is dropped.
    lineOpacity: [1, 1, 1],
    lineColors: [null, { kind: "var(--muted)" }, { all: "var(--dim-text)" }] as ({ kind?: string; all?: string } | null)[],
    slideMs: 300, // older lines move up, the top one fades out
    typingMs: 25, // per character
    cycleMs: 30_000, // no new event for this long: bring back an older one
    cycleCount: 10, // how far back the cycle goes
    cursorColor: "#4a4a4a",
    cursorFadeMs: 700,
    // The faintest text that clears 4.5:1 on --bg (#555 would be about 2.9:1).
    timeColor: "var(--dim-text)",
    kindColor: "var(--fg-2)",
    detailColor: "var(--dim-text)",
    hotColor: "var(--critical-text)",
    hotWords: /\b(?:KEV|critical|exploited)\b/i, // non-capturing: the split below adds its own group
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

function spikes(hours: ActivityHour[], peak7d: number) {
  const T = ACTIVITY.trace
  const f = T.scale === "sqrt" ? Math.sqrt : (n: number) => n
  const max = Math.max(1, T.scaleBasis === "7d" ? f(peak7d) : 0, ...hours.map((h) => f(h.items)))
  const slot = T.width / Math.max(1, hours.length)
  return hours.map((h, i) => ({
    x: (i + 0.5) * slot,
    h: h.items ? Math.max(T.minSpike, (Math.min(f(h.items), max) / max) * T.maxSpike) : 0,
    hot: h.critical > 0,
  }))
}

function tracePath(hours: ActivityHour[], peak7d: number): string {
  const T = ACTIVITY.trace
  const d = [`M0 ${T.baseline}`]
  for (const s of spikes(hours, peak7d)) {
    if (!s.h) continue
    d.push(`L${s.x - T.spikeHalfWidth} ${T.baseline}`, `L${s.x} ${T.baseline - s.h}`, `L${s.x + T.spikeHalfWidth} ${T.baseline}`)
  }
  d.push(`L${T.width} ${T.baseline}`)
  return d.join(" ")
}

function Trace({ hours, peak7d, animate }: { hours: ActivityHour[]; peak7d: number; animate: boolean }) {
  const T = ACTIVITY.trace
  const P = ACTIVITY.pulse
  const d = useMemo(() => tracePath(hours, peak7d), [hours, peak7d])
  const hot = useMemo(() => spikes(hours, peak7d).filter((s) => s.hot && s.h), [hours, peak7d])
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
      <p aria-hidden className="mt-1.5 flex justify-between font-mono text-[11px] leading-4 text-dim-text">
        <span>-24h</span>
        <span>now</span>
      </p>
    </div>
  )
}

// ---------------------------------------------------------------- log line

type Part = { text: string; color: string }

function lineParts(e: BoardEvent, slot = 0): Part[] {
  const L = ACTIVITY.log
  const over = L.lineColors[slot] ?? null
  const at = new Date(e.at)
  const joiner = e.kind === "cluster" || e.kind === "summary" ? " · " : " "
  const detail = `${e.subject}${joiner}${e.detail}`
  return [
    { text: `${pad(at.getHours())}:${pad(at.getMinutes())}  `, color: over?.all ?? L.timeColor },
    { text: e.kind.padEnd(L.kindWidth), color: over?.all ?? over?.kind ?? L.kindColor },
    ...detail
      .split(HOT_SPLIT)
      .filter(Boolean)
      .map((text) => ({ text, color: over?.all ?? (L.hotWords.test(text) ? L.hotColor : L.detailColor) })),
  ]
}

type Line = { key: number; event: BoardEvent | null }

/** The parts cut to the first `typed` characters (all of them when null). */
function Parts({ parts, typed }: { parts: Part[]; typed: number | null }) {
  const starts = parts.map((_, i) => parts.slice(0, i).reduce((n, p) => n + p.text.length, 0))
  return (
    <>
      {parts.map((p, i) => (
        <span key={i} style={{ color: p.color }}>
          {typed === null ? p.text : p.text.slice(0, Math.max(0, typed - starts[i]))}
        </span>
      ))}
    </>
  )
}

/** The board's log: L.lines lines, newest on the bottom. A new event (or, after L.cycleMs of
 * quiet, an older one brought back) enters on the bottom line and types in; the older lines
 * move up a line and the top one fades out. No events yet: "watching N sources…". */
function Log({ events, sources, animate }: { events: BoardEvent[]; sources: number | null; animate: boolean }) {
  const L = ACTIVITY.log
  // Line keys: the first render's lines take 0..L.lines-1, later ones count up from L.lines.
  const seq = useRef(L.lines)
  const [lines, setLines] = useState<Line[]>(() =>
    events.length
      ? events
          .slice(0, L.lines)
          .reverse()
          .map((event, i) => ({ key: i, event }))
      : [{ key: 0, event: null }],
  ) // oldest first; the last is the bottom line
  const [typed, setTyped] = useState<number | null>(null) // characters of the bottom line; null = all
  const [cursor, setCursor] = useState(!events.length)
  // Newness by time: derived events have no id. The newest time shown so far.
  const newest = useRef(events[0] ? Date.parse(events[0].at) : 0)
  const cycle = useRef(L.lines - 1)
  const eventsRef = useRef(events)
  const lastChange = useRef(0)
  useLayoutEffect(() => {
    eventsRef.current = events
  })

  // Pushes `e` on the bottom line and types it in (at once under reduced motion). The line that
  // leaves the top stays one slide long so it can fade out.
  const push = useRef<(e: BoardEvent) => void>(() => undefined)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    let drop: ReturnType<typeof setTimeout> | undefined
    push.current = (e: BoardEvent) => {
      clearTimeout(timer)
      lastChange.current = Date.now()
      setLines((prev) => [...prev.filter((l) => l.event).slice(-L.lines), { key: seq.current++, event: e }])
      clearTimeout(drop)
      drop = setTimeout(() => setLines((prev) => prev.slice(-L.lines)), animate ? L.slideMs + 50 : 0)
      if (!animate) {
        setTyped(null)
        setCursor(false)
        return
      }
      const length = lineParts(e).reduce((n, p) => n + p.text.length, 0)
      let n = 0
      setCursor(true)
      setTyped(0)
      const step = () => {
        n += 1
        setTyped(n)
        if (n < length) timer = setTimeout(step, L.typingMs)
        else {
          setTyped(null)
          timer = setTimeout(() => setCursor(false), 400)
        }
      }
      timer = setTimeout(step, L.slideMs / 2)
    }
    return () => {
      clearTimeout(timer)
      clearTimeout(drop)
    }
  }, [animate, L.lines, L.slideMs, L.typingMs])

  // A new event from the poll: push it now, or on return when the tab is hidden.
  useEffect(() => {
    const top = events[0]
    if (!top || Date.parse(top.at) <= newest.current) return
    newest.current = Date.parse(top.at)
    cycle.current = L.lines - 1
    if (!document.hidden) push.current(top)
    else {
      const onShow = () => {
        if (document.hidden) return
        document.removeEventListener("visibilitychange", onShow)
        push.current(eventsRef.current[0])
      }
      document.addEventListener("visibilitychange", onShow)
      return () => document.removeEventListener("visibilitychange", onShow)
    }
  }, [events, L.lines])

  // Quiet for L.cycleMs: bring back the last L.cycleCount events, older each time, one per interval.
  useEffect(() => {
    if (!animate) return
    lastChange.current = Date.now()
    const timer = setInterval(() => {
      const list = eventsRef.current.slice(0, L.cycleCount)
      if (document.hidden || list.length <= L.lines || Date.now() - lastChange.current < L.cycleMs) return
      cycle.current = (cycle.current + 1) % list.length
      push.current(list[cycle.current])
    }, 1000)
    return () => clearInterval(timer)
  }, [animate, L.cycleCount, L.cycleMs, L.lines])

  const bottom = lines.length - 1
  const latest = [...lines].reverse().find((l) => l.event)?.event ?? null
  return (
    <div className="mt-3 w-full" style={{ maxWidth: ACTIVITY.trace.width }}>
      {/* Lines are stacked from the bottom; a line's slot sets its offset and opacity, so a new
          line moves the others up and fades the one leaving the top (CSS transitions). The
          height of all L.lines is reserved from the first render. */}
      <div aria-hidden className="relative overflow-hidden font-mono text-[12.5px]" style={{ height: L.lines * L.lineHeight }}>
        {lines.map((line, i) => {
          const slot = bottom - i // 0 = bottom
          const parts = line.event
            ? lineParts(line.event, Math.min(slot, L.lines - 1))
            : [{ text: `watching ${sources ?? "the"} ${sources === 1 ? "source" : "sources"}…`, color: L.detailColor }]
          return (
            <p
              key={line.key}
              className="absolute inset-x-0 bottom-0 overflow-hidden text-left text-ellipsis whitespace-pre motion-reduce:transition-none"
              style={{
                height: L.lineHeight,
                lineHeight: `${L.lineHeight}px`,
                transform: `translateY(${-slot * L.lineHeight}px)`,
                opacity: slot < L.lines ? (L.lineOpacity[slot] ?? 0.5) : 0,
                transition: animate ? `transform ${L.slideMs}ms ease-out, opacity ${L.slideMs}ms ease-out` : undefined,
              }}
            >
              <Parts parts={parts} typed={slot === 0 && line.event ? typed : null} />
              {slot === 0 && (
                <span
                  className="ml-px inline-block h-[13px] w-[7px] align-[-2px]"
                  style={{
                    background: L.cursorColor,
                    opacity: cursor || !line.event ? 1 : 0,
                    transition: animate ? `opacity ${L.cursorFadeMs}ms` : undefined,
                  }}
                />
              )}
            </p>
          )
        })}
      </div>
      <p className="sr-only">
        {latest
          ? `Latest board event: ${lineParts(latest)
              .map((p) => p.text)
              .join("")
              .replace(/\s+/g, " ")}`
          : `Watching ${sources ?? ""} sources.`}
      </p>
    </div>
  )
}

/** The landing's activity: a 24-hour trace of rows per hour and one line of the board's log.
 * Heights are fixed from the first render, so nothing moves when data arrives. */
export function Activity({ data, sources }: { data: ActivityData | null; sources: number | null }) {
  const reduced = useReducedMotion()
  const animate = !reduced
  const L = ACTIVITY.log
  const events = useMemo(() => (data?.events ?? []).filter((e) => L.kinds.includes(e.kind)), [data?.events, L.kinds])
  return (
    <section aria-label="Activity" className="mt-[clamp(28px,4.4vh,56px)] flex w-full flex-col items-center">
      {ACTIVITY.trace.on && <Trace hours={data?.hours ?? []} peak7d={data?.peak_7d ?? 0} animate={animate} />}
      {ACTIVITY.log.on && <Log events={events} sources={sources} animate={animate} />}
    </section>
  )
}
