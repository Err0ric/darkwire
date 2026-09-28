// Malicious ?stack= / ?services= / ?theme= values, and a poisoned remembered preference, must not
// run anything, and the page must still render. Run against a live site:
//   npm run test:e2e                              (http://localhost:3000)
//   BASE_URL=https://darkwire.tech npm run test:e2e
import { expect, test, type Page } from "@playwright/test"

// Each payload sets a canary (and alerts) if it ever runs.
const RUN = "window.__pwned=1;alert(1)"
const PAYLOADS: Record<string, string> = {
  "script breakout": `</script><script>${RUN}</script>`,
  "U+2028 line separator": `cisco${String.fromCharCode(0x2028)}${RUN}//`,
  "U+2029 paragraph separator": `"${String.fromCharCode(0x2029)}${RUN}//`,
}

/** Collects anything that would mean code ran or the page broke. */
function watch(page: Page): string[] {
  const problems: string[] = []
  page.on("dialog", (d) => {
    problems.push(`dialog: ${d.message()}`)
    void d.dismiss()
  })
  page.on("pageerror", (e) => problems.push(`page error: ${e.message}`))
  return problems
}

async function expectSafe(page: Page, problems: string[]) {
  await expect(page.locator("h1").first()).toBeAttached()
  await page.waitForTimeout(1500) // effects and the prefs provider have run
  expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined()
  expect(problems).toEqual([])
  // Nothing from the payload became a theme.
  expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBeNull()
}

for (const path of ["/", "/wire"]) {
  for (const [name, payload] of Object.entries(PAYLOADS)) {
    test(`${path} with a ${name} in ?stack, ?services and ?theme`, async ({ page }) => {
      const problems = watch(page)
      const query = new URLSearchParams({ stack: payload, services: payload, theme: payload })
      await page.goto(`${path}?${query}`)
      await expectSafe(page, problems)
    })
  }
}

test("a poisoned remembered preference in localStorage", async ({ page }) => {
  const problems = watch(page)
  const payload = PAYLOADS["script breakout"]
  await page.addInitScript((p) => {
    localStorage.setItem("darkwire.prefs", JSON.stringify({ stack: [p, "cisco"], services: [p, "aws"], theme: p }))
  }, payload)
  await page.goto("/")
  await expectSafe(page, problems)
  // Only the known slugs survive; they are what goes into the URL.
  const url = new URL(page.url())
  expect(url.searchParams.get("stack")).toBe("cisco")
  expect(url.searchParams.get("services")).toBe("aws")
})

test("a real ?theme= still applies before paint (the constant head script works)", async ({ page }) => {
  const problems = watch(page)
  await page.goto("/?theme=amber")
  expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe("amber")
  expect(problems).toEqual([])
})
