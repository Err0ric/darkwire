"use client"

import { hms, useClock, utcHHMM, zoneName } from "@/lib/clock"

/** The wire's heading: the live clock HH:MM:SS (seconds dim) in Geist Mono at the old title's
 * size, and on its baseline "Sunday, Sep 27 · PDT · 21:17 UTC" (date sans, times mono). Under
 * 1200px the clock drops to 28px and the date line wraps under it. UTC viewers see "UTC" once.
 * Heights are reserved so nothing moves when it fills in after mount. */
export function WireClock() {
  const now = useClock()
  const [hm, s] = now ? hms(now) : ["", ""]
  const zone = now ? zoneName(now) : ""
  const dot = <span className="text-dim"> · </span>
  return (
    <div className="flex flex-wrap items-baseline gap-x-4">
      <h1 className="sr-only">The wire</h1>
      <p className="h-9 font-mono text-[28px] leading-9 font-bold tracking-[-0.02em] text-fg tabular-nums min-[1200px]:h-11 min-[1200px]:text-[36px] min-[1200px]:leading-[44px]">
        {now && (
          <time dateTime={now.toISOString()}>
            {hm}
            <span className="text-dim">{s}</span>
          </time>
        )}
      </p>
      <p className="h-5 w-full text-[13px] leading-5 text-muted min-[1200px]:w-auto">
        {now && (
          <>
            {now.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" })}
            {dot}
            {zone !== "UTC" && (
              <>
                <span className="font-mono text-dim">{zone}</span>
                {dot}
              </>
            )}
            <span className="font-mono text-dim">{utcHHMM(now)} UTC</span>
          </>
        )}
      </p>
    </div>
  )
}
