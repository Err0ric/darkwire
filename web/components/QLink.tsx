"use client"

import Link from "next/link"
import type { ComponentProps } from "react"

import { usePrefs } from "@/lib/prefs"

/** Internal link that carries ?stack= / ?services= / ?theme= like every other link, so server
 * components can use it. `params` are extra query params for this link. */
export function QLink({
  href,
  params,
  ...rest
}: Omit<ComponentProps<typeof Link>, "href"> & { href: string; params?: Record<string, string | undefined> }) {
  const { query } = usePrefs()
  return <Link href={`${href}${query(params)}`} {...rest} />
}
