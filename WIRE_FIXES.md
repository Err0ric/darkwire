# Wire feed fixes (Oct 2026 review)

Source: review of https://darkwire.tech/wire at 1920, 1366, 768 and 375 widths on Oct 25, 2026.

## How to work this file

- CLAUDE.md is the spec. Most of what is below already has a rule there (dedupe, CVE attachment, categories, recaps, ads, vendor marks). Treat each item as a **misfire to diagnose against the existing rules**, not a feature to build.
- For each case: find the row(s), state which CLAUDE.md rule applied, explain why it produced this result, then propose the smallest fix. Options in order of preference: (1) bug fix where the code does not match the spec, (2) data fix (`CATEGORY_OVERRIDES`, `MERGE_EXCLUSIONS`, `seed.py` aliases), (3) a rule change.
- A rule change updates CLAUDE.md in the same commit.
- Production data rules in CLAUDE.md apply to everything here: read-only diagnosis is fine; any bulk change is a logged dry run first and applies only with sign-off. Propose follow-ups, do not apply them.
- One P-level per session. Stop for review after each.

---

## P1. Dedupe misses

Each of these rendered as multiple rows. For each, report which rows exist, their pinned/subject CVEs, and which `dedupe.py` rule should have merged them and why it did not.

| Story | Rows seen | Shared key |
|---|---|---|
| Arista VeloCloud zero-day | 5: "CISA Adds One Known Exploited Vulnerability" (CISA), "CISA Flags Two Actively Exploited Critical Flaws in Collabora Online and Arista VeloCloud" (THN), "Arista Warns of Critical VeloCloud SQL Injection Zero-Day" (THN), "Arista patches new VeloCloud Orchestrator zero-day" (BleepingComputer), "Attackers Exploit Third VeloCloud Orchestrator Zero-Day in Four Months" (SecurityWeek) | CVE-2026-114625 |
| Popcorn Time updater | 2: THN Oct 24 "Researchers Push Over 2 Million Updates...", BleepingComputer Oct 23 "Abandoned Popcorn Time app exposed millions..." | CVE-2026-30612 |
| PHP2Shell | 3 wire rows plus Dark Reading "Exposed to PHP2Shell?" | CVE-2026-109618 |
| Capcom breach | 2: SecurityWeek "11 Million Impacted", BleepingComputer "Capcom confirms data breach affecting 11.7 million accounts" | no CVE, same vendor, breach |
| Quest Diagnostics breach | 2: The Record Oct 23 05:52, SecurityWeek + BleepingComputer Oct 23 01:25 | no CVE, same org, breach |

Notes for diagnosis:
- The THN "CISA Flags Two..." row names two CVEs (Collabora + Arista). Check whether the 2+ vendor rule correctly kept it separate, and whether that is the desired outcome.
- Capcom and Quest are title-similarity cases. Check normalized similarity scores against the 0.85 threshold and whether either side lacked a vendor tag (Capcom and Quest Diagnostics may not be in `seed.py`).
- Popcorn Time: check whether CVE-2026-30612 is a subject CVE on both rows, and the 72h window (Oct 23 13:55 to Oct 24 02:04 is inside it).

**Acceptance:** a written diagnosis per case, a proposed fix per case, and a dry run of any re-merge showing exactly which rows would combine. No production writes without sign-off.

### P1 diagnosis (2026-10-25)

**Data used.** The local DB could not reproduce the CVE cases: with no `ANTHROPIC_API_KEY` no article is fetched, so rows never gain their CVEs, and CISA returns 403 locally, so there is no KEV alert row. Row layout and CVE sets came from prod's public API (GET `/feed?q=`, `/items/{id}`, read only); article text was fetched again with `app.fetcher` as the summarizer does; title rules ran on local data. Row ids below are prod ids. SecurityWeek article text did not extract locally, so row 1908's text is unknown.

