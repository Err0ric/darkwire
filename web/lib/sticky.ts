"use client"

import { useEffect, type RefObject } from "react"

/** Sticky rails. A rail shorter than the window pins `gap` below the top (below a sticky bar
 * whose height is the CSS variable `offsetVar`, when given). A taller one gets a negative top,
 * so it scrolls with the page until its bottom is `gap` above the window's bottom, then holds
 * there. Recomputed when the rail or the window resizes. */
export function useStickyTop(ref: RefObject<HTMLElement | null>, gap = 24, offsetVar?: string) {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => {
      const offset = offsetVar ? parseFloat(getComputedStyle(document.documentElement).getPropertyValue(offsetVar)) || 0 : 0
      el.style.top = `${Math.min(offset + gap, window.innerHeight - el.offsetHeight - gap)}px`
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    window.addEventListener("resize", update)
    return () => {
      observer.disconnect()
      window.removeEventListener("resize", update)
    }
  }, [ref, gap, offsetVar])
}
