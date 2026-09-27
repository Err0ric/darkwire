"use client"

import { useState, type MouseEvent, type ReactNode } from "react"
import { cn } from "cn"
import { Bug, ChevronDown, FileText, FlaskConical, Newspaper, ShieldAlert, type LucideIcon } from "lucide-react"

import { getItem, type Category, type FeedItem, type ItemDetail, type PatchStatus, type Severity } from "@/lib/api"
import { IMPACT_METRICS, parseVector } from "@/lib/cvss"
import { age, useNow } from "@/lib/time"
import { vendorLogo, vendorMark } from "@/lib/vendors"

const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const
const MAX_SOURCES = 4

const CATEGORY_LABEL: Record<Category, string> = {
  vulnerability: "Vulnerability",
  breach: "Breach",
  ransomware: "Ransomware",
  advisory: "Advisory",
  research: "Research",
  news: "News",
}

const CATEGORY_ICON: Record<Category, LucideIcon> = {
  vulnerability: Bug,
  breach: ShieldAlert,
  ransomware: ShieldAlert,
  advisory: FileText,
  research: FlaskConical,
  news: Newspaper,
}

type Detail = { state: "idle" | "loading" | "error" } | { state: "ready"; item: ItemDetail }

export function FeedRow({
  item,
  detail: initialDetail,
  defaultExpanded = false,
  fresh = false,
  pinned = false,
}: {
  item: FeedItem
  detail?: ItemDetail
  defaultExpanded?: boolean
  /** Arrived on a poll: fades in with the red left edge. */
  fresh?: boolean
  /** Held at the top of home (Critical or KEV in the last 48h). */
  pinned?: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [detail, setDetail] = useState<Detail>(
    initialDetail ? { state: "ready", item: initialDetail } : { state: "idle" },
  )
  const detailId = `row-${item.id}-detail`

  function toggle() {
    const next = !expanded
    setExpanded(next)
    if (next && (detail.state === "idle" || detail.state === "error")) {
      setDetail({ state: "loading" })
      getItem(item.id)
        .then((d) => setDetail({ state: "ready", item: d }))
        .catch(() => setDetail({ state: "error" }))
    }
  }

  function onRowClick(e: MouseEvent) {
    if ((e.target as HTMLElement).closest("a, button")) return
    toggle()
  }

  return (
    <article
      className={cn(
        "border-b border-hairline",
        fresh && "animate-row-in",
        expanded && "-mx-4 bg-surface px-4 md:-mx-6 md:px-6",
      )}
    >
      <div
        onClick={onRowClick}
        className="flex cursor-pointer items-start py-3 md:h-16 md:items-center md:py-0"
      >
        <VendorMark item={item} />

        <div className="min-w-0 flex-1 md:mr-[22px]">
          <a
            href={item.primary_url}
            {...EXTERNAL}
            className="line-clamp-2 text-[15px] leading-5 font-medium tracking-[-0.01em] text-fg outline-none focus-visible:underline md:block md:truncate"
          >
            {item.headline}
          </a>
          <MetaLine item={item} pinned={pinned} />
          <div className="mt-2 flex items-center md:hidden">
            <Score item={item} className="mr-3" />
            <Bar item={item} />
            <Badge item={item} className="ml-3" />
            <Age iso={item.last_event_at} className="ml-auto" />
          </div>
        </div>

        <div className="hidden shrink-0 items-center md:flex">
          {/* Dropped when the feed column is narrow (rail beside it at ~1000-1300px), so the
              headline keeps room. Needs an @container ancestor; without one it always shows. */}
          <span className="w-[128px] font-mono text-xs text-muted @max-[760px]:hidden">{item.cve_id}</span>
          <Score item={item} className="w-[47px] text-right" />
          <Bar item={item} className="ml-[21px]" />
          <Badge item={item} className="ml-5" />
          <Age iso={item.last_event_at} className="w-[51px] text-right" />
        </div>

        <button
          type="button"
          onClick={toggle}
          aria-expanded={expanded}
          aria-controls={detailId}
          aria-label={expanded ? "Collapse" : "Expand"}
          className="relative ml-3 flex size-5 shrink-0 items-center justify-center outline-none after:absolute after:-inset-2 after:content-[''] focus-visible:outline-1 focus-visible:outline-rule md:ml-[25px] md:size-3"
        >
          <ChevronDown
            className={cn("size-3", expanded ? "rotate-180 text-critical" : "text-chevron")}
            strokeWidth={2}
          />
        </button>
      </div>

      {expanded && (
        <div id={detailId} className="pb-[22px] pl-8 md:-mt-0.5 md:pl-10">
          <Expanded item={item} detail={detail} />
        </div>
      )}
    </article>
  )
}

function VendorMark({ item }: { item: FeedItem }) {
  const box = "mr-3 flex h-5 w-5 shrink-0 items-center justify-center text-muted md:mr-5"
  if (item.vendor) {
    const logo = vendorLogo(item.vendor)
    return (
      <span className={box} title={item.vendor.name}>
        {logo ? (
          // Monochrome SVG tinted through CSS mask so it follows currentColor.
          <span
            aria-hidden
            className="size-5 bg-current"
            style={{ mask: `url(${logo}) center / contain no-repeat` }}
          />
        ) : (
          <span className="font-mono text-[11px] leading-none">{vendorMark(item.vendor)}</span>
        )}
        <span className="sr-only">{item.vendor.name}</span>
      </span>
    )
  }
  const Icon = CATEGORY_ICON[item.category]
  return (
    <span className={box} aria-hidden>
      <Icon className="size-4" strokeWidth={1.5} />
    </span>
  )
}

function Sep({ wide = false }: { wide?: boolean }) {
  return (
    <span aria-hidden className={cn("text-dim", wide ? "mx-1.5 md:mx-4" : "mx-1.5")}>
      ·
    </span>
  )
}

function MetaLine({ item, pinned = false }: { item: FeedItem; pinned?: boolean }) {
  const parts: ReactNode[] = []
  if (item.sources.length === 0) {
    parts.push("NVD", "CVE published", "no coverage yet")
  } else {
    for (const s of item.sources.slice(0, MAX_SOURCES)) {
      parts.push(
        <a key={s.url} href={s.url} {...EXTERNAL} className="text-fg-2 outline-none hover:text-fg focus-visible:text-fg">
          {s.name}
        </a>,
      )
    }
    const hidden = item.sources.slice(MAX_SOURCES)
    if (hidden.length) {
      parts.push(
        <span key="more" title={hidden.map((s) => s.name).join(", ")}>
          +{hidden.length}
        </span>,
      )
    }
    parts.push(CATEGORY_LABEL[item.category])
  }
  if (item.kev) parts.push(<span key="kev" className="text-critical">KEV</span>)
  else if (item.exploited) parts.push(<span key="exploited" className="text-critical">EXPLOITED</span>)
  if (pinned) parts.push(<span key="pinned" className="text-dim">pinned</span>)

  return (
    <p className="mt-0.5 truncate text-xs leading-4 text-muted">
      {parts.map((p, i) => (
        <span key={i}>
          {i > 0 && <Sep />}
          {p}
        </span>
      ))}
    </p>
  )
}

function Score({ item, className }: { item: FeedItem; className?: string }) {
  if (item.cvss === null) return <span className={className} />
  return (
    <span className={cn("font-mono text-sm font-medium", item.cvss >= 7 ? "text-fg" : "text-fg-2", className)}>
      {item.cvss.toFixed(1)}
    </span>
  )
}

const BAR_FILL: Partial<Record<Severity, string>> = {
  critical: "bg-critical",
  high: "bg-accent",
  medium: "bg-medium",
  low: "bg-dim",
}

function Bar({ item, className }: { item: FeedItem; className?: string }) {
  // Only scored rows get a bar. Unscored rows keep the 68px slot so columns stay aligned.
  if (item.cvss === null) return <span aria-hidden className={cn("w-[68px] shrink-0", className)} />
  const filled = Math.round(item.cvss)
  const fill = (item.severity && BAR_FILL[item.severity]) || "bg-medium"
  return (
    <span className={cn("flex shrink-0 gap-0.5", className)} aria-label={`CVSS ${item.cvss}`}>
      {Array.from({ length: 10 }, (_, i) => (
        <span
          key={i}
          className={cn("h-2.5 w-[5px]", i < filled ? cn(fill, "animate-cell-fill") : "bg-rule")}
          style={i < filled ? { animationDelay: `${i * 25}ms` } : undefined}
        />
      ))}
    </span>
  )
}

const BADGE: Record<string, string> = {
  critical: "border-critical bg-critical text-fg",
  high: "border-accent text-fg",
  medium: "border-outline-medium text-fg-2",
  low: "border-outline-muted text-muted",
  muted: "border-outline-muted text-muted",
}

function Badge({ item, className }: { item: FeedItem; className?: string }) {
  // Scored rows show severity; breach and ransomware rows a gray BREACH; everything else no
  // badge, just the 64px slot so columns stay aligned. Never a guessed score.
  const severity = item.severity && item.severity !== "none" ? item.severity : null
  const breach = item.category === "breach" || item.category === "ransomware"
  if (!severity && !breach) return <span aria-hidden className={cn("w-16 shrink-0", className)} />
  const label = severity ?? "breach"
  return (
    <span
      className={cn(
        "flex h-[18px] w-16 shrink-0 items-center justify-center rounded-badge border font-mono text-[10px] leading-none font-medium tracking-[0.04em] uppercase",
        BADGE[severity ?? "muted"],
        className,
      )}
    >
      {label}
    </span>
  )
}

function Age({ iso, className }: { iso: string; className?: string }) {
  const now = useNow()
  return (
    <time dateTime={iso} title={new Date(iso).toUTCString()} className={cn("font-mono text-xs text-muted", className)}>
      {now === null ? "" : age(iso, now)}
    </time>
  )
}

// ---------------------------------------------------------------- expanded

function Unknown() {
  return <span className="text-dim">—</span>
}

function Expanded({ item, detail }: { item: FeedItem; detail: Detail }) {
  const d = detail.state === "ready" ? detail.item : null
  const cve = d?.cve ?? null
  const advisory = d?.patch_url ?? d?.msrc?.url ?? null

  return (
    <>
      <p className="line-clamp-3 max-w-[720px] text-sm leading-[1.6] text-summary">
        {detail.state === "ready" ? (
          (d?.summary ?? <span className="text-dim">No summary yet.</span>)
        ) : detail.state === "error" ? (
          <span className="text-dim">Details unavailable.</span>
        ) : (
          <span className="text-dim">Loading…</span>
        )}
      </p>

      {item.cve_id && (
        <>
          <p className="mt-[21px] text-[13px] leading-4 text-muted">
            {cve?.cvss_version ? `CVSS ${cve.cvss_version} vector` : "CVSS vector"}
          </p>
          <div className="mt-2 flex flex-wrap items-start gap-y-5">
            <VectorChips vector={cve?.cvss_vector ?? null} />
            <Metrics detail={d} />
          </div>
        </>
      )}

      <div className="mt-4 flex flex-col gap-3 text-sm leading-5 md:flex-row md:items-baseline md:justify-between">
        {item.cve_id ? (
          <p className="min-w-0 text-muted">
            Affected <span className="text-fg-2">{d ? (affected(d) ?? <Unknown />) : <Unknown />}</span>
            <Sep wide />
            <Patch status={d?.patch_status ?? null} url={d?.patch_url ?? null} />
          </p>
        ) : (
          <span />
        )}
        <p className="flex shrink-0 gap-5 text-fg-2">
          <a href={item.primary_url} {...EXTERNAL} className="outline-none hover:text-fg focus-visible:text-fg">
            Source
          </a>
          {advisory && (
            <a href={advisory} {...EXTERNAL} className="outline-none hover:text-fg focus-visible:text-fg">
              Vendor advisory
            </a>
          )}
          {item.cve_id && (
            <a
              href={`https://nvd.nist.gov/vuln/detail/${item.cve_id}`}
              {...EXTERNAL}
              className="outline-none hover:text-fg focus-visible:text-fg"
            >
              NVD
            </a>
          )}
        </p>
      </div>
    </>
  )
}

function VectorChips({ vector }: { vector: string | null }) {
  return (
    <ul className="flex flex-wrap gap-0.5" aria-label="CVSS vector">
      {parseVector(vector).map((c) => (
        <li
          key={c.metric}
          className={cn(
            "min-w-[60px] py-[7px] pr-3 pl-2.5",
            IMPACT_METRICS.has(c.metric) && c.value === "H" ? "bg-chip-impact" : "bg-chip",
          )}
        >
          <span className={cn("block font-mono text-xs leading-4", c.value ? "text-fg" : "text-dim")}>
            {c.metric}:{c.value ?? "—"}
          </span>
          <span className="block text-[10px] leading-[14px] text-muted">{c.label ?? " "}</span>
        </li>
      ))}
    </ul>
  )
}

function Metrics({ detail }: { detail: ItemDetail | null }) {
  const cve = detail?.cve ?? null
  const num = (v: number | null | undefined, digits: number) =>
    v === null || v === undefined ? <Unknown /> : v.toFixed(digits)
  // kev=false is only a fact once enrichment has run; before that it is a default.
  const kev = cve?.kev || detail?.kev ? "yes" : cve?.fetched_at ? "no" : null

  const pairs: [string, ReactNode][] = [
    ["Impact", num(cve?.impact_score, 1)],
    ["Exploitability", num(cve?.exploitability_score, 1)],
    ["EPSS", num(cve?.epss ?? detail?.epss, 2)],
    ["KEV", kev === null ? <Unknown /> : <span className={kev === "yes" ? "text-critical" : "text-muted"}>{kev}</span>],
  ]
  return (
    <dl className="flex basis-full gap-8 md:-mt-px md:ml-12 md:basis-auto">
      {pairs.map(([label, value]) => (
        <div key={label}>
          <dt className="text-[13px] leading-4 text-muted">{label}</dt>
          <dd className="mt-px font-mono text-lg leading-6 text-fg">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

const PATCH: Record<PatchStatus, { mark: string; text: string; tone: string }> = {
  patched: { mark: "●", text: "patched", tone: "text-fg" },
  no_fix: { mark: "○", text: "no fix", tone: "text-muted" },
  workaround: { mark: "○", text: "no fix · workaround", tone: "text-muted" },
  unverified: { mark: "○", text: "unverified", tone: "text-muted" },
}

function Patch({ status, url }: { status: PatchStatus | null; url: string | null }) {
  if (status === null) return <Unknown />
  const p = PATCH[status]
  const body = (
    <>
      {p.mark} {p.text}
      {url && (status === "patched" || status === "workaround") && (
        <span aria-hidden className="ml-1 text-[10px] text-critical">
          ↗
        </span>
      )}
    </>
  )
  const cls = cn("font-mono text-xs whitespace-nowrap", p.tone)
  return url && (status === "patched" || status === "workaround") ? (
    <a href={url} {...EXTERNAL} className={cn(cls, "outline-none hover:text-fg focus-visible:text-fg")}>
      {body}
    </a>
  ) : (
    <span className={cls}>{body}</span>
  )
}

/** Affected ranges as computed by the API from NVD, else the MSRC product. Null when unknown. */
function affected(d: ItemDetail): string | null {
  return d.cve?.affected ?? d.msrc?.product ?? null
}
