import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The deployed commit, for auto-reload on a new deploy (components/AutoUpdate.tsx).
  env: {
    NEXT_PUBLIC_BUILD_ID: process.env.VERCEL_GIT_COMMIT_SHA ?? "dev",
  },
};

export default nextConfig;
