# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
MediAd View — startup configuration validator (fail-fast)

Runs BEFORE FastAPI imports any router. If a critical piece of configuration
is missing, malformed, or unusable, the process exits with an error message
that names the offending variable — never a silent partial-startup.

Environment tiers:
  development  — permissive (localhost Mongo, * CORS, no Redis required)
  staging      — strict as production (Atlas required, no localhost Mongo,
                 no wildcard CORS) — EXCEPT: Stripe may stay in test mode
  production   — fully strict, all secrets required

Fase 6 additions:
  - staging is now as strict as production for infrastructure checks
  - MONGO_URL with localhost → FAIL in staging AND production
  - CORS_ORIGINS="*" → FAIL in staging AND production
  - ORDER_LINK_SECRET required in production
  - STORAGE_DRIVER validation + R2 vars required when STORAGE_DRIVER=r2
  - Weak/default JWT_SECRET → FAIL in staging AND production
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the standard location; safe no-op in prod where Render
# injects the env directly.
load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("startup_check")

# ─── Environment tier helpers ──────────────────────────────────────────
def _env() -> str:
    """Returns the current environment tier: development | staging | production"""
    return os.environ.get("ENVIRONMENT", "development").lower()

def _is_prod() -> bool:
    """True for production only."""
    return _env() == "production"

def _is_strict() -> bool:
    """True for staging AND production — both tiers require Atlas, no localhost, no wildcard."""
    return _env() in ("production", "staging")

def _is_dev() -> bool:
    return _env() == "development"


# ─── Known weak / default secrets that must never reach staging or prod ──
_WEAK_SECRETS = {
    "mediaview-secure-jwt-secret-2026",
    "changeme",
    "secret",
    "password",
    "12345678",
    "dev-secret",
    "test-secret",
    "your-secret-here",
    "jwt-secret",
}


def _is_weak_secret(v: str) -> bool:
    """Return True if v is empty, too short, or a known placeholder."""
    if not v or len(v) < 32:
        return True
    return v.lower() in _WEAK_SECRETS


def _mongo_url_safe(v: str) -> bool:
    """
    In development: any valid Mongo URL is fine (including localhost).
    In staging/production: localhost / 127.0.0.1 / ::1 are rejected — must use Atlas.
    """
    if not v.startswith(("mongodb://", "mongodb+srv://")):
        return False
    if _is_strict():
        # Reject localhost / loopback in strict environments
        low = v.lower()
        for bad in ("localhost", "127.0.0.1", "::1", "@localhost:", "@127.", "[::1]"):
            if bad in low:
                return False
    return True


def _cors_safe(v: str) -> bool:
    """
    In development: * is fine.
    In staging/production: * is forbidden — must be explicit origin list.
    """
    if not v:
        return False
    if v.strip() == "*":
        return not _is_strict()   # OK in dev, FAIL in staging/prod
    # Comma-separated list of https:// origins
    origins = [o.strip() for o in v.split(",") if o.strip()]
    return all(o.startswith(("http://", "https://")) for o in origins)


# ─── Validation rules ──────────────────────────────────────────────────
# Each entry: (env_var_name, required_strict, required_dev, validator)
# required_strict = required in staging AND production
# required_dev    = required in development
_RULES: list[tuple[str, bool, bool, object]] = [
    # Core
    ("MONGO_URL",            True,  True,  _mongo_url_safe),
    ("DB_NAME",              True,  True,  lambda v: len(v) >= 1 and " " not in v),
    # JWT — weak/default rejected in strict environments
    ("JWT_SECRET",           True,  True,  lambda v: not _is_weak_secret(v)),
    # ORDER_LINK_SECRET required in production (P0-ENV-001 Fase 5)
    ("ORDER_LINK_SECRET",    True,  False, lambda v: not _is_weak_secret(v)),
    # CORS — wildcard forbidden in staging/production
    ("CORS_ORIGINS",         True,  False, _cors_safe),
    # Storage driver
    ("STORAGE_DRIVER",       False, False, lambda v: v in ("local", "r2", "memory")),
    # Redis (required in production for multi-instance rate limiting)
    ("REDIS_URL",            False, False, lambda v: v.startswith(("redis://", "rediss://"))),
    # Stripe — optional, validated by stripe_config.py when present
    ("STRIPE_SECRET_KEY",    False, False, lambda v: v.startswith(("sk_test_", "sk_live_"))),
    ("STRIPE_PUBLISHABLE_KEY", False, False, lambda v: v.startswith(("pk_test_", "pk_live_"))),
    ("STRIPE_WEBHOOK_SECRET",  False, False, lambda v: v.startswith("whsec_")),
]

