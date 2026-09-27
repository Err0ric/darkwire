import type { Metadata } from "next"
import { connection } from "next/server"

import { FeedRow } from "@/components/FeedRow"
import { getFeed, getItem, type FeedItem } from "@/lib/api"

export const metadata: Metadata = {
  title: "Row review · darkwire",
  robots: { index: false, follow: false },
}

// Review page for the row component: real rows from the API, one of each kind.
export default async function RowReview() {
  await connection()
  const { items } = await getFeed({ limit: 200 })

  const used = new Set<number>()
  const pick = (why: string, test: (i: FeedItem) => boolean) => {
    const item = items.find((i) => !used.has(i.id) && test(i))
    if (item) used.add(item.id)
    return item ? { why, item } : null
  }

  // Expanded: prefer a CVE row with MSRC detail, since that is the richest data we have.
  const cveRows = items.filter((i) => i.cve_id)
  const withDetail = await Promise.all(cveRows.slice(0, 10).map((i) => getItem(i.id)))
  const richest = withDetail.find((d) => d.msrc) ?? withDetail[0]
  if (richest) used.add(richest.id)

  const rows = [
    pick("multi-source", (i) => i.sources.length > 1),
    pick("breach", (i) => i.category === "breach"),
    richest ? { why: "expanded", item: richest, detail: richest } : null,
    pick("with CVE", (i) => Boolean(i.cve_id)),
    pick("no vendor", (i) => i.vendor === null),
    pick("vendor, no CVE", (i) => i.vendor !== null && !i.cve_id),
    pick("research", (i) => i.category === "research"),
  ].filter((r) => r !== null)

  return (
    <main className="flex-1 px-4 pb-24 md:px-12">
      <div className="max-w-[1060px]">
        <h1 className="mt-10 text-[13px] font-medium text-fg">Row review</h1>
        <p className="mt-1 text-xs text-muted">
          Live rows from {process.env.NEXT_PUBLIC_API_URL ?? "the local API"}: {rows.map((r) => r.why).join(" · ")}.
          Scores, vectors, EPSS and KEV come from NVD, FIRST and CISA; rows without a CVE stay unscored.
        </p>
        <div className="mt-6 border-t border-rule">
          {rows.map((r) => (
            <FeedRow
              key={r.item.id}
              item={r.item}
              detail={"detail" in r ? r.detail : undefined}
              defaultExpanded={r.why === "expanded"}
            />
          ))}
        </div>
      </div>
    </main>
  )
}
