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
| `/` | Home, a calm landing page. A centered block, max 880px, about half the viewport tall with black space around it: the lockup as centerpiece, as in og.png: the nav's wordmark at `clamp(40px, 3.2vw, 64px)` (red i-dot, typing ".tech", see Motion) with "live security news + CVEs" in 13px Geist Mono `--muted` under it, its right ink edge exactly on the right ink edge of the fully typed "h" of ".tech" (measured at runtime: canvas `actualBoundingBoxRight` on the wordmark's invisible reserve "h" and on the tagline's last glyph via a Range, applied as a transform, re-measured on resize and when fonts are ready, so typing never moves it and nothing shifts; the cursor's space hangs outside, so the lockup centers on the visible text); 20px below, a 15px date line `Sunday, Sep 27 · 14:09 PDT · 21:09 UTC` (date sans `--fg-2`, times mono `--fg-2`, dots `--dim-text`; UTC viewers see only UTC) updating each minute; the lockup and date line sit on the same center axis as the activity trace and OPEN WIRE; the activity block (`web/components/home/Activity.tsx`, every setting in its exported `ACTIVITY` config: colors, opacity, pulse speed and on/off, trace and log on/off, typing speed, cycle interval): a thin SVG trace up to 760px wide and 60px tall over 24 hourly slots from `/activity`, each hour a spike whose height is the square root of its row count against the busiest single hour of the last 7 days (`peak_7d` from `/activity`; `scaleBasis` in the config), so a quiet day draws small blips and a busy one tall spikes (any non-zero hour at least 3px), so quiet hours stay visible bumps and one busy hour does not flatten the rest, flat when none; line #3a1414, hours with a Critical, KEV or exploited row in `--critical` at 60%; a short bright `--critical` segment with a small dot travels along it left to right every 8s; under it "-24h" and "now" in 11px mono `--dim-text`. Then a 3-line log, 12.5px mono, newest on the bottom, as a block centered on the page axis and as wide as its longest line (in `ch`, the typing line at full length, plus the cursor; the width eases over 200ms when lines change), lines left-aligned inside so the columns line up, with no article headlines: only ingest (source and count), kev (CVE ID), nvd (CVE ID and score) and services (service and state change) events (`kinds` in the config; cluster and summary events are still recorded): "18:12  kev      CVE-2026-88772 added" (time `--dim-text`, since #555 fails 4.5:1; type `--fg-2`; detail `--dim-text`; KEV, critical and exploited in `--critical-text`); older lines dimmer by stepping through text tokens, not opacity, which would fail 4.5:1: the middle line's type column in `--muted`, the top line all `--dim-text`. A new event (the 60s poll) enters on the bottom line and types in at 25ms a character with a faint block cursor that fades, as the older lines slide up and the top one fades out, and the trace takes the new counts; quiet for 30s, the last 10 events come back one at a time every 30s, the same way. Fewer than 3 real lines (`hideWhenFewer` in the config): the log folds away (height to 0 over 200ms, instant under reduced motion) and the ticker moves up under the trace; with the flag at 0 the log stays, showing one line "watching N sources…" (N from `/status`) with the faint cursor when empty. The 3-line height is reserved from the first render. Reduced motion: static lines, no pulse, no typing, no cycling. Hidden tab: frames stop and a new event enters on return. Heights are fixed from the first render. Then a 13px ticker crossfading through the last 10 headlines every 8s, OPEN WIRE (40px, 13px mono) with CVEs · Vendors · Services under it, and the stack link. No status line or clock: those live on `/wire`. The nav shows its wordmark here too, and hides its UTC time. Footer: sources line from `/status`, darkwire.tech. No scrolling at 1920x1080 or 2560x1440; vertically centered in portrait. |
| `/wire` | The board. Full feed, seven tabs, vendor filter, search, right rail. |
| `/cves` | Every CVE on the board, one table of two-line rows (about 48px): Vendor (vendor `--fg` over product `--muted`, as a pair from CPE, else the CNA, else the KEV catalog, else the row's tag; empty if unknown), CVE / Description (CVE ID mono `--fg-2`, links to `/cve/[id]`, over the NVD description in one truncated `--fg-2` line, full text on hover; the widest column), CVSS (score and the 10-cell bar), EPSS (percent, 1 decimal; under 1% `--dim`, over 10% `--fg`), KEV (`--critical`), Patch (as in the expanded row, plus `○ unverified`), Published ("Sep 24", local). No placeholders. The Vendor header sorts alphabetically. Default order KEV first, then CVSS, then newest; headers sort. Search (ID, vendor, product, description) and chips KEV only, Critical, High, Has fix, No fix that combine and live in the URL (`?kev=1&sev=critical&q=citrix`). A row click expands the wire's expanded row in place. Subheader "N CVEs on the board · CVSS from NVD, EPSS from FIRST, KEV from CISA", or "12 of 84 …" when filtered. |
| `/vendor/[slug]` | Everything tagged to one vendor over the last 14 days, as wire rows. Header: vendor name, "N rows in the last 14 days · N with a CVE · N in KEV · N this week", and an "Open on the wire" link (`/wire?vendor=`). `/vendors` links here. |
| `/item/[id]`, `/cve/[id]` | Permalinks that open the expanded row. |
| `/services` | Third-party service status (was `/outages`, which redirects here permanently). Header "Services" and "22 tracked · N impacted · checked Nm ago", then one legend line (swatches operational · degraded · major · no data, "each block = 1 hour, your local time"). "Impacted now": one full-width line per impacted service (dot, name, `degraded`/`major`, incident title linking to the vendor page, age), major first then most recent; "All N services operational." when none. Then the four groups (Cloud, Identity, Collaboration, Dev) as columns separated only by gap: 4 from 1600px, 2x2 from 1200px, stacked below. Each group: 13px/500 label over a hairline, a time axis for the strips ("-24h", "-12h", "now" in 11px mono `--dim-text`, aligned to the cells), then per service a name line (dot, name, state word only when impacted, and right-aligned a summary: for a service impacted now only its impacted hours in the state's color, "6h of 24h" or "6h since 11:00" when tracking is shorter, since the name line already says the state; otherwise "100%" in `--dim-text` when every tracked hour was operational, else "degraded 6h" / "major 2h" in their colors, plus "since 16:00" when tracking covers under 24h) over the 24-cell strip (operational `--strip-ok`, amber degraded, red major, no data = outlined). Each cell has an instant custom tooltip "14:00–15:00 · degraded" on hover, and on focus (the strip is one tab stop; arrow keys move, Home/End jump). Clicking a service name opens an inline panel: its incidents of the last 7 days, one line each (severity, title linking to the vendor's incident page, local start–end, duration), or "No incidents in the last 7 days", and the status page link. Incidents come from `service_incidents` (recorded every poll; Statuspage services backfilled hourly from their incident history). Stale events stay collapsed, full width, below. Nav link "Services". |
| Nav | Main links: `WIRE` as a small outlined button (Geist Mono 12px/500, 0.06em, 1px outline, 4px radius, about 4px 10px; on `/wire` outline `--critical` and text `--fg`, elsewhere outline `--accent` at 60% and text `--fg-2`, full `--critical` on hover; no fill, no glow), then Vendors as a plain link (Services lives in the status indicator). Right side: `Services` (`web/components/NavServices.tsx`), a quiet link styled like CVEs to `/services`, fed by the same watched set and 3-minute poll as the rail (`web/lib/services-live.ts`); a dot before the word only when something is wrong (amber `--degraded` when any service is degraded, `--critical` when any has a major outage, worst wins), none when all are operational; hover and focus show an instant tooltip with the detail ("Cloudflare degraded", "AWS major outage" (+N), "3 services degraded", "All services operational"), which is also the dot's aria-label. Same on every page and in the condensed bar. Then `CVEs` as a quiet link (`--muted`, `--fg` when active), `·` and the UTC time (not on `/` and `/wire`, whose own lines show UTC; there CVEs sits right next to "Synced", same spacing), "Synced N min ago", then the theme picker (a 14px Lucide "contrast" icon in `--muted`, `--fg` on hover, aria-label "Theme"; never a dot, so it cannot read as a status light). One shared container with the pages. The wordmark (see Motion) shows on every page. |
| `/sources` | Every feed we ingest, how tagging works, what KEV and EPSS mean. Plain, not a pitch. |
| `/feed.xml`, `/feed.json` | Our own output for other people's tools. |

No pricing, login, signup, newsletter, about-us hero, or footer CTA. Ever.

Errors: a page that cannot render (usually the API not answering) shows the same page header titled "Feed unreachable" with "Try again" and "Home" (`web/app/error.tsx`), never the framework's default screen. Every page has exactly one H1 (permalinks carry a screen-reader H1 with the headline).

Page header (`web/components/PageHeader.tsx`), the same on every page: 24px top padding (33px from 768px), the title in the wire clock's slot at its size (36px/700, -0.02em, 44px line; 28px under 1200px), then the counts line 3px below (15px, words `--muted`, numbers `--fg`). The wire's clock is its title. No other H1 sizes.

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
| `--muted` | #8b8b8b | meta text, labels (5.6:1; was #737373, which fails 4.5:1) |
| `--dim` | #525252 | lines, borders and non-text marks only, never text |
| `--dim-text` | #7d7d7d | tertiary text: timestamps in rail, separators, pinned (4.66:1 on `--bg` and `--surface`) |
| `--accent` | #b91c1c | outlines, HIGH, the wordmark's i-dot when stale (50%) |
| `--critical` | #dc2626 | CRITICAL fill, outlines, focus ring |
| `--critical-text` | #e14343 | red text: KEV, EXPLOITED, arrows, errors (4.6:1) |

Every text color clears 4.5:1 on `--bg` and `--surface` (axe-checked); fade with a color token, never with opacity on text. Red is a signal, not a paint job. If more than ~5% of a screen is red, it is wrong.

Type: Geist Sans for words, Geist Mono for data (CVE IDs, scores, timestamps, vector chips, badges, status line). One scale: 11, 12, 13, 15 and 20px, plus the page title / wire clock (36px, 28px under 1200px) and the wordmark (nav 16/18px, landing `clamp(40px, 3.2vw, 64px)`). Nothing else. Headline 15px/500 tracking -0.01em. Meta 12px. Section labels 13px/500 in sans, never mono-caps. Badges and chip labels 11px; scores 15px; metric numbers 20px.

Details: thin dark scrollbars (`--rule` thumb on `--bg`), a red-tinted selection (`--critical` at 32%), antialiased font smoothing.

Layout: no boxes, no cards, no panel borders. Separate regions with background tone and 1px hairlines. 48px page gutter on desktop, 16px on mobile. Row height 64px. Radius: 4px on inputs and buttons, 3px on badges, 0 elsewhere.

## Layout

Built for wall displays as much as laptops. Primary targets: 1920x1080 and 2560x1440 landscape; secondary: 1080x1920 and 1440x2560 portrait; plus 390px phones. Wider screens (3440) just work and are not tuned for.

- One container on every page (`page-frame`): nav and content share the same gutters (16px mobile, 48px from 768px) and left edge. From 2200px wide it is a centered block as wide as the wire's fluid columns: rails `clamp(300px, 15vw, 380px)`, feed `clamp(880px, 48vw, 1200px)`, gaps `clamp(48px, 3.5vw, 96px)` (`--rail-w`, `--feed-w`, `--col-gap` in `globals.css`), with outer margins of at least 48px; extra width goes to equal outer margins. The nav's wordmark lines up with the left rail's left edge and its right end (Synced, theme dot) with the right rail's right edge; pages without rails left-align to the same block.
- The feed column fills what the rail leaves from 1200 to 2199px, and takes `--feed-w` from 2200px, so the data columns (CVE ID, score, bar, badge, age, chevron) stay near the headline instead of across dead space. Inside it the headline absorbs width; the data columns stay fixed. Under a 760px feed the CVE ID column drops out; under 940px the wire's tabs and filters split onto two lines (container queries on the feed column).
- Wire rail: see "Wire rails". Under 1200px (so 1080px portrait) it stacks below the feed, at most 640px wide, and the Services block moves to the top of the feed, under the counts, so an outage is seen without scrolling.
- Home has no rail and no feed: one centered block, max 880px; the clock scales with the width and the gaps with the height, so it scales smoothly instead of jumping at breakpoints.
- Loading: `/`, `/wire`, `/cves` and `/services` have a `loading.tsx` skeleton (static `--hairline` blocks, `web/components/Skeleton.tsx`) in the page's real shape: same header, row heights (64px wire rows, 48px CVE rows, the landing's 60px trace and 18px log line) and columns, so nothing moves when data arrives. Anything filled in after mount (ages, clocks) reserves its space from the first render. Target CLS under 0.05 at every size. Fill the height with rows, never a fixed count. Home is exactly one screen tall with the block vertically centered. Wire loads at least a screenful and scrolls.
- Sticky header: the nav is sticky on every page (full width, `--bg`, a 1px `--rule` line under it once the page scrolls, drawn as a shadow so it stays 60px). On `/wire` from 900px wide the nav and page header scroll away instead, and once the tabs row reaches the top a condensed bar (44px, `--bar-h`, fixed, `--bg` with a `--rule` bottom border) fades in over 150ms (instant under reduced motion): wordmark without ".tech", WIRE, Vendors, compact counts ("1 crit / 0 high / 8 articles · 12 KEV", same clicks), the clock (HH:MM:SS, 15px mono, seconds `--dim-text`), the services status, CVEs, Synced (from 1400px) and the theme icon. The tabs row sticks right under it, the day labels under the tabs (`--tabs-h`, measured), "N new ↑" under them, rails 24px under the bar. Back at the top the full header returns. Under 900px only the nav sticks (the tabs row scrolls, to save height) and day labels stick under the nav. Nothing sticky shifts layout (CLS 0 while scrolling).
- Kiosk: key `f` (or `?kiosk=1`) hides nav and rail and scales type about 15%. `f` again leaves it.
- Tap targets: at 390px wide every link, button and input is at least 44x44. Small ones get an invisible `::before` hit area (`max-md:tap`, or `max-md:tap-down` for meta links under a headline, which grows downward only); inputs are 44px tall under 768px. Nothing changes on desktop.
- Check new work at 1920x1080 and 2560x1440 first, then 1080x1920, 1440x2560 and 390x844.

