# Claude Code kickoff for darkwire.tech

## Before you start

Nothing exists yet, so start clean.

1. `mkdir darkwire && cd darkwire && git init`
2. Copy `CLAUDE.md` to the folder root.
3. Copy `design-refs/home.png` and `design-refs/wire.png` into `design-refs/`.
4. `git add . && git commit -m "design spec and refs"`
5. Create the GitHub repo: `gh repo create Err0ric/darkwire --private --source=. --push` (or make it on github.com and add the remote). Railway needs it to exist before the API can deploy.
6. Start `claude` in the folder.

Docker Desktop should be running for the local Postgres.

Recommended add-ons in Claude Code before the first prompt (each is one command, all optional but the first two matter):

- Anthropic `frontend-design` skill (already added)
- Playwright MCP, so it screenshots its own work: `claude mcp add playwright npx @playwright/mcp@latest`
- shadcn MCP: `claude mcp add shadcn npx shadcn@latest mcp`
- Context7 for current Next.js docs: `claude mcp add context7 npx @upstash/context7-mcp`

## Prompt 0: monorepo and API skeleton

```
Read CLAUDE.md and both images in /design-refs before doing anything.

Create the monorepo: /api and /web, docker-compose.yml at the root with Postgres 16, a root README with the three local-dev commands, and a .gitignore that covers Python, Node, and .env files.

In /api: FastAPI, SQLAlchemy 2 (async), Alembic, APScheduler, httpx, feedparser. Models for: sources (feed url, name, stream main|elsewhere, health), items (the clustered row: headline, primary url, vendor_id, category, cve_id, cvss, severity, kev, epss, patch_status, summary, last_event_at), item_sources (each outlet's article in the cluster), vendors (slug, name, aliases[], domain, logo_path), cves (raw NVD enrichment). First Alembic migration. Endpoints: GET /feed (filters: tab, vendor, q, limit, since), GET /items/{id}, GET /cves, GET /vendors, GET /elsewhere, GET /status (last sync, source health, counts). Stub the ingest job so it runs on a schedule but only logs for now.

Seed 12 sources from the RSS list in CLAUDE.md and 40 vendors with aliases. Railway-ready: read DATABASE_URL and PORT from env, start with uvicorn. Run it locally against docker compose, hit /status, commit.
```

## Prompt 1: scaffold and shell

```
Scaffold /web as a Next.js App Router project with TypeScript and Tailwind. Set up next/font with Geist Sans and Geist Mono. Put the palette from CLAUDE.md into globals.css as CSS variables and configure Tailwind to use them. Install shadcn and add only: select, input, dialog.

Build the layout shell: nav (wordmark with the pulsing dot, Wire / CVEs / Vendors, "Synced N min ago" on the right) and nothing else. Dark only, no theme toggle.

Add lib/api.ts that reads NEXT_PUBLIC_API_URL and exposes typed fetchers. Stub the types for FeedItem, Vendor, and CveDetail based on the row anatomy in CLAUDE.md, then look at /api to align them with what FastAPI actually returns and tell me where they differ.

Screenshot at 1440 and 390 with Playwright. Compare to /design-refs/wire.png for spacing and type. Run npm run build. Commit.
```

## Prompt 2: the row

```
Build components/FeedRow.tsx exactly per the "The row" and "Expanded row" sections of CLAUDE.md. Props come from the FeedItem type. Include the 10-cell bar, the badge variants, the chevron, the multi-source meta line with the +N overflow, and the expanded state with vector chips, scores, affected line, patch status, and links.

Every external link: target="_blank" rel="noopener noreferrer".

Build a /dev/row page that renders one row per severity plus a breach row, a CVE-only row, and one expanded. Screenshot it. Compare pixel spacing to the Palo Alto expanded row in /design-refs/wire.png. Iterate until it matches. Delete /dev before committing.
```

## Prompt 3: the wire

```
Build /wire per CLAUDE.md: "Today" header with the counts line, seven text tabs with underline active state, vendor select and search on the right, the feed of FeedRow components, and the right rail in the order specified (Elsewhere, Most active, Added to KEV, Last 24 hours, sources line). Rail is plain text, no boxes.

Wire it to the real API. If an endpoint doesn't exist yet in /api, add it (FastAPI) rather than mocking. No mock data in the repo.

Client-side: tabs and vendor filter update the list without a full reload. Poll every 15 minutes; new rows fade in per the Motion section. Age strings update every 60s.

Screenshot at 1440 and 390. Mobile: headline wraps to 2 lines, badge and bar move into the meta row, rail stacks below the feed. Build, commit.
```

## Prompt 4: home

```
Build / per CLAUDE.md and /design-refs/home.png: status header (date at 22px, mono status line with ticking clock, OPEN WIRE link with red outline), four tabs, latest 8 rows, the "latest 8 · full feed on the wire" note, footer line with sources. No rail. Same FeedRow component. Build, screenshot, commit.
```

## Prompt 5: ingest and data rules

```
In /api, implement per the Data rules section of CLAUDE.md:
- vendors table with aliases and logo_path; seed with the top 40 vendors by headline volume
- alias matcher on ingest
- dedupe clustering (CVE ID, then title similarity within 48h)
- NVD enrichment (vector, sub-scores, CPE ranges, reference tags), EPSS from FIRST, KEV from CISA
- patch status derivation from reference tags + CPE upper bound
- "last significant event" timestamp for sort order
- Elsewhere feed pool, per-feed assignment
- /feed.xml and /feed.json output

Add a script that pulls monochrome SVGs from the simple-icons npm package into /web/public/vendors/{slug}.svg for every seeded vendor, and logs which ones it couldn't find so I can source them manually.

Write tests for the alias matcher and dedupe against 50 real headlines from the last week.
```

## Prompt 6: remaining pages and polish

```
Build /cves (sortable table), /vendor/[slug], /item/[id] and /cve/[id] permalinks that open the expanded row, and /sources. Add keyboard shortcuts per CLAUDE.md. Add empty states for tabs with nothing today. Add the stale state (status line red, dot stops pulsing) when last sync > 30 min. Lighthouse pass. Build, commit.
```

## Deploying the API (after prompt 0 is pushed)

Come back to the Cowork chat and say "deploy the API." Railway is connected there, so I can create the darkwire project, add Postgres, attach the `Err0ric/darkwire` repo with `/api` as the root directory, set `DATABASE_URL`, and generate a domain. You then put that domain in Vercel as `NEXT_PUBLIC_API_URL`.

## Things to say when it drifts

- "That looks like the default. Reread the Banned section and the two PNGs."
- "Less. Remove the border."
- "Mono is for data only. That label should be sans."
- "Screenshot it and compare before you tell me it's done."
