# darkwire.tech

Live board of security news and CVEs. See `CLAUDE.md` for the spec.

- `api/` FastAPI + PostgreSQL. Deployed on Railway.
- `web/` Next.js. Deployed on Vercel.

## Local dev

```sh
docker compose up -d
cd api && alembic upgrade head && uvicorn app.main:app --reload
cd web && npm run dev
```

First time in `api/`: `python -m venv .venv`, activate it, `pip install -r requirements.txt`, `cp .env.example .env`.

The API seeds sources and vendors on startup and runs ingest every 15 minutes. `GET /status` shows sync state and source health. Docs at `http://localhost:8000/docs`.

## Deploy

Railway service root: `api/`. It reads `DATABASE_URL` and `PORT` from the environment. `api/railway.json` runs migrations, then uvicorn.