## The row (non-negotiable anatomy)

```
[vendor mark 20px] [headline, one line, ellipsis]              [CVE ID]  [9.8] [██████████] [CRITICAL] [2h] [v]
                   [source · source · source · category · KEV]
```

- Phones (under 768px): the age ends the meta line, right-aligned; the score / bar / badge line under it shows only when the row has one; the chevron keeps its column.
- Rows with no CVE ID, score, bar or badge drop those empty columns: the headline runs to the age column. Rows with data keep the aligned columns.
- Headlines are one line (ellipsis) only on wide landscape screens (over 1600px wide, landscape); narrower and portrait screens (1200-1600px wide, 1080x1920, 1440x2560) wrap them to at most two lines, and the row grows from 64px.
- Vendor mark: `/public/vendors/{slug}.svg`, monochrome, currentColor at `--muted`, 20px, no circle. Fallback: Lucide category icon (shield-alert for breach, bug for vuln, file-text for advisory, flask for research).
- Headline links to the primary source, `target="_blank" rel="noopener noreferrer"`.
- Meta line: every source name is a link to that outlet's article, same 12px, `--fg-2`, with a quiet `#333` underline (`--outline-medium`, 3px offset) so a link is not told apart by color alone. One name per outlet: an outlet with several articles in the cluster links to its newest. Cap 4 visible, then `+N`. Then category, then `KEV` in `--critical` if listed, else `EXPLOITED` in `--critical` when a headline says zero-day / actively exploited / in the wild and no CVE is known. Separator is `·`.
- KEV due: within 7 days of CISA's due date the marker reads `KEV due in Nd` (`KEV` red, the rest `--fg-2`; all red at 2 days or less, `KEV due today` on the day), and `KEV overdue` in red for 7 days after it. Days count in UTC. These rows count toward the unseen `!`.
- Old CVEs: a CVE published more than 90 days ago, not in KEV, and in a row where no headline is about exploitation (exploit, exploited, zero-day, in the wild, under attack) keeps its score but dims: the score and badge text take `--dim-text` (the badge a quiet `#333` outline) and the bar cells 40%. Such rows are left out of severity totals, pinning and the unseen `!`.
- Score: Geist Mono 15px/500. `--fg` for 7.0+, `--fg-2` below. Empty for non-CVE rows.
- Bar: 10 cells, 5x10px, 2px gap. Filled = round(CVSS). Fill color by severity: Critical `--critical`, High `--accent`, Medium #6b6b6b. Empty cells `--rule`. Only rendered when the row has a score; unscored rows keep the empty 68px slot so columns align.
- Badge: Geist Mono 11px/500, letterspacing 0.04em, 64px wide. CRITICAL = white on `--critical`. HIGH = `--fg` with `--accent` outline. MEDIUM = `--fg-2` with #333 outline. BREACH (breach and ransomware rows) = `--muted` with #262626 outline. Unscored news, advisory and research rows get no badge, just the empty 64px slot.
- Age: relative, Geist Mono 12px `--muted`. Updates on a timer without reload.
- Chevron: Lucide chevron-down 12px at #404040. Expanded: rotate 180, color `--critical`.

