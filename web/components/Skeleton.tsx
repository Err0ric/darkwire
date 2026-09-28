import type React from "react"
import { cn } from "cn"

import { PAGE_COUNTS, PAGE_HEADER, PAGE_TITLE } from "@/components/PageHeader"

// Loading placeholders (the route loading.tsx files) shaped like the real page, so nothing
// moves when data arrives: the same header, row heights and column widths. Static blocks in
// --hairline; nothing pulses (CLAUDE.md Motion).

export function Bar({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <span aria-hidden className={cn("block rounded-badge bg-hairline", className)} style={style} />
}

export function SkeletonHeader({ title = "w-[180px]", counts = "w-[420px]" }: { title?: string; counts?: string }) {
  return (
    <div className={PAGE_HEADER}>
      <div className={cn(PAGE_TITLE, "flex items-center")}>
        <Bar className={cn("h-7 max-w-full", title)} />
      </div>
      <div className={cn(PAGE_COUNTS, "flex items-center")}>
        <Bar className={cn("h-3 max-w-full", counts)} />
      </div>
    </div>
  )
}

/** Feed rows at the real row height: 64px, vendor mark, headline over meta, age. */
export function SkeletonFeedRows({ count = 12, className }: { count?: number; className?: string }) {
  const widths = ["w-[62%]", "w-[48%]", "w-[70%]", "w-[55%]", "w-[40%]", "w-[66%]"]
  return (
    <div className={className} aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex h-[68px] items-center gap-5 border-b border-rule">
          <Bar className="size-5 shrink-0" />
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <Bar className={cn("h-3.5", widths[i % widths.length])} />
            <Bar className="h-2.5 w-[24%]" />
          </div>
          <Bar className="h-2.5 w-8 shrink-0" />
        </div>
      ))}
    </div>
  )
}

/** Short rail placeholder: a label and a few lines. */
export function SkeletonRail({ sections = 3 }: { sections?: number }) {
  return (
    <div className="flex flex-col gap-10" aria-hidden>
      {Array.from({ length: sections }, (_, i) => (
        <div key={i} className="flex flex-col gap-3">
          <Bar className="h-3 w-28" />
          {Array.from({ length: 4 }, (_, j) => (
            <Bar key={j} className={cn("h-2.5", j % 2 ? "w-[70%]" : "w-[85%]")} />
          ))}
        </div>
      ))}
    </div>
  )
}

/** Screen-reader text for a loading page. */
export function Loading({ label }: { label: string }) {
  return (
    <p role="status" className="sr-only">
      Loading {label}
    </p>
  )
}
