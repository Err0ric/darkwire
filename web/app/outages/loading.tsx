import { Bar, Loading, SkeletonHeader } from "@/components/Skeleton"

// /outages while it renders: header, the Impacted now block and the four groups of name + strip.
export default function OutagesLoading() {
  return (
    <main className="flex-1 page-frame pb-16">
      <Loading label="outages" />
      <SkeletonHeader title="w-[170px]" counts="w-[300px]" />
      <div className="mt-8" aria-hidden>
        <div className="border-b border-rule pb-2.5">
          <Bar className="h-3 w-24" />
        </div>
        <div className="flex min-h-11 items-center border-b border-hairline">
          <Bar className="h-3 w-[50%]" />
        </div>
      </div>
      <div className="mt-10 grid gap-x-12 gap-y-10 min-[1200px]:grid-cols-2 min-[1600px]:grid-cols-4" aria-hidden>
        {Array.from({ length: 4 }, (_, g) => (
          <div key={g}>
            <div className="border-b border-rule pb-2.5">
              <Bar className="h-3 w-20" />
            </div>
            <div className="mt-7">
              {Array.from({ length: 5 }, (_, i) => (
                <div key={i} className="py-2">
                  <Bar className="h-3 w-28" />
                  <Bar className="mt-2.5 h-2 w-full" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </main>
  )
}
