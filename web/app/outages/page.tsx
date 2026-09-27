import type { Metadata } from "next"
import { connection } from "next/server"

import { OutagesBoard } from "@/components/OutagesBoard"
import { getServices } from "@/lib/api"

export const metadata: Metadata = { title: "Outages · darkwire" }

// Every service we watch, grouped, with the last 24 hours as a strip of hourly cells.
export default async function Outages() {
  await connection()
  const data = await getServices("all").catch(() => null)
  return <OutagesBoard initial={data} />
}