## Expanded row

Only the headline text is a link (inline, not stretched across the row). A click anywhere else on the row, including the blank space beside the headline, toggles it; so do Enter and Space while the row has focus (visible focus ring). Source links, the CVE ID and the links in the expanded row keep their own behavior. Same on the wire and `/cves`. Background `--surface`, extends 24px past the row edges. Contents in order:

1. Summary, 3 lines max, 15px, `#b5b5b5`, max-width 720px. Generated once on ingest, cached. Prompt: what it is, who is affected, is there a fix. No adjectives.
2. What to do (CVE rows only), label then label/value lines:
   - `Update to`: first fixed version per affected range, product once then versions in Geist Mono. Source order: NVD CPE `versionEndExcluding`, then the CNA's `lessThan` / unaffected-at versions, then MSRC KBs. Never from the summary model. `advisory ↗` after the first line.
   - `Workaround`: one sentence from the summary model (only a concrete mitigation the articles name), plus a link to the NVD reference tagged Mitigation when there is one.
   - `KEV due`: CISA's due date, shown as a UTC calendar date, when the CVE is in KEV.
3. `CVSS 3.1 vector` label, then 8 chips: `AV:N / Network` etc. Chip = Geist Mono 12px value over 11px sans label, background `#161616`. Impact-side chips (C, I, A) at High get background `#1c1010`.
4. Impact, Exploitability, EPSS, KEV as label-over-number pairs, Geist Mono 20px.
5. Affected line: version ranges from CPE. Then patch status: `● patched ↗` (link to vendor advisory, or NVD reference tagged Patch), `○ no fix`, or `○ no fix · workaround ↗`.
6. Links right-aligned: Source, Vendor advisory, NVD, then `Copy`. All new tab.

