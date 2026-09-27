"use client"

import { Select as SelectPrimitive } from "radix-ui"

import { Select, SelectContent, SelectItem } from "@/components/ui/select"
import { usePrefs } from "@/lib/prefs"
import { parseTheme, THEMES } from "@/lib/stack"

/** Nav, top right: a dot in the current theme's text color that opens the list of themes. */
export function ThemePicker() {
  const { theme, setTheme } = usePrefs()
  return (
    <Select value={theme} onValueChange={(v) => setTheme(parseTheme(v))}>
      <SelectPrimitive.Trigger
        aria-label={`Theme: ${theme}`}
        title="Theme"
        className="relative flex size-5 items-center justify-center rounded-control outline-none after:absolute after:-inset-2 after:content-[''] focus-visible:outline-1 focus-visible:outline-rule"
      >
        <span aria-hidden className="size-2 rounded-full bg-fg-2 ring-1 ring-rule ring-offset-2 ring-offset-bg" />
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
