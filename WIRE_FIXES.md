# Wire feed fixes (Oct 2026 review)

Source: review of https://darkwire.tech/wire at 1920, 1366, 768, and 375 widths on Oct 25, 2026.

Work through these in order. Each task has a goal, the evidence that triggered it, and acceptance criteria. Before starting, read the ingestion, enrichment, and feed API code and note in this file where each fix will land (file + function). Do not change the visual design system unless a task says so.

Stack reminder: FastAPI + PostgreSQL (api), web front end (web), deployed on Railway.

---

## P1. CVE-based story clustering

**Goal:** One row per story, not one row per outlet.

**Evidence (Oct 22-25 data):**
- Arista VeloCloud CVE-2026-114625: 5 separate rows (CISA x2, The Hacker News, BleepingComputer, SecurityWeek)
- PHP2Shell CVE-2026-109618: 3 rows in the wire, plus 2 in Elsewhere
- Popcorn Time CVE-2026-30612: 2 rows
- Capcom breach: 2 rows (SecurityWeek, BleepingComputer)
- Quest Diagnostics breach: 2 rows (The Record, SecurityWeek)

Some rows already merge sources ("The Hacker News · BleepingComputer"), so a dedupe step exists but only catches near-identical titles.

**Approach:**
1. Primary key: any shared CVE ID within a 7-day window joins articles into one cluster
2. Secondary key (no CVE): same normalized org/vendor name + same category within 72h, plus title similarity above a threshold (start at 0.6 token Jaccard, tune with real data)
3. Cluster primary article: earliest of (vendor advisory, CISA, NVD) if present, else earliest published
4. Store cluster membership in the DB (cluster_id on article, or a join table) so it is stable across refreshes, not recomputed client side
5. Cluster timestamp = most recent member, so an active story stays near the top
6. Do not cluster across categories that are clearly different (a CISA KEV add and a vendor patch for the same CVE SHOULD cluster; two unrelated stories that share a vendor name should NOT)

**UI:**
- Row shows the primary title and source, then "+N sources" on the metadata line
- Expanded panel lists all member articles (source, title, time, link, new tab)

**Acceptance:**
- [ ] VeloCloud CVE-2026-114625 renders as 1 row with +4 sources
- [ ] Capcom and Quest Diagnostics each render as 1 row
- [ ] Fri Oct 23 item count drops noticeably (was 30)
- [ ] Re-running ingestion does not create duplicate clusters
- [ ] Unit tests for: shared CVE, no CVE + same org, same vendor but unrelated stories (must not merge)

---

## P2. Detail panel data bleed and CVE extraction bugs

**Evidence:**
- PHP2Shell (CVE-2026-109618) detail panel shows "Fixed: PAN-OS 10.2.7, 11.1.4" under the PHP fixed versions. Data from another record is leaking into this one.
- CVE-2026-111497 is attached to both "OpenAI AI Agents Demonstrate VM Escapes" and "Node2Shell RCE Exploit on Node.js". At least one is a wrong extraction.

**Tasks:**
1. Trace how affected/fixed version data is joined to a CVE. Check for: joins on vendor instead of CVE ID, a shared mutable object reused across loop iterations, or cached enrichment keyed incorrectly
2. Trace CVE extraction from article text. When an article mentions multiple CVEs, the row should show the primary one (most mentioned or in title) and the panel should list all
3. Add a guard: only attach a CVE to an article if the CVE ID string actually appears in the article title, summary, or body
4. Backfill: re-run enrichment on the last 14 days after the fix

**Acceptance:**
- [ ] PHP2Shell panel shows only PHP fixed versions
- [ ] CVE-2026-111497 is attached only to articles that contain that string
- [ ] Test case: two CVEs from different vendors enriched in the same batch do not cross-contaminate

---

## P3. Roundup type and category cleanup

**Evidence:**

| Row | Current | Should be |
|---|---|---|
| Microsoft: Windows Server 2016 reaches end of support | Vulnerability | Advisory |
| Why Caribbean Threats Cascade Into Global Cyber-Risk | Vulnerability | Research |
| Exposed to PHP2Shell? Cyber Experts Weigh In | Vulnerability | Research / commentary |
| Exposed Infrastructure Reveals How Ransomware Affiliates Used AI Agents | Ransomware + BREACH | Research |
| In Other News: Tor Exit Relays Hijacked... | Ransomware + BREACH + Apple tag | Roundup |
| ThreatsDay: AI Secrets Leak... | Vulnerability | Roundup |
| Metasploit Wrap Up | Vulnerability + single CVE | Roundup |

