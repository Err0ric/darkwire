import Link from "next/link"

export default function NotFound() {
  return (
    <main className="flex-1 page-frame">
      <p className="pt-6 text-[15px] leading-5 text-fg-2 md:pt-[39px]">
        Nothing at this address.{" "}
        <Link href="/wire" className="text-fg outline-none hover:underline focus-visible:underline">
          Back to the wire <span className="text-critical">→</span>
        </Link>
      </p>
    </main>
  )
}
