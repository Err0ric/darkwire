// "What to do" for a CVE row and the plain-text block the Copy button puts on the clipboard.
// Every field is optional: callers render a line only when it has a value.

import type { ItemDetail } from "@/lib/api"

export interface FixLine {
  product: string | null // null when MSRC names no product
  versions: string[]
}

export interface Todo {
  fixed: FixLine[]
  fixedUrl: string | null
  /** The articles' fixed version, only when vendor, NVD and MSRC data have none. */
  fixedPerArticle: string | null
  /** The articles' fix per release branch ("7.24 stable", "7.23.5 long-term"), one line each. */
  fixedBranches: { version: string; branch: string }[]
  workaround: string | null
  workaroundUrl: string | null
  kevDue: Date | null
}

/** Fixed versions: NVD / CNA ranges, else MSRC's KBs. Never from the summary model. */
function fixes(d: ItemDetail): FixLine[] {
  const nvd = d.cve?.fixed_versions ?? []
  if (nvd.length) {
    const byProduct = new Map<string, string[]>()
    for (const f of nvd) byProduct.set(f.product, [...(byProduct.get(f.product) ?? []), f.version])
    return [...byProduct].map(([product, versions]) => ({ product, versions }))
  }
  const kbs = d.msrc?.kbs ?? []
  if (kbs.length) return [{ product: d.msrc?.product ?? null, versions: kbs.map((k) => `KB${k.kb.replace(/^KB/i, "")}`) }]
  return []
}

export function whatToDo(d: ItemDetail): Todo | null {
  const cve = d.cve
  const fixed = fixes(d)
  const todo: Todo = {
    fixed,
    fixedUrl: fixed.length ? (d.patch_url ?? d.msrc?.url ?? null) : null,
    fixedPerArticle: fixed.length ? null : (d.article_facts?.fixed ?? null),
    fixedBranches: fixed.length ? [] : (d.article_facts?.fixed_branches ?? []),
    workaround: d.action?.workaround ?? null,
    workaroundUrl: cve?.workaround_url ?? null,
    kevDue: cve?.kev && cve.kev_due_date ? new Date(cve.kev_due_date) : null,
  }
  return todo.fixed.length || todo.fixedPerArticle || todo.workaround || todo.workaroundUrl || todo.kevDue ? todo : null
}

/** KEV dates are calendar dates stored at midnight UTC; show them in UTC so they never shift a day. */
export const kevDate = (d: Date) => d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" })

const SEVERITY_WORD: Record<string, string> = { critical: "Critical", high: "High", medium: "Medium", low: "Low" }

/** Paste-ready for Teams or a ticket. Plain text, one fact per line, nothing empty. */
export function ticketText(d: ItemDetail): string {
  const lines: string[] = [d.headline]
  if (d.cve_id) {
    const facts = [d.cve_id]
    if (d.cvss !== null) facts.push(`CVSS ${d.cvss.toFixed(1)}${d.severity && SEVERITY_WORD[d.severity] ? ` ${SEVERITY_WORD[d.severity]}` : ""}`)
    if (d.kev) facts.push("CISA KEV")
    lines.push(facts.join(" · "))
  }
  const affected = d.cve?.affected ?? d.msrc?.product
  if (affected) lines.push(`Affected: ${affected}`)
  else if (d.article_facts?.affected) lines.push(`Affected: ${d.article_facts.affected} (per article)`)
  const todo = d.cve_id ? whatToDo(d) : null
  if (todo?.fixed.length) {
    lines.push(`Fixed in: ${todo.fixed.map((f) => [f.product, f.versions.join(", ")].filter(Boolean).join(" ")).join("; ")}`)
  }
  if (todo?.fixedPerArticle) lines.push(`Fixed in: ${todo.fixedPerArticle} (per article)`)
  if (todo?.workaround) lines.push(`Workaround: ${todo.workaround}`)
  if (todo?.kevDue) lines.push(`KEV due date: ${todo.kevDue.toISOString().slice(0, 10)}`)
  lines.push("")
  lines.push(`Source: ${d.primary_url}`)
  const advisory = d.patch_url ?? d.msrc?.url
  if (advisory) lines.push(`Vendor advisory: ${advisory}`)
  if (todo?.workaroundUrl && todo.workaroundUrl !== advisory) lines.push(`Mitigation: ${todo.workaroundUrl}`)
  if (d.cve_id) lines.push(`NVD: https://nvd.nist.gov/vuln/detail/${d.cve_id}`)
  return lines.join("\n")
}
