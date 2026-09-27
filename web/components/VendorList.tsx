"use client";

import Link from "next/link";
import { Fragment } from "react";
import { Check, Plus } from "lucide-react";
import { cn } from "cn";

import { VendorGlyph } from "@/components/VendorGlyph";
import type { VendorOut } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";

/** Vendors by rows this week (most active first), each linking to its page (/vendor/[slug]) and
 * addable to your stack. */
export function VendorList({ vendors }: { vendors: VendorOut[] }) {
  const { stack, toggleVendor, query } = usePrefs();
  const names = vendors
    .filter((v) => stack.includes(v.slug))
    .map((v) => v.name);
  // Most active first, then alphabetical; the quiet ones (0 this week) last, under a rule.
  const sorted = [...vendors].sort(
    (a, b) => b.items_7d - a.items_7d || a.name.localeCompare(b.name),
  );

  return (
    <>
      <p className="mt-2 min-h-5 text-[15px] leading-5 text-muted">
        {stack.length ? (
          <>
            Your stack: <span className="text-fg-2">{names.join(", ")}</span>{" "}
            <span aria-hidden className="mx-2 text-dim-text">
              ·
            </span>
            <Link
              href={`/wire${query({ tab: "stack" })}`}
              className="max-md:tap text-fg outline-none hover:underline focus-visible:underline"
            >
              View my stack on the wire{" "}
              <span className="text-critical-text">→</span>
            </Link>
          </>
        ) : (
          "Add vendors to your stack to get a My stack tab on the wire."
        )}
      </p>

      <ul className="mt-8 grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-x-16 border-t border-rule md:mt-[26px]">
        {sorted.map((v, i) => {
          const inStack = stack.includes(v.slug);
          const firstQuiet =
            v.items_7d === 0 && (i === 0 || sorted[i - 1].items_7d > 0);
          return (
            <Fragment key={v.slug}>
              {firstQuiet && (
                // A thin rule and a small label above the vendors with no rows this week.
                <li
                  aria-hidden
                  className="col-span-full mt-8 border-t border-rule pt-3 pb-1 text-[12px] leading-4 text-muted"
                >
                  Quiet this week
                </li>
              )}
              <li className="flex h-12 items-center gap-3 border-b border-hairline hover:bg-surface">
                <Link
                  href={`/vendor/${v.slug}${query()}`}
                  className="max-md:tap group flex min-w-0 flex-1 items-center gap-4 outline-none"
                >
                  <span
                    className={cn(
                      "flex size-5 shrink-0 items-center justify-center",
                      inStack
                        ? "text-fg"
                        : v.items_7d === 0
                          ? "text-dim-text"
                          : "text-muted",
                    )}
                  >
                    <VendorGlyph vendor={v} />
                  </span>
                  {/* Quiet this week: the name in --dim-text (not faded, so it keeps 4.5:1). */}
                  <span
                    className={cn(
                      "flex-1 truncate text-[15px] group-hover:text-fg group-focus-visible:text-fg",
                      v.items_7d === 0 && !inStack
                        ? "text-dim-text"
                        : "text-fg-2",
                    )}
                  >
                    {v.name}
                  </span>
                  <span
                    className={cn(
                      "font-mono text-xs",
                      v.items_7d ? "text-fg-2" : "text-dim-text",
                    )}
                  >
                    {v.items_7d}
                  </span>
                </Link>
                <button
                  type="button"
                  onClick={() => toggleVendor(v.slug)}
                  aria-pressed={inStack}
                  aria-label={`${inStack ? "Remove" : "Add"} ${v.name} ${inStack ? "from" : "to"} my stack`}
                  title={inStack ? "In your stack" : "Add to my stack"}
                  className={cn(
                    "max-md:tap",
                    "flex size-6 shrink-0 items-center justify-center rounded-control border outline-none focus-visible:outline-1 focus-visible:outline-fg-2",
                    inStack
                      ? "border-fg-2 text-fg"
                      : "border-transparent text-dim-text hover:border-rule hover:text-fg-2",
                  )}
                >
                  {inStack ? (
                    <Check className="size-3.5" />
                  ) : (
                    <Plus className="size-3.5" />
                  )}
                </button>
              </li>
            </Fragment>
          );
        })}
      </ul>
    </>
  );
}
