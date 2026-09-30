// An open wire row is one toggle target: a click on blank space in its panel closes it; links keep
// their own behavior; a click that ends a text selection does not close it (lib/toggle.ts).
//   npm run test:e2e                              (http://localhost:3000)
import { expect, test, type Locator, type Page } from "@playwright/test"

/** Opens the first expandable row on /wire; returns the row, its chevron and its panel. */
async function openRow(page: Page): Promise<{ row: Locator; chevron: Locator; panel: Locator }> {
  // Outside links open in a new tab: keep them off the network.
  await page.context().route(/^https?:\/\/(?!localhost|127\.0\.0\.1|darkwire\.tech|api\.darkwire\.tech)/, (r) => r.abort())
  await page.goto("/wire", { waitUntil: "networkidle" })
  const row = page.locator("article").filter({ has: page.locator("button[aria-expanded]") }).first()
  const chevron = row.locator("button[aria-expanded]")
  await chevron.click()
  await expect(chevron).toHaveAttribute("aria-expanded", "true")
  const panel = row.locator('[id$="-detail"]')
  await expect(panel.getByRole("link", { name: "Source" })).toBeVisible()
  return { row, chevron, panel }
}

test("a click on blank space in the open panel collapses the row", async ({ page }) => {
  const { chevron, panel } = await openRow(page)
  const box = (await panel.boundingBox())!
  // The panel's left padding, under the vendor mark: no text, no link.
  await page.mouse.click(box.x + 6, box.y + box.height - 6)
  await expect(chevron).toHaveAttribute("aria-expanded", "false")
})

test("a click on the Source link does not toggle the row", async ({ page }) => {
  const { chevron, panel } = await openRow(page)
  const popup = page.context().waitForEvent("page").catch(() => null)
  await panel.getByRole("link", { name: "Source" }).click()
  await (await popup)?.close()
  await expect(chevron).toHaveAttribute("aria-expanded", "true")
})

test("selecting text in the open panel does not collapse the row", async ({ page }) => {
  const { chevron, panel } = await openRow(page)
  // The summary (or the feed excerpt): plain text, no links.
  const text = panel.locator("p.line-clamp-3").first()
  const box = (await text.boundingBox())!
  const y = box.y + Math.min(10, box.height / 2)
  await page.mouse.move(box.x + 2, y)
  await page.mouse.down()
  await page.mouse.move(box.x + Math.min(240, box.width - 4), y, { steps: 8 })
  await page.mouse.up()
  expect((await page.evaluate(() => window.getSelection()?.toString() ?? "")).trim().length).toBeGreaterThan(3)
  await expect(chevron).toHaveAttribute("aria-expanded", "true")
})

test("Esc closes the open row", async ({ page }) => {
  const { row, chevron } = await openRow(page)
  await row.locator('[role="group"]').focus()
  await page.keyboard.press("Escape")
  await expect(chevron).toHaveAttribute("aria-expanded", "false")
})
