# darkwire.tech

Live board of security news and CVEs. One merged feed, tagged by vendor, scored by CVSS, flagged by KEV. No accounts, no email, no ads, no tracking. Someone opens it in the morning and leaves it on a second monitor.

Reference mockups: `/design-refs/home.png` and `/design-refs/wire.png`. Match them. When in doubt, do less.

## Stack

- Backend: FastAPI + PostgreSQL (SQLAlchemy 2, Alembic, APScheduler for ingest jobs). Deployed on Railway with a Railway Postgres plugin, same setup as crawlr.
- Frontend: Next.js (App Router) + TypeScript + Tailwind. shadcn/ui only for primitives (select, input, dialog). Everything else is plain markup.
- Fonts: Geist Sans (UI), Geist Mono (data). Load via `next/font`.
- Hosting: API on Railway, web on Vercel. Monorepo: `/api` and `/web`, with `docker-compose.yml` at the root for local Postgres.
- Local dev: `docker compose up -d` for Postgres, `uvicorn` in `/api`, `npm run dev` in `/web`. `NEXT_PUBLIC_API_URL` points at localhost:8000 locally and the Railway domain in prod.
- Icons: Lucide, stroke only. Never emoji.

## Pages

| Route | Purpose |
|---|---|
| `/` | Home. Status header, as many rows as fit the screen (Critical/KEV of the last 48h pinned first), four tabs, OPEN WIRE link. Meant to be left open. |
| `/wire` | The board. Full feed, seven tabs, vendor filter, search, right rail. |
| `/cves` | Sortable table: CVE, vendor, product, CVSS, EPSS, KEV, published. |
| `/vendor/[slug]` | Everything tagged to one vendor. |
| `/item/[id]`, `/cve/[id]` | Permalinks that open the expanded row. |
| `/sources` | Every feed we ingest, how tagging works, what KEV and EPSS mean. Plain, not a pitch. |
| `/feed.xml`, `/feed.json` | Our own output for other people's tools. |

No pricing, login, signup, newsletter, about-us hero, or footer CTA. Ever.

## Design system

Palette. Use CSS variables, never hardcode in components.

| Token | Value | Use |
|---|---|---|
| `--bg` | #0a0a0a | page |
| `--surface` | #0f0f0f | expanded row band |
| `--hairline` | #161616 | row dividers |
| `--rule` | #1f1f1f | section dividers, empty bar cells |
| `--fg` | #f5f5f5 | headlines, primary text |
| `--fg-2` | #a3a3a3 | source links, secondary |
| `--muted` | #737373 | meta text, labels |
| `--dim` | #525252 | tertiary, timestamps in rail |
| `--accent` | #b91c1c | outlines, HIGH, wordmark dot |
| `--critical` | #dc2626 | CRITICAL fill, KEV text, arrows |

Red is a signal, not a paint job. If more than ~5% of a screen is red, it is wrong.

Type: Geist Sans for words, Geist Mono for data (CVE IDs, scores, timestamps, vector chips, badges, status line). Headline 15px/500 tracking -0.01em. Meta 12px. Section labels 13px/500 in sans, never mono-caps.

Layout: no boxes, no cards, no panel borders. Separate regions with background tone and 1px hairlines. 48px page gutter on desktop, 16px on mobile. Row height 64px. Radius: 4px on inputs and buttons, 3px on badges, 0 elsewhere.

## Layout

Built for wall displays as much as laptops: portrait and landscape, 390px to 3440px wide.

- One container on every page: nav and content share the same gutters (16px mobile, 48px from 768px) and left edge.
- The feed column is capped at 1200px (its flex basis too), so the data columns (CVE ID, score, bar, badge, age, chevron) stay near the headline instead of across dead space. Inside it the headline absorbs width; the data columns stay fixed. Under a 760px feed the CVE ID column drops out; under 940px the wire's tabs and filters split onto two lines (container queries on the feed column).
- Wire rail: beside the feed from 1200px wide (so 1080px portrait stacks it below the feed), at least 280px, and it takes all the width the capped feed leaves. When the rail is 600px or wider it splits into Elsewhere | stats; Elsewhere items flow into columns and the stat sections sit side by side as the rail grows.
- Home has no rail: its content caps at 1200px, and from 2500px wide the rows flow into two columns (left column first).
- Fill the height with rows, never a fixed count. Home is exactly one screen tall: header, as many whole rows as fit, footer at the bottom; on the All tab, Critical or KEV rows with an event in the last 48h are pinned first with a dim `pinned` marker. Wire loads at least a screenful and scrolls.
- Kiosk: key `f` (or `?kiosk=1`) hides nav and rail and scales type about 15%. `f` again leaves it.
- Check new work at 390x844, 1080x1920, 1440x2560, 1920x1080, 2560x1440 and 3440x1440.

