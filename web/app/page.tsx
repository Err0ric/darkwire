import { connection } from "next/server"

import { HomeBoard } from "@/components/home/HomeBoard"
import { getActivity, getFeed, getStatus } from "@/lib/api"

// Home is a landing page, not a feed: date and clock, the board's activity over the last
// 24 hours and its latest event, the latest headline, and the way into the wire. /wire is the all-day screen.
export default async function Home() {
  await connection()
  const [activity, latest, status] = await Promise.allSettled([
    getActivity(),
    getFeed({ limit: 10 }),
    getStatus(),
  ])
  const value = <T,>(r: PromiseSettledResult<T>, fallback: T) => (r.status === "fulfilled" ? r.value : fallback)
  return (
    <HomeBoard
      initial={{
        activity: value(activity, null),
        latest: value(latest, { items: [], total: 0 }).items,
        status: value(status, null),
        failed: latest.status === "rejected",
      }}
    />
  )
}
