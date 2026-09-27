import { Bar, Loading } from "@/components/Skeleton"

// Home while it renders: the landing block's shape (lockup, date line, Right now rows, ticker,
// OPEN WIRE) centered like the real page.
export default function HomeLoading() {
  return (
    <main className="flex min-h-[calc(100dvh/var(--zoom)-var(--nav-h))] flex-col page-frame">
      <Loading label="the board" />
      <div className="mx-auto my-auto flex w-full max-w-[880px] flex-col items-center py-[clamp(24px,5vh,72px)]" aria-hidden>
        <Bar className="h-[clamp(40px,3.2vw,64px)] w-[clamp(220px,17vw,340px)]" />
        <Bar className="mt-7 h-3 w-[300px]" />
        <div className="mt-[clamp(28px,4.4vh,56px)] w-full">
          <div className="border-b border-rule pb-2">
            <Bar className="h-3 w-40" />
          </div>
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="flex h-11 items-center gap-4 border-b border-hairline">
              <Bar className="h-3 w-24" />
              <Bar className="h-3 flex-1" />
              <Bar className="h-2.5 w-8" />
            </div>
          ))}
        </div>
        <Bar className="mt-[clamp(20px,3vh,36px)] h-3 w-[420px] max-w-full" />
        <Bar className="mt-[clamp(24px,3.6vh,48px)] h-10 w-[158px]" />
      </div>
    </main>
  )
}
