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

---

## P2. Data correctness bugs

1. **Fixed versions bleed:** the PHP2Shell row (CVE-2026-109618) detail panel shows "Fixed: PAN-OS 10.2.7, 11.1.4" under the PHP versions. Trace where that line comes from (vendor data, NVD CPE, `facts.py` per-article fallback, `versions.py`). PAN-OS on a PHP CVE is wrong regardless of source.
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

Tasks:
1. For each row, say which rule produced the category and whether the code or the rule is at fault
2. Recap detection: "In Other News" and "ThreatsDay" are not in the recap patterns listed in CLAUDE.md. Propose adding them (and check for other recurring roundup titles in the last 30 days)
3. The Metasploit row has a CVE despite the rule. Find out how
4. Where the rule is right and it is a one-off, add a `CATEGORY_OVERRIDES` entry with the reason

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