## The row (non-negotiable anatomy)

```
[vendor mark 20px] [headline, one line, ellipsis]              [CVE ID]  [9.8] [██████████] [CRITICAL] [2h] [v]
                   [source · source · source · category · KEV]
```

- Vendor mark: `/public/vendors/{slug}.svg`, monochrome, currentColor at `--muted`, 20px, no circle. Fallback: Lucide category icon (shield-alert for breach, bug for vuln, file-text for advisory, flask for research).
- Headline links to the primary source, `target="_blank" rel="noopener noreferrer"`.
- Meta line: every source name is a link to that outlet's article, same 12px, `--fg-2`. Cap 4 visible, then `+N`. Then category, then `KEV` in `--critical` if listed, else `EXPLOITED` in `--critical` when a headline says zero-day / actively exploited / in the wild and no CVE is known. Separator is `·`.
- Score: Geist Mono 14px/500. `--fg` for 7.0+, `--fg-2` below. Empty for non-CVE rows.
- Bar: 10 cells, 5x10px, 2px gap. Filled = round(CVSS). Fill color by severity: Critical `--critical`, High `--accent`, Medium #6b6b6b. Empty cells `--rule`. Only rendered when the row has a score; unscored rows keep the empty 68px slot so columns align.
- Badge: Geist Mono 10px/500, letterspacing 0.04em, 64px wide. CRITICAL = white on `--critical`. HIGH = `--fg` with `--accent` outline. MEDIUM = `--fg-2` with #333 outline. BREACH (breach and ransomware rows) = `--muted` with #262626 outline. Unscored news, advisory and research rows get no badge, just the empty 64px slot.
- Age: relative, Geist Mono 12px `--muted`. Updates on a timer without reload.
- Chevron: Lucide chevron-down 12px at #404040. Expanded: rotate 180, color `--critical`.

## Expanded row

Click anywhere on the row except a link. Background `--surface`, extends 24px past the row edges. Contents in order:

1. Summary, 3 lines max, 14px, `#b5b5b5`, max-width 720px. Generated once on ingest, cached. Prompt: what it is, who is affected, is there a fix. No adjectives.
2. What to do (CVE rows only), label then label/value lines:
   - `Update to`: first fixed version per affected range, product once then versions in Geist Mono. Source order: NVD CPE `versionEndExcluding`, then the CNA's `lessThan` / unaffected-at versions, then MSRC KBs, then what the summary model read in the articles. `advisory ↗` after the first line.
   - `Workaround`: one sentence from the summary model (only a concrete mitigation the articles name), plus a link to the NVD reference tagged Mitigation when there is one.
   - `KEV due`: CISA's due date, shown as a UTC calendar date, when the CVE is in KEV.
3. `CVSS 3.1 vector` label, then 8 chips: `AV:N / Network` etc. Chip = Geist Mono 12px value over 10px sans label, background `#161616`. Impact-side chips (C, I, A) at High get background `#1c1010`.
4. Impact, Exploitability, EPSS, KEV as label-over-number pairs, Geist Mono 18px.
5. Affected line: version ranges from CPE. Then patch status: `● patched ↗` (link to vendor advisory, or NVD reference tagged Patch), `○ no fix`, or `○ no fix · workaround ↗`.
6. Links right-aligned: Source, Vendor advisory, NVD, then `Copy`. All new tab.

Rules:

