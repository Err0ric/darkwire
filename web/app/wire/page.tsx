import { connection } from "next/server"

import { WireBoard } from "@/components/wire/WireBoard"
import { feedQuery, parseSeverity, stackCriticalQuery, TABS, type Filters, type WireData, type WireTab } from "@/lib/wire"
import { parseStack } from "@/lib/stack"
import { getElsewhere, getFeed, getKev, getServices, getStatus, getVendors } from "@/lib/api"

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? ""

export default async function Wire({ searchParams }: PageProps<"/wire">) {
  await connection()
  const params = await searchParams
  const tab = one(params.tab) as WireTab
  const stack = parseStack(one(params.stack))
  const watched = parseStack(one(params.services))
  const filters: Filters = {
    tab: TABS.some(([t]) => t === tab) || (tab === "stack" && stack.length > 0) ? tab : "all",
    vendor: one(params.vendor),
    q: one(params.q),
    severity: parseSeverity(one(params.severity)),
    window: one(params.window) === "24h" ? "24h" : "",
  }

  const [feed, status, vendors, elsewhere, kev, critical, services] = await Promise.allSettled([
    getFeed({ ...feedQuery(filters, stack), limit: 50 }),
    getStatus(),
    getVendors("active"),
    getElsewhere(5),
    getKev(7, 8),
    stack.length ? getFeed(stackCriticalQuery(stack)).then((p) => p.total) : Promise.resolve(null),
    getServices(watched.join(",") || undefined),
  ])
  const value = <T,>(r: PromiseSettledResult<T>, fallback: T) => (r.status === "fulfilled" ? r.value : fallback)

  const initial: WireData = {
    filters,
    feed: value(feed, { items: [], total: 0 }),
    status: value(status, null),
    vendors: value(vendors, []),
    elsewhere: value(elsewhere, []),
    kev: value(kev, []),
    services: value(services, null),
    error: feed.status === "rejected",
    stack,
    stackCritical: value(critical, null),
  }
  return <WireBoard initial={initial} />
}