# R2 vars required when STORAGE_DRIVER=r2
_R2_VARS = [
    "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL",
]


def check_env_file_syntax():
    """Parse .env manually and catch: missing =, duplicate keys, malformed
    quoting, keys glued together without newline (the bug that hit us)."""
    p = Path("/app/backend/.env")
    if not p.exists():
        return  # env may come from Render / Docker directly
    lines = p.read_text().splitlines()
    keys, errors = {}, []
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if '="' in s and '="' in s[s.index('="') + 2:]:
            errors.append(
                f"line {i}: two variables glued together (missing newline?) → {s[:80]!r}"
            )
            continue
        if "=" not in s:
            errors.append(f"line {i}: no '=' → {s!r}")
            continue
        k = s.split("=", 1)[0].strip()
        if not k.replace("_", "").isalnum():
            errors.append(f"line {i}: invalid key name → {k!r}")
        if k in keys:
            errors.append(
                f"line {i}: duplicate key {k!r} (also on line {keys[k]})"
            )
        keys[k] = i
    if errors:
        print("❌ .env file has syntax errors:", file=sys.stderr)
        for e in errors:
            print("   - " + e, file=sys.stderr)
        sys.exit(2)


def validate_environment():
    """Check every critical variable is present, well-formed, and USABLE.
    Exits with a clear error otherwise.

    Fase 6: staging is now treated identically to production for
    infrastructure checks (MongoDB, CORS, JWT strength, ORDER_LINK_SECRET).
    """
    check_env_file_syntax()
    env   = _env()
    strict = _is_strict()   # True for staging AND production

    problems: list[str] = []

    for name, req_strict, req_dev, validator in _RULES:
        v = os.environ.get(name, "").strip()
        required = req_strict if strict else req_dev
        if not v:
            if required:
                tier = "staging/production" if req_strict else "development"
                problems.append(
                    f"{name}: MISSING (required in {tier})"
                )
            continue
        if validator and not validator(v):
            if name == "MONGO_URL" and _is_strict():
                problems.append(
                    f"{name}: localhost/loopback not allowed in {env} — use MongoDB Atlas (mongodb+srv://)"
                )
            elif name == "CORS_ORIGINS" and _is_strict():
                problems.append(
                    f"{name}: wildcard '*' not allowed in {env} — set explicit origin(s), e.g. "
                    f"CORS_ORIGINS=https://app.mediaview.io  [PRODUCTION_DOMAIN_REQUIRED]"
                )
            elif name in ("JWT_SECRET", "ORDER_LINK_SECRET"):
                problems.append(
                    f"{name}: value is too short, empty, or a known default/weak placeholder — "
                    f"generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
                )
            else:
                problems.append(f"{name}: value does not pass validation")

    # R2 vars: all required when STORAGE_DRIVER=r2
    if os.environ.get("STORAGE_DRIVER", "").lower() == "r2":
        for var in _R2_VARS:
            if not os.environ.get(var, "").strip():
                problems.append(
                    f"{var}: MISSING (required when STORAGE_DRIVER=r2)"
                )

    if problems:
        print(
            f"❌ MediAd View cannot start ({env}) — configuration errors:",
            file=sys.stderr,
        )
        for p in problems:
            print("   - " + p, file=sys.stderr)
        print(
            "   Set the missing/invalid variables in the backend .env or Render "
            "env group and restart.",
            file=sys.stderr,
        )
        sys.exit(2)

    log.info("✓ Environment validation passed (env=%s)", env)

    # ── Stripe safety switch ──────────────────────────────────────────────
    try:
        from stripe_config import configure_stripe
        configure_stripe()
    except SystemExit:
        raise
    except Exception:
        log.exception("Stripe config init failed; payment routes will 503")


if __name__ == "__main__":
    validate_environment()
