"use client"

import Link from "next/link"
import { Check, Plus } from "lucide-react"
import { cn } from "cn"

import { VendorGlyph } from "@/components/VendorGlyph"
import type { VendorOut } from "@/lib/api"
import { usePrefs } from "@/lib/prefs"

/** Vendors with 7-day counts; each links to its page (/vendor/[slug]) and can be added to your stack. */
export function VendorList({ vendors }: { vendors: VendorOut[] }) {
  const { stack, toggleVendor, query } = usePrefs()
  const names = vendors.filter((v) => stack.includes(v.slug)).map((v) => v.name)

  return (
    <>
      <p className="mt-2 min-h-5 text-[15px] leading-5 text-muted">
        {stack.length ? (
          <>
            Your stack: <span className="text-fg-2">{names.join(", ")}</span>{" "}
            <span aria-hidden className="mx-2 text-dim-text">·</span>
            <Link href={`/wire${query({ tab: "stack" })}`} className="text-fg outline-none hover:underline focus-visible:underline">
              View my stack on the wire <span className="text-critical-text">→</span>
            </Link>
          </>
        ) : (
          "Add vendors to your stack to get a My stack tab on the wire."
        )}
      </p>

      <ul className="mt-8 grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-x-16 border-t border-rule md:mt-[26px]">
        {vendors.map((v) => {
          const inStack = stack.includes(v.slug)
          return (
            <li key={v.slug} className="flex h-12 items-center gap-3 border-b border-hairline">
              <Link
                href={`/vendor/${v.slug}${query()}`}
                className="group flex min-w-0 flex-1 items-center gap-4 outline-none"
              >
                <span className={cn("flex size-5 shrink-0 items-center justify-center", inStack ? "text-fg" : v.items_7d === 0 ? "text-dim-text" : "text-muted")}>
                  <VendorGlyph vendor={v} />
                </span>
                {/* Quiet this week: the name in --muted (not faded, so it keeps 4.5:1). */}
                <span
                  className={cn(
                    "flex-1 truncate text-[15px] group-hover:text-fg group-focus-visible:text-fg",
                    v.items_7d === 0 && !inStack ? "text-muted" : "text-fg-2",
                  )}
                >
                  {v.name}
                </span>
                <span className={cn("font-mono text-xs", v.items_7d ? "text-fg-2" : "text-dim-text")}>{v.items_7d}</span>
              </Link>
              <button
                type="button"
                onClick={() => toggleVendor(v.slug)}
                aria-pressed={inStack}
                aria-label={`${inStack ? "Remove" : "Add"} ${v.name} ${inStack ? "from" : "to"} my stack`}
                title={inStack ? "In your stack" : "Add to my stack"}
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-control border outline-none focus-visible:outline-1 focus-visible:outline-fg-2",
                  inStack ? "border-fg-2 text-fg" : "border-transparent text-dim-text hover:border-rule hover:text-fg-2",
                )}
              >
                {inStack ? <Check className="size-3.5" /> : <Plus className="size-3.5" />}
              </button>
            </li>
          )
        })}
      </ul>
    </>
  )
}