**Arista VeloCloud** (1871 BC, 1891 THN, 1908 SecurityWeek, 1944 CISA alert, 1951 THN "CISA Flags Two").
- 1871, 1891, 1908 all hold and display CVE-2026-114625, plus context CVEs (1871: 93952; 1891 and 1908: 16812, 93952). No feed text names a CVE; they came from fetched articles.
- CVE rule: news joins news only on a CVE that is a subject of both. Both articles say "Tracked as CVE-2026-114625", in paragraph 3 or 4, outside the lede window (excerpt plus 2 paragraphs) and named once, so it was a subject of neither. The vendor-data fallback (`row_subject`, a row's only CVE when it is its vendor's) could not apply: Arista was not seeded, and each row holds 2-3 CVEs.
- Title rules: no vendor on either side; stripped similarity 0.37-0.61; only `arista` and `velocloud` shared, under 3.
- 1944: when the alert arrived, three rows held its CVE, so it rightly started its own row; nothing ever moved it after that.
- 1951: holds only Collabora's CVE-2026-110447, from the full RSS summary at ingest. The fetch step adds CVEs only to rows with none, so it never gained Arista's CVE and the 2+ vendor rule never ran. Keeping it separate is right: merged, the Arista row would carry Collabora's CVE.

**Popcorn Time** (1948 BC, 1952 THN). Both hold only CVE-2026-30612, 12h apart. It is a subject of BC's article (paragraph 2), not of THN's (paragraph 10, "now tracked as"). Title similarity 0.31. No vendor data to fall back on (no CPE, CNA "n/a").

**PHP2Shell** (1760, 1766 with 9 sources, 1796, 1836, 1940, 1964; 1839, 1945, 1814 with no CVE; 1927 a different CVE).
- Bug: subject CVEs found in fetched text were never stored (the article is not stored, and `recheck` kept them only for rows gaining CVEs in that same pass). 1760's BC article makes both PHP CVEs subjects, but when 1766 arrived ingest saw none, so it never joined (prod logs should show `not joining row 1760`).
- 1836: "Tracked as" in paragraph 5, the same gap as Arista.
- 1796, 1940 (The Record): the CVE named once, no introducer. They stay separate; widening the rule further is not proposed.
- 1964: Oct 25, outside 72h of 1760: separate by design.
- 1839, 1945, 1814: no CVE, no title rule matches: separate (categories are P3). 1814 is tagged Signal from "Bugs Signal Red Alert" (see P3).
- Mis-merge found: THN's "PHP Warns of Another Unpatched RCE" (CVE-2026-115560) joined the PHP2Shell row by `shared_story` (php, php2shell, rce). With subject CVEs kept, it would pull 1927 (BC on that CVE) in too.

**Capcom** (1893 BC, 1905 SecurityWeek) and **Quest Diagnostics** (1906 SecurityWeek+BC, 1915 The Record). No vendor; similarity Capcom 0.36 (stripped 0.40), Quest 0.48-0.51 (stripped 0.53-0.57); shared distinctive words Capcom `capcom`, Quest `quest`, `diagnostic`: under 3. Seeding them would not help: the same-vendor test still needs > 0.85.

### P1 fixes (approved 2026-10-25, branch wire-fixes-p1)

1. `MERGE_EXCLUSIONS`: 1927 vs 1760 and vs 1766 (either may survive), with the reason. Data fix.
2. `item_cves.subject` (migration 0020): a CVE's subject flag is stored when linked (ingest, fetched articles, merges) and read with the stored text's subjects by ingest's CVE cluster check and `article_cves.recheck`. Bug fix, no spec change.
3. Arista seeded (`Arista`, `Arista Networks`, `VeloCloud`, `VeloCloud Orchestrator`; named "Arista" as KEV and CPE write it). The existing zero-day + product alias rule then merges 1871, 1891 and 1908 by title and keeps 1951 out. 58 vendors.
4. Rule change: a CVE introduced anywhere in the text as the flaw's ID ("tracked as", "identified as", "assigned") is a subject CVE.
5. Rule change: a KEV alert's own row joins the one other row that comes to hold all its CVEs (no alert of its own, not a recap), after the post-fetch re-check or in a signed-off re-merge (`article_cves.rehome_alerts`).
6. Shadow mode: Breach rows within 72h whose titles share a proper noun are logged as would-merge pairs (`dedupe.breach_shadow`); nothing merges. Local data, 2 weeks, 12 breach articles: Capcom and Quest found, no false pairs.

**Re-merge dry run** (in memory over the prod rows, with the live `article_cves.pair` rule; the prod dry run is `python -m app.p1_remerge`, waiting for sign-off):

| With | Rows that combine |
|---|---|
| Code before these fixes | none |
| Fix 2 only | 1766→1760, and 1927→1760 (wrong; fix 1 blocks it) |
| Fixes 1, 2, 4 | 1766→1760, 1836→1760, 1891→1871, 1952→1948 |
| Fix 3 (titles) | 1908 joins the Arista row; fix 5 then folds 1944 into it |
| Fix 6 | nothing merges; 1905/1893 and 1915/1906 are logged |

