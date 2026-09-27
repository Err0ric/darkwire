"use client"

import { useCallback, useEffect, useRef } from "react"

// Unseen-item indicators (CLAUDE.md): while the tab is hidden, rows found by a poll are
// counted in the title, "(3) darkwire" or "(3!) darkwire" when any is Critical or KEV,
// and the favicon gets a static red dot. Both clear when the tab is visible again.
// Nothing is stored between visits.

// Canvas cannot use CSS variables directly, so the theme's current values are read at draw time.
const token = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
// On the icon's 32-unit grid: a dot in the bottom-right corner with a 2-unit ring (the stem
// ends at x=17, the square sits top center), so the unseen state reads at 16px too.
const DOT = { cx: 25, cy: 25, r: 5, ring: 2 }

function iconLinks(): HTMLLinkElement[] {
  return [...document.querySelectorAll<HTMLLinkElement>('link[rel~="icon"]')]
}

async function dottedIcon(src: string): Promise<string | null> {
  const img = new Image()
  img.src = src
  try {
    await img.decode()
  } catch {
    return null
  }
  const size = 64
  const canvas = document.createElement("canvas")
  canvas.width = canvas.height = size
  const ctx = canvas.getContext("2d")
  if (!ctx) return null
  ctx.drawImage(img, 0, 0, size, size)
  const u = size / 32
  ctx.fillStyle = token("--bg", "#0a0a0a")
  ctx.beginPath()
  ctx.arc(DOT.cx * u, DOT.cy * u, (DOT.r + DOT.ring) * u, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = token("--critical", "#dc2626")
  ctx.beginPath()
  ctx.arc(DOT.cx * u, DOT.cy * u, DOT.r * u, 0, Math.PI * 2)
  ctx.fill()
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
    const dotted = await dottedIcon(baseIcons.current.values().next().value ?? links[0].href)
    if (dotted && document.hidden) links.forEach((l) => (l.href = dotted))
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