- Every section, line and pair renders only when it has data. No dashes, blanks, "unknown", "null", "No summary yet" or loading text anywhere in the expanded row. Unverified patch status is not shown. KEV `no` shows only once enrichment has checked.
- Plain news (no CVE) expands to its summary, when there is one, and the Source link. Nothing else.
- `Copy` (CVE rows) puts a Teams/ticket-ready plain-text block on the clipboard, one fact per line, only lines with data: headline; `CVE · CVSS n.n Severity · CISA KEV`; `Affected:`; `Fixed in:`; `Workaround:`; `KEV due date: YYYY-MM-DD`; blank line; `Source:`, `Vendor advisory:`, `Mitigation:` (only if different from the advisory), `NVD:`.
- The summary model (`ANTHROPIC_API_KEY`) is optional. Without it, What to do comes from NVD, MSRC and KEV alone.

## Right rail (wire only), in this order

1. Elsewhere. Five most recent from the policy/privacy/culture pool (EFF, 404 Media, Citizen Lab, Lawfare, Wired, TechCrunch Security, Ars). Headline 13px + `source · age` 11px. No vendor, no score.
2. Most active this week. Vendor + count.
3. Added to KEV. CVE ID + vendor, last 7 days.
4. Last 7 days. Four 3px bars: Critical, High, Medium, Low.
5. Sources line: count, health, refresh interval.

## Data rules

- Merged stream. A CVE with no article is a row with headline = CVE description, meta = `NVD · CVE published · no coverage yet`. When an article arrives, the row updates in place.
- Dedupe: cluster by any shared CVE ID first; else normalized-title similarity > 0.85 within 48h, same vendor; or same vendor, a shared product alias and "zero-day" in both titles within 48h; or, when at least one row has no vendor (and vendors do not conflict), at least 3 shared distinctive words (stopwords and generic security terms dropped) of which one is a proper noun or product name, within 48h. One row per cluster. Primary source = vendor PSIRT if present, else earliest.
- Sort by last significant event (published, KEV added, PoC published, CVSS changed), not first-seen.
- Vendor tagging: `vendors(slug, name, aliases[], domain, logo_path)`. Match aliases, case-insensitive, word boundaries. A title match wins (earliest, then longest alias). With no title match, the first paragraph must mention the vendor 2+ times or the article stays untagged. The vendor name is not an alias unless listed, so ambiguous names use qualified aliases ("Intel CPU", "Arm Cortex", never bare "Intel" or "Arm"). A vendor feed tags its own vendor. 56 vendors, list in `api/app/seed.py`. Nightly job lists untagged articles.
- Category: classify from the title first; the first paragraph only if the title matches nothing. A CVE with no keyword is vulnerability. Otherwise default to news, never guess breach.
- Skip at ingest: ads (title, URL or first paragraph says sponsored, sponsored by, partner content, webinar, virtual event) and anything dated more than 1 hour in the future. The ad count per run is in `/status`. Some THN sponsored posts carry no marker in the feed and still get through.
- Enrichment: NVD API for vector, base, impact, exploitability, CPE, reference tags. FIRST.org for EPSS. CISA KEV JSON for KEV. Cache all of it.
- Elsewhere is assigned per feed, not per article.
- Timezone: viewer's local, fall back to UTC. Never hardcode PT.

## Sources

Seeded from `api/app/seed.py`. Keep this table and that file in sync. Main feeds become rows. Elsewhere feeds only appear in the rail. Enrichment feeds never become rows; their entries are stored keyed by CVE and attached to rows about that CVE. A vendor feed is linked to its vendor and wins primary-source selection.

| Name | Stream | Vendor | Feed URL |
|---|---|---|---|
| BleepingComputer | main | | https://www.bleepingcomputer.com/feed/ |
| The Record | main | | https://therecord.media/feed |
| SecurityWeek | main | | https://www.securityweek.com/feed/ |
| Dark Reading | main | | https://www.darkreading.com/rss.xml |
| Krebs on Security | main | | https://krebsonsecurity.com/feed/ |
| The Hacker News | main | | https://feeds.feedburner.com/TheHackersNews |
| CISA | main | | https://www.cisa.gov/cybersecurity-advisories/all.xml |
| Rapid7 | main | | https://www.rapid7.com/blog/rss/ |
| Unit 42 | main | | https://unit42.paloaltonetworks.com/feed/ |
| Palo Alto Networks | main | palo-alto-networks | https://security.paloaltonetworks.com/rss.xml |
| MSRC | enrichment | microsoft | https://api.msrc.microsoft.com/update-guide/rss |
| EFF | elsewhere | | https://www.eff.org/rss/updates.xml |
| 404 Media | elsewhere | | https://www.404media.co/rss/ |
| Citizen Lab | elsewhere | | https://citizenlab.ca/feed/ |
| Lawfare | elsewhere | | https://www.lawfaremedia.org/feeds/articles |
| Wired | elsewhere | | https://www.wired.com/feed/category/security/latest/rss |
| TechCrunch | elsewhere | | https://techcrunch.com/category/security/feed/ |
| Ars Technica | elsewhere | | https://arstechnica.com/security/feed/ |

