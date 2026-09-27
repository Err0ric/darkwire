import * as React from "react"
import { cn } from "cn"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-9 w-full min-w-0 rounded-control border border-transparent bg-hairline px-3 text-[13px] text-fg outline-none placeholder:text-muted focus-visible:border-rule disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-accent",
        className
      )}
      {...props}
    />
  )
}

export { Input }
