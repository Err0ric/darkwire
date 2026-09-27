"use client"

import { cn } from "cn"

import { hms, useClock, zoneAndUtc } from "@/lib/clock"

/** The wire's clock. Wide: HH:MM:SS (seconds dim) over "PDT · 19:20 UTC", right-aligned in
 * the header row. Narrow: one line under the counts, "12:20:07 PDT · 19:20 UTC". Heights are
 * reserved so nothing moves when it fills in after mount. */
export function WireClock({ variant }: { variant: "wide" | "narrow" }) {
  const now = useClock()
  const [hm, s] = now ? hms(now) : ["", ""]
  if (variant === "narrow") {
    return (
      <p className="mt-1 h-5 font-mono text-[13px] leading-5 text-muted min-[1200px]:hidden">
        {now && (
          <>
            <span className="text-fg-2">
              {hm}
              {s}
            </span>{" "}
            {zoneAndUtc(now)}
          </>
        )}
      </p>
    )
  }
  return (
    <div className="hidden shrink-0 text-right min-[1200px]:block">
      <p
        className={cn("h-[1.25em] font-mono leading-[1.25em] text-fg tabular-nums")}
        style={{ fontSize: "clamp(24px, 1.6vw, 32px)" }}
      >
        {now && (
          <time dateTime={now.toISOString()}>
            {hm}
            <span className="text-dim">{s}</span>
          </time>
        )}
      </p>
      <p className="mt-1 h-4 font-mono text-xs leading-4 text-dim">{now && zoneAndUtc(now)}</p>
    </div>
  )
}
