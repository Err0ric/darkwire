import Link from "next/link"

import { PageHeader } from "@/components/PageHeader"

export default function NotFound() {
  return (
    <main className="flex-1 page-frame">
      <PageHeader title="Not found">
        Nothing at this address.{" "}
        <Link href="/wire" className="text-fg underline decoration-outline-medium underline-offset-4 outline-none hover:decoration-fg">
          Back to the wire <span className="text-critical-text">→</span>
        </Link>
      </PageHeader>
    </main>
  )
}
