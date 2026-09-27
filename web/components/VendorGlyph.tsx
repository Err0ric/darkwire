import type { VendorRef } from "@/lib/api"
import { vendorLogo, vendorMark } from "@/lib/vendors"

/** The 20px vendor mark: monochrome logo tinted by currentColor, else two-letter initials. */
export function VendorGlyph({ vendor }: { vendor: VendorRef }) {
  const logo = vendorLogo(vendor)
  return logo ? (
    // Monochrome SVG tinted through a CSS mask so it follows currentColor.
    <span aria-hidden className="size-5 bg-current" style={{ mask: `url(${logo}) center / contain no-repeat` }} />
  ) : (
    <span aria-hidden className="font-mono text-[11px] leading-none">
      {vendorMark(vendor)}
    </span>
  )
}
