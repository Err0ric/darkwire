import type { Metadata } from "next"
import { connection } from "next/server"

import { CveTable } from "@/components/CveTable"
import { SiteFooter } from "@/components/SiteFooter"
import { getCves } from "@/lib/api"

export const metadata: Metadata = { title: "CVEs" }

// Every CVE on the board, newest first; the table sorts client-side.
export default async function Cves() {
  await connection()
  const rows = await getCves({ sort: "published", order: "desc", limit: 500 }).catch(() => null)

  return (
    <main className="flex-1 px-4 pb-24 md:px-12">
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
