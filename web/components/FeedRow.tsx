"use client"

import { useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react"
import { cn } from "cn"
import { Bug, ChevronDown, FileText, FlaskConical, Newspaper, ShieldAlert, type LucideIcon } from "lucide-react"

import { VendorGlyph } from "@/components/VendorGlyph"
import { getItem, type Category, type FeedItem, type ItemDetail, type PatchStatus, type Severity } from "@/lib/api"
import { useHoverPreview } from "@/components/HoverPreview"
import { IMPACT_METRICS, parseVector, plainVector } from "@/lib/cvss"
import { kevDueIn, URGENT_DAYS } from "@/lib/kev"
import { kevDate, ticketText, whatToDo, type Todo } from "@/lib/todo"
import { NewDot, type DotState } from "@/lib/dots"
import { age, clockTime, useNow } from "@/lib/time"
import { shouldToggle } from "@/lib/toggle"

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

export type Detail = { state: "idle" | "loading" | "error" } | { state: "ready"; item: ItemDetail }

/** KEV, exploited or Critical (an old CVE, dimmed, is not): these rows get the critical edge. */
function flagged(item: FeedItem): boolean {
  return !item.stale && (item.severity === "critical" || item.kev || item.exploited)
}

export function FeedRow({
  item,
  detail: initialDetail,
  defaultExpanded = false,
  fresh = false,
  pinned = false,
  inStack = false,
  dot,
  onSeen,
  clockAge = false,
}: {
  item: FeedItem
  detail?: ItemDetail
  defaultExpanded?: boolean
  /** Arrived on a poll: fades in from the top. */
  fresh?: boolean
  /** Held at the top of home (Critical or KEV in the last 48h). */
  pinned?: boolean
  /** Vendor is in the viewer's stack: brighter mark and a quiet "stack" in the meta line. */
  inStack?: boolean
  /** New-row dot (lib/dots.tsx), left of the headline. */
  dot?: DotState
  /** Expanding the row clears its dot. */
  onSeen?: () => void
  /** Under a day separator older than today: the age column shows the local clock time. */
  clockAge?: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [detail, setDetail] = useState<Detail>(
    initialDetail ? { state: "ready", item: initialDetail } : { state: "idle" },
  )
  const detailId = `row-${item.id}-detail`
  // Hover card with the summary (NEXT_PUBLIC_HOVER_PREVIEW); never while the row is open.
  const preview = useHoverPreview(item.summary, !expanded)
  const hasData = item.cve_id !== null || item.cvss !== null || hasBadge(item)
  // A plain row with no summary and no feed excerpt has nothing to show: headline link only,
  // no chevron (its column keeps its width). Older API responses lack the flag: expandable.
  const canExpand = item.expandable !== false

  function toggle() {
    const next = !expanded
    setExpanded(next)
    if (next) onSeen?.()
    if (next && (detail.state === "idle" || detail.state === "error")) {
      setDetail({ state: "loading" })
      getItem(item.id)
        .then((d) => setDetail({ state: "ready", item: d }))
        .catch(() => setDetail({ state: "error" }))
    }
  }

  const rowRef = useRef<HTMLElement>(null)
  const headRef = useRef<HTMLDivElement>(null)

  // Header and open panel are one toggle target: anywhere but a link or button, and never when
  // the click ends a text selection in the row (lib/toggle.ts).
  function onRowClick(e: MouseEvent) {
    if (shouldToggle(e.target, rowRef.current)) toggle()
  }

  // Esc anywhere in an open row closes it and puts focus back on the row.
  function onArticleKey(e: KeyboardEvent) {
    if (e.key !== "Escape" || !expanded) return
    toggle()
    headRef.current?.focus()
  }

  function onRowKey(e: KeyboardEvent) {
    if (e.target !== e.currentTarget || (e.key !== "Enter" && e.key !== " ")) return
    e.preventDefault()
    toggle()
  }

  return (
    <article
      ref={rowRef}
      id={`row-${item.id}`}
      onKeyDown={canExpand ? onArticleKey : undefined}
      className={cn(
        "scroll-mt-12 border-b border-rule",
        fresh && "animate-row-in",
        // Open: header and panel share one band and one hover, so they read as one unit.
        expanded && "-mx-4 bg-surface px-4 hover:bg-row-hover md:-mx-6 md:px-6",
      )}
    >
      {/* The row is the expand toggle: a click anywhere but a link (the headline, the sources,
          the CVE ID) toggles it, and so do Enter / Space while the row has focus. */}
      <div
        ref={headRef}
        onClick={canExpand ? onRowClick : undefined}
        onKeyDown={canExpand ? onRowKey : undefined}
        role={canExpand ? "group" : undefined}
        tabIndex={canExpand ? 0 : undefined}
        aria-label={canExpand ? `${item.headline}. ${expanded ? "Collapse" : "Expand"} details` : undefined}
        className={cn(
          // Rhythm: 15px above and below, 4px from headline to meta, so rows read as units.
          "relative flex min-h-14 items-start py-[15px] outline-offset-[-1px] md:items-center",
          !expanded && "hover:bg-row-hover",
          canExpand && "cursor-pointer",
          // KEV, exploited or Critical: a 2px --rail-critical edge the row's full height, in the
          // gutter just left of it, so the icon and headline do not move.
          flagged(item) &&
            "before:pointer-events-none before:absolute before:inset-y-0 before:-left-2.5 before:w-0.5 before:bg-rail-critical",
        )}
      >
        <VendorMark item={item} inStack={inStack} />

        <div className="relative min-w-0 flex-1 md:mr-[22px]">
          {dot && <NewDot state={dot} className="top-[7px] -left-[9px] md:-left-[13px]" />}
          {/* Only the headline text is the link (inline), so the space beside it toggles the row. */}
          <p className="line-clamp-2 max-w-[72ch] text-[15px] leading-[1.35] font-medium tracking-[-0.01em] text-fg">
            <a
              href={item.primary_url}
              {...EXTERNAL}
              {...preview.handlers}
              className="max-md:tap outline-none hover:underline focus-visible:underline"
            >
              {item.headline}
            </a>
          </p>
          {preview.card}
          {/* Phones: the age ends the meta line (right-aligned), and the score / bar / badge line
              shows only when the row has one. The chevron stays in its column. */}
          <MetaLine
            item={item}
            pinned={pinned}
            inStack={inStack}
            end={<Age iso={item.last_event_at} clock={clockAge} className="ml-auto shrink-0 pl-3 md:hidden" />}
          />
          {hasData && (
            <div className="mt-2 flex items-center md:hidden">
              <Score item={item} className="mr-3" />
              <Bar item={item} />
              <Badge item={item} className="ml-3" />
            </div>
          )}
        </div>

        <div className="hidden shrink-0 items-center md:flex">
          {/* Dropped when the feed column is narrow (rail beside it at ~1000-1300px), so the
              headline keeps room. Needs an @container ancestor; without one it always shows. */}
          {/* No CVE, score, bar or badge: the empty columns go, and the headline runs to the age. */}
          {hasData && (
            <>
              <span className="w-[128px] font-mono text-xs text-muted @max-[760px]:hidden">{item.cve_id}</span>
              <Score item={item} className="w-[47px] text-right" />
              <Bar item={item} className="ml-[21px]" />
              <Badge item={item} className="ml-5" />
            </>
          )}
          <Age iso={item.last_event_at} clock={clockAge} className="w-[51px] text-right" />
        </div>

        {canExpand ? (
          <button
            type="button"
            onClick={toggle}
            tabIndex={-1}
            aria-expanded={expanded}
            aria-controls={detailId}
            aria-label={expanded ? "Collapse" : "Expand"}
            className="max-md:tap relative ml-3 flex size-5 shrink-0 items-center justify-center outline-none after:absolute after:-inset-2 after:content-[''] focus-visible:outline-1 focus-visible:outline-rule md:ml-[25px] md:size-3"
          >
            <ChevronDown
              className={cn("size-3", expanded ? "rotate-180 text-critical-text" : "text-chevron")}
              strokeWidth={2}
            />
          </button>
        ) : (
          <span aria-hidden className="ml-3 size-5 shrink-0 md:ml-[25px] md:size-3" />
        )}
      </div>

      {expanded && (
        <div id={detailId} onClick={onRowClick} className="cursor-pointer pb-[22px] pl-8 md:-mt-0.5 md:pl-10">
          <Expanded item={item} detail={detail} />
        </div>
      )}
    </article>
  )
}

function VendorMark({ item, inStack }: { item: FeedItem; inStack: boolean }) {
  // A fixed 20px column, marks aligned to its left: one hard edge for icons, one for text.
  const box = cn("mr-3 flex h-5 w-5 shrink-0 items-center justify-start md:mr-5", inStack ? "text-fg" : "text-muted")
  if (item.vendor) {
    return (
      <span className={box} title={item.vendor.name}>
        <VendorGlyph vendor={item.vendor} />
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
    <span aria-hidden className={cn("text-dim-text", wide ? "mx-1.5 md:mx-4" : "mx-1.5")}>
      ·
    </span>
  )
}

function MetaLine({
  item,
  pinned = false,
  inStack = false,
  end,
}: {
  item: FeedItem
  pinned?: boolean
  inStack?: boolean
  /** Right-aligned at the end of the line (the age on phones). */
  end?: ReactNode
}) {
  const parts: ReactNode[] = []
  if (item.sources.length === 0) {
    parts.push("NVD", "CVE published", "no coverage yet")
  } else {
    for (const s of item.sources.slice(0, MAX_SOURCES)) {
      parts.push(
        <a key={s.url} href={s.url} {...EXTERNAL} className="max-md:tap-down decoration-fg-2 underline-offset-[3px] outline-none hover:text-fg-2 hover:underline focus-visible:text-fg-2 focus-visible:underline">
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
  if (item.kev) parts.push(<KevMark key="kev" item={item} />)
  else if (item.exploited) parts.push(<span key="exploited" className="text-critical-text">EXPLOITED</span>)
  else if (item.poc) parts.push(<span key="poc" className="text-critical-text">POC</span>)
  if (pinned) parts.push(<span key="pinned" className="text-dim-text">pinned</span>)
  if (inStack) parts.push(<span key="stack" className="text-dim-text">your stack</span>)

  return (
    <p className="mt-1 flex items-baseline font-mono text-xs leading-4 whitespace-nowrap text-muted">
      <span className="min-w-0 truncate">
        {parts.map((p, i) => (
          <span key={i}>
            {i > 0 && <Sep />}
            {p}
          </span>
        ))}
      </span>
      {end}
    </p>
  )
}

/** "KEV", or "KEV due in 5d" within a week of CISA's deadline: red in full at 2 days or less,
 * "KEV overdue" for a week after it. */
function KevMark({ item }: { item: FeedItem }) {
  const now = useNow()
  const days = now === null ? null : kevDueIn(item, now)
  if (days === null) return <span className="text-critical-text">KEV</span>
  if (days < 0) return <span className="text-critical-text">KEV overdue</span>
  const when = days === 0 ? "due today" : `due in ${days}d`
  return days <= URGENT_DAYS ? (
    <span className="text-critical-text">KEV {when}</span>
  ) : (
    <span>
      <span className="text-critical-text">KEV</span> <span className="text-fg-2">{when}</span>
    </span>
  )
}

// An old CVE (over 90 days, not in KEV, nothing about exploitation) keeps its score but reads quieter.
// Old CVEs dim: the score and badge text take --dim-text (still >= 4.5:1), the bar's cells 40%.
const STALE_TEXT = "text-dim-text"
const STALE_BAR = "opacity-40"
const STALE_TITLE = "Older CVE: published over 90 days ago, not in KEV, no reported exploitation"

function Score({ item, className }: { item: FeedItem; className?: string }) {
  if (item.cvss === null) return <span className={className} />
  return (
    <span
      title={item.stale ? STALE_TITLE : undefined}
      className={cn("font-mono text-[15px] font-medium", item.stale ? STALE_TEXT : item.cvss >= 7 ? "text-fg" : "text-fg-2", className)}
    >
      {item.cvss.toFixed(1)}
    </span>
  )
}

export const BAR_FILL: Partial<Record<Severity, string>> = {
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
    <span className={cn("flex shrink-0 gap-0.5", item.stale && STALE_BAR, className)} role="img" aria-label={`CVSS ${item.cvss}`}>
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
  critical: "border-critical bg-critical text-on-critical",
  high: "border-accent text-fg",
  medium: "border-outline-medium text-fg-2",
  low: "border-outline-muted text-muted",
  muted: "border-outline-muted text-muted",
}

function hasBadge(item: FeedItem): boolean {
  const severity = item.severity && item.severity !== "none" ? item.severity : null
  return severity !== null || item.category === "breach" || item.category === "ransomware"
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
        "flex h-[18px] w-16 shrink-0 items-center justify-center rounded-badge border font-mono text-[11px] leading-none font-medium tracking-[0.04em] uppercase",
        // Stale: a quiet outline and --dim-text instead of the severity colors.
        item.stale ? "border-outline-medium text-dim-text" : BADGE[severity ?? "muted"],
        className,
      )}
    >
      {label}
    </span>
  )
}

/** Relative age ("6h") for today's rows; local clock time ("14:32") for older ones, with the
 * relative age on hover. Both from last_event_at, the row's sort key, like the day separators. */
function Age({ iso, clock = false, className }: { iso: string; clock?: boolean; className?: string }) {
  const now = useNow()
  const relative = now === null ? "" : age(iso, now)
  return (
    <time
      dateTime={iso}
      title={clock ? (relative ? `${relative} ago` : undefined) : new Date(iso).toLocaleString()}
      className={cn("font-mono text-xs text-muted", className)}
    >
      {now === null ? "" : clock ? clockTime(iso) : relative}
    </time>
  )
}

// ---------------------------------------------------------------- expanded
// Every section renders only when it has data: no dashes, blanks, "unknown" or placeholders.
// Plain news expands to its summary (when there is one) and its source link, nothing else.

const LINK = "max-md:tap outline-none hover:text-fg focus-visible:text-fg"

export function Expanded({ item, detail }: { item: FeedItem; detail: Detail }) {
  const d = detail.state === "ready" ? detail.item : null
  const cve = d?.cve ?? null
  const advisory = d?.patch_url ?? d?.msrc?.url ?? null
  const todo = d && item.cve_id ? whatToDo(d) : null
  const chips = parseVector(cve?.cvss_vector ?? null).filter((c) => c.value)
  const metrics = d && item.cve_id ? metricPairs(d) : []
  const affectedText = d && item.cve_id ? (cve?.affected ?? d.msrc?.product ?? null) : null
  // Vendor data first; the articles' own words only when it names nothing, labeled.
  const affectedPerArticle = d && item.cve_id && !affectedText ? (d.article_facts?.affected ?? null) : null
  const plain = plainVector(cve?.cvss_vector ?? null)
  // The list already carries the summary: it shows at once, before the detail arrives.
  const summary = item.summary ?? d?.summary ?? null
  const patch = d && item.cve_id && d.patch_status !== "unverified" ? d.patch_status : null
  // kev=false is only a fact once enrichment has run; before that it is a default.
  const kev = !d || !item.cve_id ? null : cve?.kev || d.kev ? "yes" : cve?.fetched_at ? "no" : null

  return (
    <div className="flex flex-col gap-4">
      {summary && <p className="line-clamp-3 max-w-[720px] text-[15px] leading-[1.6] text-summary">{summary}</p>}
      {/* No summary (declined, or the article fetch failed): the stored RSS excerpt, labeled and attributed. */}
      {d && !summary && d.excerpt && (
        <div>
          <p className="text-[13px] font-medium leading-4 text-muted">From the feed</p>
          <p className="mt-2 line-clamp-3 max-w-[720px] text-[15px] leading-[1.6] text-fg-2">
            {d.excerpt.source}: “{d.excerpt.text}”
          </p>
        </div>
      )}

      <Facts
        todo={todo}
        affected={affectedText ? { text: affectedText, perArticle: false } : affectedPerArticle ? { text: affectedPerArticle, perArticle: true } : null}
        kev={kev}
        exploited={!!d && item.exploited}
      />

      {(chips.length > 0 || metrics.length > 0) && (
        <div className="flex flex-wrap items-end gap-x-12 gap-y-5">
          {chips.length > 0 && (
            <div>
              <p className="text-[13px] leading-4 text-muted">{cve?.cvss_version ? `CVSS ${cve.cvss_version} vector` : "CVSS vector"}</p>
              <VectorChips chips={chips} />
              {plain && <p className="mt-2 text-[13px] leading-5 text-fg-2">{plain}</p>}
            </div>
          )}
          {metrics.length > 0 && <Metrics pairs={metrics} />}
        </div>
      )}

      <div className="flex flex-col gap-3 text-[13px] leading-5 md:flex-row md:items-baseline md:justify-between">
        {patch ? (
          <p className="min-w-0 text-muted">
            <Patch status={patch} url={d?.patch_url ?? null} />
          </p>
        ) : (
          <span />
        )}
        <p className="flex shrink-0 flex-wrap gap-x-5 gap-y-1 text-fg-2">
          <a href={item.primary_url} {...EXTERNAL} className={LINK}>
            Source
          </a>
          {advisory && (
            <a href={advisory} {...EXTERNAL} className={LINK}>
              Vendor advisory
            </a>
          )}
          {item.cve_id && (
            <a href={`https://nvd.nist.gov/vuln/detail/${item.cve_id}`} {...EXTERNAL} className={LINK}>
              NVD
            </a>
          )}
          {d && item.cve_id && <CopyButton text={ticketText(d)} />}
        </p>
      </div>
    </div>
  )
}

/** Affected, Fixed, KEV (or Exploited), Workaround, in that order: vendor, NVD and CISA data
 * first, the articles' own words only as a fallback, labeled "per article". Values share one
 * size; KEV "yes" is red. */
function Facts({
  todo,
  affected,
  kev,
  exploited,
}: {
  todo: Todo | null
  affected: { text: string; perArticle: boolean } | null
  kev: "yes" | "no" | null
  exploited: boolean
}) {
  const fixed = todo && (todo.fixed.length > 0 || todo.fixedPerArticle)
  const workaround = todo && (todo.workaround || todo.workaroundUrl)
  if (!affected && !fixed && !kev && !exploited && !workaround) return null
  return (
    <section aria-label="Affected and fixed" className="max-w-[720px]">
      <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-[13px] leading-5">
        {affected && (
          <>
            <dt className="text-muted">Affected</dt>
            <dd className="min-w-0 text-fg-2">
              {affected.text}
              {affected.perArticle && <span className="ml-3 text-muted">per article</span>}
            </dd>
          </>
        )}
        {todo && todo.fixed.length > 0 && (
          <>
            <dt className="text-muted">Fixed</dt>
            <dd className="min-w-0">
              {todo.fixed.map((f, i) => (
                <span key={i} className="block">
                  {f.product && <span className="text-fg-2">{f.product} </span>}
                  <span className="font-mono text-[13px] text-fg">{f.versions.join(", ")}</span>
                  {i === 0 && todo.fixedUrl && (
                    <a href={todo.fixedUrl} {...EXTERNAL} className={cn(LINK, "ml-3 text-fg-2")}>
                      advisory <span aria-hidden className="text-[11px] text-critical-text">↗</span>
                    </a>
                  )}
                </span>
              ))}
            </dd>
          </>
        )}
        {todo && !todo.fixed.length && todo.fixedPerArticle && (
          <>
            <dt className="text-muted">Fixed</dt>
            <dd className="min-w-0">
              {todo.fixedBranches.length ? (
                todo.fixedBranches.map((b, i) => (
                  <span key={i} className="block">
                    <span className="font-mono text-[13px] text-fg">{b.version}</span>
                    <span className="ml-2 text-fg-2">{b.branch}</span>
                    {i === 0 && <span className="ml-3 text-muted">per article</span>}
                  </span>
                ))
              ) : (
                <>
                  <span className="font-mono text-[13px] text-fg">{todo.fixedPerArticle}</span>
                  <span className="ml-3 text-muted">per article</span>
                </>
              )}
            </dd>
          </>
        )}
        {kev === "yes" ? (
          <>
            <dt className="text-muted">KEV</dt>
            <dd className="min-w-0">
              <span className="text-critical-text">yes</span>
              {todo?.kevDue && (
                <span className="ml-3 text-muted">
                  due <time dateTime={todo.kevDue.toISOString().slice(0, 10)} className="font-mono text-fg">{kevDate(todo.kevDue)}</time>
                  <span className="ml-2">CISA deadline for federal agencies</span>
                </span>
              )}
            </dd>
          </>
        ) : exploited ? (
          <>
            <dt className="text-muted">Exploited</dt>
            <dd className="min-w-0 text-critical-text">yes</dd>
          </>
        ) : (
          kev === "no" && (
            <>
              <dt className="text-muted">KEV</dt>
              <dd className="min-w-0 text-muted">no</dd>
            </>
          )
        )}
        {todo && workaround && (
          <>
            <dt className="text-muted">Workaround</dt>
            <dd className="min-w-0 text-summary">
              {todo.workaround}
              {todo.workaroundUrl && (
                <a href={todo.workaroundUrl} {...EXTERNAL} className={cn(LINK, "text-fg-2", todo.workaround && "ml-3")}>
                  {todo.workaround ? "details" : "vendor mitigation"}{" "}
                  <span aria-hidden className="text-[11px] text-critical-text">↗</span>
                </a>
              )}
            </dd>
          </>
        )}
      </dl>
    </section>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Clipboard API blocked (plain http, older browsers): the textarea route still works.
      const area = document.createElement("textarea")
      area.value = text
      area.style.position = "fixed"
      area.style.opacity = "0"
      document.body.appendChild(area)
      area.select()
      document.execCommand("copy")
      area.remove()
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button type="button" onClick={copy} className={LINK} title="Copy headline, CVE, fix and links as plain text">
      <span aria-live="polite">{copied ? "Copied" : "Copy"}</span>
    </button>
  )
}

function VectorChips({ chips }: { chips: ReturnType<typeof parseVector> }) {
  return (
    <ul className="mt-2 flex flex-wrap gap-0.5" aria-label="CVSS vector">
      {chips.map((c) => (
        <li
          key={c.metric}
          className={cn(
            "min-w-[60px] py-[7px] pr-3 pl-2.5",
            IMPACT_METRICS.has(c.metric) && c.value === "H" ? "bg-chip-impact" : "bg-chip",
          )}
        >
          <span className="block font-mono text-xs leading-4 text-fg">
            {c.metric}:{c.value}
          </span>
          {c.label && <span className="block text-[11px] leading-[14px] text-muted">{c.label}</span>}
        </li>
      ))}
    </ul>
  )
}

function metricPairs(d: ItemDetail): [string, ReactNode][] {
  const cve = d.cve
  const pairs: [string, ReactNode][] = []
  if (cve?.impact_score != null) pairs.push(["Impact", cve.impact_score.toFixed(1)])
  if (cve?.exploitability_score != null) pairs.push(["Exploitability", cve.exploitability_score.toFixed(1)])
  const epss = cve?.epss ?? d.epss
  if (epss != null) pairs.push(["EPSS", epss.toFixed(2)])
  return pairs
}

function Metrics({ pairs }: { pairs: [string, ReactNode][] }) {
  return (
    <dl className="flex gap-8">
      {pairs.map(([label, value]) => (
        <div key={label}>
          <dt className="text-[13px] leading-4 text-muted">{label}</dt>
          <dd className="mt-px font-mono text-[20px] leading-6 text-fg">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export type KnownPatch = Exclude<PatchStatus, "unverified">

export const PATCH: Record<KnownPatch, { mark: string; text: string; tone: string }> = {
  patched: { mark: "●", text: "patched", tone: "text-fg" },
  no_fix: { mark: "○", text: "no fix", tone: "text-muted" },
  workaround: { mark: "○", text: "no fix · workaround", tone: "text-muted" },
}

function Patch({ status, url }: { status: KnownPatch; url: string | null }) {
  const p = PATCH[status]
  const linked = url && status !== "no_fix" ? url : null
  const body = (
    <>
      {p.mark} {p.text}
      {linked && (
        <span aria-hidden className="ml-1 text-[11px] text-critical-text">
          ↗
        </span>
      )}
    </>
  )
  const cls = cn("font-mono text-xs whitespace-nowrap", p.tone)
  return linked ? (
    <a href={linked} {...EXTERNAL} className={cn(cls, LINK)}>
      {body}
    </a>
  ) : (
    <span className={cls}>{body}</span>
  )
}
