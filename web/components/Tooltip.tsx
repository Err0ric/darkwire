"use client"

import { useId, useState, type ReactElement, type ReactNode } from "react"
import { cn } from "cn"

/** A small label that appears at once on hover and on keyboard focus (never the native title
 * attribute, which is slow and cannot be styled). The trigger gets aria-describedby. */
export function Tooltip({
  label,
  children,
  side = "top",
  className,
}: {
  label: ReactNode
  children: (props: { "aria-describedby": string; onMouseEnter: () => void; onMouseLeave: () => void; onFocus: () => void; onBlur: () => void }) => ReactElement
  side?: "top" | "bottom"
  className?: string
}) {
  const id = useId()
  const [open, setOpen] = useState(false)
  return (
    <span className={cn("relative inline-flex", className)}>
      {children({
        "aria-describedby": id,
        onMouseEnter: () => setOpen(true),
        onMouseLeave: () => setOpen(false),
        onFocus: () => setOpen(true),
        onBlur: () => setOpen(false),
      })}
      <span
        id={id}
        role="tooltip"
        className={cn(
          "pointer-events-none absolute right-0 z-20 rounded-control border border-rule bg-surface px-2 py-1 font-mono text-[11px] leading-4 whitespace-nowrap text-fg-2",
          side === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5",
          open ? "block" : "hidden",
        )}
      >
        {label}
      </span>
    </span>
  )
}
