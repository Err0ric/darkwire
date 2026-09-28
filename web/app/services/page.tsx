import type { Metadata } from "next"
import { connection } from "next/server"

import { ServicesBoard } from "@/components/ServicesBoard"
import { getServices } from "@/lib/api"

export const metadata: Metadata = { title: "Services" }

// Every third-party service we watch, grouped, with the last 24 hours as a strip of hourly
// cells and the last 7 days of incidents on demand.
export default async function Services({ searchParams }: PageProps<"/services">) {
  await connection()
  const { open } = await searchParams
  const data = await getServices("all").catch(() => null)
  // ?open=slug (the wire rail's links): that service starts expanded.
  return <ServicesBoard initial={data} open={typeof open === "string" ? open : null} />
}
