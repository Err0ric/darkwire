"use client"

import type { ReactNode } from "react"
import { cn } from "cn"

import type { ElsewhereItem, KevRow, Status, VendorOut } from "@/lib/api"
import { age, useNow } from "@/lib/time"

const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const

function Section({ title, aside, children, className }: { title: string; aside?: string; children: ReactNode; className?: string }) {
  return (
    <section className={className}>
      <div className="flex items-baseline justify-between">
        <h2 className="text-[13px] font-medium text-fg">{title}</h2>
        {aside && <span className="text-[11px] text-dim">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

export function Rail({
  elsewhere,
  active,
  kev,
  status,
  onVendor,
}: {
  elsewhere: ElsewhereItem[]
  active: VendorOut[]
  kev: KevRow[]
  status: Status | null
  onVendor: (slug: string) => void
}) {
  const now = useNow()
  const counts = status?.counts
  const last24: [string, number, string][] = counts
    ? [
        ["Critical", counts.critical_24h, "bg-critical"],
        ["High", counts.high_24h, "bg-accent"],
        ["Medium", counts.medium_24h, "bg-dim"],
        ["Low", counts.low_24h, "bg-outline-medium"],
      ]
    : []
  const peak = Math.max(1, ...last24.map(([, n]) => n))

  return (
    <aside aria-label="Context" className="text-[13px]">
      <Section title="Elsewhere" aside="policy · privacy · culture">
        <ul className="mt-3 space-y-3.5">
          {elsewhere.map((e) => (
            <li key={e.id}>
              <a href={e.url} {...EXTERNAL} className="block leading-[18px] text-fg-2 outline-none hover:text-fg focus-visible:text-fg">
                {e.headline}
              </a>
              <p className="mt-1 text-[11px] leading-4 text-dim">
                {e.source}
                {e.published_at && now !== null && <> · {age(e.published_at, now)}</>}
              </p>
            </li>
          ))}
          {elsewhere.length === 0 && <li className="text-dim">Nothing yet.</li>}
        </ul>
      </Section>

      <Section title="Most active this week" className="mt-10">
        <ul className="mt-2.5">
          {active.map((v) => (
            <li key={v.slug} className="flex h-6 items-center justify-between">
              <button type="button" onClick={() => onVendor(v.slug)} className="text-fg-2 outline-none hover:text-fg focus-visible:text-fg">
                {v.name}
              </button>
              <span className="font-mono text-xs text-muted">{v.items_7d}</span>
            </li>
          ))}
          {active.length === 0 && <li className="text-dim">No tagged rows this week.</li>}
        </ul>
      </Section>

      <Section title="Added to KEV" className="mt-10">
        <ul className="mt-2.5">
          {kev.map((k) => (
            <li key={k.cve_id} className="flex h-6 items-center justify-between gap-3">
              <a
                href={`https://nvd.nist.gov/vuln/detail/${k.cve_id}`}
                {...EXTERNAL}
                title={`Added ${k.date_added}${k.product ? ` · ${k.product}` : ""}`}
                className="shrink-0 font-mono text-xs text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
              >
                {k.cve_id}
              </a>
              <span className="truncate text-muted">{k.vendor}</span>
            </li>
          ))}
          {kev.length === 0 && <li className="text-dim">No additions this week.</li>}
        </ul>
      </Section>

      <Section title="Last 24 hours" className="mt-10">
        <ul className="mt-2.5">
          {last24.map(([label, n, fill]) => (
            <li key={label} className="flex h-[22px] items-center">
              <span className="w-[62px] text-muted">{label}</span>
              <span className="relative h-[3px] flex-1 bg-rule" aria-hidden>
                <span className={cn("absolute inset-y-0 left-0", fill)} style={{ width: `${(n / peak) * 100}%` }} />
              </span>
              <span className="w-7 text-right font-mono text-xs text-fg-2">{n}</span>
            </li>
          ))}
        </ul>
      </Section>

      {status && (
        <p className="mt-10 leading-[19px] text-muted">
          Sources: NVD, CISA KEV, vendor PSIRTs, {status.sources_total} feeds.{" "}
          {status.sources_failing === 0 ? "All healthy." : `${status.sources_failing} failing.`}
          <br />
          <span className="mt-2 inline-block">Refreshes every {status.sync.interval_minutes} minutes.</span>
        </p>
      )}
    </aside>
  )
}
