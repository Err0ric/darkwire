import type { ReactNode } from "react"
import { cn } from "cn"

// One header pattern for every page (CLAUDE.md "Page header"): the wire's clock slot holds the
// page title here, same size and weight (36px bold, 28px under 1200px), and under it the
// counts line (15px, --muted words, --fg numbers). The wire itself uses the same classes.

export const PAGE_HEADER = "pt-6 md:pt-[33px]"
export const PAGE_TITLE =
  "h-9 text-[28px] leading-9 font-bold tracking-[-0.02em] text-fg min-[1200px]:h-11 min-[1200px]:text-[36px] min-[1200px]:leading-[44px]"
export const PAGE_COUNTS = "mt-[3px] min-h-5 text-[15px] leading-5 text-muted"

export function PageHeader({ title, children, className }: { title: ReactNode; children?: ReactNode; className?: string }) {
  return (
    <header className={cn(PAGE_HEADER, className)}>
      <h1 className={PAGE_TITLE}>{title}</h1>
      {children !== undefined && <p className={PAGE_COUNTS}>{children}</p>}
    </header>
  )
}
