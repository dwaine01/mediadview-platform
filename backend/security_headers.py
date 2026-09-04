"""
MediaDView — HTTP Security Headers middleware (P0-A1).

Adds OWASP-recommended headers to every response. Two-layer defense:
this middleware SETS them, and Cloudflare Transform Rules SHOULD
re-affirm them (documented in RUNBOOK.md §9).

Headers set:
    · Strict-Transport-Security  — HTTPS enforcement (prod only, HTTPS-only)
    · X-Frame-Options            — clickjacking defense
    · X-Content-Type-Options     — MIME-sniffing defense
    · Referrer-Policy            — no leaking referrers cross-origin
    · Permissions-Policy         — disable unused browser APIs
    · Content-Security-Policy    — script/style/frame source allowlist
                                   (report-only in dev; enforce in prod)

H1 — CSP 'unsafe-inline' AUDIT (updated Fase 6 Security Hardening)
═══════════════════════════════════════════════════════════════════

STATUS: 'unsafe-inline' remains in script-src and style-src.

KNOWN BLOCKERS (must be resolved before this can be removed):

  script-src 'unsafe-inline' blockers:
  1. /api/menus/{id}/render — render_menu() builds inline <script> blocks
     for slideshow animation, promo scroll, and WebSocket live-reload.
     FIX PATH: extract to /static/menu-player.js parameterised via data-* attrs.

  2. /api/widgets/{id}/render — render_widget() builds type-specific inline
     <script> blocks (clock, ticker, countdown, YouTube etc.).
     FIX PATH: extract to per-widget /static/widget-<type>.js.

  3. /player/{id}/web — player SPA uses inline <script> with dynamic data.
     FIX PATH: extract to /static/player.js + JSON data endpoint.

  4. /api/s/{code} — screen pairing page has inline script.
     FIX PATH: extract to /static/pairing.js.

  style-src 'unsafe-inline' blockers:
  1. All the above renderers use inline <style> blocks.
     FIX PATH: move to /static/*.css with template params via CSS variables.

  ACCEPTANCE CRITERIA to remove unsafe-inline:
  - All inline <script> moved to external files served from /static/
  - All inline <style> moved to external CSS with CSS custom properties
  - Add a Content-Security-Policy nonce generator for any remaining dynamic
    content that truly cannot be externalised.

  TARGET: P1 — Sprint 2 (before high-traffic public launch).
  Current risk is REDUCED but not ZERO since SEC-001 and SEC-003 HTML sinks
  were fixed (all user data is now HTML/JS-escaped). The remaining unsafe-inline
  risk is limited to self-generated static markup, not user-controlled input.
"""
from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CSP_DIRECTIVES = (
    # default: same origin only
    "default-src 'self'; "
    # scripts: self + Chart.js CDN (used by admin-reports.html)
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    # styles: self + Google Fonts + inline (existing HTML uses <style>)
    "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
    # fonts from Google
    "font-src 'self' https://fonts.gstatic.com data:; "
    # images: self + data-URIs (base64 previews) + https everywhere for R2
    "img-src 'self' data: blob: https:; "
    # media (video previews)
    "media-src 'self' blob: https:; "
    # connect (fetch + WebSocket)
    "connect-src 'self' https: wss: ws:; "
    # frames — used by player-activate.html to render iframe of widget
    "frame-src 'self' https:; "
    # deny everything else
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
    # NOTE: `upgrade-insecure-requests` is intentionally OMITTED here
    # because it is ignored (and warns to console) in the
    # `Content-Security-Policy-Report-Only` header used in dev.
    # It is re-added by Cloudflare Transform Rules in production, and
    # our enforcing CSP in production adds it via SecurityHeadersMiddleware
    # override (see below).
)


CSP_DIRECTIVES_ENFORCE = CSP_DIRECTIVES + "; upgrade-insecure-requests"


PERMISSIONS_POLICY = (
    "accelerometer=(), autoplay=(self), camera=(), display-capture=(), "
    "encrypted-media=(), fullscreen=(self), geolocation=(), gyroscope=(), "
    "microphone=(), midi=(), payment=(self), picture-in-picture=(), "
    "publickey-credentials-get=(self), sync-xhr=(), usb=(), "
    "screen-wake-lock=(), xr-spatial-tracking=()"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security headers to every response.

    In development we still set most headers (the API benefits from them),
    but we send `Content-Security-Policy-Report-Only` instead of
    the enforcing variant to avoid breaking local iteration.
    HSTS is only sent when the connection is HTTPS (behind Cloudflare or
    Render's cert).
    """

    def __init__(self, app, is_production: bool):
        super().__init__(app)
        self.is_production = is_production

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Do not stomp headers on WebSocket upgrades (Starlette handles those separately)
        if response is None:
            return response

        headers = response.headers

        # Frame options — DENY globally, except PDF endpoints which are
        # embedded in same-origin iframes by the admin panel (preview view).
        path = request.url.path or ""
        is_pdf_preview = path.endswith("/pdf") or "/pdf?" in str(request.url) or path.endswith(".pdf")
        if is_pdf_preview:
            headers["X-Frame-Options"] = "SAMEORIGIN"
        else:
            headers.setdefault("X-Frame-Options", "DENY")
        # MIME sniffing defense
        headers.setdefault("X-Content-Type-Options", "nosniff")
        # Referrer policy — do not leak paths cross-origin
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Permissions-Policy
        headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)

        # HSTS only on HTTPS (or when we know we're in prod behind CF)
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        is_https = (request.url.scheme == "https") or (forwarded_proto == "https")
        if self.is_production or is_https:
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )

        # CSP: enforce in prod, report-only in dev to keep iteration fast.
        if self.is_production:
            headers.setdefault("Content-Security-Policy", CSP_DIRECTIVES_ENFORCE)
        else:
            headers.setdefault("Content-Security-Policy-Report-Only", CSP_DIRECTIVES)

        return response


def install(app) -> None:
    """Wire the middleware to a FastAPI/Starlette app."""
    env = (os.environ.get("ENVIRONMENT") or "").lower()
    is_prod = env == "production"
    app.add_middleware(SecurityHeadersMiddleware, is_production=is_prod)
