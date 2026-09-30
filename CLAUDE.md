# darkwire.tech

Live board of security news and CVEs. One merged feed, tagged by vendor, scored by CVSS, flagged by KEV. No accounts, no email, no ads, no tracking. Someone opens it in the morning and leaves it on a second monitor.

Reference mockups: `/design-refs/home.png` and `/design-refs/wire.png`. Match them. When in doubt, do less.

This file is the spec. Measurements and tuning values live in the code (component comments and the exported `WORDMARK` / `ACTIVITY` configs); change them there.

## Stack

- Backend: FastAPI + PostgreSQL (SQLAlchemy 2, Alembic, APScheduler for ingest jobs), on Railway with its Postgres plugin.
- Frontend: Next.js (App Router) + TypeScript + Tailwind. shadcn/ui only for primitives (select, input, dialog); everything else is plain markup.
- Fonts: Geist Sans (UI), Geist Mono (data), via `next/font`.
- Hosting: API on Railway, web on Vercel. Monorepo: `/api` and `/web`, `docker-compose.yml` at the root for local Postgres.
- Local dev: `docker compose up -d`, `uvicorn` in `/api`, `npm run dev` in `/web`. `NEXT_PUBLIC_API_URL` points at localhost:8000 locally and the Railway domain in prod.
- Icons: Lucide, stroke only. Never emoji.

## Pages

| Route | Purpose |
|---|---|
| `/` | A calm landing page on one screen: the wordmark lockup, the board's last 24 hours as a trace and a short log, the latest headline, and the way into the wire. |
| `/wire` | The board: the full feed with tabs, vendor filter, search and rails. The all-day screen. |
| `/cves` | Every CVE on the board in one sortable, filterable table, expanding into the same detail as the wire. |
| `/vendors`, `/vendor/[slug]` | Pick vendors for your stack; everything tagged to one vendor over the last 14 days. |
| `/item/[id]`, `/cve/[id]` | Permalinks that open the expanded row. |
| `/services` | Third-party service status: what is impacted now, and 24 hours of history per service. |
| `/sources` | Every feed we ingest, how tagging works, what KEV and EPSS mean. Plain, not a pitch. (Not built yet.) |
| `/feed.xml`, `/feed.json` | Our own output for other people's tools. (Not built yet.) |

No pricing, login, signup, newsletter, about-us hero, or footer CTA. Ever.

- Every page has exactly one H1 and the same page header (`PageHeader`): the title in the wire clock's slot, the counts line under it. The wire's clock is its title.
- A page that cannot render (usually the API not answering) shows the same header titled "Feed unreachable" with "Try again" and "Home", never the framework's default screen.
- Nav, on every page: the wordmark; `WIRE` (a small outlined button, red outline on `/wire`) and Vendors; on the right `Services` (a status dot only when something is wrong, the detail in an instant tooltip), `CVEs`, the UTC time (not on `/` or `/wire`, which show their own), "Synced N min ago", and the theme picker (an icon, never a dot).

### Landing (`/`)

- Three clusters, tight inside and about 48px apart at 1080px tall: identity (wordmark and tagline), live (date line, trace, log), action (ticker, OPEN WIRE, CVEs · Vendors · Services). The stack link sits just above the footer. No scrolling at 1920x1080 or 2560x1440; vertically centered.
- The tagline ends exactly under the ink of the typed "h" of ".tech"; the trace is as wide as the lockup's ink. Both are measured, and nothing shifts when they are.
- Trace: rows per hour over 24 hours, scaled against the busiest hour of the last 7 days, so a quiet day shows small blips. Hours with a Critical, KEV or exploited row are red. A short bright pulse travels along it.
- Log: three lines, newest on the bottom, no article headlines (ingest, KEV, NVD and services events only). A new event types in on the bottom line as the others move up; after 30s of quiet the last 10 events replay in time order. Fewer than 3 lines: the log folds away and the ticker moves up.
- Ticker: the latest 10 headlines, one every 8s, capped at the column width.

## Design system

Palette. Use CSS variables, never hardcode in components.

