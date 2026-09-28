import type { Metadata, Viewport } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import { headers } from "next/headers"

import { AutoUpdate } from "@/components/AutoUpdate"
import { Kiosk } from "@/components/Kiosk"
import { Nav } from "@/components/nav"
import { PrefsProvider } from "@/lib/prefs"
import OG from "@/lib/og-images.json"
import { THEME_SCRIPT } from "@/lib/stack"

import "./globals.css"

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

const DESCRIPTION = "Security news and CVEs on one live board. No accounts. No ads. No bullshit."

// Link previews (Discord, Slack, X, iMessage, Teams). The images are static files made by
// scripts/make-og.py (npm run og) writes og.<hash>.gif (the typing lockup) and og.<hash>.png (the
// still, for X); lib/og-images.json has the current names, so each change is a new URL.
// Pages set only a title; the template adds " · darkwire" and everything else is inherited.
export const metadata: Metadata = {
  metadataBase: new URL("https://darkwire.tech"),
  title: { default: "darkwire", template: "%s · darkwire" },
  description: DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: "darkwire.tech",
    url: "/",
    title: "darkwire",
    description: DESCRIPTION,
    images: [{ url: OG.gif, width: 1200, height: 630, type: "image/gif", alt: "darkwire" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "darkwire",
    description: DESCRIPTION,
    images: [OG.png],
  },
}

// theme-color: Discord's embed side bar.
export const viewport: Viewport = {
  themeColor: "#b91c1c",
}

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // The CSP nonce from proxy.ts, for the one inline script of our own.
  const nonce = (await headers()).get("x-nonce") ?? undefined
  return (
    // data-theme is set by the head script before paint, so the server markup never has it.
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col">
        <PrefsProvider>
          <Kiosk />
          <AutoUpdate />
          <Nav />
          {children}
        </PrefsProvider>
      </body>
    </html>
  )
}
