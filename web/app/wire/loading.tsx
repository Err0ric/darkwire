import { Bar, Loading, SkeletonFeedRows, SkeletonHeader, SkeletonRail } from "@/components/Skeleton"

// The wire while it renders: header, tabs line and a screen of rows at the real row height,
// with the rails' columns in place so the feed does not change width when data arrives.
export default function WireLoading() {
  return (
    <main className="flex-1 page-frame pb-24">
      <Loading label="the wire" />
      <div className="min-[1200px]:flex min-[1200px]:items-start min-[1200px]:gap-12 min-[2200px]:gap-(--col-gap)">
        <aside className="mt-[133px] hidden w-(--rail-w) shrink-0 min-[2200px]:block">
          <SkeletonRail />
        </aside>
        <div className="min-w-0 flex-1 min-[2200px]:w-(--feed-w) min-[2200px]:flex-none">
          <SkeletonHeader title="w-[200px]" counts="w-[460px]" />
          <div className="mt-8 flex h-[46px] items-start gap-6 border-b border-rule md:mt-[32px]" aria-hidden>
            {[18, 96, 64, 89, 71].map((w, i) => (
              <Bar key={i} className="mt-1 h-3" style={{ width: w }} />
            ))}
          </div>
          <div className="flex h-9 items-center" aria-hidden>
            <Bar className="h-3 w-40" />
          </div>
          <SkeletonFeedRows count={14} />
        </div>
        <aside className="mt-16 hidden shrink-0 min-[1200px]:mt-[133px] min-[1200px]:block min-[1200px]:w-[340px] min-[2200px]:w-(--rail-w)">
          <SkeletonRail />
        </aside>
      </div>
    </main>
  )
}