| Token | Value | Use |
|---|---|---|
| `--bg` | #0a0a0a | page |
| `--surface` | #0f0f0f | expanded row band |
| `--hairline` | #161616 | table and list dividers (/cves, /vendors, /services) |
| `--rule` | #1f1f1f | section dividers, wire row dividers, empty bar cells |
| `--fg` | #f5f5f5 | headlines, primary text |
| `--fg-2` | #a3a3a3 | source links, secondary |
| `--muted` | #8b8b8b | meta text, labels (5.6:1; was #737373, which fails 4.5:1) |
| `--dim` | #525252 | lines, borders and non-text marks only, never text |
| `--dim-text` | #7d7d7d | tertiary text: timestamps in rail, separators, pinned (4.66:1 on `--bg` and `--surface`) |
| `--row-hover` | #111111 | wire row hover (each theme sets its own) |
| `--accent` | #b91c1c | outlines, HIGH, the wordmark's i-dot when stale (50%) |
| `--critical` | #dc2626 | CRITICAL fill, outlines, focus ring |
| `--critical-text` | #e14343 | red text: KEV, EXPLOITED, arrows, errors (4.6:1) |

Every text color clears 4.5:1 on `--bg` and `--surface` (axe-checked); fade with a color token, never with opacity on text. Red is a signal, not a paint job. If more than ~5% of a screen is red, it is wrong.

Type: Geist Sans for words, Geist Mono for data (CVE IDs, scores, timestamps, vector chips, badges, status line). One scale: 11, 12, 13, 15 and 20px, plus the page title / wire clock (36px, 28px under 1200px) and the wordmark (nav 16/18px, landing `clamp(40px, 3.2vw, 64px)`). Nothing else. Headline 15px/500 tracking -0.01em. Meta 12px. Section labels 13px/500 in sans, never mono-caps. Badges and chip labels 11px; scores 15px; metric numbers 20px.

Details: thin dark scrollbars (`--rule` thumb on `--bg`), a red-tinted selection (`--critical` at 32%), antialiased font smoothing.

Layout: no boxes, no cards, no panel borders. Separate regions with background tone and 1px hairlines. 48px page gutter on desktop, 16px on mobile. Wire rows: 15px padding above and below, 56px minimum height, 4px from headline to meta, so the gap between rows is clearly larger than the gap inside one. Radius: 4px on inputs and buttons, 3px on badges, 0 elsewhere.

## Layout

Built for wall displays as much as laptops. Primary targets: 1920x1080 and 2560x1440 landscape; secondary: 1080x1920 and 1440x2560 portrait; plus 390px phones. Wider screens (3440) just work and are not tuned for.

- One container on every page (`page-frame`): nav and content share the same gutters and left edge. From 1600px on a landscape screen it is a centered block as wide as the wire's three columns (`--left-rail-w`, `--rail-w`, `--col-gap` and the feed's cap `--feed-max`, 1120px, in `globals.css`) once that is narrower than the screen; extra width goes to equal outer margins. The feed never grows past `--feed-max`, so short headlines stay near their data columns.
- The feed column keeps the data columns (CVE ID, score, bar, badge, age, chevron) near the headline; the headline absorbs width. Narrow feeds drop the CVE ID column and split the tabs and filters onto two lines (container queries).
- Loading skeletons (`loading.tsx`) in each page's real shape, and space reserved for anything filled in after mount, so nothing moves when data arrives. CLS under 0.05 at every size. Fill the height with rows, never a fixed count.
- Sticky header: the nav sticks on every page. On `/wire` from 900px, once the tabs reach the top, a condensed bar (compact counts, clock, nav) takes over with the tabs, day labels and "N new ↑" stuck under it; under 900px only the nav sticks. Nothing sticky shifts layout.
- Kiosk: key `f` (or `?kiosk=1`) hides nav and rail and scales type about 15%. `f` again leaves it.
- Tap targets: at 390px wide every link, button and input is at least 44x44 (invisible hit areas, `max-md:tap`); nothing changes on desktop.
- Check new work at 1920x1080 and 2560x1440 first, then 1080x1920, 1440x2560 and 390x844.

## The row (non-negotiable anatomy)

```
[vendor mark 20px] [headline, one line, ellipsis]              [CVE ID]  [9.8] [██████████] [CRITICAL] [2h] [v]
                   [source · source · source · category · KEV]
```

