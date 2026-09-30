// Unit tests for lib/cvss.ts plainVector: the plain-English line is built from the NVD vector in
// code, never by a model. Run: npm test.
import assert from "node:assert/strict"
import { test } from "node:test"

import { plainVector } from "../../lib/cvss.ts"

test("remote, no auth, no user interaction", () => {
  assert.equal(plainVector("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"), "Remote, no auth, no user interaction")
})

test("high complexity, privileges and user interaction are named", () => {
  assert.equal(
    plainVector("CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:H/I:N/A:N"),
    "Local access, hard to exploit, admin account, needs user interaction",
  )
  assert.equal(plainVector("CVSS:3.1/AV:A/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:N"), "Adjacent network, low-privilege account, no user interaction")
})

test("no vector, no line", () => {
  assert.equal(plainVector(null), null)
  assert.equal(plainVector("CVSS:3.1/AC:L"), null)
})
