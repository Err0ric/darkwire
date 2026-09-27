// Plain module so the server pages can parse ?stack= too ("use client" exports can't cross).

const SLUG = /^[a-z0-9-]{1,64}$/
const MAX_STACK = 50

/** "cisco, Fortinet,cisco" -> ["cisco", "fortinet"]; anything that isn't a slug is dropped. */
export function parseStack(raw: string | null | undefined): string[] {
  if (!raw) return []
  return [...new Set(raw.split(",").map((s) => s.trim().toLowerCase()).filter((s) => SLUG.test(s)))].slice(0, MAX_STACK)
}