- MSRC: the RSS gives one entry per CVE revision and is stored in `msrc_updates`. Product, KBs, fixed builds and the exploited flag come from the Security Update Guide API (`api.msrc.microsoft.com/sug/v2.0`), fetched only for CVEs on the board and refetched when MSRC revises them. Exposed on `/items/{id}` as `msrc`.
- CISA advisories: some networks get a 403 from cisa.gov (seen on a residential connection; Railway fetches it fine). Locally it may show as failing; that is expected.

NVD, FIRST.org EPSS and the CISA KEV JSON are enrichment APIs, not feeds, and are not in this table.

## Motion (all respect prefers-reduced-motion)

- Wordmark dot pulses 2.4s while live. Solid if last sync > 30 min. Gray if fetch failing.
- Status line clock ticks seconds.
- New rows fade in from top over 300ms with a 1px `--critical` left edge that fades over 10s.
- Bar cells fill left to right, 25ms per cell, on first paint and for new rows.
- Nothing else moves. No hover lifts, no bounce, no parallax, no background effects.

## Unseen-item indicators

- When a poll finds new rows and `document.hidden` is true: title becomes `(3) darkwire`, or `(3!) darkwire` if any new row is Critical or KEV.
- Favicon swaps to a copy with a static red dot drawn via canvas. Never blinking.
- Both clear on `visibilitychange` when the tab is visible. Nothing stored between visits.
- Opt-in bell in the status line: requests Notification permission only on click, sends one grouped notification for Critical/KEV additions only. Never prompt on load.
- With a stack set, only stack rows count toward the title and dot.

## Your stack (no accounts)

- `?stack=slug,slug` on every page. Every internal link carries it, so any URL is shareable as-is.
- `/vendors`: a toggle per vendor updates the URL; "View my stack on the wire" appears when any are selected.
- Wire with a stack: "My stack" tab first (all categories, stack vendors only), brighter vendor mark and a dim `your stack` in the meta line on other tabs, one quiet line under the counts when the stack has nothing Critical or KEV in 24h: "Nothing critical in your stack today."
- "remember on this browser" in the footer, off by default. When on, localStorage keeps only `{stack, theme}` under `darkwire.prefs`; the footer then reads `remembered · reset`. The URL always overrides it, and a stack arriving in a shared link is never written to storage.
- No service worker, no offline cache, no feed data in the browser.

## Themes

- `?theme=darkwire|amber|phosphor|high-contrast`; darkwire is the default and is never written to the URL. Links carry a non-default theme like they carry the stack.
- Every theme redefines the same variables under `html[data-theme=...]` in `globals.css`. Components never know which theme is on.
- Severity stays red and the loudest thing in every theme: amber and phosphor run text in a desaturated tone of their hue; high-contrast is pure black and white with a red chosen so both white-on-red and red-on-black clear 4.5:1.
- A head script sets `data-theme` before paint (URL first, then a remembered theme). Picker: four words in the footer. Remembered only when "remember on this browser" is on.

## Keyboard

`j` / `k` move, `enter` expand, `o` open primary source, `/` focus search, `f` kiosk (hide nav and rail, bigger type; also `?kiosk=1`).

## Banned

Purple, indigo, gradients, glassmorphism, glow, blobs, particles, rounded-2xl, Inter as display, emoji, sparkle icons, three-card feature grids, centered hero copy, marketing verbs (unlock, supercharge, seamless, empower), cookie banners, newsletter modals, autoplay, marquees.

## Working rules

- Read `/design-refs/*.png` before touching any page.
- Screenshot your work at 1440 and 390 with Playwright and compare before saying done.
- `npm run build` clean before every commit.
- Real RSS from the first commit. No mock data in the repo.
- Small commits, one page or one component each.
