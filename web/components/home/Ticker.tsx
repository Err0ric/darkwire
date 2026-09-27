"use client"

import { useEffect, useRef, useState } from "react"

import type { FeedItem } from "@/lib/api"
import { age, useNow } from "@/lib/time"

// The landing ticker: one line with the latest headline, advancing every 8s through the last
// 10. The swap is the one text animation on the site (CLAUDE.md Motion):
//   1. encode out (~300ms): the old headline's characters flip to random 0/1, right to left, red;
//   2. decode in (~700ms): the new headline starts as red 0/1 glyphs and each character resolves
//      left to right with a small random stagger; unresolved glyphs re-randomize every 50ms;
//   3. the source · age meta fades in over 200ms.
// The line is locked to the new headline's final width during the swap, so nothing jitters.
// Reduced motion: a 200ms crossfade. Hidden tab: instant. Plain requestAnimationFrame, no
// libraries, no inline scripts. The link points to the new article as soon as a swap starts.

const TICKER_MS = 8_000
const ENCODE_MS = 300
const DECODE_MS = 700
const STAGGER_MS = 110
const SCRAMBLE_MS = 50
const FADE_MS = 200
const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const

type Segment = { text: string; glyph: boolean }

const bit = () => (Math.random() < 0.5 ? "0" : "1")
const scramble = (s: string) => Array.from(s, (c) => (c === " " ? " " : bit()))

/** Paint runs of resolved text and red binary glyphs into `el`. */
function paint(el: HTMLElement, segments: Segment[]) {
  const nodes = segments
    .filter((s) => s.text)
    .map((s) => {
      const span = document.createElement("span")
      if (s.glyph) span.className = "font-mono text-critical"
      span.textContent = s.text
      return span
    })
  el.replaceChildren(...nodes)
}

/** Group per-character states into segments. */
function runs(chars: string[], glyph: boolean[]): Segment[] {
  const out: Segment[] = []
  chars.forEach((c, i) => {
    const last = out.at(-1)
    if (last && last.glyph === glyph[i]) last.text += c
    else out.push({ text: c, glyph: glyph[i] })
  })
  return out
}

export function Ticker({ items }: { items: FeedItem[] }) {
  const now = useNow()
  const list = items.slice(0, 10)
  const [index, setIndex] = useState(0)
  const current = list.length ? list[index % list.length] : null

  const line = useRef<HTMLAnchorElement>(null)
  const text = useRef<HTMLSpanElement>(null)
  const measure = useRef<HTMLSpanElement>(null)
  const meta = useRef<HTMLSpanElement>(null)
  const shown = useRef<string | null>(null)
  const frame = useRef(0)

  useEffect(() => {
    if (list.length < 2) return
    const timer = setInterval(() => setIndex((i) => i + 1), TICKER_MS)
    return () => clearInterval(timer)
  }, [list.length])

  // Each new headline: animate from what is on screen to it.
  useEffect(() => {
    const el = text.current
    const a = line.current
    const m = meta.current
    const probe = measure.current
    if (!current || !el || !a || !m || !probe) return
    const from = shown.current
    const to = current.headline
    shown.current = to
    cancelAnimationFrame(frame.current)

    const finish = () => {
      paint(el, [{ text: to, glyph: false }])
      a.style.width = ""
      a.style.textOverflow = ""
      a.style.opacity = ""
      m.style.opacity = "1"
    }
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    if (from === null || from === to || document.hidden) {
      finish()
      return
    }
    if (reduced) {
      // 200ms crossfade (the ticker-fade class keeps this transition under reduced motion).
      a.style.opacity = "0"
      m.style.opacity = "0"
      const t = window.setTimeout(() => {
        paint(el, [{ text: to, glyph: false }])
        a.style.opacity = "1"
        m.style.opacity = "1"
      }, FADE_MS)
      return () => window.clearTimeout(t)
    }

    // Lock the line: first to the old width while it encodes, then to the new headline's width.
    probe.textContent = to
    const toWidth = Math.ceil(probe.getBoundingClientRect().width)
    a.style.width = `${Math.ceil(a.getBoundingClientRect().width)}px`
    a.style.textOverflow = "clip" // glyphs are mono and run wider; clip them, no ellipsis
    m.style.opacity = "0"

    const old = Array.from(from)
    const next = Array.from(to)
    const resolveAt = next.map((_, i) => (i / Math.max(1, next.length)) * (DECODE_MS - STAGGER_MS) + Math.random() * STAGGER_MS)
    let glyphs = scramble(to)
    let oldGlyphs = scramble(from)
    let lastScramble = 0
    let start = 0
    let widthSet = false

    const step = (t: number) => {
      if (!start) start = t
      const elapsed = t - start
      if (t - lastScramble >= SCRAMBLE_MS) {
        glyphs = scramble(to)
        oldGlyphs = scramble(from)
        lastScramble = t
      }
      if (elapsed < ENCODE_MS) {
        // Right to left: the last `flipped` characters are glyphs.
        const flipped = Math.ceil((elapsed / ENCODE_MS) * old.length)
        const keep = old.length - flipped
        paint(el, runs(old.map((c, i) => (i < keep ? c : oldGlyphs[i])), old.map((c, i) => i >= keep && c !== " ")))
      } else {
        if (!widthSet) {
          a.style.width = `${toWidth}px`
          widthSet = true
        }
        const d = elapsed - ENCODE_MS
        const resolved = resolveAt.map((at) => d >= at)
        paint(el, runs(next.map((c, i) => (resolved[i] ? c : glyphs[i])), next.map((c, i) => !resolved[i] && c !== " ")))
        if (resolved.every(Boolean)) {
          finish()
          return
        }
      }
      frame.current = requestAnimationFrame(step)
    }
    frame.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame.current)
  }, [current])

  if (!current) return null
  return (
    <div className="relative mt-[clamp(20px,3vh,36px)] flex h-5 w-full justify-center">
      <p className="flex max-w-full min-w-0 items-baseline gap-2.5 text-[13px] leading-5">
        <span aria-hidden className="text-critical">
          ›
        </span>
        <a
          ref={line}
          href={current.primary_url}
          {...EXTERNAL}
          aria-label={current.headline}
          className="ticker-fade block min-w-0 truncate text-left text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
        >
          <span ref={text} aria-hidden className="whitespace-pre" />
        </a>
        <span
          ref={meta}
          className="ticker-fade hidden shrink-0 font-mono text-[11px] text-dim transition-opacity duration-200 sm:inline"
        >
          {current.sources[0]?.name}
          {now !== null && <> · {age(current.last_event_at, now)}</>}
        </span>
      </p>
      {/* Width probe for the final headline (same font as the link), and the accessible headline. */}
      <span ref={measure} aria-hidden className="pointer-events-none invisible absolute text-[13px] whitespace-pre" />
      <span className="sr-only" aria-live="polite">
        {current.headline}
      </span>
    </div>
  )
}
