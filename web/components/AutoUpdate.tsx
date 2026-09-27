"use client"

import { useEffect } from "react"

// Auto-update on deploy: every 5 minutes ask /api/version which build is live. When it differs
// from this page's build, reload, but only at a safe moment: at once if the tab is hidden,
// else when it next goes hidden, or after 2 minutes with no pointer or key activity. Never
// while a row is expanded or a text field has focus. location.reload() keeps the full URL
// (?stack=, filters, theme).

const BUILD = process.env.NEXT_PUBLIC_BUILD_ID ?? "dev"
const CHECK_MS = 5 * 60_000
const IDLE_MS = 2 * 60_000
const IDLE_CHECK_MS = 15_000

function busy(): boolean {
  const active = document.activeElement
  const typing = active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement
  return typing || document.querySelector('article [aria-expanded="true"]') !== null
}

export function AutoUpdate() {
  useEffect(() => {
    let pending: string | null = null
    let lastActivity = Date.now()

    const reload = (reason: "hidden" | "idle") => {
      if (!pending || busy()) return
      if (reason === "hidden" && !document.hidden) return
      console.log(`darkwire: new build ${pending}, reloading`)
      window.location.reload()
    }

    const check = async () => {
      try {
        const res = await fetch("/api/version", { cache: "no-store" })
        const { build } = (await res.json()) as { build?: string }
        if (build && build !== BUILD) {
          pending = build
          reload("hidden")
        }
      } catch {
        // Offline or mid-deploy: try again next time.
      }
    }

    const onActivity = () => {
      lastActivity = Date.now()
    }
    const onVisibility = () => reload("hidden")
    const events = ["pointermove", "pointerdown", "keydown", "wheel", "touchstart"] as const
    events.forEach((e) => window.addEventListener(e, onActivity, { passive: true }))
    document.addEventListener("visibilitychange", onVisibility)

    const checker = setInterval(check, CHECK_MS)
    const idler = setInterval(() => {
      if (pending && Date.now() - lastActivity >= IDLE_MS) reload(document.hidden ? "hidden" : "idle")
    }, IDLE_CHECK_MS)
    return () => {
      events.forEach((e) => window.removeEventListener(e, onActivity))
      document.removeEventListener("visibilitychange", onVisibility)
      clearInterval(checker)
      clearInterval(idler)
    }
  }, [])
  return null
}
