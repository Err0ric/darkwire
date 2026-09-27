"use client"

import { usePrefs } from "@/lib/prefs"

/** The footer's only control, and only once there is something to keep: a stack, or a
 * browser that already remembers. "remember on this browser" (off by default) or
 * "remembered · reset". */
export function PrefsControls() {
  const { remember, setRemember, reset, stack } = usePrefs()
  if (remember) {
    return (
      <span className="whitespace-nowrap">
        remembered ·{" "}
        <button type="button" onClick={reset} className="text-fg-2 outline-none hover:text-fg focus-visible:text-fg">
          reset
        </button>
      </span>
    )
  }
  if (!stack.length) return null
  return (
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
