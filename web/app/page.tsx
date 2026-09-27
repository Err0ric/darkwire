import { connection } from "next/server"

import { HomeBoard } from "@/components/home/HomeBoard"
import { getFeed, getServices, getStatus } from "@/lib/api"
import { parseStack } from "@/lib/stack"

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? ""

// Home is a landing page, not a feed: date and clock, one status line, what matters right now,
// the latest headline, and the way into the wire. /wire is the all-day screen.
export default async function Home({ searchParams }: PageProps<"/">) {
  await connection()
  const params = await searchParams
  const watched = parseStack(one(params.services))
  const [rightNow, latest, status, services] = await Promise.allSettled([
    getFeed({ pinned: true, limit: 5 }),
    getFeed({ limit: 10 }),
    getStatus(),
    getServices(watched.join(",") || undefined),
  ])
  const value = <T,>(r: PromiseSettledResult<T>, fallback: T) => (r.status === "fulfilled" ? r.value : fallback)
  return (
    <HomeBoard
      initial={{
        rightNow: value(rightNow, { items: [], total: 0 }).items,
        latest: value(latest, { items: [], total: 0 }).items,
        status: value(status, null),
        services: value(services, null),
        failed: rightNow.status === "rejected",
      }}
    />
  )
}
