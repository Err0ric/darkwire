import type { Metadata } from "next"
import { connection } from "next/server"

import { CveTable } from "@/components/CveTable"
import { PageHeader } from "@/components/PageHeader"
import { SiteFooter } from "@/components/SiteFooter"
import { getCves, type CveRow } from "@/lib/api"
import { parseFilters } from "@/lib/cve-filters"

export const metadata: Metadata = { title: "CVEs" }

// The API serves at most 100 rows a request: read up to 500 in pages.
const PAGE = 100
const MAX_ROWS = 500

async function allCves(): Promise<CveRow[]> {
  const rows: CveRow[] = []
  for (let offset = 0; offset < MAX_ROWS; offset += PAGE) {
    const page = await getCves({ sort: "published", order: "desc", limit: PAGE, offset })
    rows.push(...page)
    if (page.length < PAGE) break
  }
  return rows
}

// Every CVE on the board; the table filters and sorts client-side.
export default async function Cves({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await connection()
  const [rows, params] = await Promise.all([allCves().catch(() => null), searchParams])

  return (
    <main className="flex-1 page-frame pb-24">
      <PageHeader title="CVEs">{rows ? undefined : "The API is unreachable right now."}</PageHeader>
      {rows && <CveTable rows={rows} initial={parseFilters(params)} />}
      <SiteFooter className="mt-16" />
    </main>
  )
}
