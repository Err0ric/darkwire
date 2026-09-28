"use client"

import { Newspaper } from "lucide-react"

import type { ElsewhereItem } from "@/lib/api"
import { NewDot, type DotState } from "@/lib/dots"
import { age, useNow } from "@/lib/time"

// The wire's Elsewhere tab: every Elsewhere item of the last 7 days (policy, privacy, courts,
// ...) in the normal row style, without the CVE / score / bar / badge columns: a mark, the
// headline (two lines at most, linking to the article), and "source · topic" under it, the
// age on the right. Nothing to expand. New items get the new-row dot like the main feed.

const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const

export function ElsewhereList({
  items,
  dots,
  onSeen,
}: {
  items: ElsewhereItem[]
  dots: ReadonlyMap<number, DotState>
  onSeen: (id: number) => void
}) {
  const now = useNow()
  if (!items.length) return <p className="py-10 text-[15px] text-muted">Nothing here in the last 7 days.</p>
  return (
    <div className="[&>article:last-child]:border-b-0">
      {items.map((e) => {
        const dot = dots.get(e.id)
        return (
          <article key={e.id} id={`elsewhere-${e.id}`} className="border-b border-rule hover:bg-row-hover">
            <div className="flex min-h-14 items-start py-[15px] md:items-center">
              <span
                aria-hidden
                className="mt-0.5 mr-3 flex size-5 shrink-0 items-center justify-start text-muted md:mt-0 md:mr-5"
              >
                <Newspaper className="size-4" strokeWidth={1.75} />
              </span>
              <div className="relative min-w-0 flex-1 md:mr-[22px]">
                {dot && <NewDot state={dot} className="top-[7px] -left-[9px] md:-left-[13px]" />}
                <a
                  href={e.url}
                  {...EXTERNAL}
                  onClick={() => onSeen(e.id)}
                  className="max-md:tap line-clamp-2 max-w-[72ch] text-[15px] leading-[1.35] font-medium tracking-[-0.01em] text-fg outline-none focus-visible:underline"
                >
                  {e.headline}
                </a>
                <p className="mt-1 flex items-baseline font-mono text-xs leading-4 whitespace-nowrap text-muted">
                  <span className="min-w-0 truncate">
                    <span className="text-fg-2">{e.source}</span>
                    {e.topic && (
                      <>
                        <span aria-hidden className="mx-1.5 text-dim-text">
                          ·
                        </span>
                        <span className="font-mono text-[11px] text-dim-text">{e.topic}</span>
                      </>
                    )}
                  </span>
                  <span className="ml-auto shrink-0 pl-3 font-mono text-xs md:hidden">
                    {e.published_at && now !== null ? age(e.published_at, now) : ""}
                  </span>
                </p>
              </div>
              <time
                dateTime={e.published_at ?? undefined}
                className="hidden w-[51px] shrink-0 text-right font-mono text-xs text-muted md:block"
              >
                {e.published_at && now !== null ? age(e.published_at, now) : ""}
              </time>
            </div>
          </article>
        )
      })}
    </div>
  )
}
