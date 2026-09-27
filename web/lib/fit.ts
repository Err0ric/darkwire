"use client"

import { useEffect, useState, type RefObject } from "react"

/**
 * How many rows fit between the top of `list` and the bottom of the viewport, minus
 * whatever `reserve` occupies (a pinned footer). Uses the first row's real height, so it
 * holds for 2-line mobile rows and kiosk zoom. Null until measured on the client.
 */
export function useFitCount(list: RefObject<HTMLElement | null>, reserve?: RefObject<HTMLElement | null>, min = 3) {
  const [count, setCount] = useState<number | null>(null)
  useEffect(() => {
    const measure = () => {
      const el = list.current
      if (!el) return
      const top = el.getBoundingClientRect().top + window.scrollY
      const row = el.querySelector("article")
      const pitch = row ? row.getBoundingClientRect().height : 65
      const bottom = reserve?.current?.getBoundingClientRect().height ?? 0
      setCount(Math.max(min, Math.floor((window.innerHeight - top - bottom) / Math.max(pitch, 1))))
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(document.documentElement)
    window.addEventListener("resize", measure)
    return () => {
      observer.disconnect()
      window.removeEventListener("resize", measure)
    }
  }, [list, reserve, min])
  return count
}
