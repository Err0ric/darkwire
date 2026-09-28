// Unit tests for lib/stack.ts: URL / storage values are validated against the known slug lists,
// and the <head> theme script is a constant. Run: npm test (node --test, no browser).
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"

import { parseServices, parseStack, parseTheme, SERVICE_SLUGS, THEME_SCRIPT, VENDOR_SLUGS } from "../../lib/stack.ts"

const SCRIPT_BREAKOUT = "</script><script>alert(1)</script>"
// U+2028 / U+2029 end a line in JavaScript source; a classic way out of a string built into code.
// Built with fromCharCode so the test file itself carries no raw separators.
const LS = String.fromCharCode(0x2028)
const PS = String.fromCharCode(0x2029)
const LINE_SEPARATOR = `cisco${LS}alert(1)//`
const PARAGRAPH_SEPARATOR = `fortinet${PS}alert(1)//`

test("parseStack keeps known vendor slugs only", () => {
  assert.deepEqual(parseStack("cisco, Fortinet,cisco,not-a-vendor"), ["cisco", "fortinet"])
  assert.deepEqual(parseStack(SCRIPT_BREAKOUT), [])
  assert.deepEqual(parseStack(`cisco,${SCRIPT_BREAKOUT}`), ["cisco"])
  assert.deepEqual(parseStack(LINE_SEPARATOR), [])
  assert.deepEqual(parseStack(`${PARAGRAPH_SEPARATOR},microsoft`), ["microsoft"])
  assert.deepEqual(parseStack(null), [])
})

test("parseServices keeps known service slugs only", () => {
  assert.deepEqual(parseServices("aws,github,slack,cisco"), ["aws", "github", "slack"])
  assert.deepEqual(parseServices(SCRIPT_BREAKOUT), [])
  assert.deepEqual(parseServices(`aws${LS}alert(1)//`), [])
})

test("parseTheme only returns a listed theme", () => {
  assert.equal(parseTheme(SCRIPT_BREAKOUT), "darkwire")
  assert.equal(parseTheme("amber"), "amber")
})

test("THEME_SCRIPT is a constant with nothing user-controlled in it", () => {
  // No markup that could end the <script> element, no line terminators.
  assert.ok(!/<\/?script/i.test(THEME_SCRIPT))
  assert.ok(![LS, PS, String.fromCharCode(10), String.fromCharCode(13)].some((ch) => THEME_SCRIPT.includes(ch)))
  // The allowed names are read from <html data-themes>, not written into the code.
  assert.ok(THEME_SCRIPT.includes('getAttribute("data-themes")'))
  assert.ok(!/amber|phosphor|high-contrast/.test(THEME_SCRIPT))
})

test("the slug lists match the API's seed data", () => {
  const seed = readFileSync(new URL("../../../api/app/seed.py", import.meta.url), "utf8")
  const vendors = new Set([...seed.matchAll(/"slug":\s*"([a-z0-9-]+)"/g)].map((m) => m[1]))
  assert.deepEqual([...VENDOR_SLUGS].sort(), [...vendors].sort(), "VENDOR_SLUGS differs from api/app/seed.py")
  const services = readFileSync(new URL("../../../api/app/services.py", import.meta.url), "utf8")
  // Entries of the SERVICES list, declared with Service(...) or the Statuspage helper _sp(...).
  const start = services.indexOf("SERVICES: list[Service] = [")
  const list = services.slice(start, services.indexOf("\n]\n", start))
  const tracked = new Set([...list.matchAll(/(?:Service|_sp)\(\s*"([a-z0-9-]+)"/g)].map((m) => m[1]))
  assert.deepEqual([...SERVICE_SLUGS].sort(), [...tracked].sort(), "SERVICE_SLUGS differs from api/app/services.py")
})