**Tasks:**
1. Add a `roundup` type. Detect by title patterns: "In Other News", "ThreatsDay", "Weekly Recap", "Wrap Up", "This Week in", "Week in Review". Make the pattern list a config constant
2. Roundups get no CVE, no severity badge, no vendor tag, and a neutral icon
3. BREACH badge only when the article reports a confirmed incident at a named organization (keywords like "confirms", "discloses", "data breach affecting", "notifies" plus an org entity). Research about attacker infrastructure is not a breach
4. "Vulnerability" requires a CVE or a vendor-acknowledged flaw. End of support, commentary, and expert opinion pieces go to Advisory or Research
5. Add "Roundup" to the filter tabs only if it does not crowd mobile; otherwise fold it into Research

**Acceptance:**
- [ ] All 7 rows above land in the correct category
- [ ] No roundup row shows a CVE, score, or BREACH badge

---

## P4. KEV due date and missing scores

**Evidence:**
- VeloCloud shows "KEV due in 1d" despite being added around Oct 22-23
- Collabora CVE-2026-110447 (in KEV), HPE "eight max severity" AOS flaws, and Tailscale show no score

**Tasks:**
1. Confirm "KEV due in Nd" is computed from the KEV catalog `dueDate` field, not `dateAdded` plus a fixed offset. Compare against the live KEV JSON for CVE-2026-114625
2. Score fallback order: NVD CVSS 3.1/4.0, then CNA/vendor CVSS from the CVE record, then vendor advisory severity text. If none, show "awaiting NVD" in muted text instead of blank
3. Mark the score source in the detail panel (NVD vs CNA vs vendor)

**Acceptance:**
- [ ] KEV due dates match the catalog for 3 spot-checked CVEs
- [ ] Collabora and HPE rows show a score or "awaiting NVD"

---

## P5. Feed hygiene

**Evidence:**
- French-language headline from Dark Reading: "Les supermarchés de l'UE paient d'un firmware de réfrigérateur non mis à jour"
- Sponsored or opinion pieces mixed into the main wire ("Trust Is Not What It Seems", "Cyber Insurance's New Reality")
- Services showed "Cloudflare major outage" today and "1Password major outage" for 2+ days last week

**Tasks:**
1. Language filter: drop or route non-English items (simple langdetect on title is fine)
2. Identify sponsored/commentary sources or URL paths (Dark Reading has distinct section paths) and route them to Elsewhere or a quiet "Commentary" tag
3. Services: verify the status page indicator mapping (statuspage.io `indicator` values: none, minor, major, critical). Show "since [time]" next to any non-green status, and auto-clear when the indicator returns to none
4. Optional: tag funding/M&A news as "Industry"

**Acceptance:**
- [ ] No non-English titles in the wire
- [ ] Services outage line shows start time and clears correctly

---

## P6. Mobile and tablet layout

**Evidence (375px):** About half of the first screen is header chrome (nav, stats on 2 lines, large clock, outage line, search) before the first headline. Headlines truncate mid-sentence. Tabs overflow with no scroll cue. CVE IDs hidden.

**Evidence (768px):** CVE IDs hidden from rows. Vuln titles clamp at 2 lines, article titles at 1 line. "Elsewhere" tab touches the right edge.

**Tasks (mobile, under 768px):**
1. Hide the large clock, or render it as small inline text in the stats line
2. Stats on one line: "1 crit · 0 high · 8 KEV"
3. Remove the line clamp on titles. Headlines wrap fully
4. Show the CVE ID on the metadata line
5. Horizontal tab row: add a right-edge gradient fade and `scroll-snap` so it reads as scrollable

**Tasks (tablet, 768 to 1279px):**
1. Keep the CVE ID visible (metadata line if the column is too narrow)
2. Same clamp rule for all row types (2 lines max, or no clamp)
3. Add right padding to the tab row

**Acceptance:**
- [ ] At 375x812, the first headline starts in the top 40% of the screen
- [ ] At 768x1024, every vuln row shows its CVE ID
- [ ] No horizontal page scroll at any width

---

## P7. Polish

1. KEV rail: collapse repeated vendors ("Plex ×4"), expand on click
2. KEV rail: widen the vendor column or use short names so "EG Secure Solutions" does not truncate
3. Hide zero rows in "Last 7 days" (Low 0)
4. Vendor logo coverage: add logos for frequent vendors this week (Arista, PHP, HPE, Tailscale, Collabora, Capcom, Plex). Lettered tile fallback for any vendor without a logo so the icon column is consistent
5. Optional: at 1920+, move the stats and clock into the nav bar (Option A from the layout review) to remove the centered floating block
6. Surface the footer source health line ("20 feeds, all healthy") near "Synced just now", or as a tooltip on it

---

## Verification checklist (run after each P-level)

- [ ] Load /wire at 1920x1080, 1366x768, 768x1024, 375x812
- [ ] Spot-check 5 vuln rows: CVE, score, KEV status, and fixed versions against NVD and the KEV catalog
- [ ] Count rows per day before and after (P1 should drop counts)
- [ ] No console errors
- [ ] Commit per P-level with a clear message so each change is easy to roll back
