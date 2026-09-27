import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import SessionLocal, engine
from app.ingest import scheduler, start_scheduler
from app.routers import cves, feed, status, vendors
from app.seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with SessionLocal() as session:
        await seed(session)
    if get_settings().ingest_enabled:
        start_scheduler()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await engine.dispose()


app = FastAPI(title="darkwire", docs_url="/docs", redoc_url=None, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)
for r in (feed.router, cves.router, vendors.router, status.router):
    app.include_router(r)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"ok": True}
