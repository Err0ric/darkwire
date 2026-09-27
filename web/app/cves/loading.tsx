import { Bar, Loading, SkeletonHeader } from "@/components/Skeleton"

// /cves while it renders: header, the search and chip row, and table rows at the real 48px.
export default function CvesLoading() {
  return (
    <main className="flex-1 page-frame pb-24">
      <Loading label="CVEs" />
      <SkeletonHeader title="w-[110px]" counts="w-[460px]" />
      <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3 md:mt-8" aria-hidden>
        <Bar className="h-[30px] w-full md:w-[300px]" />
        <div className="flex gap-2">
          {[76, 62, 48, 70, 62].map((w, i) => (
            <Bar key={i} className="h-[30px]" style={{ width: w }} />
          ))}
        </div>
      </div>
      <div className="mt-5 border-b border-rule pb-4" aria-hidden>
        <Bar className="mt-4 h-3 w-[60%]" />
      </div>
      <div aria-hidden>
        {Array.from({ length: 14 }, (_, i) => (
          <div key={i} className="flex h-12 items-center gap-5 border-b border-hairline">
            <div className="flex w-[200px] shrink-0 flex-col gap-1.5">
              <Bar className="h-3 w-24" />
              <Bar className="h-2.5 w-32" />
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <Bar className="h-2.5 w-28" />
              <Bar className="h-2.5 w-[80%]" />
            </div>
            <Bar className="hidden h-3 w-24 shrink-0 md:block" />
          </div>
        ))}
      </div>
    </main>
  )
}
