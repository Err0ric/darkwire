"use client"

import { useCallback, useEffect, useId, useRef, useState, type FocusEvent, type KeyboardEvent, type MouseEvent, type ReactNode } from "react"
import { createPortal } from "react-dom"

/** Behind NEXT_PUBLIC_HOVER_PREVIEW=1 (build time). Off by default. */
export const HOVER_PREVIEW = process.env.NEXT_PUBLIC_HOVER_PREVIEW === "1"

const DELAY = 550 // ms of hover (or focus on the headline link) before the card shows
const WIDTH = 360
const GAP = 12
const EDGE = 16

type Place = { left: number; top: number; width: number }

/** Where the card goes: right of the end of the headline text; if it would leave the viewport,
 * under the headline (or above it near the bottom edge). Fixed position, so nothing shifts. */
function place(el: HTMLElement): Place {
  const rects = [...el.getClientRects()]
  const first = rects[0] ?? el.getBoundingClientRect()
  const last = rects[rects.length - 1] ?? first
  const width = Math.min(WIDTH, window.innerWidth - 2 * EDGE)
  if (last.right + GAP + width <= window.innerWidth - EDGE) return { left: last.right + GAP, top: last.top - 4, width }
  const left = Math.max(EDGE, Math.min(first.left, window.innerWidth - EDGE - width))
  const below = last.bottom + 8
  // Three 20px lines and 24px padding: about 90px tall.
  return below + 96 <= window.innerHeight ? { left, top: below, width } : { left, top: Math.max(EDGE, first.top - 8 - 96), width }
}

/** Handlers for the headline link and the card to render beside it. Shows the row summary after
 * DELAY on hover (fine pointers only, never on touch) or when the link itself has keyboard focus;
 * hides on leave, blur, Esc, scroll or resize, and never shows while `enabled` is false (the row
 * is expanded) or the row has no summary. */
export function useHoverPreview(summary: string | null, enabled: boolean) {
  const id = useId()
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [at, setAt] = useState<Place | null>(null)
  const [shown, setShown] = useState(false)
  const active = HOVER_PREVIEW && enabled && !!summary
  // Read by the delayed timer: a row expanded (or a summary gone) during the delay never shows.
  const live = useRef(active)
  useEffect(() => {
    live.current = active
  })

  const hide = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
    setShown(false)
    setAt(null)
  }, [])

  const show = useCallback(
    (el: HTMLElement) => {
      if (!active) return
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => {
        if (!live.current) return
        setAt(place(el))
        requestAnimationFrame(() => setShown(true))
      }, DELAY)
    },
    [active],
  )

  useEffect(() => {
    if (!at) return
    const off = () => hide()
    window.addEventListener("scroll", off, { passive: true })
    window.addEventListener("resize", off)
    return () => {
      window.removeEventListener("scroll", off)
      window.removeEventListener("resize", off)
    }
  }, [at, hide])

  useEffect(() => hide, [hide])

  const handlers = active
    ? {
        "aria-describedby": at ? id : undefined,
        onMouseEnter: (e: MouseEvent<HTMLElement>) => {
          if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) show(e.currentTarget)
        },
        onMouseLeave: hide,
        // Only focus on the link itself: j / k move focus between rows, not onto headlines.
        onFocus: (e: FocusEvent<HTMLElement>) => {
          if (e.currentTarget.matches(":focus-visible")) show(e.currentTarget)
        },
        onBlur: hide,
        onKeyDown: (e: KeyboardEvent) => {
          if (e.key === "Escape") hide()
        },
      }
    : {}

  const card: ReactNode =
    active && at
      ? createPortal(
          <div
            id={id}
            role="tooltip"
            style={{ left: at.left, top: at.top, width: at.width }}
            className={`pointer-events-none fixed z-50 border border-rule bg-bg px-3 py-3 text-[13px] leading-5 text-fg-2 transition-opacity duration-[120ms] motion-reduce:transition-none ${shown ? "opacity-100" : "opacity-0"}`}
          >
            <p className="line-clamp-3">{summary}</p>
          </div>,
          document.body,
        )
      : null

  return { handlers, card }
}
