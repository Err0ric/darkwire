import { connection } from "next/server"

import { HomeBoard } from "@/components/home/HomeBoard"
import { getFeed, getStatus } from "@/lib/api"

// Home is a landing page, not a feed: date and clock, what matters right now, the latest
// headline, and the way into the wire. /wire is the all-day screen.
export default async function Home() {
  await connection()
  const [rightNow, latest, status] = await Promise.allSettled([
    getFeed({ pinned: true, limit: 3 }),
    getFeed({ limit: 10 }),
    getStatus(),
  ])
  const value = <T,>(r: PromiseSettledResult<T>, fallback: T) => (r.status === "fulfilled" ? r.value : fallback)
  return (
    <HomeBoard
      initial={{
        rightNow: value(rightNow, { items: [], total: 0 }).items,
        latest: value(latest, { items: [], total: 0 }).items,
        status: value(status, null),
        failed: rightNow.status === "rejected",
      }}
    />
  )
}
