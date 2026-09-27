import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { connection } from "next/server"

import { FeedRow } from "@/components/FeedRow"
import { QLink } from "@/components/QLink"
import { ApiError, getItem } from "@/lib/api"

async function load(id: string) {
  const n = Number(id)
  if (!Number.isInteger(n) || n <= 0) notFound()
  try {
    return await getItem(n)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound()
    throw e
  }
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const item = await load((await params).id).catch(() => null)
  return { title: item ? `${item.headline} · darkwire` : "darkwire" }
}

// Permalink: one row, already expanded.
export default async function Item({ params }: { params: Promise<{ id: string }> }) {
  await connection()
  const item = await load((await params).id)
  return (
    <main className="flex-1 px-4 pb-24 md:px-12">
      <div className="@container pt-6 min-[1200px]:max-w-[1200px] md:pt-[33px]">
        <QLink href="/wire" className="text-[13px] text-muted outline-none hover:text-fg-2 focus-visible:text-fg-2">
          ← The wire
        </QLink>
        <div className="mt-4 border-t border-rule">
          <FeedRow item={item} detail={item} defaultExpanded />
        </div>
      </div>
    </main>
  )
}
