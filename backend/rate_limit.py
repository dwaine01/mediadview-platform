"""
MediAd View — Rate limiting (slowapi)

Applies per-IP rate limits to sensitive endpoints.
- In-memory fallback when REDIS_URL is empty (dev / single instance).
- Redis backend when REDIS_URL is set (production multi-instance safe).

Usage in server.py:

    from rate_limit import limiter, install_rate_limiter
    install_rate_limiter(app)

    from rate_limit import LIMITS
    @limiter.limit(LIMITS.login)
    @app.post("/api/auth/login")
    async def login(request: Request, ...):
        ...
"""
import os
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request

log = logging.getLogger("rate_limit")


def _client_key(request: Request) -> str:
    """Use Cloudflare / proxy header when available, fall back to socket IP."""
    xff = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


REDIS_URL = os.environ.get("REDIS_URL", "").strip()

# Instantiate limiter. Storage:
#   memory://   → single-instance (dev / Render single-worker)
#   redis://... → multi-instance safe
storage_uri = REDIS_URL if REDIS_URL else "memory://"
limiter = Limiter(
    key_func=_client_key,
    storage_uri=storage_uri,
    default_limits=[],  # We set explicit limits per endpoint (no global default).
    strategy="fixed-window",
    headers_enabled=True,
)


def install_rate_limiter(app):
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    log.info(
        "✓ Rate limiter installed (storage=%s)",
        "redis" if REDIS_URL else "memory (single-instance)",
    )


class LIMITS:
    """Centralized limit strings so they're easy to review."""
    # Auth
    login          = "5/minute; 20/hour"
    register       = "3/minute; 10/hour"
    refresh        = "30/minute"
    change_pass    = "5/hour"
    forgot_pass    = "3/hour"
    # Uploads & pricey ops
    media_upload   = "20/minute; 200/hour"
    payment_create = "10/minute; 50/hour"
    qr_generate    = "60/minute"
    # Public
    public_read    = "120/minute"
    # Webhooks: intentionally generous — Stripe retries need to succeed
    webhook        = "300/minute"
