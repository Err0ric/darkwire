# The API app: routers, rate limits, CORS, security headers, and the ingest/enrich schedulers.
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.db import SessionLocal, engine
from app.enrich import schedule as schedule_enrich
from app.ingest import scheduler, start_scheduler
from app.routers import activity, cves, feed, kev, services, status, vendors
from app.services import schedule as schedule_services
from app.seed import seed
from app.throttle import limiter, rate_limited

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


# API docs only locally: in production /docs, /redoc and /openapi.json are 404.
_local = not get_settings().on_railway
app = FastAPI(
    title="darkwire",
    docs_url="/docs" if _local else None,
    redoc_url="/redoc" if _local else None,
    openapi_url="/openapi.json" if _local else None,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limited)

# Browsers may call the API only from the site itself and local dev. Fixed in code, not
# configurable, so no environment variable can widen it.
ALLOWED_ORIGINS = [
    "https://darkwire.tech",
    "https://www.darkwire.tech",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET"], allow_headers=[])
for r in (feed.router, cves.router, kev.router, vendors.router, status.router, services.router, activity.router):
    app.include_router(r)


# Every response: HSTS, no sniffing, no referrer, never cached (the data is live). The Server banner
# is off at uvicorn (--no-server-header in railway.json).
SECURITY_HEADERS = {
    # HTTPS only (Railway's edge redirects plain HTTP). No preload directive on the API host.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"ok": True}
