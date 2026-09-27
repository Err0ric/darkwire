"use client"

import Link from "next/link"

import { byImpact, isImpacted, StateDot } from "@/components/ServiceBits"
import type { ServicesOut } from "@/lib/api"
import { usePrefs } from "@/lib/prefs"
import { age, useNow } from "@/lib/time"

const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const

/** First block of the rail. One quiet line while everything is fine; when something is
 * degraded or down it opens: affected services first (red major, amber degraded) with the
 * incident, its age and a link to the vendor's page, then "N others operational". */
export function Services({ data }: { data: ServicesOut | null }) {
  const now = useNow()
  const { query } = usePrefs()
  if (!data || !data.services.length) return null

  const list = [...data.services].sort(byImpact)
  const impacted = list.filter(isImpacted)
  const ok = list.filter((s) => s.state === "operational").length
  const silent = list.length - impacted.length - ok
  const outages = (
    <Link href={`/outages${query()}`} className="outline-none hover:text-fg-2 focus-visible:text-fg-2">
      all outages
    </Link>
  )

  if (!impacted.length) {
    return (
      <section aria-label="Services" className="flex items-baseline justify-between gap-3">
        <p className="leading-[19px] text-muted">
          <span className="font-medium text-fg">Services</span>
          {" · "}
          {silent ? `${ok} operational · ${silent} not reporting` : `all ${ok} operational`}
        </p>
        <span className="text-[11px] min-[2200px]:text-[12px] text-dim-text">{outages}</span>
      </section>
    )
  }

  return (
    <section aria-label="Services">
      <div className="flex items-baseline justify-between">
        <h2 className="text-[13px] font-medium text-fg">Services</h2>
        <span className="text-[11px] min-[2200px]:text-[12px] text-dim-text">{outages}</span>
      </div>
      <ul className="mt-3">
        {impacted.map((s) => (
          <li key={s.slug} className="mb-3">
            <p className="flex items-center gap-2 leading-[18px]">
              <StateDot state={s.state} />
              <span className="text-fg">{s.name}</span>
              <span className={s.state === "major" ? "text-critical-text" : "text-degraded"}>
                {s.state === "major" ? "major outage" : "degraded"}
              </span>
              {s.incident?.started_at && now !== null && (
                <span className="ml-auto font-mono text-[11px] min-[2200px]:text-[12px] text-dim-text">{age(s.incident.started_at, now)}</span>
              )}
            </p>
            <a
              href={s.incident?.url ?? s.page}
              {...EXTERNAL}
              className="mt-0.5 ml-3.5 line-clamp-2 leading-[18px] text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
            >
              {s.incident?.title ?? "Status page"} <span aria-hidden className="text-[10px] text-critical-text">↗</span>
            </a>
          </li>
        ))}
      </ul>
      <p className="text-muted">
        {ok ? `${ok} other${ok === 1 ? "" : "s"} operational` : ""}
        {ok && silent ? " · " : ""}
        {silent ? `${silent} not reporting` : ""}
      </p>
    </section>
  )
}
