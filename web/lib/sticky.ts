"use client"

import { useEffect, type RefObject } from "react"

/** Sticky rails. A rail shorter than the window pins `gap` below the top (below a sticky bar
 * whose height is the CSS variable `offsetVar`, when given). A taller one, with `tall: "hold"`,
 * gets a negative top, so it scrolls with the page until its bottom is `gap` above the window's
 * bottom, then holds there; with `tall: "scroll"` it is not pinned at all and scrolls with the
 * page. Recomputed when the rail or the window resizes. */
export function useStickyTop(
  ref: RefObject<HTMLElement | null>,
  gap = 24,
  offsetVar?: string,
  tall: "hold" | "scroll" = "hold",
) {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => {
      const offset = offsetVar ? parseFloat(getComputedStyle(document.documentElement).getPropertyValue(offsetVar)) || 0 : 0
      const fits = offset + gap + el.offsetHeight + gap <= window.innerHeight
      // No top: position sticky without an offset stays in the flow, like a static rail.
      el.style.top = fits ? `${offset + gap}px` : tall === "scroll" ? "" : `${window.innerHeight - el.offsetHeight - gap}px`
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    window.addEventListener("resize", update)
    return () => {
      observer.disconnect()
      window.removeEventListener("resize", update)
    }
  }, [ref, gap, offsetVar, tall])
}
