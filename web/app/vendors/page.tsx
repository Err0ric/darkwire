import type { Metadata } from "next"
import Link from "next/link"
import { connection } from "next/server"
import { cn } from "cn"

import { VendorGlyph } from "@/components/VendorGlyph"
import { getVendors } from "@/lib/api"

export const metadata: Metadata = { title: "Vendors · darkwire" }

// Every vendor we tag, alphabetical, with rows in the last 7 days. Each opens the wire filtered to it.
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

      {vendors && (
        <ul className="mt-8 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-x-16 border-t border-rule md:mt-[32px]">
          {vendors.map((v) => (
            <li key={v.slug} className="border-b border-hairline">
              <Link
                href={`/wire?vendor=${v.slug}`}
                className={cn(
                  "group flex h-12 items-center gap-4 outline-none",
                  v.items_7d === 0 && "opacity-60",
                )}
              >
                <span className="flex size-5 shrink-0 items-center justify-center text-muted">
                  <VendorGlyph vendor={v} />
                </span>
                <span className="flex-1 truncate text-[15px] text-fg-2 group-hover:text-fg group-focus-visible:text-fg">
                  {v.name}
                </span>
                <span className={cn("font-mono text-xs", v.items_7d ? "text-fg-2" : "text-dim")}>{v.items_7d}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