Rules:

- Every section, line and pair renders only when it has data. No dashes, blanks, "unknown", "null", "No summary yet" or loading text anywhere in the expanded row. Unverified patch status is not shown. KEV `no` shows only once enrichment has checked.
- No summary: the expanded row shows the feed's own excerpt instead, in `--fg-2`, attributed: `BleepingComputer: “…”` (the primary article's RSS excerpt, cleaned of markup, "The post … appeared first on …", "Read more" and a repeated title; its first one or two sentences, at most 220 chars; under 40 chars is none; `api/app/excerpt.py`, sent as `excerpt` on `/items/{id}`).
- Plain news (no CVE) expands to its summary (or the excerpt) and the Source link. Nothing else. A plain row with neither has nothing to expand (`expandable: false` on `/feed`): no chevron (its column keeps its width), no row focus or click, the headline link only.
- `Copy` (CVE rows) puts a Teams/ticket-ready plain-text block on the clipboard, one fact per line, only lines with data: headline; `CVE · CVSS n.n Severity · CISA KEV`; `Affected:`; `Fixed in:`; `Workaround:`; `KEV due date: YYYY-MM-DD`; blank line; `Source:`, `Vendor advisory:`, `Mitigation:` (only if different from the advisory), `NVD:`.
- The summary model (`ANTHROPIC_API_KEY`) is optional. Without it, What to do comes from NVD, MSRC and KEV alone.

## Summary model

Claude Haiku writes the row summary and the What to do workaround sentence. Rules, enforced in `api/app/summaries.py`:

- No tools, and no data beyond the article text: headline, article titles, excerpts and bodies, wrapped in `<article>` tags the prompt says are material, never instructions. No NVD, KEV, EPSS or vendor data goes in.
- Better input, for summaries only (`api/app/fetcher.py`): when a feed's own text is short (under 1,500 chars), the article itself is fetched server-side (the primary source first, at most 2 per row) and its main text extracted with trafilatura, cut to about 4,000 chars. robots.txt is honored (cached a day), requests identify as `darkwire.tech summarizer` (with a link to /sources), at most one request per domain every 5 seconds (robots.txt included), 10s timeout, redirects to another site count as failures. The fetched text is never stored or shown; only the summary is kept. Blocked or failed fetches fall back to the RSS excerpt. Per-domain outcomes (ok, blocked, failed, empty) are logged after each pass (`fetch: ...`), with a coverage line for the last 7 days (`summaries: last 7 days: ...`). Bumping `RETRY_VERSION` re-asks, once, the rows of the last 7 days whose summary was declined or discarded.
- Output renders as plain text only (never HTML or markdown).
- Structured facts (CVSS, KEV, fixed version, patch status) come only from NVD, CISA and vendor data, never from the model.
- Summaries are at most 2 sentences and 45 words. Sentence 2 must add who is affected, scope or status; if it only restates the product or vendor from sentence 1 it is dropped.
- Fix claims (patched, fixed, patch or update available, released a patch, addressed, "fixes a flaw"; a bare noun such as "subsequent patches cause issues" is not one) are allowed only when attributed to the vendor or the outlet ("Cloudflare says it fixed…", "according to BleepingComputer, a patch is available") and the headline or articles report a fix too, or when the row's patch status from vendor/NVD data is already patched. An unattributed claim loses only its clause, or its sentence when the claim is in the main clause; the rest stays. The summary is discarded for this only when fewer than 12 words are left. Workaround sentences stay. The prompt tells the model to state a fix only as an attributed statement. Each rejection is logged with its reason (skip, format, first person, fix claim, length, empty).
- Discard output over the length limit (workaround 25 words), or containing a URL, markdown, a line break, or the first person (refusals, talk about its instructions). Discarded output is stored as empty so it is not re-asked; the row shows no summary. Sentences about what the articles do not say ("No information about remediation is provided.") are dropped before storing; the rest of the summary stays. The model summarizes a bare headline-plus-excerpt item in a sentence or two and replies SKIP only when there is nothing beyond the headline.
- Bumping `RULES_VERSION` wipes every stored summary and workaround so they regenerate under the new rules.
- `/status` reports the model's health (ok, auth failing, quota, error, no key, pending); the rail says "Summaries paused." when it is not ok.

## Services

Third-party status for the rail and `/services`, from each vendor's official source, polled by the API every 3 minutes (`api/app/services.py`, `/services`). States: operational, degraded (amber `--degraded`), major (red `--critical`), unknown (source failing or not read yet). Statuspage services follow the page's own overall indicator; an open incident the vendor rates "none" is not an outage. The worst state per UTC hour is kept for 24 hours. An open event the vendor has not updated in 72 hours is stale: it never counts toward a service's state, the rail, the unseen indicator or the home status line, and `/services` lists it under a collapsed "Stale (no update in 72h+)" group in `--dim`.

- Default set: AWS (all regions, us-east-1 included), Azure, Microsoft 365, Google Cloud, Cloudflare, GitHub, Slack, Okta; its major outages fire the unseen indicator. `?services=aws,m365,slack` picks the viewer's own set instead (listed first in the rail's grid) with the same rules as `?stack=` (URL wins, carried on every link, remembered only with "remember on this browser").
- Rail block (`web/components/wire/Services.tsx`), last in the right rail, every tracked service, compact: the header "Services" with "all services"; impacted services first (major, then degraded), one line each: dot (amber / red), name, state word, age, the incident title in an instant tooltip on hover and focus; then every other service in a 2-column grid, a small `--dim` dot and the name in `--muted`, 12px, tight lines (not reporting: an outlined dot). Services the viewer picked (`?services=` or remembered) lead the grid with names in `--fg-2`, above a thin `--rule` divider. Every name opens that service on `/services` expanded (`?open=slug`). The nav's Services dot reads the same data (all services); a major outage fires the unseen indicator only for a picked service, else one of the default 8.
- A service newly in a major outage fires the unseen-tab indicator like a Critical row.

## Wire rails

Three layouts by viewport width:

