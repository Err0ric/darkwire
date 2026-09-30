import { Bar, Loading, SkeletonFeedRows, SkeletonRail } from "@/components/Skeleton"

// The wire while it renders: header, tabs line and a screen of rows at the real row height,
// with the rails' columns in place so the feed does not change width when data arrives.
export default function WireLoading() {
  return (
    <main className="flex-1 page-frame pb-24">
      <Loading label="the wire" />
      <div className="min-[1024px]:flex min-[1024px]:items-start min-[1024px]:gap-10 min-[1600px]:gap-(--col-gap)">
        <aside className="mt-[103px] hidden w-(--left-rail-w) shrink-0 min-[1600px]:block">
          <SkeletonRail />
        </aside>
        <div className="min-w-0 max-w-(--feed-max) flex-1">
          {/* The one-line header: counts left, clock right. */}
          <div className="flex h-7 items-center justify-between pt-6 md:mt-[33px] md:pt-0" aria-hidden>
            <Bar className="h-3 w-[460px] max-w-[70%]" />
            <Bar className="hidden h-4 w-[200px] min-[1200px]:block" />
          </div>
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
        <aside className="mt-16 hidden shrink-0 min-[1024px]:mt-[103px] min-[1024px]:block min-[1024px]:w-[300px] min-[1600px]:w-(--rail-w)">
          <SkeletonRail />
        </aside>
      </div>
    </main>
  )
}
