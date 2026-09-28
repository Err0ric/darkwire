"use client"

import { hms, useClock, utcHHMM, zoneName } from "@/lib/clock"

/** The wire's clock, the right end of its one-line header: HH:MM:SS in Geist Mono 24px (the
 * seconds dimmer), then "PDT · 23:18 UTC" in 12px mono --dim-text on the same baseline (just
 * "UTC" for UTC viewers). Its width is reserved so nothing moves when it fills in after mount. */
export function WireClock() {
  const now = useClock()
  const [hm, s] = now ? hms(now) : ["", ""]
  const zone = now ? zoneName(now) : ""
  return (
    <p className="flex h-7 shrink-0 items-baseline gap-2.5 font-mono whitespace-nowrap tabular-nums">
      <time dateTime={now?.toISOString()} className="inline-block min-w-[8ch] text-[24px] leading-7 text-fg">
        {now && (
          <>
            {hm}
            <span className="text-dim-text">{s}</span>
          </>
        )}
      </time>
      <span className="min-w-[15ch] text-xs text-dim-text">{now && (zone === "UTC" ? "UTC" : `${zone} · ${utcHHMM(now)} UTC`)}</span>
    </p>
  )
}

/** The condensed bar's clock: HH:MM:SS in 15px mono, seconds dimmer, no zone line. */
export function CompactClock() {
  const now = useClock()
  const [hm, s] = now ? hms(now) : ["", ""]
  return (
    <time dateTime={now?.toISOString()} className="inline-block min-w-[8ch] shrink-0 font-mono text-[15px] leading-5 text-fg tabular-nums">
      {now && (
        <>
          {hm}
          <span className="text-dim-text">{s}</span>
        </>
      )}
    </time>
  )
}