- 2200px and wider: three fluid columns in one centered block (left rail `--left-rail-w` = `clamp(260px, 12vw, 300px)`, right rail `--rail-w`, feed `--wire-feed-w` = `--feed-w` plus what the narrower left rail frees, so the block keeps its width; gaps `--col-gap`, 40px between rail sections; rail item text 13px, rail meta 12px). Left rail: Most active this week, Last 7 days, Added to KEV. Right rail: Elsewhere, Services.
- 1200 to 2199px: feed plus one 340px right rail, 48px apart: Elsewhere, Most active this week, Last 7 days, Added to KEV, Services.
- Under 1200px: the rail stacks below the feed: Elsewhere, Most active, Added to KEV, Last 7 days, Services; the impacted services (or one "Services · all N operational" line) also sit above the feed, so an outage is seen without scrolling.

Rail hierarchy (wire only): section titles `--fg-2`, item text `--muted`, numbers and CVE IDs `--dim-text` (only the Last 7 days Critical count stays `--critical-text`), Elsewhere headlines `--fg-2`, Services keeps its state colors; feed headlines stay `--fg`, the brightest text on the page. Rail bars are quieter than the feed's: Last 7 days `--rail-critical` #7f1d1d, `--rail-high` #5a1a1a, `--rail-medium` #3a3a3a, `--rail-low` #2a2a2a; Most active top vendor `--rail-top` #5a5a5a, others `--rail-bar` #3a3a3a. A 1px `--rule` line sits midway in the gap between each rail and the feed, as tall as the rail's content.

Rails are `position: sticky` in the two- and three-column layouts: a rail shorter than the window pins 24px from the top; a taller one scrolls with the page until its bottom is 24px above the window's bottom, then holds (`web/lib/sticky.ts`). On `/wire` they pin under the condensed bar (`--bar-h`).

Sections:

