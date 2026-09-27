import { NextResponse, type NextRequest } from "next/server"

// Content-Security-Policy with a fresh nonce per request. Next.js reads the nonce from this
// header while rendering and puts it on its own scripts; the root layout puts it on the theme
// script. Every page already renders per request (connection()), so nonces cost nothing extra.

const API_ORIGIN = new URL(process.env.NEXT_PUBLIC_API_URL ?? "https://api.darkwire.tech").origin

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64")
  const dev = process.env.NODE_ENV === "development"
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    `connect-src 'self' ${API_ORIGIN}`,
    "img-src 'self' data:",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ")

  const requestHeaders = new Headers(request.headers)
  requestHeaders.set("x-nonce", nonce)
  requestHeaders.set("Content-Security-Policy", csp)
  const response = NextResponse.next({ request: { headers: requestHeaders } })
  response.headers.set("Content-Security-Policy", csp)
  return response
}

export const config = {
  matcher: [
    {
      // Pages only: not route handlers, build assets, or the static files in /public.
      source: "/((?!api|_next/static|_next/image|favicon.ico|icon.svg|apple-icon.png|icon-192.png|icon-512.png|manifest.webmanifest|og.gif|og.png|vendors/).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
}
