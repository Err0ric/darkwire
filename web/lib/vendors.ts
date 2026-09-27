import type { VendorRef } from "@/lib/api"

// Slugs with a monochrome mark in /public/vendors/{slug}.svg, from Simple Icons (CC0; the marks
// stay their owners' trademarks). Rendered as a CSS mask in currentColor. Add a slug here when its
// SVG lands; everything else falls back to initials, so no request ever 404s.
export const VENDOR_LOGOS = new Set<string>([
  "amd",
  "apache",
  "apple",
  "arm",
  "atlassian",
  "broadcom",
  "cisco",
  "citrix",
  "cloudflare",
  "docker",
  "f5",
  "fortinet",
  "github",
  "gitlab",
  "google",
  "intel",
  "jenkins",
  "jetbrains",
  "juniper",
  "kubernetes",
  "linux",
  "mozilla",
  "npm",
  "nvidia",
  "okta",
  "openssl",
  "palo-alto-networks",
  "progress",
  "pypi",
  "qnap",
  "qualcomm",
  "red-hat",
  "samsung",
  "sap",
  "sonicwall",
  "synology",
  "tp-link",
  "trend-micro",
  "ubiquiti",
  "veeam",
  "vmware",
  "wordpress",
])

// Two-letter marks where the mechanical rule reads wrong (from design-refs).
const MARKS: Record<string, string> = {
  microsoft: "MS",
  fortinet: "FT",
  cisco: "CS",
  "palo-alto-networks": "PA",
}

export function vendorMark(vendor: VendorRef): string {
  if (MARKS[vendor.slug]) return MARKS[vendor.slug]
  const words = vendor.name.split(/[\s-]+/).filter(Boolean)
  if (words.length > 1) return (words[0][0] + words[1][0]).toUpperCase()
  const capitals = vendor.name.match(/[A-Z0-9]/g) ?? []
  if (capitals.length >= 2 && capitals.length < vendor.name.length) return capitals.slice(0, 2).join("")
  return vendor.name.slice(0, 2).toUpperCase()
}

export function vendorLogo(vendor: VendorRef): string | null {
  return VENDOR_LOGOS.has(vendor.slug) ? (vendor.logo_path ?? `/vendors/${vendor.slug}.svg`) : null
}
