import type { Metadata } from "next"
import { connection } from "next/server"

import { CveTable } from "@/components/CveTable"
import { SiteFooter } from "@/components/SiteFooter"
import { getCves, type CveRow } from "@/lib/api"

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

// Every CVE on the board, newest first; the table sorts client-side.
export default async function Cves() {
  await connection()
  const rows = await allCves().catch(() => null)

  return (
    <main className="flex-1 page-frame pb-24">
      <header className="pt-6 md:pt-[33px]">
        <h1 className="text-[36px] leading-[44px] font-bold tracking-[-0.02em] text-fg">CVEs</h1>
        <p className="mt-[3px] text-[15px] leading-5 text-muted">
          {rows ? (
            <>
              <span className="text-fg">{rows.length}</span> CVEs on the board · CVSS from NVD, EPSS from FIRST, KEV from
              CISA
            </>
          ) : (
            "The API is unreachable right now."
          )}
        </p>
      </header>
      {rows && <CveTable rows={rows} />}
      <SiteFooter className="mt-16" />
    </main>
  )
}
