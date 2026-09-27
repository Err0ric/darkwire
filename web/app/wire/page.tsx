import { connection } from "next/server"

import { WireBoard } from "@/components/wire/WireBoard"
import { TABS, type Filters, type WireData } from "@/lib/wire"
import { getElsewhere, getFeed, getKev, getStatus, getVendors, type Tab } from "@/lib/api"

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? ""

export default async function Wire({ searchParams }: PageProps<"/wire">) {
  await connection()
  const params = await searchParams
  const tab = one(params.tab) as Tab
  const filters: Filters = {
    tab: TABS.some(([t]) => t === tab) ? tab : "all",
    vendor: one(params.vendor),
    q: one(params.q),
  }

  const [feed, status, vendors, elsewhere, kev] = await Promise.allSettled([
    getFeed({ tab: filters.tab, vendor: filters.vendor || undefined, q: filters.q || undefined, limit: 50 }),
    getStatus(),
    getVendors("active"),
    getElsewhere(5),
    getKev(7, 8),
  ])
  const value = <T,>(r: PromiseSettledResult<T>, fallback: T) => (r.status === "fulfilled" ? r.value : fallback)

  const initial: WireData = {
    filters,
    feed: value(feed, { items: [], total: 0 }),
    status: value(status, null),
    vendors: value(vendors, []),
    elsewhere: value(elsewhere, []),
    kev: value(kev, []),
    error: feed.status === "rejected",
  }
  return <WireBoard initial={initial} />
}
