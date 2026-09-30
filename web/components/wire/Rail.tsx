"use client"

import type { ReactNode } from "react"
import { cn } from "cn"

import type { ElsewhereItem, KevRow, Severity, Status, VendorOut } from "@/lib/api"
import { NewDot, type DotState } from "@/lib/dots"
import { age, useNow } from "@/lib/time"

const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const
// Elsewhere items by screen height, in CSS only (the rail-tall / rail-taller variants in
// globals.css): all are rendered, the extra ones hidden until the screen is tall enough.
const ELSEWHERE_SHOWN = [6, 9, 12] as const
const ELSEWHERE_ITEM = ["", "hidden rail-tall:block", "hidden rail-taller:block"] as const
const ELSEWHERE_MORE = ["rail-tall:hidden", "hidden rail-tall:block rail-taller:hidden", "hidden rail-taller:block"] as const

function Section({
  title,
  aside,
  children,
  className,
}: {
  title: string
  aside?: string
  children: ReactNode
  className?: string
}) {
  return (
    <section className={className}>
      <div className="flex items-baseline justify-between">
        <h2 className="text-[13px] font-medium text-fg-2">{title}</h2>
        {aside && <span className="text-[11px] min-[2200px]:text-[12px] text-dim-text">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

// Model not usable (no key, bad key, out of quota, failing): new rows arrive without summaries.
const SUMMARIES_PAUSED: ReadonlySet<string> = new Set(["no_key", "auth_failing", "quota", "error"])

/** The most recent Elsewhere items (6, then 9 and 12 on taller wide screens): headline (2 lines)
 * over "source · age · topic"; new ones get the new-row dot. "+ N more" counts what is hidden at
 * the current height and opens the wire's Elsewhere tab (all of the last 7 days). */
export function Elsewhere({
  elsewhere,
  dots,
  onSeen,
  onMore,
}: {
  elsewhere: ElsewhereItem[]
  dots?: ReadonlyMap<number, DotState>
  onSeen?: (id: number) => void
  onMore?: () => void
}) {
  const now = useNow()
  const shown = elsewhere.slice(0, ELSEWHERE_SHOWN[2])
  // The subtitle: this week's three most common topics.
  const counts = new Map<string, number>()
  for (const e of elsewhere) if (e.topic) counts.set(e.topic, (counts.get(e.topic) ?? 0) + 1)
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 3).map(([t]) => t)
  return (
    <Section title="Elsewhere" aside={top.length ? top.join(" · ") : undefined}>
      <ul className="mt-3">
        {shown.map((e, i) => {
          const dot = dots?.get(e.id)
          const tier = ELSEWHERE_SHOWN.findIndex((n) => i < n)
          return (
            <li key={e.id} className={cn("relative -mx-2 mb-1.5 px-2 py-1 hover:bg-surface", ELSEWHERE_ITEM[tier])}>
              {dot && <NewDot state={dot} className="top-[12px] -left-[7px]" />}
              <a
                href={e.url}
                {...EXTERNAL}
                onClick={() => onSeen?.(e.id)}
                className="max-md:tap line-clamp-2 leading-[18px] font-medium text-fg outline-none hover:underline focus-visible:underline"
              >
                {e.headline}
              </a>
              <p className="mt-1 text-[11px] leading-4 text-dim-text min-[2200px]:text-[12px]">
                {e.source}
                {e.published_at && now !== null && <> · {age(e.published_at, now)}</>}
                {e.topic && <span className="font-mono text-[11px]"> · {e.topic}</span>}
              </p>
            </li>
          )
        })}
        {elsewhere.length === 0 && <li className="text-dim-text">Nothing yet.</li>}
        {onMore &&
          ELSEWHERE_SHOWN.map((n, tier) => {
            const more = elsewhere.length - Math.min(n, elsewhere.length)
            return more > 0 ? (
              <li key={n} className={cn("-mx-2 px-2", ELSEWHERE_MORE[tier])}>
                <button
                  type="button"
                  onClick={onMore}
                  className="max-md:tap text-dim-text outline-none hover:text-fg-2 focus-visible:text-fg-2"
                >
                  + {more} more
                </button>
              </li>
            ) : null
          })}
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
  const top = Math.max(1, ...active.map((v) => v.items_7d))
  return (
    <Section title="Most active this week">
      <ul className="mt-2.5">
        {active.map((v, i) => {
          const on = vendor === v.slug
          return (
            <li key={v.slug} className="-mx-2 flex h-6 items-center justify-between px-2 hover:bg-surface">
              <button
                type="button"
                onClick={() => onVendor(v.slug)}
                aria-pressed={on}
                className={cn(
                  "max-md:tap",
                  "w-28 shrink-0 truncate text-left outline-none hover:text-fg-2 focus-visible:text-fg-2",
                  on ? "text-fg-2" : "text-muted",
                )}
              >
                {/* Names take a fixed column so the bars line up; the active one is underlined. */}
                <span
                  className={cn(
                    "relative",
                    on && "after:absolute after:inset-x-0 after:-bottom-1 after:h-px after:bg-fg",
                  )}
                >
                  {v.name}
                </span>
              </button>
              {/* A thin bar scaled to the most active vendor. */}
              <span aria-hidden className="mr-3 h-[3px] min-w-6 flex-1 bg-rule">
                <span
                  className={cn("block h-full", i === 0 ? "bg-rail-top" : "bg-rail-bar")}
                  style={{ width: `${(v.items_7d / top) * 100}%` }}
                />
              </span>
              <span className="w-6 text-right font-mono text-xs text-dim-text">{v.items_7d}</span>
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
const MINI_FILL: Partial<Record<Severity, string>> = {
  critical: "bg-rail-critical",
  high: "bg-rail-high",
  medium: "bg-rail-medium",
  low: "bg-rail-low",
}

/** CVSS score in mono with a 5-cell bar (one cell per 2 points), colored by severity; an
 * unscored CVE keeps the space so the rows line up. */
function MiniScore({ cvss, severity }: { cvss: number | null; severity: Severity | null }) {
  if (cvss === null) return <span className="w-[62px] shrink-0" />
  const filled = Math.round(cvss / 2)
  const fill = (severity && MINI_FILL[severity]) || "bg-rail-medium"
  return (
    <span className="flex w-[62px] shrink-0 items-center justify-end gap-2">
      <span className="font-mono text-xs text-dim-text">{cvss.toFixed(1)}</span>
      <span role="img" aria-label={`CVSS ${cvss}`} className="flex gap-0.5">
        {Array.from({ length: 5 }, (_, i) => (
          <span key={i} className={cn("h-2 w-[4px]", i < filled ? fill : "bg-rule")} />
        ))}
      </span>
    </span>
  )
}

/** CISA's catalog additions of the last 7 days, newest first. A CVE with a row on the board links
 * to that row (scrolled to and expanded when it is on this view, else its permalink); any other
 * CVE links to NVD. `query` carries the stack and theme on internal links. */
/** CISA's catalog additions of the last 7 days, newest first: vendor, CVE ID, CVSS with a mini bar
 * (the due date lives in the expanded row).
 * A CVE with a row on the board links to that row (scrolled to and expanded when it is on this
 * view, else its permalink); any other CVE links to NVD. `query` carries the stack and theme on
 * internal links. When the week has more additions than rows shown, "+N more" opens the wire's
 * KEV tab. */
export function AddedToKev({
  kev,
  total,
  query = "",
  onMore,
}: {
  kev: KevRow[]
  /** The header's "added to KEV this week" count. */
  total?: number
  query?: string
  onMore?: () => void
}) {
  const more = total !== undefined ? total - kev.length : 0
  return (
    <Section title="Added to KEV">
      <ul className="mt-2.5">
        {kev.map((k) => {
          const title = `Added ${k.date_added}${k.product ? ` · ${k.product}` : ""}`
          // A fixed, left-aligned column (monospace): short IDs (CVE-2026-5430) line up with long ones.
          const cls = "max-md:tap w-[15ch] shrink-0 text-left font-mono text-xs text-dim-text outline-none hover:text-fg-2 focus-visible:text-fg-2"
          const itemId = k.item_id
          return (
            <li key={k.cve_id} className="-mx-2 flex h-6 items-center gap-3 px-2 hover:bg-surface">
              <span className="min-w-0 flex-1 truncate text-muted">{k.vendor}</span>
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
                <a
                  href={`https://nvd.nist.gov/vuln/detail/${k.cve_id}`}
                  {...EXTERNAL}
                  title={`${title} · NVD`}
                  className={cls}
                >
                  {k.cve_id}
                </a>
              )}
              <MiniScore cvss={k.cvss} severity={k.severity} />
            </li>
          )
        })}
        {kev.length === 0 && <li className="text-dim-text">No additions this week.</li>}
        {more > 0 && onMore && (
          <li className="-mx-2 flex h-6 items-center px-2">
            <button
              type="button"
              onClick={onMore}
              className="max-md:tap text-dim-text outline-none hover:text-fg-2 focus-visible:text-fg-2"
            >
              +{more} more
            </button>
          </li>
        )}
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
        ["critical", "Critical", counts.critical_7d, "bg-rail-critical"],
        ["high", "High", counts.high_7d, "bg-rail-high"],
        ["medium", "Medium", counts.medium_7d, "bg-rail-medium"],
        ["low", "Low", counts.low_7d, "bg-rail-low"],
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
                    on ? "text-fg-2" : "text-muted",
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
              <span className={cn("w-8 text-right font-mono text-xs", key === "critical" && n > 0 ? "text-critical-text" : "text-dim-text")}>{n}</span>
            </>
          )
          return (
            <li key={key} className="-mx-2 h-6 px-2 hover:bg-surface">
              {n > 0 ? (
                <button
                  type="button"
                  onClick={() => onSeverity(key)}
                  aria-pressed={on}
                  title={on ? "Clear the severity filter" : `Show ${label.toLowerCase()} rows from the last 7 days`}
                  className="max-md:tap group flex h-full w-full items-center outline-none focus-visible:outline-1 focus-visible:outline-rule"
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

/** The wire's footer text: sources and their health. */
export function SourcesLine({ status }: { status: Status | null }) {
  if (!status) return null
  return (
    <>
      Sources: NVD, CISA KEV, vendor PSIRTs, {status.sources_total} feeds.{" "}
      {status.sources_failing === 0 ? "All healthy." : `${status.sources_failing} failing.`}
      {SUMMARIES_PAUSED.has(status.summaries.state) && " Summaries paused."} Rows update every minute.
    </>
  )
}
