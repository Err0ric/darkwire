// Plain module so server code can use these too ("use client" exports can't cross). No imports,
// so the unit tests (tests/unit) can load it with plain Node.

const MAX_SLUGS = 50

/** Every vendor slug the API tags (api/app/seed.py VENDORS). A stack can only name these.
 * tests/unit checks this list against seed.py. */
export const VENDOR_SLUGS: ReadonlySet<string> = new Set([
  "adobe", "amd", "apache", "apple", "arm", "atlassian", "aws", "broadcom", "check-point", "cisco",
  "citrix", "cloudflare", "connectwise", "crowdstrike", "d-link", "docker", "f5", "fortinet", "github", "gitlab",
  "google", "ibm", "intel", "ivanti", "jenkins", "jetbrains", "juniper", "kaseya", "kubernetes", "linux",
  "microsoft", "mozilla", "npm", "nvidia", "okta", "openssl", "oracle", "palo-alto-networks", "progress", "pypi",
  "qnap", "qualcomm", "red-hat", "samsung", "sap", "solarwinds", "sonicwall", "sophos", "synology", "tp-link",
  "trend-micro", "ubiquiti", "veeam", "vmware", "wordpress", "zyxel",
])

/** Every service slug the API tracks (api/app/services.py SERVICES). tests/unit checks it. */
export const SERVICE_SLUGS: ReadonlySet<string> = new Set([
  "aws", "azure", "gcp", "cloudflare", "digitalocean", "akamai", "okta", "duo", "1password", "ping",
  "m365", "google-workspace", "slack", "zoom", "atlassian", "dropbox", "github", "gitlab", "npm", "docker",
  "pypi", "vercel",
])

/** "cisco, Fortinet,cisco" -> ["cisco", "fortinet"]: known slugs only, deduplicated, capped;
 * anything else (unknown names, markup, control characters) is dropped. */
function parseSlugs(raw: string | null | undefined, known: ReadonlySet<string>): string[] {
  if (!raw) return []
  return [...new Set(raw.split(",").map((s) => s.trim().toLowerCase()).filter((s) => known.has(s)))].slice(0, MAX_SLUGS)
}

/** ?stack= (and a remembered stack): vendor slugs. */
export const parseStack = (raw: string | null | undefined): string[] => parseSlugs(raw, VENDOR_SLUGS)

/** ?services= (and a remembered set): service slugs. */
export const parseServices = (raw: string | null | undefined): string[] => parseSlugs(raw, SERVICE_SLUGS)

export const THEMES = ["darkwire", "amber", "phosphor", "high-contrast"] as const
export type Theme = (typeof THEMES)[number]
export const DEFAULT_THEME: Theme = "darkwire"

export function parseTheme(raw: string | null | undefined): Theme {
  return THEMES.find((t) => t === raw) ?? DEFAULT_THEME
}

/** The non-default themes, for <html data-themes="…"> (React escapes it as an attribute). */
export const THEME_CHOICES = THEMES.slice(1).join(" ")

/** Runs in <head> before first paint: ?theme= wins, else a remembered theme; no flash. A
 * constant: nothing is interpolated into it. The allowed names come from the data-themes
 * attribute on <html>, and ?theme= / storage are only compared against them, never run. */
export const THEME_SCRIPT =
  '(function(){try{var d=document.documentElement,ok=(d.getAttribute("data-themes")||"").split(" "),' +
  't=new URLSearchParams(location.search).get("theme");' +
  'if(t===null){var s=JSON.parse(localStorage.getItem("darkwire.prefs")||"null");t=s&&s.theme}' +
  'if(typeof t==="string"&&t&&ok.indexOf(t)>=0)d.setAttribute("data-theme",t)}catch(e){}})()'
