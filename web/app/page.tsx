import { connection } from "next/server"

import { HomeBoard } from "@/components/home/HomeBoard"
import { getFeed, getStatus } from "@/lib/api"

// Home: status header, as many rows as fit (Critical/KEV of the last 48h pinned first),
// four tabs. Meant to be left open.
export default async function Home() {
  await connection()
  const [feed, pinned, status] = await Promise.allSettled([
    getFeed({ limit: 40 }),
    getFeed({ pinned: true, limit: 10 }),
    getStatus(),
  ])
  return (
    <HomeBoard
      initialItems={feed.status === "fulfilled" ? feed.value.items : []}
      initialPinned={pinned.status === "fulfilled" ? pinned.value.items : []}
      initialStatus={status.status === "fulfilled" ? status.value : null}
      initialFailed={feed.status === "rejected"}
    />
  )
}
