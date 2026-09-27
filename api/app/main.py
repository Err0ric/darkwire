import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import SessionLocal, engine
from app.enrich import schedule as schedule_enrich
from app.ingest import scheduler, start_scheduler
from app.routers import cves, feed, kev, services, status, vendors
from app.services import schedule as schedule_services
from app.seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with SessionLocal() as session:
        await seed(session)
    if get_settings().ingest_enabled:
        schedule_enrich(scheduler)
        schedule_services(scheduler)
        start_scheduler()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await engine.dispose()


app = FastAPI(title="darkwire", docs_url="/docs", redoc_url=None, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_origin_regex=get_settings().cors_origin_regex,
    allow_methods=["GET"],
    allow_headers=["*"],
)
for r in (feed.router, cves.router, kev.router, vendors.router, status.router, services.router):
    app.include_router(r)


# Live data: browsers and CDNs must never serve these from cache.
NO_STORE = ("/feed", "/status", "/services")


@app.middleware("http")
async def no_store(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(NO_STORE):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"ok": True}
