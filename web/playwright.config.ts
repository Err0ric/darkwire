import { defineConfig } from "@playwright/test"

// Browser tests (tests/e2e) against a running site: BASE_URL, else the local production server.
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  use: { baseURL: process.env.BASE_URL ?? "http://localhost:3000", viewport: { width: 1440, height: 900 } },
  reporter: "list",
})
