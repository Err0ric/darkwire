"use client"

import Link from "next/link"
import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "cn"

import type { CveRow, PatchStatus } from "@/lib/api"

type Key = "cve" | "vendor" | "product" | "cvss" | "epss" | "kev" | "patch" | "published"

const PATCH_LABEL: Record<PatchStatus, string> = {
  patched: "patched",
  no_fix: "no fix",
  workaround: "workaround",
  unverified: "unverified",
}

// Sort values; null always sorts last whichever way the column is ordered.
const VALUE: Record<Key, (r: CveRow) => string | number | null> = {
  cve: (r) => {
    const [, year, num] = r.id.split("-")
    return Number(year) * 1e8 + Number(num)
  },
  vendor: (r) => r.vendor?.name.toLowerCase() ?? null,
  product: (r) => r.product?.toLowerCase() ?? null,
  cvss: (r) => r.cvss,
  epss: (r) => r.epss,
  kev: (r) => (r.kev ? 1 : 0),
  patch: (r) => (r.patch_status ? ["patched", "workaround", "no_fix", "unverified"].indexOf(r.patch_status) : null),
  published: (r) => (r.published_at ? Date.parse(r.published_at) : null),
}

const COLUMNS: { key: Key; label: string; className?: string; numeric?: boolean }[] = [
  { key: "cve", label: "CVE" },
  { key: "vendor", label: "Vendor" },
  { key: "product", label: "Product" },
  { key: "cvss", label: "CVSS", numeric: true },
  { key: "epss", label: "EPSS", numeric: true },
  { key: "kev", label: "KEV" },
  { key: "patch", label: "Patch" },
  { key: "published", label: "Published", numeric: true },
]

// Text columns start ascending; numbers and dates start with the biggest / newest.
const FIRST_ORDER: Record<Key, "asc" | "desc"> = {
  cve: "desc", vendor: "asc", product: "asc", cvss: "desc", epss: "desc", kev: "desc", patch: "asc", published: "desc",
}

function Dash() {
  return <span className="text-dim">—</span>
}

export function CveTable({ rows }: { rows: CveRow[] }) {
  const [sort, setSort] = useState<{ key: Key; order: "asc" | "desc" }>({ key: "published", order: "desc" })

  const sorted = [...rows].sort((a, b) => {
    const va = VALUE[sort.key](a)
    const vb = VALUE[sort.key](b)
    if (va === null && vb === null) return 0
    if (va === null) return 1
    if (vb === null) return -1
    const cmp = va < vb ? -1 : va > vb ? 1 : 0
    return sort.order === "asc" ? cmp : -cmp
  })

  function by(key: Key) {
    setSort((s) => (s.key === key ? { key, order: s.order === "asc" ? "desc" : "asc" } : { key, order: FIRST_ORDER[key] }))
  }

  return (
    <div className="mt-8 overflow-x-auto md:mt-[32px]">
      <table className="w-full min-w-[860px] border-collapse text-left">
        <thead>
          <tr className="border-b border-rule">
            {COLUMNS.map((c) => (
              <th
                key={c.key}
                scope="col"
                aria-sort={sort.key === c.key ? (sort.order === "asc" ? "ascending" : "descending") : "none"}
                className="h-11 pr-6 align-middle text-[13px] font-medium whitespace-nowrap"
              >
                <button
                  type="button"
                  onClick={() => by(c.key)}
                  className={cn(
                    "inline-flex items-center gap-1.5 outline-none focus-visible:text-fg",
                    sort.key === c.key ? "text-fg" : "text-muted hover:text-fg-2",
                  )}
                >
                  {c.label}
                  <ChevronDown
                    aria-hidden
                    className={cn(
                      "size-3",
                      sort.key === c.key ? "text-critical" : "invisible",
                      sort.key === c.key && sort.order === "asc" && "rotate-180",
                    )}
                  />
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.id} className="border-b border-hairline">
              <td className="h-11 pr-6 font-mono text-xs whitespace-nowrap">
                <Link href={`/wire?q=${r.id}`} className="text-fg-2 outline-none hover:text-fg focus-visible:text-fg">
                  {r.id}
                </Link>
              </td>
              <td className="pr-6 text-sm text-fg-2">{r.vendor?.name ?? <Dash />}</td>
              <td className="max-w-[280px] truncate pr-6 text-sm text-muted">{r.product ?? <Dash />}</td>
              <td className={cn("pr-6 font-mono text-sm font-medium", r.cvss !== null && r.cvss >= 7 ? "text-fg" : "text-fg-2")}>
                {r.cvss !== null ? r.cvss.toFixed(1) : <Dash />}
              </td>
              <td className="pr-6 font-mono text-xs text-fg-2">{r.epss !== null ? r.epss.toFixed(3) : <Dash />}</td>
              <td className="pr-6 font-mono text-xs">{r.kev ? <span className="text-critical">KEV</span> : <Dash />}</td>
              <td className={cn("pr-6 font-mono text-xs whitespace-nowrap", r.patch_status === "patched" ? "text-fg-2" : "text-muted")}>
                {r.patch_status ? PATCH_LABEL[r.patch_status] : <Dash />}
              </td>
              <td className="font-mono text-xs whitespace-nowrap text-muted">
                {r.published_at ? new Date(r.published_at).toLocaleDateString([], { year: "numeric", month: "2-digit", day: "2-digit" }) : <Dash />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
