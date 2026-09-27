import type { Metadata } from "next"
import { connection } from "next/server"

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
    <main className="flex-1 px-4 pb-24 md:px-12">
      <header className="pt-6 md:pt-[33px]">
        <h1 className="text-[36px] leading-[44px] font-bold tracking-[-0.02em] text-fg">Vendors</h1>
        <p className="mt-[3px] text-[15px] leading-5 text-muted">
          {vendors ? (
            <>
              <span className="text-fg">{vendors.length}</span> vendors · rows in the last 7 days
            </>
          ) : (
            "The API is unreachable right now."
          )}
        </p>
      </header>

      {vendors && <VendorList vendors={vendors} />}
      <SiteFooter className="mt-16" />
    </main>
  )
}
