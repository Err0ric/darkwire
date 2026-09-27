import type { ReactNode } from "react"

import { PrefsControls } from "@/components/PrefsControls"

/** Bottom line of a page: optional sources text left; preferences and the domain right. */
export function SiteFooter({
  children,
  className = "",
  ...rest
}: { children?: ReactNode; className?: string; "data-chrome"?: boolean }) {
  return (
    <footer {...rest} className={`flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 text-[13px] text-muted ${className}`}>
      <span>{children}</span>
      <span className="flex flex-wrap items-baseline gap-x-6">
        <PrefsControls />
        <span className="shrink-0">darkwire.tech</span>
      </span>
    </footer>
  )
}