- Services (see Services).
- Elsewhere. The six most recent relevant items (see Sources: Elsewhere relevance): headline 13px, clamped to 2 lines, then `source · age · topic` 11px (the topic in mono `--dim-text`); the section's subtitle names this week's three most common topics. No vendor, no score. New items get the same new-row dot as the main feed (polled every minute). "+ N more" in `--dim-text` opens the wire's Elsewhere tab (after KEV in the tabs row): every relevant Elsewhere item of the last 7 days in the normal row style, without the CVE / score / bar / badge columns and with nothing to expand.
- Most active this week. Vendor (a fixed name column), a thin 3px bar scaled to the top vendor (`--rule` track, #6b6b6b fill, the top vendor `--fg-2`), count. Each name sets the wire's vendor filter (same as the All vendors menu); the active one is underlined like the active tab, and clicking it again clears the filter.
- Added to KEV. From CISA's catalog, not the board: entries with `dateAdded` in the last 7 days, newest first: vendor, CVE ID, then the CVSS score (mono) with a 5-cell mini bar in the rail's severity tokens (`--rail-critical` etc.) (empty when NVD has no score yet). No due dates here: CISA's deadline shows only in the expanded row ("KEV due · CISA deadline for federal agencies"). A CVE with a row on the board links to it (scrolled to and expanded when it is on the current wire view, else `/item/[id]`); any other links to its NVD page in a new tab. No link may 404. When the week's count (the header's) is larger than the rows shown, a last line "+N more" in `--dim-text` opens the wire's KEV tab.
- Last 7 days. Four 3px bars: Critical, High, Medium, Low. Each row with a count filters the wire to that severity over the last 7 days (`?severity=critical`, combinable with tab, vendor, search and stack; old CVEs excluded, so the list matches the count). The active row is underlined like the active tab; clicking it again clears the filter. Zero rows are not clickable. The header's "N critical" and "N high" are 24-hour counts, so they set the filter with a 24-hour window (`?severity=critical&window=24h`) and the row count matches the number clicked. The footer line names the active window.
- Sources line, in the full-width page footer at the bottom of /wire (the landing footer's style, left of the preferences and the domain), not in a rail: "Sources: NVD, CISA KEV, vendor PSIRTs, N feeds. All healthy. Rows update every minute." (or "N failing.", plus "Summaries paused." when the model is not ok).

The feed has day separators, one per local calendar day of `last_event_at` (the sort key): 32px above each (none above the first, under the tabs), a 1px `--rule` line above the label and nothing below it. Label: the day name in 13px/600 `--fg-2` ("Today", "Yesterday", then "Fri Sep 25"), then the date and row count in `--dim` ("Yesterday · Sat Sep 26 · 11 items"; "Today · Sun Sep 27 · 1 item"). The last row of each day has no bottom hairline; the next label's rule does that job. The label is sticky under the tabs row (under the nav below 900px), on `--bg`, until the next day's section pushes it out. Rows under Today show relative age ("6h"); older rows show the local clock time ("14:32") with the relative age on hover, from the same `last_event_at`, so no row shows a time from another day. Separators are not rows: no dot, not counted by "N new ↑", and not `<article>`.

The wire header is one row: the counts line on the left ("Last 24h: N critical / N high / N articles · N added to KEV this week"; "Last 24h:" in `--muted` sans, numbers `--fg`; critical and high apply the 24h severity filter), the clock on the right (HH:MM:SS in Geist Mono 24px, seconds `--dim-text`, then "PDT · 23:18 UTC" in 12px mono `--dim-text` on the same baseline; just "UTC" for UTC viewers), its right edge on the feed's. The tabs row sits directly below; the rails start level with it (103px under the nav). Under 1200px: the counts line, then the clock line, both left-aligned. A screen-reader H1 "The wire" heads the page.

The nav shows the current UTC time ("19:08 UTC", 12px mono `--dim`) before "Synced N min ago" from 1200px wide on `/cves`, `/vendors`, `/services` and permalinks; not on `/` or `/wire`, whose own lines show UTC.

## Data rules

- Merged stream. A CVE with no article is a row with headline = CVE description, meta = `NVD · CVE published · no coverage yet`. When an article arrives, the row updates in place.
- Dedupe: cluster by any shared CVE ID first; else normalized-title similarity > 0.85 within 48h, same vendor; or same vendor, a shared product alias and "zero-day" in both titles within 48h; or, when at least one row has no vendor (and vendors do not conflict), at least 3 shared distinctive words (stopwords and generic security terms dropped) of which one is a proper noun or product name, within 48h. One row per cluster. Primary source = vendor PSIRT if present, else earliest.
- Sort by last significant event (published, KEV added, PoC published, CVSS changed), not first-seen.
- Vendor tagging: `vendors(slug, name, aliases[], domain, logo_path)`. Match aliases, case-insensitive, word boundaries. A title match wins (earliest, then longest alias). With no title match, the first paragraph must mention the vendor 2+ times or the article stays untagged. The vendor name is not an alias unless listed, so ambiguous names use qualified aliases ("Intel CPU", "Arm Cortex", never bare "Intel" or "Arm"). A vendor feed tags its own vendor. 56 vendors, list in `api/app/seed.py`. Nightly job lists untagged articles.
- Category: classify from the title first; the first paragraph only if the title matches nothing. A CVE with no keyword is vulnerability. Otherwise default to news, never guess breach.
- Skip at ingest: ads (title, URL or first paragraph says sponsored, sponsored by, partner content, webinar, virtual event) and anything dated more than 1 hour in the future. The ad count per run is in `/status`. Some THN sponsored posts carry no marker in the feed and still get through.
- CVE attachment: an article gets only the CVE IDs it ties to its headline: IDs in the title; all when it names three or fewer; IDs in the lead paragraph unless the lead lists a whole bulletin (more than three); the first N when the headline counts them ("Two ... Zero-Days", "2 exploited zero-days"); for exploitation headlines, the IDs in sentences about exploitation or KEV that name three or fewer; IDs mentioned more than once; else the first. Across a cluster the tied IDs are unioned, and a count in one outlet's title fills from another's bulletin list up to that count. A bulletin listed in passing ("the six other flaws ...") does not attach.
- Patch status: "patched" needs an NVD reference tagged Patch, or an explicit fixed version (NVD's CPE upper bound, the CNA's "unaffected at", MSRC KBs), AND no headline or lead paragraph in the cluster saying unpatched / no patch / not yet fixed. A CNA "affected before X" range alone, or a vendor advisory link alone, is not a fix ("unverified"). When coverage says unpatched: "no fix" if the vendor data has no explicit fix, "unverified" if it does (they disagree).
- Enrichment: NVD API for vector, base, impact, exploitability, CPE, reference tags. FIRST.org for EPSS. CISA KEV JSON for KEV, polled hourly (inside the 15-minute enrich pass). Cache all of it.
- Vendor · product on `/cves` come as a pair from one source: the first CPE with a product (its vendor field, shown with the seeded vendor's name when it matches), else the CNA's affected list, else the KEV catalog; the row's vendor tag only when none of those say. A Google article about a Windows bug is still Microsoft · Windows.
- Elsewhere is assigned per feed, not per article.
- Timezone: viewer's local, fall back to UTC. Never hardcode PT.

## Board events and /activity

`board_events` (`api/app/events.py`, recorded by the existing pipeline in the same transaction as what they describe, pruned after 7 days by ingest): `ingest` (a main feed added rows: source, "+3 items"), `kev` (a CVE on the board entered KEV: "CVE-… added"), `nvd` (a CVE got its first score or a new one: "scored 9.8 critical"), `cluster` (another outlet joined a story: headline, "4 sources"), `services` (a service changed between known states: "Cloudflare degraded"), `summary` (a row got its summary: headline, "done"). Public facts only. `GET /activity` (no-store): 24 hourly counts of main rows (all, and those now Critical, KEV or exploited), oldest first, the last being the current hour, each row counted at its first article's published time (its first-seen time when no article has one; a future date counts as now); and the last 20 events of the last 24 hours, newest first: recorded board_events merged with events derived from the data (`derived_events`: ingest batches from `item_sources.fetched_at` per source and minute, KEV catalog entries by `dateAdded` at 00:00 UTC, board CVEs scored at NVD's `lastModified`, service incident starts and ends), a derived one dropped when the board recorded the same (kev any time, nvd with the same detail, ingest and services within 10 minutes). Each carries a stable `key`; derived ones have no `id`. So the log has real lines right after a deploy; "watching N sources…" only when there is nothing in 24 hours.

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
| EFF Deeplinks | elsewhere | | https://www.eff.org/deeplinks.xml |
| 404 Media | elsewhere | | https://www.404media.co/rss/ |
| Citizen Lab | elsewhere | | https://citizenlab.ca/feed/ |
| Lawfare | elsewhere | | https://www.lawfaremedia.org/feeds/articles |
| Wired | elsewhere | | https://www.wired.com/feed/category/security/latest/rss |
| TechCrunch | elsewhere | | https://techcrunch.com/category/security/feed/ |
| Ars Technica | elsewhere | | https://arstechnica.com/security/feed/ |
| Schneier on Security | elsewhere | | https://www.schneier.com/feed/atom/ |
| CyberScoop | elsewhere | | https://cyberscoop.com/news/policy/feed/ |

- Elsewhere uses section feeds where they exist (Wired Security, CyberScoop policy, EFF Deeplinks, TechCrunch and Ars security). Lawfare has no working topic feed (its topic URLs return HTML or 403) and The Record has no policy-only feed (it is a main source already), so Lawfare stays on its full feed and every Elsewhere item passes the relevance filter. A feed removed from `seed.py` is disabled on the next start; its rows age out.
- Elsewhere relevance (`api/app/topics.py`): an item stays only if it is about surveillance, privacy, disinformation, courts (only when the case itself is about technology, data, privacy, surveillance, online speech or cybercrime; a trial where tech is incidental is off-topic), security policy, civil liberties online, cybercrime, security (research, breaches, attacks, cryptography) or AI security (attacks on or by AI models and agents). Strong keyword phrases on the headline, then the excerpt, pick the topic; everything else goes to claude-haiku-4-5, which answers with one word (a topic or "off-topic"), cached in `items.topic`, no tools, the article text only, anything but an allowed word discarded. Science, culture, listicles, product reviews, organizations' reports and blog filler are off-topic and hidden; items not classified yet (or when the model is unavailable) show untagged. Topics: surveillance, privacy, disinfo, courts, policy, rights, cybercrime, security, ai-security. Bumping `RULES_VERSION` re-classifies the last 7 days and logs every item whose status changes.
- MSRC: the RSS gives one entry per CVE revision and is stored in `msrc_updates`. Product, KBs, fixed builds and the exploited flag come from the Security Update Guide API (`api.msrc.microsoft.com/sug/v2.0`), fetched only for CVEs on the board and refetched when MSRC revises them. Exposed on `/items/{id}` as `msrc`.
- CISA advisories: some networks get a 403 from cisa.gov (seen on a residential connection; Railway fetches it fine). Locally it may show as failing; that is expected.

NVD, FIRST.org EPSS and the CISA KEV JSON are enrichment APIs, not feeds, and are not in this table.

Feed audit: `AUDIT_TOKEN=... python -m app.audit [--api URL] [--feed NAME] [-v]` in `/api` re-fetches each feed and labels every entry with the ingest rules: kept, merged, elsewhere, ad, future-dated, too old, invalid, or not on board. `/status` carries each source's counts from its last fetch in `last_counts`.

## API protection

In `api/app/throttle.py` and `api/app/main.py`:

- Rate limits per client IP (slowapi, in memory): 120 requests/min shared across all read endpoints; 10/min for `/feed?all_sources=true` or any request asking for `limit` > 100. A 429 carries `Retry-After`.
- Client IP: Railway's edge sets `X-Real-IP`; it (or the last `X-Forwarded-For` hop) is trusted only on Railway or from a private/loopback peer. Spoofed headers were checked not to change the key in production.
- `limit` is clamped to 100 on public requests. Larger limits and `all_sources` need `X-Audit-Token` matching the Railway variable `AUDIT_TOKEN` (the feed audit tool sends it).
- Optional `SSR_TOKEN` (Railway) / `API_SERVER_TOKEN` (Vercel, server-only): server-rendered page requests carry it as `X-SSR-Token` and skip the per-IP bucket, since Vercel's servers share IPs across visitors.
- `/docs`, `/redoc`, `/openapi.json` exist only locally (off when `RAILWAY_ENVIRONMENT_NAME` is set).
- CORS: GET only, from `https://darkwire.tech`, `https://www.darkwire.tech` and localhost:3000. Fixed in code.
- Every response: `Strict-Transport-Security: max-age=63072000; includeSubDomains` (no preload on the API host), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`; uvicorn runs with `--no-server-header`.
- Every 5 minutes the API logs how many read requests were server renders (SSR bucket) vs per-IP; counts only.
- Never commit a token value. Tokens are compared in constant time.

Web (`web/proxy.ts`, `web/next.config.ts`): a Content-Security-Policy with a per-request nonce (`script-src 'self' 'nonce-…' 'strict-dynamic'`; `connect-src 'self'` plus the API origin; `img-src 'self' data:` for the favicon dot; `style-src 'self' 'unsafe-inline'`; `font-src 'self'`; `object-src 'none'`; `frame-ancestors 'none'`; `base-uri` and `form-action 'self'`). Next.js puts the nonce on its scripts; the root layout on the theme script. Every page renders per request anyway, so nonces cost nothing. Plus HSTS (2 years, subdomains, preload), `nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, a `Permissions-Policy` denying camera, microphone, geolocation and interest-cohort, `X-Frame-Options: DENY`, and no `X-Powered-By`. The web app asks the API for at most 100 rows a request (`/cves` pages through up to 500).

## Icons and link previews

All from one design, generated by `web/scripts/make-og.py` (`npm run og`): the favicon (16 and 32), `app/icon.svg`, the apple-touch-icon and the 192/512 manifest icons are a lowercase "d" in #f5f5f5 and a block cursor in #991b1b on #000, drawn cell by cell on a 16px grid (d stem x 8-9, y 2-14; bowl x 3-8, y 5-14; one empty column; cursor x 11-13, y 2-14: as tall as the d, about 40% of its width) so 16 and 32 are crisp; the larger ones scale the same design into the central 60% (maskable safe zone). The in-page wordmark keeps the red i-dot; only the icons use the "d". `public/og.<hash>.png` is the static lockup ("darkwire" with the red i-dot, faint ".tech", the tagline right-aligned to its end). `public/og.<hash>.gif`: frame 1 is that same finished lockup, then ".tech" fades, types in with the binary effect, the cursor and the dot blink twice in sync, and it holds; one 8-color palette, under 300KB. The names carry a content hash (a new URL for every change, so Discord and other link unfurlers fetch the new image); `web/lib/og-images.json` holds the current names for the page metadata, and `/og.png` / `/og.gif` redirect to them for old links. `docs/banner.png` is the README copy.

## Motion (all respect prefers-reduced-motion)

- Wordmark (`web/components/Wordmark.tsx`, every parameter in its exported `WORDMARK` config): "darkwire" in Geist Sans 700, -0.03em, the i drawn as the real Geist glyph with only its dot red (a copy of the "i" in the status color layered over the white one, clipped to everything above the x-height, so the dot keeps Geist's own shape, size and gap); then ".tech" in Geist Mono 400 at 0.55em, baseline-aligned, #4a4a4a, -0.04em (decorative, exempt from contrast). The width of ".tech" plus the cursor is reserved, so nothing shifts. It types in: one character every ~0.7s, each first a very dim red binary digit (#3d1a1a) that changes once, then fading into the character over ~350ms, a faint cursor after the text (0.4em wide, the mono x-height tall, #4a4a4a at 40%, on the baseline). Then the cursor and the red dot blink together twice, in sync (one cosine curve, 1 -> 0.25 -> 1, ~1.8s each), the cursor goes entirely and the dot stays solid; a timer settles the mark at the end even when animation frames stop (a background or occluded window), so the cursor never stays. Stale and failing states show a static ".tech" and never a cursor. It runs once on page load and again when a poll finds NEW rows (".tech" fades out over ~0.8s, 300ms pause, types again); a hidden tab queues one run for when it is visible. Dot states: live `--critical`; stale (last sync over 30 min) `--accent` at 50%, no animation; failing #525252, no animation. Reduced motion: static "darkwire.tech", solid red dot. The link reads "darkwire.tech" (aria-label); the animated parts are aria-hidden. Shown in the nav on every page (".tech" hidden under 640px so the nav fits) and at landing size in the lockup. Plain requestAnimationFrame, no libraries. When the API does not answer, the nav status reads "Feed unreachable · retrying" in red, it retries every 15s, and the last good data stays on screen.
- The wire clock ticks seconds; the landing's date line and the nav UTC time change each minute.
- New rows (see Live updates) fade in from the top over 300ms and get a 6px `--critical` dot just left of the headline, inside the gutter, so the headline does not shift. The dot fades in over 300ms, pulses opacity 1 -> 0.3 -> 1 three times on the 2.4s cycle (about 7.5s), then holds solid at 60%. At 10 minutes it fades out over 1s. Expanding the row clears it at once.
- A row that arrived while the tab was hidden gets a solid dot; its three pulses start on the next visibilitychange to visible, so a returning viewer sees them.
- More than 5 new rows in one poll: only the top 5 pulse; the rest get the solid dot (fade in to 60%).
- No dots on first page load: everything on screen at load is baseline.
- Reduced motion: a solid 60% dot, no pulse, gone at 10 minutes.
- Bar cells fill left to right, 25ms per cell, on first paint and for new rows.
- Landing ticker (`/` only) advances every 8s with one of the two allowed text animations (the other is the wordmark's ".tech"): encode out (~300ms, the old headline's characters flip to random 0/1 right to left in `--critical`), then decode in (~700ms, red 0/1 glyphs the length of the new headline resolve left to right with a small random stagger, unresolved glyphs re-randomize every 50ms, spaces stay spaces), then the meta fades in over 200ms. Glyphs are Geist Mono at the headline size; the line is locked to the new headline's width, overflow clipped. The scramble is aria-hidden; a visually hidden `aria-live="polite"` element gets the real headline once per swap, and the link points at the new article from the start. Reduced motion: 200ms crossfade. Hidden tab: instant swap. No glow, no blur, no other text animation anywhere besides the wordmark. Nothing scrolls.
- Hover: rows (wire, /cves, /vendors, /services) and rail items take a `--surface` background; nothing else changes on hover. Focus: everything focusable shows a 1px `--critical` ring with a 2px offset on `:focus-visible` only (keyboard), never on mouse click; set globally in `globals.css`.
- Nothing else moves. No hover lifts, no bounce, no parallax, no background effects.

## Live updates

- `/wire` and `/` poll `GET /feed?since=<newest last_event_at>&changed_since=<previous poll, less 3 min>` every 60s, hidden or not (the unseen count depends on it). The API returns rows with a newer event or any newer change (`items.changed_at`) and sends `Cache-Control: no-store` on `/feed`, `/status` and `/services`. No service worker, no feed data in localStorage.
- NEW: a row that was not on screen and is newer than everything on screen, or an on-screen row that escalated (became KEV, became Critical, or got EXPLOITED). New rows go to the top, count toward the unseen title and favicon dot, and get the new-row dot.
- Not new: a source added, an age change, a summary filled in, an EPSS change. The row updates in place, silently.
- Scrolled down on `/wire` (more than 160px), new rows are not inserted above the viewer: a small `N new ↑` button is pinned under the tabs. Clicking it scrolls to the top and inserts them; scrolling back to the top inserts them too.
- Home: new rows lead the ticker; `/activity` is read with each poll, and a new board event types into the log line.
- Ages update every 60s without a refetch.

## Auto-update on deploy

- `NEXT_PUBLIC_BUILD_ID` is `VERCEL_GIT_COMMIT_SHA` at build time (`dev` locally). `/api/version` returns `{ build }`, dynamic, `Cache-Control: no-store`.
- Every open page checks it every 5 minutes. A different build reloads the page at a safe moment: at once if the tab is hidden, else on the next switch to hidden, or after 2 minutes with no pointer or key activity. Never while a row is expanded or a text field has focus. The full URL is kept. It logs `darkwire: new build <sha>, reloading` first.

## Unseen-item indicators

- When a poll finds NEW rows (see Live updates) and `document.hidden` is true: title becomes `(3) darkwire`, or `(3!) darkwire` if any new row is Critical or KEV.
- Favicon swaps to a copy whose cursor block is #ef4444 instead of #991b1b, drawn via canvas. Never blinking, never animated.
- Both clear on `visibilitychange` when the tab is visible. Nothing stored between visits.
- Opt-in bell in the status line: requests Notification permission only on click, sends one grouped notification for Critical/KEV additions only. Never prompt on load.
- With a stack set, only stack rows count toward the title and dot.

## Your stack (no accounts)

- `?stack=slug,slug` on every page. Every internal link carries it, so any URL is shareable as-is.
- `/vendors`: vendors sorted by rows this week (most first), then alphabetically; the ones with none this week come last in `--dim-text` under a thin `--rule` divider labeled "Quiet this week". Each name opens `/vendor/[slug]`; a toggle per vendor updates the URL (a "+" with an instant "Add to stack" label on hover and focus, or a check mark with "In your stack · remove"; custom tooltip, never the native title); "View my stack on the wire" appears when any are selected.
- Wire with a stack: "My stack" tab first (all categories, stack vendors only), brighter vendor mark and a dim `your stack` in the meta line on other tabs, one quiet line under the counts when the stack has nothing Critical or KEV in 24h: "Nothing critical in your stack today."
- "remember on this browser" is the footer's only control, shown only when a stack is set (or the browser already remembers), off by default. When on, localStorage keeps only `{stack, theme}` under `darkwire.prefs`; the footer then reads `remembered · reset`. The URL always overrides it, and a stack arriving in a shared link is never written to storage.
- No service worker, no offline cache, no feed data in the browser.

## Themes

- `?theme=darkwire|amber|phosphor|high-contrast`; darkwire is the default and is never written to the URL. Links carry a non-default theme like they carry the stack.
- Every theme redefines the same variables under `html[data-theme=...]` in `globals.css`. Components never know which theme is on.
- Severity stays red and the loudest thing in every theme: amber and phosphor run text in a desaturated tone of their hue; high-contrast is pure black and white with a red chosen so both white-on-red and red-on-black clear 4.5:1.
- A head script sets `data-theme` before paint (URL first, then a remembered theme). Picker: the "contrast" icon in the nav's top right, next to "Synced N min ago", opening the list of theme names. Remembered only when "remember on this browser" is on.

## Keyboard

`j` / `k` move, `enter` expand, `o` open primary source, `/` focus search, `f` kiosk (hide nav and rail, bigger type; also `?kiosk=1`).

## Banned

Purple, indigo, gradients, glassmorphism, glow, blobs, particles, rounded-2xl, Inter as display, emoji, sparkle icons, three-card feature grids, centered hero copy, marketing verbs (unlock, supercharge, seamless, empower), cookie banners, newsletter modals, autoplay, marquees.

## Working rules

- Read `/design-refs/*.png` before touching any page.
- Screenshot your work at 1440 and 390 with Playwright and compare before saying done.
- `npm run lint` and `npm run build` clean before every commit (in `/web`).
- Real RSS from the first commit. No mock data in the repo.
- Small commits, one page or one component each.
