import type { Metadata } from "next"
import { connection } from "next/server"

import { ServicesBoard } from "@/components/ServicesBoard"
import { getServices } from "@/lib/api"

export const metadata: Metadata = { title: "Services" }

// Every third-party service we watch, grouped, with the last 24 hours as a strip of hourly
// cells and the last 7 days of incidents on demand.
export default async function Services() {
  await connection()
  const data = await getServices("all").catch(() => null)
  return <ServicesBoard initial={data} />
}