- Phones: the age ends the meta line; the score / bar / badge line shows only when the row has one.
- Rows with no CVE ID, score, bar or badge drop those columns: the headline runs to the age. Rows with data keep the aligned columns.
- Headline: `--fg`, 15px/500, line-height 1.35, at most 72ch wide, wrapping to at most two lines (ellipsis). Icon column and text column keep one hard left edge on every row (marks left-aligned in a fixed 20px column).
- Vendor mark: `/public/vendors/{slug}.svg`, monochrome, `--muted`, 20px, no circle; with no logo, the Lucide category icon (never initials).
- Only the headline text links to the primary source (new tab, `noopener noreferrer`); a click anywhere else on the row, its open panel included, or Enter/Space when it has focus, toggles it. Links and buttons keep their own behavior, a click that ends a text selection in the row does not toggle (so summaries and CVE IDs can be copied), and Esc closes an open row (`web/lib/toggle.ts`; `/cves` rows too). An open row's header and panel share one band and one hover.
- Meta line: 12px Geist Mono in `--muted`, one line. Each source name links to that outlet's article (no underline until hover or keyboard focus), one name per outlet (its newest), at most 4 then `+N`; then category, then `KEV` in red if listed, else `EXPLOITED` in red when a headline says zero-day / actively exploited / in the wild and no CVE is known, else `POC` in red when the articles state a public proof of concept (quote-verified, `api/app/facts.py`). Separator `·`.
- Flag edge: KEV, exploited or Critical rows (not old CVEs) get a 2px `--rail-critical` line down the full row height, in the gutter just left of the icon, so nothing shifts. `--rail-critical` is set per theme.
- KEV due: within 7 days of CISA's due date the marker reads `KEV due in Nd` (all red at 2 days or less, `KEV due today` on the day), and `KEV overdue` for 7 days after it. Days count in UTC. These rows count toward the unseen `!`.
- Old CVEs: published more than 90 days ago, not in KEV, and no headline about exploitation: the score, bar and badge dim. Such rows are left out of severity totals, pinning and the unseen `!`.
- Score: Geist Mono 15px/500, `--fg` for 7.0+, `--fg-2` below. Bar: 10 cells, filled = round(CVSS), colored by severity (Critical `--critical`, High `--accent`, Medium #6b6b6b), empty cells `--rule`; unscored rows keep the empty slot so columns align.
- Badge: CRITICAL white on `--critical`, HIGH `--fg` with an `--accent` outline, MEDIUM `--fg-2` with a #333 outline, BREACH (breach and ransomware) `--muted` with a #262626 outline. Unscored news, advisory and research rows get the empty slot.
- Age: relative, updates on a timer; under a day separator older than today, the local clock time with the relative age on hover.
- Chevron: rotates and turns red when expanded. A plain row with nothing to expand has none.

## Expanded row

Background `--surface`, extending past the row edges. Contents in order, each only when it has data:

1. Summary (at most 3 lines). With no summary (declined, or the article fetch failed), the stored RSS excerpt under a `From the feed` label in `--muted`, attributed: `BleepingComputer: “…”`.
2. One list, values at one size (CVE rows): `Affected` (ranges from CPE, else MSRC's product, else the articles' words labeled `per article`), `Fixed` (first fixed version per affected range, from NVD CPE, then the CNA, then MSRC KBs, with `advisory ↗`; only when none of those has one, the articles' version, or one line per release branch, labeled `per article`), `KEV` (`yes` in red with CISA's due date, UTC; `no` once enrichment has checked) or else `Exploited` `yes` in red, then `Workaround` (one sentence from the model plus the NVD Mitigation reference).
3. `CVSS 3.1 vector`: 8 chips (`AV:N / Network` etc.), impact chips at High tinted red, and under them one plain line built from the vector in code ("Remote, no auth, no user interaction"; `web/lib/cvss.ts`).
4. Impact, Exploitability, EPSS as label-over-number pairs.
5. Patch status: `● patched ↗`, `○ no fix`, or `○ no fix · workaround ↗`.
6. Links right-aligned: Source, Vendor advisory, NVD, then `Copy`. All new tab.

Rules:

- No dashes, blanks, "unknown", "null", "No summary yet" or loading text anywhere. Unverified patch status is not shown. KEV `no` shows only once enrichment has checked.
- Plain news (no CVE) expands to its summary (or excerpt) and the Source link, nothing else; with neither it does not expand.
- `Copy` (CVE rows) puts a Teams/ticket-ready plain-text block on the clipboard, one fact per line, only lines with data: headline; `CVE · CVSS n.n Severity · CISA KEV`; `Affected:`; `Fixed in:`; `Workaround:`; `KEV due date: YYYY-MM-DD`; blank line; `Source:`, `Vendor advisory:`, `Mitigation:` (only if different from the advisory), `NVD:`.
- The summary model (`ANTHROPIC_API_KEY`) is optional. Without it, What to do comes from NVD, MSRC and KEV alone.

## Summary model

Claude Haiku writes the row summary and the What to do workaround sentence. Rules, enforced in `api/app/summaries.py`:

- No tools, and no data beyond the article text, wrapped in `<article>` tags the prompt says are material, never instructions. No NVD, KEV, EPSS or vendor data goes in.
- The summary reads every source of the row, up to about 6k tokens, the vendor's own or a government advisory first, then research teams, then news; the first three whose feed text is short are fetched. A row whose sources grew is summarized again, at most every 6 hours (`items.summary_sources`, `summarized_at`); if that attempt fails the old summary stays. "From the feed" shows only when every attempt failed.
- For summaries only, a short feed text is topped up with the article itself, fetched server-side (`api/app/fetcher.py`): robots.txt honored, identified as `darkwire.tech summarizer`, one request per domain every 5 seconds, never stored or shown; failures fall back to the RSS excerpt. Per-domain outcomes are logged.
- The same call returns JSON (structured outputs): the summary, held to every rule here, and what the articles state: in-the-wild exploitation, a public proof of concept, affected products and versions, a fixed version (`api/app/facts.py`). Each needs a quote that appears word for word in the article text the model was given, with the value inside the quote, or it is dropped; stored in `items.facts`. Each must also say the right kind of thing: a public PoC quote says a PoC or exploit is public (published, released, public, available, GitHub, posted), is not negated, and if it names CVEs names the row's displayed one; a fixed version is at least major.minor or a build / release number (not a date, a product name alone, or "v4"); an affected value is software, a product or a platform (not people, customer counts, organization types, sectors, web domains or sites). A fixed version inside the affected range drops both, logged, unless the quotes name separate release branches with one version each, shown one per line with the branch name (`api/app/versions.py`). Vendor, NVD and MSRC version data always come first. A summary that states a fix version inside its own affected range is regenerated once without version numbers, then has its versions stripped if it still conflicts; an ICS advisory row gets its template instead. In-the-wild exploitation is stored but shown nowhere. These show only as `POC` in the meta line and as `per article` fallbacks after vendor data. CVSS, KEV, patch status and vendor fixed versions come only from NVD, CISA and vendor data, never from the model. `app/facts_backfill.py` reads existing rows through the Batch API: a logged dry run first, written only with sign-off.
- At most 2 sentences and 45 words; sentence 2 must add who is affected, scope or status, or it is dropped.
- A fix claim stays only when attributed (to an outlet, "says", or to the vendor as the one who fixed it: "Cisco released updates", "the vendor patched") and backed by the articles, or when vendor/NVD data already says patched. When the vendor backs a fix (vendor/NVD fix data, or the vendor's own advisory on the row, by its domain or feed, reporting one; `summaries.fix_vendor`), a passive claim is kept as the vendor's statement: "Fixed releases are available." becomes "Cisco says fixed releases are available." Otherwise a passive or speculative claim ("was patched", "a fix is available") loses its clause (or sentence). Workaround sentences stay.
- Discard output over the length limit (workaround 25 words), or with a full URL (a scheme, or a domain with a path), markdown, a line break, or the first person. A bare domain in a summary is defanged (`radaris[.]com`) and kept; a workaround with any domain is discarded. Sentences about what the articles do not say are dropped. SKIP only when there is nothing beyond the headline. Discarded output is stored empty so it is not re-asked; each rejection is logged with its reason.
- Bumping `RULES_VERSION` regenerates every summary and workaround; bumping `RETRY_VERSION` re-asks the last 7 days' declined ones once.
- Stale sources: a CISA or vendor advisory on a row (CISA feed, a vendor's own feed, or the row's vendor's domain) is read once more 24-48h after its first read (`api/app/advisories.py`). Only a digest of its fix and affected sentences is kept, never the text. When they changed, the row's summary and facts are made again from the new text (facts replaced; an ICS advisory keeps its template summary) and the change is logged. Nothing else is fetched again.
- `/status` reports the model's health; the wire footer says "Summaries paused." when it is not ok.
- CISA ICS advisory rows never go to the model: their summary is built from stored fields (vendor and product from CISA's title, CVE count, highest CVSS, fix status), leaving out anything missing (`api/app/ics.py`). Model summaries written before stay. `python -m app.ics` dry-runs the rows with no summary; `BACKFILL_VERSION` in that file fills them once, only with sign-off.

## Services

Third-party status from each vendor's official source, polled every 3 minutes (`api/app/services.py`). States: operational, degraded (amber `--degraded`), major (`--critical`), unknown. Statuspage services follow the page's own overall indicator; an incident rated "none" is not an outage. The worst state per UTC hour is kept for 24 hours; incidents for 7 days.

- An open event not updated in 72 hours is stale: it never counts toward a state, the rail or the unseen indicator, and `/services` lists it collapsed under "Stale".
- The rail lists every tracked service: impacted ones first (incident title on hover), then the rest in a compact grid. `?services=aws,m365,slack` picks the viewer's own set (listed first), with the same rules as `?stack=`. Each name opens that service on `/services`, expanded.
- A major outage of a picked service (else of the default set: AWS, Azure, Microsoft 365, Google Cloud, Cloudflare, GitHub, Slack, Okta) fires the unseen indicator like a Critical row.

## Wire

- Rails by width, on landscape screens (portrait always stacks): from 1600px a left rail (Most active, Last 7 days, Added to KEV) and a right rail (Elsewhere, Services), the feed between them at least 860px wide so the CVE ID column stays (it drops under 760px), capped at `--feed-max`; tabs and filters share one line from a 1040px feed (1140px with My stack); 1024-1599px one 300px right rail (Elsewhere, Most active, Last 7 days, Added to KEV, Services); under 1024px they stack below the feed, with impacted services also above it. A thin rule separates rails from the feed.
- Rails are quieter than the feed: `--fg-2` titles, `--muted` items, `--dim-text` numbers, the dark `--rail-*` bars; feed headlines stay the brightest text. Rails are sticky (`web/lib/sticky.ts`).
- Elsewhere: the six most recent relevant items (headlines `--fg`/500) with their topic, the week's top topics as subtitle, "+ N more" opens the Elsewhere tab.
- Most active this week: vendor, bar, count; a name sets the vendor filter, again clears it.
- Added to KEV: CISA's catalog entries of the last 7 days (not only the board's), with the CVSS score and a mini bar; no due dates here. A CVE on the board links to its row, any other to NVD; no link may 404. "+N more" opens the KEV tab.
- Last 7 days: Critical, High, Medium, Low bars; a row with a count filters the wire to that severity (`?severity=`), old CVEs excluded so the list matches the count. The header's 24-hour counts filter with `&window=24h`.
- Footer: "Sources: NVD, CISA KEV, vendor PSIRTs, N feeds. All healthy. Rows update every minute." (or "N failing.", plus "Summaries paused.").
- Header: the counts line ("Last 24h: N critical / N high / N articles · N added to KEV this week") and the clock (HH:MM:SS, zone and UTC).
- Day separators, one per local day of `last_event_at`: "Today", "Yesterday", then "Fri Sep 25", with the date and row count; 28px above, 10px around the label; sticky under the tabs. Not rows: no dot, not counted by "N new ↑", not `<article>`.

## Data rules

- Merged stream. A CVE with no article is a row with headline = CVE description, meta = `NVD · CVE published · no coverage yet`. When an article arrives, the row updates in place.
- Dedupe: cluster by any shared CVE ID first. Title merges need publish times within 72h: with the same vendor, normalized-title similarity > 0.85, or a shared product alias and "zero-day" in both titles; with no vendor on one side (vendors never conflict), the same test on the titles with boilerplate removed (CISA, adds, known, exploited, vulnerability, catalog, KEV, warns, patches, flaw, zero-day, critical, actively, attacks, stopwords; at least 3 words left), or 3 shared distinctive words one of which is a proper noun or product name (`api/app/dedupe.py`). CISA's "Adds N Known Exploited Vulnerabilities to Catalog" alerts: the CVEs an alert lists (read from the alert page, else the KEV catalog for that date when the count matches, `api/app/alerts.py`) decide. When one existing row holds all of them (and no other row does, and it has no alert yet), the alert joins it as a source: the row keeps its headline, time and CVEs and gets KEV. Otherwise the alert starts its own row, holding only its CVEs, which a news article joins only by sharing one when the row holds one CVE, or by holding all of them when it holds several (a single shared CVE never pulls a story into a multi-CVE alert row). News joins news on a shared CVE only when that CVE is a subject CVE of both (in the title or lede, the feed excerpt and first two paragraphs, or named 2+ times; `tagging.subject_cves`). Each subject CVE is logged with its row and the sentence that qualifies it. Alerts never merge with each other or by title and never pull stories in by chaining; a KEV alert's date never sets a row's time unless the row has nothing else. One row per cluster. Primary source = the alert on a row it started, else vendor PSIRT if present, else earliest. The row's displayed CVE is pinned when the row gets its first CVE, among its subject CVEs only (context CVEs never display; every CVE of a row a KEV alert started, and those a joining alert lists, are subjects; with no subject CVE in the stored text, the first linked CVE): one named in the headline first, then a KEV-listed one, then the highest CVSS known then, then the first mentioned (`cve_facts.rank`). Pins are sticky: merges, later articles, roll-ups and re-enrichment never move them; only an explicit signed-off re-pin (`api/app/maintenance.py`) does. The score, severity, EPSS and patch status shown are that CVE's (`api/app/enrich.py` roll-up). `python -m app.split_clusters` (dry run; `--apply` only with sign-off) splits existing rows merged around KEV alerts under the old rules.
- Row time = the earliest `published_at` among the row's news sources (the articles in its cluster), never a CVE, KEV or NVD date (`api/app/rowtime.py`). It sorts the wire, groups it by day and drives the age. A sync moves it back only when a news source genuinely published earlier, and every change is logged (old, new, reason). KEV additions, score changes and new exploitation still surface a row as NEW in live updates (via `items.changed_at`), without rewriting its time. `python -m app.fix_row_times` (dry run; `--apply` only with sign-off) re-derives existing rows.
- Vendor tagging: `vendors(slug, name, aliases[], domain, logo_path)`. Match aliases, case-insensitive, word boundaries. A title match wins (earliest, then longest alias). With no title match, the first paragraph must mention the vendor 2+ times or the article stays untagged. The vendor name is not an alias unless listed, so ambiguous names use qualified aliases ("Intel CPU", "Arm Cortex", never bare "Intel" or "Arm"). A vendor feed tags its own vendor. 56 vendors, list in `api/app/seed.py`. Nightly job lists untagged articles.
- Category: classify from the title first; the first paragraph only if the title matches nothing. A CVE with no keyword is vulnerability. Otherwise default to news, never guess breach. Breach means an incident (a named victim, data stolen or exposed, a confirmed intrusion): a "breach" only in the first paragraph needs an incident word there too, and an explainer, trend piece or webinar title ("Know Your Enemy", "techniques", "how to", "trends") is Research when it is about attacks, else News.
- Skip at ingest: ads (title, URL or first paragraph says sponsored, sponsored by, partner content, webinar, virtual event) and anything dated more than 1 hour in the future. The ad count per run is in `/status`. Some THN sponsored posts carry no marker in the feed and still get through.
- CVE attachment: an article gets only the CVE IDs it ties to its headline: IDs in the title; all when it names three or fewer; IDs in the lead paragraph unless the lead lists a whole bulletin (more than three); the first N when the headline counts them ("Two ... Zero-Days", "2 exploited zero-days"); for exploitation headlines, the IDs in sentences about exploitation or KEV that name three or fewer; IDs mentioned more than once; else the first. Across a cluster the tied IDs are unioned, and a count in one outlet's title fills from another's bulletin list up to that count. A bulletin listed in passing ("the six other flaws ...") does not attach. When the summarizer fetches an article for a row that has no CVE, the IDs that article ties to its headline under these same rules (read from the fetched text with related-article blocks cut, at most 10 per article, never from the model's output) are added to the row: subject CVEs whatever their age; any other only when published within 90 days (NVD's date, else CVE.org's, else treated as recent; `api/app/cve_facts.py`). Then the shared-CVE merge rule is re-checked within 72h, each merge logged (`api/app/article_cves.py`). Never on KEV-alert rows, ICS advisories, or recaps and roundups ("Weekly Recap", "Roundup", "Metasploit"), which also never merge; an article whose CVEs belong to 2+ vendors gets them but merges only into a KEV alert row whose CVEs it holds all of. The alert-row and subject rules above apply here too. Its one-time backfill of the last 9 days logs a dry run (`BACKFILL_MODE`) and applies only with sign-off, and then only to the signed-off rows and merges (`APPLY_ROWS`, `APPLY_MERGES`), followed by a verification dry run.
- Patch status: "patched" needs an NVD reference tagged Patch, or an explicit fixed version (NVD's CPE upper bound, the CNA's "unaffected at", MSRC KBs). A CNA "affected before X" range alone, or a vendor advisory link alone, is not a fix ("unverified"). A headline or lead paragraph saying unpatched / no patch / not yet fixed makes a CVE "no fix" only when vendor/NVD data has no fix for it; fix data wins over headline wording (`enrich.has_fix_data`). A row that goes from no fix to patched is summarized again once, and a patched row's summary drops "unpatched" wording (a sentence that still says there is no fix goes).
- Enrichment: NVD API for vector, base, impact, exploitability, CPE, reference tags. FIRST.org for EPSS. CISA KEV JSON for KEV, polled hourly (inside the 15-minute enrich pass). Cache all of it.
- Vendor · product on `/cves` come as a pair from one source: the first CPE with a product (its vendor field, shown with the seeded vendor's name when it matches), else the CNA's affected list, else the KEV catalog; the row's vendor tag only when none of those say. A Google article about a Windows bug is still Microsoft · Windows.
- Elsewhere is assigned per feed, not per article.
- Timezone: viewer's local, fall back to UTC. Never hardcode PT.

## Board events and /activity

- `board_events` (`api/app/events.py`): what the board did, recorded in the same transaction as the change it describes, kept 7 days, public facts only: `ingest`, `kev`, `nvd`, `cluster`, `services`, `summary`.
- `GET /activity`: rows per hour over 24 hours (by first article's published time), the busiest hour of the last 7 days, and the last events of the last 24 hours, recorded events merged with events derived from the data so the log is full right after a deploy.

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

- Elsewhere uses section feeds where they exist; Lawfare stays on its full feed. A feed removed from `seed.py` is disabled on the next start; its rows age out.
- Elsewhere relevance (`api/app/topics.py`): an item stays only if it is about surveillance, privacy, disinformation, courts (only cases about technology itself), security policy, civil liberties online, cybercrime, security or AI security. Keyword phrases first, then Haiku answering with one topic word, cached in `items.topic`. Science, culture, listicles, reviews, organizations' reports and blog filler are hidden. Bumping `RULES_VERSION` re-classifies the last 7 days.
- MSRC: stored per CVE revision in `msrc_updates`; product, KBs, fixed builds and the exploited flag come from the Security Update Guide API, fetched only for CVEs on the board.
- CISA advisories may 403 from some networks locally; Railway fetches them fine.

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

Generated by `web/scripts/make-og.py` (`npm run og`). The favicon and app icons are a thin `--critical` signal trace on black, a flat baseline with a small spike then a tall one: pixel-snapped on a 16 grid at 16 and 32 (1px and 2px lines), a smooth polyline in the larger icons. The in-page wordmark is separate and unchanged. The link previews (`og.<hash>.png`, animated `og.<hash>.gif`) show the lockup; their names carry a content hash so link unfurlers fetch new images, and `/og.png` / `/og.gif` redirect to the current ones. `docs/banner.png` is the README copy.

## Motion (all respect prefers-reduced-motion)

- Wordmark (`web/components/Wordmark.tsx`, every parameter in `WORDMARK`): "darkwire" with the real Geist i, only its dot in the status color; ".tech" faint, decorative. Live: ".tech" types in on load and again when a poll finds NEW rows (the cursor right after the last typed character, inside the reserved width), then the cursor and dot blink twice in sync and the cursor goes for good. Stale (last sync over 30 min): dimmed red dot, static. Failing: gray dot, static; the nav reads "Feed unreachable · retrying". Reduced motion: static, solid red dot.
- The wire clock ticks seconds; the landing's date line and the nav's UTC time change each minute.
- New rows fade in from the top and get a small red dot left of the headline (in the gutter, so nothing shifts): three pulses, then solid, gone at 10 minutes; expanding the row clears it. Rows that arrive while the tab is hidden pulse on return. More than 5 at once: only the top 5 pulse. No dots on first load. Reduced motion: a solid dot.
- Bar cells fill left to right on first paint and for new rows.
- Landing: the ticker's scramble swap (encode out, decode in) and the wordmark's typing are the only text animations; the trace pulse and the log's typing are part of the activity block. Reduced motion: crossfade, static trace and log.
- Hover: wire rows take `--row-hover` (no border, no radius); other rows and rail items `--surface`. Behind `NEXT_PUBLIC_HOVER_PREVIEW=1` (off by default; on in production), hovering a headline for 550ms, or keyboard focus on the headline link itself, shows the row's summary in a card right of the headline (it flips under it at the viewport edge): `--bg`, 1px `--rule` border, no shadow, no arrow, at most 360px wide and 3 lines, a 120ms fade (none under reduced motion); gone on leave, blur, Esc or scroll; never on touch, never on an expanded row, never without a summary (the list response carries it). Nothing else. Focus: a 1px `--critical` ring on `:focus-visible` only, set globally.
- Nothing else moves. No hover lifts, no bounce, no parallax, no background effects.

## Live updates

- `/wire` and `/` poll `GET /feed?since=<newest last_event_at>&changed_since=<previous poll, less 3 min>` every 60s, hidden or not. `/feed`, `/status`, `/services` and `/activity` send `Cache-Control: no-store`. No service worker, no feed data in localStorage.
- NEW: a row that was not on screen and is newer than everything on screen, or an on-screen row that escalated (became KEV, Critical or EXPLOITED). It goes to the top, counts toward the unseen indicators and gets the new-row dot.
- Not new: a source added, an age change, a summary filled in, an EPSS change. The row updates in place, silently.
- Scrolled down on `/wire`, new rows are not inserted above the viewer: a `N new ↑` button under the tabs inserts them, as does scrolling back to the top.
- Home: new rows lead the ticker; a new board event enters the log.
- Ages update every 60s without a refetch.

## Auto-update on deploy

- `NEXT_PUBLIC_BUILD_ID` is `VERCEL_GIT_COMMIT_SHA` at build time (`dev` locally). `/api/version` returns `{ build }`, no-store.
- Every open page checks it every 5 minutes and reloads a new build at a safe moment: at once if hidden, else on the next switch to hidden, or after 2 minutes idle. Never while a row is expanded or a text field has focus. The URL is kept.

## Unseen-item indicators

- When a poll finds NEW rows while `document.hidden`: the title becomes `(3) darkwire`, or `(3!) darkwire` if any is Critical or KEV, and the favicon's trace turns a brighter red, #ff4d4d (static, never blinking). Both clear when the tab is visible. Nothing stored between visits.
- Opt-in bell: requests Notification permission only on click, one grouped notification for Critical/KEV additions only; never prompt on load. (Not built yet.)
- With a stack set, only stack rows count.
- `/wire?preview=unseen` shows the indicators on demand: 10s after load, two fake rows (one Critical, both titled "Preview: … (not real)") go through the same path as a poll's new rows, in that tab only (`web/lib/preview.ts`). Nothing is fetched or stored; the poll ignores them.

## Your stack (no accounts)

- `?stack=slug,slug` on every page. Every internal link carries it, so any URL is shareable as-is.
- `?stack=` and `?services=` (and their remembered copies) keep only known vendor / service slugs (`web/lib/stack.ts`, which `npm test` checks against `seed.py` and `services.py`); anything else is dropped. No URL or storage value is ever built into script code: the `<head>` theme script is a constant that reads its allowed names from `<html data-themes>`.
- `/vendors`: vendors by rows this week, the quiet ones last; a toggle per vendor updates the URL; "View my stack on the wire" when any are selected.
- Wire with a stack: "My stack" tab first, stack rows marked on other tabs, and "Nothing critical in your stack today." when that is so.
- "remember on this browser" is the footer's only control, shown only when a stack is set (or already remembered), off by default. When on, localStorage keeps only `{stack, theme}` under `darkwire.prefs`. The URL always overrides it, and a stack arriving in a shared link is never written to storage.
- No service worker, no offline cache, no feed data in the browser.

## Themes

- `?theme=darkwire|amber|phosphor|high-contrast`; darkwire is the default and never written to the URL. Links carry a non-default theme like the stack.
- Every theme redefines the same variables under `html[data-theme=...]` in `globals.css`. Components never know which theme is on.
- Severity stays red and the loudest thing in every theme; high-contrast picks a red that clears 4.5:1 both ways.
- A head script sets `data-theme` before paint (URL first, then a remembered theme). Remembered only with "remember on this browser".

## Keyboard

`j` / `k` move, `enter` expand, `o` open primary source, `/` focus search, `f` kiosk (hide nav and rail, bigger type; also `?kiosk=1`).

## Banned

Purple, indigo, gradients, glassmorphism, glow, blobs, particles, rounded-2xl, Inter as display, emoji, sparkle icons, three-card feature grids, centered hero copy, marketing verbs (unlock, supercharge, seamless, empower), cookie banners, newsletter modals, autoplay, marquees.

## Working rules

- Read `/design-refs/*.png` before touching any page.
- Screenshot your work at 1440 and 390 with Playwright and compare before saying done.
- Screenshots in `design-refs` say where their data came from (local DB or prod) in the commit message or the report that cites them. Never hand-edit rows in a database used for review screenshots without reverting the edit afterwards.
- Stop local servers when done, including their child `node` processes (stopping the shell can leave `next start` running); never leave a build pointed at the prod API running.
- `npm run lint`, `npm test` and `npm run build` clean before every commit (in `/web`); API tests with `python -m unittest discover -s tests` (in `/api`). `npm run test:e2e` (Playwright, against a running site; `BASE_URL` to target production) checks that malicious URL and storage values run nothing.
- Real RSS from the first commit. No mock data in the repo.
- Small commits, one page or one component each.
