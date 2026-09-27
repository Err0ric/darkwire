import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { connection } from "next/server"

import { FeedRow } from "@/components/FeedRow"
import { QLink } from "@/components/QLink"
import { ApiError, getCves, getItem } from "@/lib/api"

const CVE_ID = /^CVE-\d{4}-\d{4,}$/

/** The row that carries this CVE (the most recent one, as on /cves). */
async function load(raw: string) {
  const id = decodeURIComponent(raw).toUpperCase()
  if (!CVE_ID.test(id)) notFound()
  const match = (await getCves({ q: id, limit: 5 })).find((r) => r.id === id)
  if (!match?.item_id) notFound()
  try {
    return await getItem(match.item_id)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound()
    throw e
  }
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params
  const item = await load(id).catch(() => null)
  return item ? { title: `${decodeURIComponent(id).toUpperCase()}: ${item.headline}` } : {}
}

// Permalink for a CVE: its row, already expanded.
export default async function CvePage({ params }: { params: Promise<{ id: string }> }) {
  await connection()
  const item = await load((await params).id)
  return (
    <main className="flex-1 page-frame pb-24">
      <div className="@container pt-6 min-[1200px]:max-w-[1200px] md:pt-[33px]">
        <QLink href="/cves" className="text-[13px] text-muted outline-none hover:text-fg-2 focus-visible:text-fg-2">
          ← CVEs
        </QLink>
        <div className="mt-4 border-t border-rule">
          <FeedRow item={item} detail={item} defaultExpanded />
        </div>
      </div>
    </main>
  )
}
