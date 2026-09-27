import type { NextConfig } from "next";

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
  },
  poweredByHeader: false,
  // /outages was renamed /services; keep old links working.
  async redirects() {
    return [{ source: "/outages", destination: "/services", permanent: true }]
  },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
