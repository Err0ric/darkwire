import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { connection } from "next/server"

import { FeedRow } from "@/components/FeedRow"
import { PageHeader } from "@/components/PageHeader"
import { QLink } from "@/components/QLink"
import { SiteFooter } from "@/components/SiteFooter"
import { getFeed, getVendors } from "@/lib/api"

// Everything tagged to one vendor over the board's 14 days, newest first, with the same row as
// the wire. The wire's vendor filter (/wire?vendor=) adds tabs, search and live updates.

async function load(slug: string) {
  const vendors = await getVendors("name")
  const vendor = vendors.find((v) => v.slug === slug)
  if (!vendor) notFound()
  const feed = await getFeed({ vendor: slug, limit: 100 })
  return { vendor, feed }
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { vendor } = await load((await params).slug).catch(() => ({ vendor: null }))
  return vendor ? { title: vendor.name } : {}
}

export default async function VendorPage({ params }: { params: Promise<{ slug: string }> }) {
  await connection()
  const { slug } = await params
  const { vendor, feed } = await load(slug)
  const cves = feed.items.filter((i) => i.cve_id).length
  const kev = feed.items.filter((i) => i.kev).length

  return (
    <main className="flex-1 page-frame pb-24">
      <div className="@container min-[1200px]:max-w-[1200px]">
        <PageHeader title={vendor.name}>
          <span className="text-fg">{feed.total}</span> {feed.total === 1 ? "row" : "rows"} in the last 14 days ·{" "}
          <span className="text-fg">{cves}</span> with a CVE · <span className="text-fg">{kev}</span> in KEV ·{" "}
          <span className="text-fg">{vendor.items_7d}</span> this week
        </PageHeader>
        <p className="mt-1 text-[13px] leading-5">
          <QLink
            href="/wire"
            params={{ vendor: vendor.slug }}
            className="text-fg-2 underline decoration-outline-medium underline-offset-4 outline-none hover:text-fg"
          >
            Open on the wire <span className="text-critical-text">→</span>
          </QLink>
        </p>

        <div className="mt-8 border-t border-rule">
          {feed.items.map((item) => (
            <FeedRow key={item.id} item={item} />
          ))}
          {feed.items.length === 0 && <p className="py-10 text-[15px] text-muted">Nothing tagged to {vendor.name} in the last 14 days.</p>}
        </div>
      </div>
      <SiteFooter className="mt-16" />
    </main>
  )
}
