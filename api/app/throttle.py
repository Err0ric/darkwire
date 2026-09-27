"""Public API protection: per-client-IP rate limits (slowapi), query caps, and tokens.

Client IP. Railway's edge proxy terminates every public request and sets X-Real-IP to the
client's address (docs.railway.com, Public Networking > Specs & Limits); the container has no
other public way in. So the proxy headers are trusted only on Railway (RAILWAY_ENVIRONMENT_NAME
is set) or when the TCP peer is a private/loopback address (the proxy, or local dev); otherwise
the peer address itself is the key. Verified in production by sending 130 requests with a
random spoofed X-Real-IP and X-Forwarded-For on each: the 429 still arrived, so the edge
overwrites what the client sends and a client cannot pick its own key.

Limits, per client IP (in memory; one API replica):
- READ: 120/minute shared across every read endpoint.
- HEAVY: 10/minute for /feed?all_sources=true and any request asking for limit > 100.
- 429 responses carry Retry-After (seconds until the window resets).

Caps: limit is clamped to 100 on public requests. Larger limits and all_sources need the
X-Audit-Token header matching the AUDIT_TOKEN variable (the feed audit tool).

Server rendering: the web app's pages call the API from Vercel's servers, which share a few
IPs among all visitors. With SSR_TOKEN set on Railway and API_SERVER_TOKEN set on Vercel to
the same value, those calls send X-SSR-Token and skip the READ bucket. Unset, they are limited
like anyone else.
"""

import hmac
import logging
import math
import time
from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.config import get_settings

log = logging.getLogger(__name__)

READ = "120/minute"
HEAVY = "10/minute"
PUBLIC_MAX_LIMIT = 100


def _ip(value: str | None) -> str | None:
    try:
        return str(ip_address((value or "").strip()))
    except ValueError:
        return None


_CGNAT = ip_network("100.64.0.0/10")  # shared address space some proxies use internally


def _private_peer(peer: str | None) -> bool:
    try:
        addr = ip_address(peer or "")
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or (addr.version == 4 and addr in _CGNAT)


_logged_peer = False


def client_ip(request: Request) -> str:
    """The real client address: from the proxy's headers when the request came through it."""
    global _logged_peer
    peer = request.client.host if request.client else None
    if get_settings().on_railway or _private_peer(peer):
        if not _logged_peer:
            # Once per process, without addresses: enough to confirm what the proxy sends.
            log.info(
                "throttle: peer private=%s, x-real-ip=%s, x-forwarded-for=%s",
                _private_peer(peer), "x-real-ip" in request.headers, "x-forwarded-for" in request.headers,
            )
            _logged_peer = True
        real = _ip(request.headers.get("x-real-ip"))
        if real:
            return real
        hops = [h for h in (request.headers.get("x-forwarded-for") or "").split(",") if h.strip()]
        forwarded = _ip(hops[-1]) if hops else None  # the proxy appends the address it saw
        if forwarded:
            return forwarded
    return _ip(peer) or "unknown"


def _token_ok(request: Request, header: str, expected: str | None) -> bool:
    given = request.headers.get(header)
    return bool(expected and given and hmac.compare_digest(given.encode(), expected.encode()))


def is_audit(request: Request) -> bool:
    return _token_ok(request, "x-audit-token", get_settings().audit_token)


def is_server_render(request: Request) -> bool:
    return _token_ok(request, "x-ssr-token", get_settings().ssr_token)


def is_heavy(request: Request) -> bool:
    q = request.query_params
    if q.get("all_sources", "").lower() in ("1", "true", "yes"):
        return True
    try:
        return int(q.get("limit") or 0) > PUBLIC_MAX_LIMIT
    except ValueError:
        return False


def cap(request: Request, limit: int) -> int:
    """Public requests get at most 100 rows; the audit token lifts that to the route's own max."""
    return limit if is_audit(request) else min(limit, PUBLIC_MAX_LIMIT)


def require_audit(request: Request, what: str) -> None:
    if not is_audit(request):
        raise HTTPException(403, f"{what} needs the audit token")


limiter = Limiter(key_func=client_ip)

# Decorators for read routes (the route needs a `request: Request` parameter).
# Debug-safe counter: how many read requests came from server renders (SSR bucket) vs the
# per-IP bucket, logged every LOG_EVERY seconds. Counts only; no addresses, no tokens.
LOG_EVERY = 300
_counts = {"ssr": 0, "per_ip": 0, "since": time.time()}


def _ssr_exempt(request: Request) -> bool:
    ssr = is_server_render(request)
    _counts["ssr" if ssr else "per_ip"] += 1
    now = time.time()
    if now - _counts["since"] >= LOG_EVERY:
        log.info(
            "throttle: last %ds: %d server-render requests (SSR bucket), %d per-IP requests",
            round(now - _counts["since"]), _counts["ssr"], _counts["per_ip"],
        )
        _counts.update(ssr=0, per_ip=0, since=now)
    return ssr


read_limit = limiter.shared_limit(READ, scope="read", exempt_when=_ssr_exempt)
heavy_limit = limiter.limit(HEAVY, exempt_when=lambda request: not is_heavy(request))


def rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 with Retry-After: seconds until the window that was hit resets."""
    retry = 60
    current = getattr(request.state, "view_rate_limit", None)
    if current is not None:
        try:
            reset_at, _remaining = limiter.limiter.get_window_stats(current[0], *current[1])
            retry = max(1, math.ceil(reset_at - time.time()))
        except Exception:  # never fail the 429 itself
            pass
    return JSONResponse(
        {"error": "rate limited", "detail": f"limit {exc.detail}"},
        status_code=429,
        headers={"Retry-After": str(retry)},
    )
