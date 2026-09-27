// Plain module so server code can use these too ("use client" exports can't cross).

const SLUG = /^[a-z0-9-]{1,64}$/
const MAX_STACK = 50

/** "cisco, Fortinet,cisco" -> ["cisco", "fortinet"]; anything that isn't a slug is dropped. */
export function parseStack(raw: string | null | undefined): string[] {
  if (!raw) return []
  return [...new Set(raw.split(",").map((s) => s.trim().toLowerCase()).filter((s) => SLUG.test(s)))].slice(0, MAX_STACK)
}

export const THEMES = ["darkwire", "amber", "phosphor", "high-contrast"] as const
export type Theme = (typeof THEMES)[number]
export const DEFAULT_THEME: Theme = "darkwire"

export function parseTheme(raw: string | null | undefined): Theme {
  return THEMES.find((t) => t === raw) ?? DEFAULT_THEME
}

/** Runs in <head> before first paint: ?theme= wins, else a remembered theme. No flash. */
export const THEME_SCRIPT = `(function(){try{var t=new URLSearchParams(location.search).get("theme");if(t===null){var s=JSON.parse(localStorage.getItem("darkwire.prefs")||"null");t=s&&s.theme}if(${JSON.stringify(
  THEMES.slice(1),
)}.indexOf(t)>=0)document.documentElement.setAttribute("data-theme",t)}catch(e){}})()`
