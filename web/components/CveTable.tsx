"use client"

import Link from "next/link"
import { Fragment, useMemo, useState, type MouseEvent } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "cn"

import { BAR_FILL, Expanded, PATCH, type Detail } from "@/components/FeedRow"
import { PAGE_COUNTS } from "@/components/PageHeader"
import { Input } from "@/components/ui/input"
import { getItem, type CveRow } from "@/lib/api"
import type { CveFilters, Fix, Sev } from "@/lib/cve-filters"
import { useNow } from "@/lib/time"

// /cves: every CVE on the board. Search plus combinable filter chips, both mirrored in the URL
// (?kev=1&sev=critical,high&fix=none&q=citrix). Default order: KEV first, then CVSS, then newest;
// a header click sorts by that column (the default order breaks ties). A row click expands the
// wire's expanded row in place; the CVE ID is the /cve/[id] permalink.

type Key = "cve" | "vendor" | "cvss" | "epss" | "kev" | "patch" | "published"
const SEV_CHIPS: [Sev, string][] = [
  ["critical", "Critical"],
  ["high", "High"],
]
const FIX_CHIPS: [Fix, string][] = [
  ["has", "Has fix"],
  ["none", "No fix"],
]

function syncUrl(f: CveFilters) {
  const url = new URL(window.location.href)
  const set = (k: string, v: string) => (v ? url.searchParams.set(k, v) : url.searchParams.delete(k))
  set("kev", f.kev ? "1" : "")
  set("sev", f.sev.join(","))
  set("fix", f.fix.join(","))
  set("q", f.q.trim())
  window.history.replaceState(null, "", url.pathname + url.search.replace(/%2C/gi, ",") + url.hash)
}

function matches(r: CveRow, f: CveFilters): boolean {
  if (f.kev && !r.kev) return false
  if (f.sev.length && !(r.severity && (f.sev as string[]).includes(r.severity))) return false
  if (f.fix.length) {
    const has = r.patch_status === "patched"
    const none = r.patch_status === "no_fix" || r.patch_status === "workaround"
    if (!((f.fix.includes("has") && has) || (f.fix.includes("none") && none))) return false
  }
  const q = f.q.trim().toLowerCase()
  if (q) {
    const hay = [r.id, r.vendor_name, r.product, r.description].filter(Boolean).join(" ").toLowerCase()
    if (!q.split(/\s+/).every((w) => hay.includes(w))) return false
  }
  return true
}

const PATCH_RANK = { patched: 0, workaround: 1, no_fix: 2, unverified: 3 } as const

// Sort values; null always sorts last whichever way the column is ordered.
const VALUE: Record<Key, (r: CveRow) => string | number | null> = {
  cve: (r) => {
    const [, year, num] = r.id.split("-")
    return Number(year) * 1e8 + Number(num)
  },
  vendor: (r) => [r.vendor_name, r.product].filter(Boolean).join(" ").toLowerCase() || null,
  cvss: (r) => r.cvss,
  epss: (r) => r.epss,
  kev: (r) => (r.kev ? 1 : 0),
  patch: (r) => (r.patch_status ? PATCH_RANK[r.patch_status] : null),
  published: (r) => (r.published_at ? Date.parse(r.published_at) : null),
}

// Text columns start ascending; numbers and dates start with the biggest / newest.
const FIRST_ORDER: Record<Key, "asc" | "desc"> = {
  cve: "desc", vendor: "asc", cvss: "desc", epss: "desc", kev: "desc", patch: "asc", published: "desc",
}

/** KEV first, then CVSS descending, then newest. */
function byDefault(a: CveRow, b: CveRow): number {
  return (
    Number(b.kev) - Number(a.kev) ||
    (b.cvss ?? -1) - (a.cvss ?? -1) ||
    (VALUE.published(b) as number | null ?? 0) - (VALUE.published(a) as number | null ?? 0)
  )
}

const COLUMNS: { key: Key; label: string; width?: string }[] = [
  { key: "vendor", label: "Vendor", width: "w-[220px]" },
  { key: "cve", label: "CVE / Description" },
  { key: "cvss", label: "CVSS", width: "w-[124px]" },
  { key: "epss", label: "EPSS", width: "w-[72px]" },
  { key: "kev", label: "KEV", width: "w-[52px]" },
  { key: "patch", label: "Patch", width: "w-[180px]" },
  { key: "published", label: "Published", width: "w-[96px]" },
]

// Cells: the first and last get the gutter, so an expanded band runs 16px / 24px past the text.
const CELL = "pr-5 align-middle first:pl-4 last:pr-4 md:first:pl-6 md:last:pr-6"

