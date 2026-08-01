"""
MediAd View — Stripe SDK configuration & safety switch (Fase 5 · Sprint 1 · Etapa A).

RULES ENFORCED (from user-approved blueprint):
  · Sprint 1 works ONLY in Stripe TEST mode.
  · If ENVIRONMENT=production and STRIPE_SECRET_KEY starts with "sk_test_" → abort.
  · If ENVIRONMENT!=production and STRIPE_SECRET_KEY starts with "sk_live_" → abort.
  · STRIPE_PUBLISHABLE_KEY mode MUST match STRIPE_SECRET_KEY mode.
  · If any Stripe var is present, STRIPE_WEBHOOK_SECRET is REQUIRED
    (an empty webhook secret defeats the whole security model).
  · Keys are never logged; only the detected MODE is logged.

Public API of this module:
  · configure_stripe()           → called once at process startup.
  · get_mode()                   → returns "test" | "live" | "disabled".
  · get_publishable_key()        → safe to expose to the browser.
  · webhook_secret()             → server-side only; used by webhook route.
  · is_configured()              → boolean; features can degrade if False.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Literal, Optional

import stripe

log = logging.getLogger("stripe_config")

# ─── Public state (populated by configure_stripe) ───────────────────────
_MODE: Literal["test", "live", "disabled"] = "disabled"
_PUBLISHABLE_KEY: Optional[str] = None
_WEBHOOK_SECRET: Optional[str] = None
_CONFIGURED: bool = False

# Pin the API version we send to Stripe so behaviour never silently shifts
# under us when Stripe releases a new version. Kept in one place so the
# ARQ worker and the web-api agree byte-for-byte.
STRIPE_API_VERSION = "2026-03-25.dahlia"

# Sprint 1: cards only, USD only. Enforced at PaymentIntent creation time.
DEFAULT_CURRENCY = "usd"
ALLOWED_CURRENCIES = {"usd"}
ALLOWED_PAYMENT_METHOD_TYPES = ["card"]


def _detect_mode(secret_key: str) -> Literal["test", "live", "unknown"]:
    if secret_key.startswith("sk_test_"):
        return "test"
    if secret_key.startswith("sk_live_"):
        return "live"
    return "unknown"


def _detect_pk_mode(publishable_key: str) -> Literal["test", "live", "unknown"]:
    if publishable_key.startswith("pk_test_"):
        return "test"
    if publishable_key.startswith("pk_live_"):
        return "live"
    return "unknown"


def configure_stripe() -> None:
    """Read env, validate, and initialise the Stripe SDK.

    Called once from startup_check.py (fail-fast) AND at import time of
    stripe_routes.py as a defensive double-init. Both are idempotent.
    """
    global _MODE, _PUBLISHABLE_KEY, _WEBHOOK_SECRET, _CONFIGURED

    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    publishable_key = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    is_prod = os.environ.get("ENVIRONMENT", "development").lower() == "production"

    # ── 1. Feature-toggle: no secret key → Stripe is disabled. Non-fatal
    #      in dev so the rest of the app boots for developers who haven't
    #      set up Stripe yet. In prod this MUST fail so we don't ship a
    #      half-configured payment stack.
    if not secret_key:
        if is_prod:
            print("❌ STRIPE_SECRET_KEY is required in production.", file=sys.stderr)
            sys.exit(2)
        log.warning("Stripe DISABLED (no STRIPE_SECRET_KEY set). Payment routes will 503.")
        _MODE = "disabled"
        _CONFIGURED = False
        return

    # ── 2. Detect and enforce test/live consistency
    sk_mode = _detect_mode(secret_key)
    if sk_mode == "unknown":
        print("❌ STRIPE_SECRET_KEY has an invalid prefix "
              "(must start with 'sk_test_' or 'sk_live_').", file=sys.stderr)
        sys.exit(2)

    if is_prod and sk_mode == "test":
        print("❌ ENVIRONMENT=production but STRIPE_SECRET_KEY is a TEST key. "
              "Refusing to start.", file=sys.stderr)
        sys.exit(2)

    if not is_prod and sk_mode == "live":
        print("❌ ENVIRONMENT!=production but STRIPE_SECRET_KEY is a LIVE key. "
              "Refusing to start — Sprint 1 must never touch live money.",
              file=sys.stderr)
        sys.exit(2)

    if publishable_key:
        pk_mode = _detect_pk_mode(publishable_key)
        if pk_mode == "unknown":
            print("❌ STRIPE_PUBLISHABLE_KEY has an invalid prefix.", file=sys.stderr)
            sys.exit(2)
        if pk_mode != sk_mode:
            print(f"❌ Stripe key mode mismatch: secret={sk_mode!r} "
                  f"but publishable={pk_mode!r}.", file=sys.stderr)
            sys.exit(2)

    # ── 3. Webhook secret: required as soon as Stripe is configured. A
    #      webhook endpoint without a signing secret is worse than none
    #      at all because it invites signature-bypass mistakes.
    if not webhook_secret:
        # In dev we allow it to be empty ONLY when explicitly opted-in
        # so a developer can boot without stripe listen running.
        allow_empty = os.environ.get("STRIPE_WEBHOOK_SECRET_ALLOW_EMPTY", "").lower() in ("1", "true", "yes")
        if is_prod or not allow_empty:
            print("❌ STRIPE_WEBHOOK_SECRET is required whenever Stripe is enabled. "
                  "Get one from `stripe listen` (dev) or the Stripe Dashboard (prod).",
                  file=sys.stderr)
            sys.exit(2)
        log.warning("Stripe webhook secret is EMPTY (dev override). "
                    "Webhook signature verification will fail until you set it.")
    elif not webhook_secret.startswith("whsec_"):
        print("❌ STRIPE_WEBHOOK_SECRET must start with 'whsec_'.", file=sys.stderr)
        sys.exit(2)

    # ── 4. Initialise the SDK
    stripe.api_key = secret_key
    stripe.api_version = STRIPE_API_VERSION
    # Retry idempotent requests up to 2 extra times on transient network
    # errors. Idempotency keys make this safe. Note: stripe SDK 15.x sets
    # sensible default timeouts internally; we keep the retry cap explicit.
    stripe.max_network_retries = 2

    _MODE = sk_mode
    _PUBLISHABLE_KEY = publishable_key or None
    _WEBHOOK_SECRET = webhook_secret or None
    _CONFIGURED = True

    log.info("✓ Stripe configured (mode=%s, api_version=%s, publishable_key=%s)",
             _MODE, STRIPE_API_VERSION, "SET" if _PUBLISHABLE_KEY else "MISSING")


# ─── Read-only accessors ────────────────────────────────────────────────
def get_mode() -> Literal["test", "live", "disabled"]:
    return _MODE

def get_publishable_key() -> Optional[str]:
    return _PUBLISHABLE_KEY

def webhook_secret() -> Optional[str]:
    return _WEBHOOK_SECRET

def is_configured() -> bool:
    return _CONFIGURED
