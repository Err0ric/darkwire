"use client"

import { cn } from "cn"

import { usePrefs } from "@/lib/prefs"
import { THEMES } from "@/lib/stack"

/** Four words in the footer; the current one is brighter. Updates ?theme= in place. */
export function ThemePicker() {
  const { theme, setTheme } = usePrefs()
  return (
    <span role="group" aria-label="Theme" className="flex flex-wrap items-baseline gap-x-3 whitespace-nowrap">
      {THEMES.map((t) => (
        <button
          key={t}
          type="button"
          onClick={() => setTheme(t)}
          aria-pressed={theme === t}
          className={cn("outline-none focus-visible:text-fg", theme === t ? "text-fg-2" : "hover:text-fg-2")}
        >
          {t}
        </button>
      ))}
    </span>
  )
}
