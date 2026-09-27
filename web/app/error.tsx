"use client"

import Link from "next/link"

import { PageHeader } from "@/components/PageHeader"

// A page that could not render (usually the API not answering). Same header as every page, in
// the site's own type and colors, with a retry; the nav above still works.
export default function PageError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="flex-1 page-frame">
      <PageHeader title="Feed unreachable">
        This page could not load its data. The API may be restarting.{" "}
        <button
          type="button"
          onClick={reset}
          className="max-md:tap text-critical-text underline decoration-outline-medium underline-offset-4 outline-none hover:decoration-critical-text"
        >
          Try again
        </button>{" "}
        <span aria-hidden className="text-dim-text">
          ·
        </span>{" "}
        <Link href="/" className="max-md:tap text-fg underline decoration-outline-medium underline-offset-4 outline-none hover:decoration-fg">
          Home
        </Link>
      </PageHeader>
    </main>
  )
}
