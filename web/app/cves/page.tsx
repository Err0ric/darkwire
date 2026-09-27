import type { Metadata } from "next"
import { connection } from "next/server"

import { CveTable } from "@/components/CveTable"
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
      <header className="pt-6 md:pt-[33px]">
        <h1 className="text-[36px] leading-[44px] font-bold tracking-[-0.02em] text-fg">CVEs</h1>
        {!rows && <p className="mt-[3px] text-[15px] leading-5 text-muted">The API is unreachable right now.</p>}
      </header>
      {rows && <CveTable rows={rows} initial={parseFilters(params)} />}
      <SiteFooter className="mt-16" />
    </main>
  )
}
