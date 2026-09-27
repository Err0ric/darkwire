"use client"

import { Contrast } from "lucide-react"
import { Select as SelectPrimitive } from "radix-ui"

import { Select, SelectContent, SelectItem } from "@/components/ui/select"
import { usePrefs } from "@/lib/prefs"
import { parseTheme, THEMES } from "@/lib/stack"

/** Nav, top right: a small "contrast" icon (half-filled circle) that opens the list of themes.
 * An icon, not a dot, so it never reads as a status light. */
export function ThemePicker() {
  const { theme, setTheme } = usePrefs()
  return (
    <Select value={theme} onValueChange={(v) => setTheme(parseTheme(v))}>
      <SelectPrimitive.Trigger
        aria-label="Theme"
        title={`Theme: ${theme}`}
        className="max-md:tap relative flex size-5 items-center justify-center rounded-control text-muted outline-none after:absolute after:-inset-2 after:content-[''] hover:text-fg focus-visible:text-fg"
      >
        <Contrast aria-hidden className="size-3.5" strokeWidth={2} />
      </SelectPrimitive.Trigger>
      <SelectContent>
        {THEMES.map((t) => (
          <SelectItem key={t} value={t}>
            {t}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