export function CveTable({ rows, initial }: { rows: CveRow[]; initial: CveFilters }) {
  const [filters, setFilters] = useState(initial)
  const [sort, setSort] = useState<{ key: Key; order: "asc" | "desc" } | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<number, Detail>>({})

  const shown = useMemo(() => {
    const kept = rows.filter((r) => matches(r, filters))
    return kept.sort((a, b) => {
      if (!sort) return byDefault(a, b)
      const va = VALUE[sort.key](a)
      const vb = VALUE[sort.key](b)
      if (va === null && vb === null) return byDefault(a, b)
      if (va === null) return 1
      if (vb === null) return -1
      const cmp = va < vb ? -1 : va > vb ? 1 : 0
      return (sort.order === "asc" ? cmp : -cmp) || byDefault(a, b)
    })
  }, [rows, filters, sort])

  const filtered = filters.kev || filters.sev.length > 0 || filters.fix.length > 0 || filters.q.trim() !== ""

  function apply(next: Partial<CveFilters>) {
    const f = { ...filters, ...next }
    setFilters(f)
    syncUrl(f)
  }

  function by(key: Key) {
    setSort((s) => (s?.key === key ? { key, order: s.order === "asc" ? "desc" : "asc" } : { key, order: FIRST_ORDER[key] }))
  }

  function toggle(r: CveRow) {
    if (r.item_id === null) return
    const id = r.item_id
    setOpen((o) => (o === r.id ? null : r.id))
    const d = details[id]
    if (!d || d.state === "error") {
      setDetails((m) => ({ ...m, [id]: { state: "loading" } }))
      getItem(id)
        .then((item) => setDetails((m) => ({ ...m, [id]: { state: "ready", item } })))
        .catch(() => setDetails((m) => ({ ...m, [id]: { state: "error" } })))
    }
  }

  return (
    <>
      <p className={PAGE_COUNTS}>
        {filtered ? (
          <>
            <span className="text-fg">{shown.length}</span> of {rows.length}
          </>
        ) : (
          <span className="text-fg">{rows.length}</span>
        )}{" "}
        CVEs on the board · CVSS from NVD, EPSS from FIRST, KEV from CISA
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3 md:mt-8">
        <Input
          type="search"
          value={filters.q}
          onChange={(e) => apply({ q: e.target.value })}
          onKeyDown={(e) => e.key === "Escape" && apply({ q: "" })}
          placeholder="CVE ID, vendor, product, description"
          aria-label="Search CVEs by ID, vendor, product or description"
          className="h-[30px] w-full md:w-[300px]"
        />
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filters">
          <Chip on={filters.kev} onClick={() => apply({ kev: !filters.kev })}>
            KEV only
          </Chip>
          {SEV_CHIPS.map(([v, label]) => (
            <Chip key={v} on={filters.sev.includes(v)} onClick={() => apply({ sev: flip(filters.sev, v) })}>
              {label}
            </Chip>
          ))}
          {FIX_CHIPS.map(([v, label]) => (
            <Chip key={v} on={filters.fix.includes(v)} onClick={() => apply({ fix: flip(filters.fix, v) })}>
              {label}
            </Chip>
          ))}
        </div>
      </div>

      <div className="-mx-4 mt-5 overflow-x-auto md:-mx-6">
        <table className="w-full min-w-[1060px] table-fixed border-collapse text-left">
          <thead>
            <tr className="border-b border-rule">
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={sort?.key === c.key ? (sort.order === "asc" ? "ascending" : "descending") : "none"}
                  className={cn(CELL, "h-11 text-[13px] font-medium whitespace-nowrap", c.width)}
                >
                  <button
                    type="button"
                    onClick={() => by(c.key)}
                    className={cn(
                      "inline-flex items-center gap-1.5 outline-none focus-visible:text-fg",
                      sort?.key === c.key ? "text-fg" : "text-muted hover:text-fg-2",
                    )}
                  >
                    {c.label}
                    <ChevronDown
                      aria-hidden
                      className={cn(
                        "size-3",
                        sort?.key === c.key ? "text-critical-text" : "invisible",
                        sort?.key === c.key && sort.order === "asc" && "rotate-180",
                      )}
                    />
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => {
              const expanded = open === r.id
              const detail = r.item_id !== null ? details[r.item_id] : undefined
              return (
                <Fragment key={r.id}>
                  <Row row={r} expanded={expanded} onToggle={() => toggle(r)} />
                  {expanded && (
                    <tr className="border-b border-hairline bg-surface">
                      <td colSpan={COLUMNS.length} className="px-4 pt-1 pb-[22px] md:px-6" aria-busy={detail?.state === "loading"}>
                        {detail?.state === "ready" && <Expanded item={detail.item} detail={detail} />}
                        {detail?.state === "error" && <p className="text-[13px] text-muted">Could not load this row. Try again.</p>}
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      {shown.length === 0 && <p className="mt-6 text-[15px] text-muted">No CVEs match.</p>}
    </>
  )
}

function flip<T>(list: T[], v: T): T[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v]
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        "h-[30px] rounded-control border px-3 text-[13px] outline-none focus-visible:border-muted",
        on ? "border-muted bg-hairline text-fg" : "border-rule text-muted hover:text-fg-2",
      )}
    >
      {children}
    </button>
  )
}

