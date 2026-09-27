"use client"

import { cn } from "cn"

import { PAGE_TITLE } from "@/components/PageHeader"
import { hms, useClock, utcHHMM, zoneName } from "@/lib/clock"

/** The wire's heading: the live clock HH:MM:SS (seconds dim) in Geist Mono at the old title's
 * size, and on its baseline "Sunday, Sep 27 · PDT · 21:17 UTC" (date sans, times mono). Under
 * 1200px the clock drops to 28px and the date line wraps under it. UTC viewers see "UTC" once.
 * Heights are reserved so nothing moves when it fills in after mount. */
export function WireClock() {
  const now = useClock()
  const [hm, s] = now ? hms(now) : ["", ""]
  const zone = now ? zoneName(now) : ""
  const dot = <span className="text-dim-text"> · </span>
  return (
    <div className="flex flex-wrap items-baseline gap-x-4">
      <h1 className="sr-only">The wire</h1>
      <p className={cn(PAGE_TITLE, "font-mono tabular-nums")}>
        {now && (
          <time dateTime={now.toISOString()}>
            {hm}
            <span className="text-dim-text">{s}</span>
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
                <span className="font-mono text-dim-text">{zone}</span>
                {dot}
              </>
            )}
            <span className="font-mono text-dim-text">{utcHHMM(now)} UTC</span>
          </>
        )}
      </p>
    </div>
  )
}
