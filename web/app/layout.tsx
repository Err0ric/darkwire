import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"

import { Kiosk } from "@/components/Kiosk"
import { Nav } from "@/components/nav"
import { PrefsProvider } from "@/lib/prefs"

import "./globals.css"

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: "darkwire",
  description: "Live board of security news and CVEs.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <PrefsProvider>
          <Kiosk />
          <Nav />
          {children}
        </PrefsProvider>
      </body>
    </html>
  )
}
