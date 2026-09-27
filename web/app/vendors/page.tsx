import type { Metadata } from "next"
import { connection } from "next/server"

import { PageHeader } from "@/components/PageHeader"
import { SiteFooter } from "@/components/SiteFooter"
import { VendorList } from "@/components/VendorList"
import { getVendors } from "@/lib/api"

export const metadata: Metadata = { title: "Vendors" }

// Every vendor we tag, alphabetical, with rows in the last 7 days. Each opens the wire filtered
// to it and can be added to your stack (?stack=, no account).
export default async function Vendors() {
  await connection()
  const vendors = await getVendors("name").catch(() => null)

  return (
    <main className="flex-1 page-frame pb-24">
      <PageHeader title="Vendors">
        {vendors ? (
          <>
            <span className="text-fg">{vendors.length}</span> vendors · rows in the last 7 days
          </>
        ) : (
          "The API is unreachable right now."
        )}
      </PageHeader>

      {vendors && <VendorList vendors={vendors} />}
      <SiteFooter className="mt-16" />
    </main>
  )
}
