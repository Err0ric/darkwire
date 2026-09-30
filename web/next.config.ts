import type { NextConfig } from "next";

import OG from "./lib/og-images.json";

// Security headers on every response. The Content-Security-Policy is set per request in
// proxy.ts (it carries a nonce).
const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), interest-cohort=()" },
  // Old browsers that ignore CSP frame-ancestors.
  { key: "X-Frame-Options", value: "DENY" },
];

const nextConfig: NextConfig = {
  // The deployed commit, for auto-reload on a new deploy (components/AutoUpdate.tsx).
  env: {
    NEXT_PUBLIC_BUILD_ID: process.env.VERCEL_GIT_COMMIT_SHA ?? "dev",
    // Hover card (components/HoverPreview.tsx): off by default, on for production builds while it
    // is tried out. The variable, when set, always wins.
    NEXT_PUBLIC_HOVER_PREVIEW: process.env.NEXT_PUBLIC_HOVER_PREVIEW ?? (process.env.VERCEL_ENV === "production" ? "1" : "0"),
  },
  poweredByHeader: false,
  // /outages was renamed /services; keep old links working.
  async redirects() {
    return [
      { source: "/outages", destination: "/services", permanent: true },
      // Old link-preview URLs point at the current content-hashed images (not permanent: they move).
      { source: "/og.png", destination: OG.png, permanent: false },
      { source: "/og.gif", destination: OG.gif, permanent: false },
    ]
  },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
