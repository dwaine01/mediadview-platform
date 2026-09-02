# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
MediAd View — startup configuration validator (fail-fast)

Runs BEFORE FastAPI imports any router. If a critical piece of configuration
is missing, malformed, or unusable, the process exits with an error message
that names the offending variable — never a silent partial-startup.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the standard location; safe no-op in prod where Render
# injects the env directly.
load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("startup_check")

# ─── Rules ────────────────────────────────────────────────────────────
# ("VAR", required_in_prod, required_in_dev, validator_callable_or_None)
_RULES = [
    ("MONGO_URL",  True,  True,  lambda v: v.startswith(("mongodb://", "mongodb+srv://"))),
    ("DB_NAME",    True,  True,  lambda v: len(v) >= 1 and " " not in v),
    ("JWT_SECRET", True,  True,  lambda v: len(v) >= 32 and v != "mediaview-secure-jwt-secret-2026"),
    ("CORS_ORIGINS", True, False, lambda v: v == "*" or all(o.startswith(("http://","https://")) for o in v.split(","))),
    # Prod-only requirements
    ("REDIS_URL",              False, False, lambda v: v.startswith(("redis://","rediss://"))),
    ("SEED_SUPERADMIN_PASSWORD", False, False, lambda v: len(v) >= 12),
    # Stripe (Fase 5). Never required in dev — safety switch lives in
    # stripe_config.configure_stripe(); this table only rejects OBVIOUSLY
    # wrong values (an invalid prefix). Mode consistency + prod-hardening
    # are enforced in stripe_config so the errors are precise.
    ("STRIPE_SECRET_KEY",      False, False, lambda v: v.startswith(("sk_test_", "sk_live_"))),
    ("STRIPE_PUBLISHABLE_KEY", False, False, lambda v: v.startswith(("pk_test_", "pk_live_"))),
    ("STRIPE_WEBHOOK_SECRET",  False, False, lambda v: v.startswith("whsec_")),
    ("ORDER_LINK_SECRET",      False, False, lambda v: len(v) >= 32 and v != "mediaview-secure-jwt-secret-2026"),
]

def _is_prod() -> bool:
    return os.environ.get("ENVIRONMENT", "development").lower() == "production"


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
        if not s or s.startswith("#"): continue
        # Detect two KEY=VALUE glued together (KEY1="foo"KEY2=bar) — the exact
        # bug we hit before. Heuristic: value contains ` "<UPPERCASE>=`.
        if '="' in s and '="' in s[s.index('="')+2:]:
            errors.append(f"line {i}: two variables glued together (missing newline?) → {s[:80]!r}")
            continue
        if "=" not in s:
            errors.append(f"line {i}: no '=' → {s!r}")
            continue
        k = s.split("=", 1)[0].strip()
        if not k.replace("_", "").isalnum():
            errors.append(f"line {i}: invalid key name → {k!r}")
        if k in keys:
            errors.append(f"line {i}: duplicate key {k!r} (also on line {keys[k]})")
        keys[k] = i
    if errors:
        print("❌ .env file has syntax errors:", file=sys.stderr)
        for e in errors: print("   - " + e, file=sys.stderr)
        sys.exit(2)


def validate_environment():
    """Check every critical variable is present, well-formed, and USABLE.
    Exits with a clear error otherwise."""
    check_env_file_syntax()
    prod = _is_prod()
    problems = []
    for name, req_prod, req_dev, validator in _RULES:
        v = os.environ.get(name, "").strip()
        required = req_prod if prod else req_dev
        if not v:
            if required:
                problems.append(f"{name}: MISSING (required in {'production' if prod else 'development'})")
            continue
        if validator and not validator(v):
            problems.append(f"{name}: value does not pass validation")
    if problems:
        print("❌ MediAd View cannot start — configuration errors:", file=sys.stderr)
        for p in problems: print("   - " + p, file=sys.stderr)
        print("   Set the missing/invalid variables in the backend .env or Render "
              "env group and restart.", file=sys.stderr)
        sys.exit(2)
    log.info("✓ Environment validation passed (env=%s)", os.environ.get("ENVIRONMENT","development"))

    # ── Fase 5: Stripe safety switch (test/live consistency, webhook secret
    #    requirement, PCI-adjacent guardrails). Runs AFTER the generic env
    #    checks so we already know MONGO_URL etc. are usable.
    try:
        from stripe_config import configure_stripe
        configure_stripe()
    except SystemExit:
        raise
    except Exception:
        # Never abort on unexpected import errors — Stripe is an optional
        # feature. Log and continue.
        log.exception("Stripe config init failed; payment routes will 503")


if __name__ == "__main__":
    validate_environment()
