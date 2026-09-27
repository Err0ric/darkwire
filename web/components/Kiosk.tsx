"use client"

import { useEffect } from "react"

// Kiosk mode for wall displays: key f (or ?kiosk=1) hides the nav and rail and zooms type
// about 15%. The styles live in globals.css under html[data-kiosk].
export function Kiosk() {
  useEffect(() => {
    const root = document.documentElement
    const set = (on: boolean) => {
      if (on) root.dataset.kiosk = ""
      else delete root.dataset.kiosk
      window.dispatchEvent(new Event("resize")) // row-fit counts depend on it
    }
    if (new URLSearchParams(window.location.search).get("kiosk") === "1") set(true)

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "f" || e.metaKey || e.ctrlKey || e.altKey) return
      const target = e.target as HTMLElement | null
      if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return
      set(!("kiosk" in root.dataset))
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])
  return null
}
