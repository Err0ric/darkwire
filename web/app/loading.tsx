import { Bar, Loading } from "@/components/Skeleton"

// Home while it renders: the landing block's shape (lockup, date line, activity trace and log
// line, ticker, OPEN WIRE) centered like the real page.
export default function HomeLoading() {
  return (
    <main className="flex min-h-[calc(100dvh/var(--zoom)-var(--nav-h))] flex-col page-frame">
      <Loading label="the board" />
      <div className="mx-auto my-auto flex w-full max-w-[880px] flex-col items-center py-[clamp(24px,5vh,72px)]" aria-hidden>
        <Bar className="h-[clamp(40px,3.2vw,64px)] w-[clamp(220px,17vw,340px)]" />
        <Bar className="mt-7 h-3 w-[300px]" />
        {/* The activity trace (60px + its label line) and the log line, as on the page. */}
        <div className="mt-[clamp(28px,4.4vh,56px)] flex w-full max-w-[760px] flex-col">
          <div className="flex h-[60px] items-end pb-2">
            <Bar className="h-px w-full" />
          </div>
          <div className="mt-1.5 flex h-4 justify-between">
            <Bar className="h-2.5 w-8" />
            <Bar className="h-2.5 w-36" />
            <Bar className="h-2.5 w-8" />
          </div>
          <Bar className="mt-3 h-[18px] w-[420px] max-w-full" />
        </div>
        <Bar className="mt-[clamp(20px,3vh,36px)] h-3 w-[420px] max-w-full" />
        <Bar className="mt-[clamp(24px,3.6vh,48px)] h-10 w-[158px]" />
      </div>
    </main>
  )
}
