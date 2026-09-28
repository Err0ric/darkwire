"use client"

import { useCallback, useEffect, useRef } from "react"

import ICON from "@/lib/favicon.json"

// Unseen-item indicators (CLAUDE.md): while the tab is hidden, rows found by a poll are
// counted in the title, "(3) darkwire" or "(3!) darkwire" when any is Critical or KEV,
// and the favicon's trace turns a brighter red (a static copy drawn on a canvas, never
// animated). Both clear when the tab is visible again. Nothing is stored between visits.

function iconLinks(): HTMLLinkElement[] {
  return [...document.querySelectorAll<HTMLLinkElement>('link[rel~="icon"]')]
}

/** The favicon's trace (lib/favicon.json, written by scripts/make-og.py) redrawn in the unseen
 * red, on the same black, 4 pixels per cell so it scales down crisply. */
function unseenIcon(): string | null {
  const size = ICON.grid * 4
  const canvas = document.createElement("canvas")
  canvas.width = canvas.height = size
  const ctx = canvas.getContext("2d")
  if (!ctx) return null
  const u = size / ICON.grid
  ctx.fillStyle = "#000"
  ctx.fillRect(0, 0, size, size)
  ctx.fillStyle = ICON.unseen
  for (const [x, y] of ICON.cells) ctx.fillRect(x * u, y * u, u, u)
  return canvas.toDataURL("image/png")
}

export function useUnseen() {
  const count = useRef(0)
  const important = useRef(false)
  const baseTitle = useRef<string | null>(null)
  const baseIcons = useRef<Map<HTMLLinkElement, string> | null>(null)

  const clear = useCallback(() => {
    count.current = 0
    important.current = false
    if (baseTitle.current !== null) document.title = baseTitle.current
    baseIcons.current?.forEach((href, link) => {
      link.href = href
    })
  }, [])

  const add = useCallback(async (n: number, anyImportant: boolean) => {
    if (n <= 0 || !document.hidden) return
    count.current += n
    important.current ||= anyImportant
    baseTitle.current ??= document.title.replace(/^\(\d+!?\)\s*/, "")
    document.title = `(${count.current}${important.current ? "!" : ""}) ${baseTitle.current}`

    const links = iconLinks()
    if (!links.length) return
    if (!baseIcons.current) baseIcons.current = new Map(links.map((l) => [l, l.href]))
    const icon = unseenIcon()
    if (icon && document.hidden) links.forEach((l) => (l.href = icon))
  }, [])

  useEffect(() => {
    const onVisible = () => {
      if (!document.hidden) clear()
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => {
      document.removeEventListener("visibilitychange", onVisible)
      clear()
    }
  }, [clear])

  return add
}