**Prod dry run, signed off 2026-10-25** (`python -m app.p1_remerge`, branch p1-remerge-signoff): 6 merges (cve 1766, 1836→1760; cve 1891, 1908→1871; cve 1952→1948; alert 1944→1871), 4 Arista tags (1871, 1891, 1908, 1951; 1951's kept), 10 subject flags, 1760 predicted as "PHP warns admins of two critical flaws, emergency patches coming tomorrow" with no vendor, 0 stop conditions. `SIGNED_OFF` holds exactly those merges. Not applied yet.

### P1 follow-ups (proposed, not built)

- THN's "PHP Warns of Another Unpatched RCE Risk Two Days After Emergency PHP2Shell Patches" (thehackernews.com/2026/10/urgent-php-warns-of-another-unpatched.html) is about CVE-2026-115560, a different flaw. It is a source of 1766 from an old title merge (`shared_story`: php, php2shell, rce), so after the re-merge it sits in 1760. It brings no CVE in: it has none stored, and its fetched CVEs are not flagged since none is on the row. `MERGE_EXCLUSIONS` keeps 1927 (BC on 115560) out. Moving the source out to its own row, or into 1927, would be a separate signed-off data change. Whether `shared_story` should merge two stories that share a product and a nickname but name different CVEs in their text is a rule question for later.

---

## P2. Data correctness bugs

1. **Fixed versions bleed:** the PHP2Shell row (CVE-2026-109618) detail panel shows "Fixed: PAN-OS 10.2.7, 11.1.4" under the PHP versions. Trace where that line comes from (vendor data, NVD CPE, `facts.py` per-article fallback, `versions.py`). PAN-OS on a PHP CVE is wrong regardless of source.
   - Found in P1 (2026-10-25): the line is NVD's own data. NVD's configurations for CVE-2026-109618 list 295 CPEs as vulnerable, PHP and Palo Alto (PAN-OS, Panorama) among them, and every CPE upper bound becomes a "Fixed" entry, so `cves.fixed_versions` holds PHP 8.2.35 to 8.5.12 and PAN-OS 10.2.7 and 11.1.4. It is not the primary-source rule (fixed separately in P1: Palo Alto's advisory no longer heads the PHP row) and not `facts.py` (the row has no article facts).
   - Preferred fix (owner, 2026-10-25): label other products' versions separately ("Also affects PAN-OS: fixed in 10.2.7, 11.1.4") rather than hiding them. Affected and Fixed show the displayed CVE's own product first.
   - Check NVD's AND configurations: some Palo Alto entries sit in `operator: AND` nodes (PAN-OS with Panorama hardware, the hardware `vulnerable: false`). Confirm that only `vulnerable: true` matches become affected or fixed, and how an AND node's platform entries are read.
2. **Same CVE on unrelated rows:** CVE-2026-111497 is the displayed CVE on both "OpenAI AI Agents Demonstrate VM Escapes..." (Oct 24) and "Researchers Demonstrate Node2Shell RCE Exploit on Node.js..." (Oct 23). Check which row's pin is wrong, how it was attached (`article_cves.py` rules), and whether it was a context CVE that should never display.
3. **KEV due date:** VeloCloud rows show "KEV due in 1d" though added around Oct 22-23. Confirm the value comes from the KEV catalog `dueDate` for CVE-2026-114625 and is not computed from `dateAdded`.

**Acceptance:** root cause for each, a fix with a unit test that reproduces it, and a dry run listing every other row affected by the same bug.

---

## P3. Category and badge misfires

| Row | Shown as | Expected per CLAUDE.md rules |
|---|---|---|
| Microsoft: Windows Server 2016 reaches end of support in January | Vulnerability | News (no CVE, no flaw) |
| Why Caribbean Threats Cascade Into Global Cyber-Risk | Vulnerability | Research (trend piece) |
| Exposed to PHP2Shell? Cyber Experts Weigh In With Advice | Vulnerability | Research or News |
| Exposed Infrastructure Reveals How Ransomware Affiliates Used AI Agents | Ransomware + BREACH badge | Research, no BREACH (no named victim) |
| In Other News: Tor Exit Relays Hijacked... (SecurityWeek) | Ransomware + BREACH + Apple vendor | Recap: no CVE, no badge |
| ThreatsDay: AI Secrets Leak, PingCAP Source Theft... (THN) | Vulnerability + Signal vendor | Recap |
| Metasploit Wrap Up (Rapid7) | Vulnerability + CVE-2026-93680 | Recap; CLAUDE.md says Metasploit never gets CVEs attached |
| 'PHP2Shell' Bugs Signal Red Alert for Security Industry (Dark Reading, prod 1814) | Signal vendor | Untagged: "Signal" here is a verb. `CASE_SENSITIVE_ALIASES` only stops lowercase "signal"; in a Title Case headline every word is capitalized, so it matches (found in P1) |
| State Bank of India Confirms Data Leak... / State Bank of India Suffers a Customer PII Data Leak (local rows 392, 452) | two Breach rows | One row. Both titles are Title Case, so `dedupe._proper` treats no shared word as a proper noun: `shared_story` (state, bank, india) and the P1 breach shadow rule both miss it (found in P1) |

Tasks:
1. For each row, say which rule produced the category and whether the code or the rule is at fault
2. Recap detection: "In Other News" and "ThreatsDay" are not in the recap patterns listed in CLAUDE.md. Propose adding them (and check for other recurring roundup titles in the last 30 days)
3. The Metasploit row has a CVE despite the rule. Find out how
4. Where the rule is right and it is a one-off, add a `CATEGORY_OVERRIDES` entry with the reason
5. Title Case: propose how a case-sensitive alias ("Signal") and the proper-noun test (`dedupe._proper`) should treat headlines where every word is capitalized

---

## P4. Feed hygiene

1. **Non-English headline:** Dark Reading "Les supermarchés de l'UE paient d'un firmware de réfrigérateur non mis à jour" (Oct 22). Find which feed it came from and propose a language check at ingest
2. **Sponsored/commentary:** "Trust Is Not What It Seems — And Fraudsters Are Counting on It" and "Cyber Insurance's New Reality: Underwriting Isn't Enough" (Dark Reading) got past the ad filter. Check for a URL path or feed marker that identifies them
3. **Missing scores:** Collabora CVE-2026-110447 (in KEV), the HPE AOS "eight max severity" row, and Tailscale show no score. Check whether NVD has scored them, and whether the CNA score from the CVE record should be shown as a fallback (rule change, needs approval)
4. **Services:** today showed "Cloudflare major outage"; last week showed 1Password major outage for 2+ days. Verify against each provider's status page and check the indicator mapping and how a status clears

---

## P5. Mobile and tablet

**375px:** about half of the first screen is header (nav, stats on two lines, large clock, outage line, search) before the first headline. The tab row overflows with no scroll cue. CVE IDs are hidden.

**768px:** CVE IDs hidden. Vuln rows clamp at two lines, short article rows truncate at one. The Elsewhere tab touches the right edge.

Proposals (each is a spec change, confirm before building):
1. Under 768px: hide the large clock or make it inline text; stats on one line ("1 crit · 0 high · 8 KEV")
2. Under 768px: allow headlines to wrap fully (CLAUDE.md currently caps at two lines with ellipsis)
3. CVE ID on the meta line when the CVE column is hidden
4. Right-edge fade on the tab row; right padding at tablet width

**Acceptance:** at 375x812 the first headline starts in the top 40% of the screen; no horizontal page scroll at any width.

---

## P6. Polish

1. KEV rail: collapse repeated vendors ("Plex ×4", expandable); "EG Secure Solutions" truncates at 1920
2. Hide zero rows in "Last 7 days"
3. Vendor coverage: frequent untagged or logo-less vendors this week (Arista, PHP, HPE, Tailscale, Collabora, Capcom, Plex, Quest Diagnostics). Add to `seed.py` with aliases and `/public/vendors/{slug}.svg` where appropriate. Check the nightly untagged-articles list first
4. Optional: at desktop width, move the stats and clock into the nav bar to remove the centered block above the feed

---

## Verification after each P-level

- [ ] `npm run lint`, `npm test`, `npm run build` in /web; `python -m unittest discover -s tests` in /api
- [ ] /wire at 1920x1080, 1366x768, 768x1024, 375x812
- [ ] Spot-check 5 vuln rows: CVE, score, KEV, fixed versions against NVD and the KEV catalog
- [ ] Local servers stopped, including child node processes
