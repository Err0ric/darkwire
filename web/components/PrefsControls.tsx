"use client"

import { usePrefs } from "@/lib/prefs"

/** "remember on this browser" (off by default), or "remembered · reset" once on. */
export function PrefsControls() {
  const { remember, setRemember, reset } = usePrefs()
  return remember ? (
    <span className="whitespace-nowrap">
      remembered ·{" "}
      <button type="button" onClick={reset} className="text-fg-2 outline-none hover:text-fg focus-visible:text-fg">
        reset
      </button>
    </span>
  ) : (
    <button
      type="button"
      onClick={() => setRemember(true)}
      title="Keep your stack and theme in this browser only. Nothing else is stored."
      className="whitespace-nowrap outline-none hover:text-fg-2 focus-visible:text-fg-2"
    >
      remember on this browser
    </button>
  )
}
