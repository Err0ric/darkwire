import { connection } from "next/server"

import { HomeBoard } from "@/components/home/HomeBoard"
import { getFeed, getStatus } from "@/lib/api"

// Home: status header, latest 8 rows, four tabs. Meant to be left open.
export default async function Home() {
  await connection()
  const [feed, status] = await Promise.allSettled([getFeed({ limit: 8 }), getStatus()])
  return (
    <HomeBoard
      initialItems={feed.status === "fulfilled" ? feed.value.items : []}
      initialStatus={status.status === "fulfilled" ? status.value : null}
      initialFailed={feed.status === "rejected"}
    />
  )
}
