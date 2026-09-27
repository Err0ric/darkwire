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
| `/` | Home. Status header, latest 8 rows, four tabs, OPEN WIRE link. Meant to be left open. |
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

## The row (non-negotiable anatomy)

```
[vendor mark 20px] [headline, one line, ellipsis]              [CVE ID]  [9.8] [██████████] [CRITICAL] [2h] [v]
                   [source · source · source · category · KEV]
```

- Vendor mark: `/public/vendors/{slug}.svg`, monochrome, currentColor at `--muted`, 20px, no circle. Fallback: Lucide category icon (shield-alert for breach, bug for vuln, file-text for advisory, flask for research).
- Headline links to the primary source, `target="_blank" rel="noopener noreferrer"`.
- Meta line: every source name is a link to that outlet's article, same 12px, `--fg-2`. Cap 4 visible, then `+N`. Then category, then `KEV` in `--critical` if listed. Separator is `·`.
- Score: Geist Mono 14px/500. `--fg` for 7.0+, `--fg-2` below. Empty for non-CVE rows.
- Bar: 10 cells, 5x10px, 2px gap. Filled = round(CVSS). Fill color by severity: Critical `--critical`, High `--accent`, Medium #6b6b6b. Empty cells `--rule`. Always render all 10 cells so rows align.
- Badge: Geist Mono 10px/500, letterspacing 0.04em, 64px wide. CRITICAL = white on `--critical`. HIGH = `--fg` with `--accent` outline. MEDIUM = `--fg-2` with #333 outline. BREACH/INFO = `--muted` with #262626 outline.
- Age: relative, Geist Mono 12px `--muted`. Updates on a timer without reload.
- Chevron: Lucide chevron-down 12px at #404040. Expanded: rotate 180, color `--critical`.

## Expanded row

Click anywhere on the row except a link. Background `--surface`, extends 24px past the row edges. Contents in order:

1. Summary, 3 lines max, 14px, `#b5b5b5`, max-width 720px. Generated once on ingest, cached. Prompt: what it is, who is affected, is there a fix. No adjectives.
2. `CVSS 3.1 vector` label, then 8 chips: `AV:N / Network` etc. Chip = Geist Mono 12px value over 10px sans label, background `#161616`. Impact-side chips (C, I, A) at High get background `#1c1010`.
3. Impact, Exploitability, EPSS, KEV as label-over-number pairs, Geist Mono 18px.
4. Affected line: version ranges from CPE. Then patch status: `● patched ↗` (link to vendor advisory, or NVD reference tagged Patch), `○ no fix`, `○ no fix · workaround ↗`, or `○ unverified`.
5. Links right-aligned: Source, Vendor advisory, NVD. All new tab.

## Right rail (wire only), in this order

1. Elsewhere. Five most recent from the policy/privacy/culture pool (EFF, 404 Media, Citizen Lab, Lawfare, Wired, TechCrunch Security, Ars). Headline 13px + `source · age` 11px. No vendor, no score.
2. Most active this week. Vendor + count.
3. Added to KEV. CVE ID + vendor, last 7 days.
4. Last 24 hours. Four 3px bars: Critical, High, Medium, Low.
5. Sources line: count, health, refresh interval.

## Data rules

- Merged stream. A CVE with no article is a row with headline = CVE description, meta = `NVD · CVE published · no coverage yet`. When an article arrives, the row updates in place.
- Dedupe: cluster by CVE ID first; else normalized-title similarity > 0.85 within 48h, same vendor. One row per cluster. Primary source = vendor PSIRT if present, else earliest.
- Sort by last significant event (published, KEV added, PoC published, CVSS changed), not first-seen.
- Vendor tagging: `vendors(slug, name, aliases[], domain, logo_path)`. Match aliases against title + first paragraph, case-insensitive, word boundaries. Nightly job lists untagged articles.
- Enrichment: NVD API for vector, base, impact, exploitability, CPE, reference tags. FIRST.org for EPSS. CISA KEV JSON for KEV. Cache all of it.
- Elsewhere is assigned per feed, not per article.
- Timezone: viewer's local, fall back to UTC. Never hardcode PT.

## Motion (all respect prefers-reduced-motion)

- Wordmark dot pulses 2.4s while live. Solid if last sync > 30 min. Gray if fetch failing.
- Status line clock ticks seconds.
- New rows fade in from top over 300ms with a 1px `--critical` left edge that fades over 10s.
- Bar cells fill left to right, 25ms per cell, on first paint and for new rows.
- Nothing else moves. No hover lifts, no bounce, no parallax, no background effects.

## Keyboard

`j` / `k` move, `enter` expand, `o` open primary source, `/` focus search, `f` kiosk (hide nav and rail, bigger type).

## Banned

Purple, indigo, gradients, glassmorphism, glow, blobs, particles, rounded-2xl, Inter as display, emoji, sparkle icons, three-card feature grids, centered hero copy, marketing verbs (unlock, supercharge, seamless, empower), cookie banners, newsletter modals, autoplay, marquees.

## Working rules

- Read `/design-refs/*.png` before touching any page.
- Screenshot your work at 1440 and 390 with Playwright and compare before saying done.
- `npm run build` clean before every commit.
- Real RSS from the first commit. No mock data in the repo.
- Small commits, one page or one component each.
