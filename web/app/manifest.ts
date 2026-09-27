import type { MetadataRoute } from "next"

// Installable as an app on a wall display or a phone home screen. Icons are the wordmark's red
// dot on the page background (public/icon-*.png, app/apple-icon.png, app/icon.svg).
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "darkwire",
    short_name: "darkwire",
    description: "Security news and CVEs on one live board. No accounts. No ads. No tracking.",
    start_url: "/",
    display: "standalone",
    background_color: "#0a0a0a",
    theme_color: "#b91c1c",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  }
}
