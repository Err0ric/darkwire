"use client"

import type { ReactNode } from "react"
import { cn } from "cn"

import type { ElsewhereItem, KevRow, Severity, Status, VendorOut } from "@/lib/api"
import { age, useNow } from "@/lib/time"

const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const

function Section({ title, aside, children, className }: { title: string; aside?: string; children: ReactNode; className?: string }) {
  return (
    <section className={className}>
      <div className="flex items-baseline justify-between">
        <h2 className="text-[13px] font-medium text-fg">{title}</h2>
        {aside && <span className="text-[11px] min-[2200px]:text-[12px] text-dim-text">{aside}</span>}
      </div>
      {children}
    </section>
  )
}


// Model not usable (no key, bad key, out of quota, failing): new rows arrive without summaries.
const SUMMARIES_PAUSED: ReadonlySet<string> = new Set(["no_key", "auth_failing", "quota", "error"])

export function Elsewhere({ elsewhere }: { elsewhere: ElsewhereItem[] }) {
  const now = useNow()
  return (
    <Section title="Elsewhere" aside="policy · privacy · culture">
      <ul className="mt-3">
        {elsewhere.map((e) => (
          <li key={e.id} className="-mx-2 mb-1.5 px-2 py-1 hover:bg-surface">
            <a href={e.url} {...EXTERNAL} className="line-clamp-2 leading-[18px] text-fg-2 outline-none hover:text-fg focus-visible:text-fg">
              {e.headline}
            </a>
            <p className="mt-1 text-[11px] min-[2200px]:text-[12px] leading-4 text-dim-text">
              {e.source}
              {e.published_at && now !== null && <> · {age(e.published_at, now)}</>}
            </p>
          </li>
        ))}
        {elsewhere.length === 0 && <li className="text-dim-text">Nothing yet.</li>}
      </ul>
    </Section>
  )
}

// Rail sections. The wire places them per breakpoint (CLAUDE.md "Right rail").

/** Each vendor sets the wire's vendor filter (like the All vendors menu); the active one is
 * underlined like the active tab, and clicking it again clears the filter. */
export function MostActive({
  active,
  vendor,
  onVendor,
}: {
  active: VendorOut[]
  vendor: string
  onVendor: (slug: string) => void
}) {
  return (
    <Section title="Most active this week">
      <ul className="mt-2.5">
        {active.map((v) => {
          const on = vendor === v.slug
          return (
            <li key={v.slug} className="-mx-2 flex h-6 items-center justify-between px-2 hover:bg-surface">
              <button
                type="button"
                onClick={() => onVendor(v.slug)}
                aria-pressed={on}
                className={cn(
                  "relative outline-none hover:text-fg focus-visible:text-fg",
                  on ? "text-fg after:absolute after:inset-x-0 after:-bottom-1 after:h-px after:bg-fg" : "text-fg-2",
                )}
              >
                {v.name}
              </button>
              <span className="font-mono text-xs text-muted">{v.items_7d}</span>
            </li>
          )
        })}
        {active.length === 0 && <li className="text-dim-text">No tagged rows this week.</li>}
      </ul>
    </Section>
  )
}

/** Scroll to a row on the current wire view and expand it. False when it is not on screen. */
function openRow(itemId: number): boolean {
  const row = document.getElementById(`row-${itemId}`)
  if (!row) return false
  row.scrollIntoView({ block: "center" })
  const toggle = row.querySelector<HTMLButtonElement>('button[aria-expanded="false"]')
  toggle?.click()
  return true
}

/** CISA's catalog additions of the last 7 days, newest first. A CVE with a row on the board links
 * to that row (scrolled to and expanded when it is on this view, else its permalink); any other
 * CVE links to NVD. `query` carries the stack and theme on internal links. */
export function AddedToKev({ kev, query = "" }: { kev: KevRow[]; query?: string }) {
  return (
    <Section title="Added to KEV">
      <ul className="mt-2.5">
        {kev.map((k) => {
          const title = `Added ${k.date_added}${k.product ? ` · ${k.product}` : ""}`
          const cls = "shrink-0 font-mono text-xs text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
          const itemId = k.item_id
          return (
            <li key={k.cve_id} className="-mx-2 flex h-6 items-center justify-between gap-3 px-2 hover:bg-surface">
              {itemId !== null ? (
                <a
                  href={`/item/${itemId}${query}`}
                  title={title}
                  onClick={(e) => {
                    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
                    if (openRow(itemId)) e.preventDefault()
                  }}
                  className={cls}
                >
                  {k.cve_id}
                </a>
              ) : (
                <a href={`https://nvd.nist.gov/vuln/detail/${k.cve_id}`} {...EXTERNAL} title={`${title} · NVD`} className={cls}>
                  {k.cve_id}
                </a>
              )}
              <span className="truncate text-muted">{k.vendor}</span>
            </li>
          )
        })}
        {kev.length === 0 && <li className="text-dim-text">No additions this week.</li>}
      </ul>
    </Section>
  )
}

export function LastSevenDays({
  status,
  severity,
  onSeverity,
}: {
  status: Status | null
  /** The wire's ?severity= filter; a row click sets it, clicking the active row clears it. */
  severity: Severity | ""
  onSeverity: (s: Severity) => void
}) {
  const counts = status?.counts
  const week: [Severity, string, number, string][] = counts
    ? [
        ["critical", "Critical", counts.critical_7d, "bg-critical"],
        ["high", "High", counts.high_7d, "bg-accent"],
        ["medium", "Medium", counts.medium_7d, "bg-dim"],
        ["low", "Low", counts.low_7d, "bg-outline-medium"],
      ]
    : []
  const peak = Math.max(1, ...week.map(([, , n]) => n))

  return (
    <Section title="Last 7 days">
      <ul className="mt-2.5">
        {week.map(([key, label, n, fill]) => {
          const on = severity === key
          const row = (
            <>
              <span className="w-[62px] text-left">
                <span
                  className={cn(
                    "relative",
                    on ? "text-fg" : "text-muted",
                    n > 0 && !on && "group-hover:text-fg-2",
                    on && "after:absolute after:inset-x-0 after:-bottom-1 after:h-px after:bg-fg",
                  )}
                >
                  {label}
                </span>
              </span>
              <span className="relative h-[3px] flex-1 bg-rule" aria-hidden>
                <span className={cn("absolute inset-y-0 left-0", fill)} style={{ width: `${(n / peak) * 100}%` }} />
              </span>
              <span className="w-8 text-right font-mono text-xs text-fg-2">{n}</span>
            </>
          )
          return (
            <li key={key} className="-mx-2 h-[22px] px-2 hover:bg-surface">
              {n > 0 ? (
                <button
                  type="button"
                  onClick={() => onSeverity(key)}
                  aria-pressed={on}
                  title={on ? "Clear the severity filter" : `Show ${label.toLowerCase()} rows from the last 7 days`}
                  className="group flex h-full w-full items-center outline-none focus-visible:outline-1 focus-visible:outline-rule"
                >
                  {row}
                </button>
              ) : (
                <span className="flex h-full items-center">{row}</span>
              )}
            </li>
          )
        })}
      </ul>
    </Section>
  )
}

export function SourcesLine({ status }: { status: Status | null }) {
  if (!status) return null
  return (
    <p className="leading-[19px] text-muted">
      Sources: NVD, CISA KEV, vendor PSIRTs, {status.sources_total} feeds.{" "}
      {status.sources_failing === 0 ? "All healthy." : `${status.sources_failing} failing.`}
      {SUMMARIES_PAUSED.has(status.summaries.state) && " Summaries paused."} Rows update every minute.
    </p>
  )
}