function Row({ row: r, expanded, onToggle }: { row: CveRow; expanded: boolean; onToggle: () => void }) {
  const now = useNow()
  const clickable = r.item_id !== null

  function onClick(e: MouseEvent) {
    if ((e.target as HTMLElement).closest("a, button")) return
    onToggle()
  }

  return (
    <tr
      onClick={clickable ? onClick : undefined}
      className={cn("h-12 text-[13px] hover:bg-surface", clickable && "cursor-pointer", expanded ? "bg-surface" : "border-b border-hairline")}
    >
      <td className={cn(CELL, "py-2")} title={[r.vendor_name, r.product].filter(Boolean).join(" · ") || undefined}>
        <span className="block truncate leading-4 text-fg">{r.vendor_name}</span>
        <span className="mt-0.5 block truncate text-xs leading-4 text-muted">{r.product}</span>
      </td>
      <td className={cn(CELL, "py-2")}>
        <Link
          href={`/cve/${r.id}`}
          className="block font-mono text-xs leading-4 text-fg-2 outline-none hover:text-fg focus-visible:text-fg"
        >
          {r.id}
        </Link>
        <span className="mt-0.5 block truncate text-[13px] leading-4 text-fg-2" title={r.description ?? undefined}>
          {r.description}
        </span>
      </td>
      <td className={CELL}>
        {r.cvss !== null && (
          <span className="flex items-center gap-3">
            <span className={cn("w-9 font-mono text-[15px] font-medium", r.cvss >= 7 ? "text-fg" : "text-fg-2")}>
              {r.cvss.toFixed(1)}
            </span>
            <CvssBar row={r} />
          </span>
        )}
      </td>
      <td className={cn(CELL, "font-mono text-xs")}>
        {r.epss !== null && (
          <span className={r.epss < 0.01 ? "text-dim-text" : r.epss > 0.1 ? "text-fg" : "text-fg-2"}>
            {(r.epss * 100).toFixed(1)}%
          </span>
        )}
      </td>
      <td className={cn(CELL, "font-mono text-xs")}>{r.kev && <span className="text-critical-text">KEV</span>}</td>
      <td className={cn(CELL, "font-mono text-xs whitespace-nowrap")}>
        <PatchCell status={r.patch_status} />
      </td>
      <td className={cn(CELL, "font-mono text-xs whitespace-nowrap text-muted")}>
        {r.published_at && now !== null && <time dateTime={r.published_at}>{shortDate(r.published_at, now)}</time>}
      </td>
    </tr>
  )
}

function CvssBar({ row: r }: { row: CveRow }) {
  if (r.cvss === null) return null
  const filled = Math.round(r.cvss)
  const fill = (r.severity && BAR_FILL[r.severity]) || "bg-medium"
  return (
    <span aria-hidden className="flex shrink-0 gap-0.5">
      {Array.from({ length: 10 }, (_, i) => (
        <span key={i} className={cn("h-2.5 w-[5px]", i < filled ? fill : "bg-rule")} />
      ))}
    </span>
  )
}

/** As in the expanded row: ● patched, ○ no fix, ○ no fix · workaround; plus ○ unverified. */
function PatchCell({ status }: { status: CveRow["patch_status"] }) {
  if (!status) return null
  if (status === "unverified") return <span className="text-dim-text">○ unverified</span>
  const p = PATCH[status]
  return (
    <span className={p.tone}>
      {p.mark} {p.text}
    </span>
  )
}

/** "Sep 24" in the viewer's zone; with the year when it is not this year. */
function shortDate(iso: string, now: number): string {
  const d = new Date(iso)
  const sameYear = d.getFullYear() === new Date(now).getFullYear()
  return d.toLocaleDateString([], { month: "short", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) })
}
