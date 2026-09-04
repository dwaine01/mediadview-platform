"""
health.py — Fase 6: Liveness + Readiness probes

GET /api/livez   — LIVENESS: process alive? Always 200 (never touches DB).
GET /api/health  — Legacy liveness alias (for Android Player backwards compat).
GET /api/ready   — READINESS: all hard dependencies reachable?
                   Returns 503 if MongoDB or Storage are unavailable.

Design:
  LIVENESS ≠ READINESS.
  - Liveness: Is the process responsive?  K8s/Render restarts on failure.
  - Readiness: Can we serve traffic?  Load-balancer removes instance on failure.
  A healthy process can be NOT READY (DB temporarily down) — and vice-versa is
  not meaningful.

Hard dependencies (503 if down):
  - MongoDB
  - Storage (local or R2)

Soft dependencies (degraded but 200 if down):
  - Redis  — rate limiter falls back to in-memory
  - Worker — absent in development
"""
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Response

log = logging.getLogger("health")
router = APIRouter(prefix="/api")

_STARTED_AT = time.monotonic()
_APP_STARTED_ISO = datetime.now(timezone.utc).isoformat()


def build_health_router(db):

    # ── LIVENESS ─────────────────────────────────────────────────────────
    @router.get("/livez")
    @router.get("/health")   # legacy alias — Android Player pings this
    async def liveness():
        """
        Liveness probe.  ALWAYS 200 if the process can respond.
        Never touches DB, Redis, or storage — purely in-process.
        Render health-check and the Android APK both hit this endpoint.
        """
        return {
            "ok":         True,
            "status":     "healthy",          # legacy field for Android Player
            "app":        "MediAd View",
            "env":        os.environ.get("ENVIRONMENT", "development"),
            "started_at": _APP_STARTED_ISO,
            "uptime_s":   round(time.monotonic() - _STARTED_AT, 1),
            "version":    (
                os.environ.get("APP_RELEASE")
                or os.environ.get("RENDER_GIT_COMMIT")
                or "dev"
            ),
        }

    # ── READINESS ────────────────────────────────────────────────────────
    @router.get("/ready")
    async def readiness(response: Response):
        """
        Readiness probe.  Checks:
          - MongoDB: hard dependency — 503 if down
          - Storage: hard dependency — 503 if down
          - Redis:   soft dependency — degraded but NOT 503
          - Worker:  soft dependency — not required in development

        Never exposes credentials, hostnames, or stack traces in the response.
        """
        checks: dict = {}
        env = os.environ.get("ENVIRONMENT", "development")

        # ── 1. MongoDB ────────────────────────────────────────────────────
        t = time.monotonic()
        try:
            await db.command("ping")
            checks["mongo"] = {
                "ok":         True,
                "latency_ms": round((time.monotonic() - t) * 1000, 1),
            }
        except Exception as exc:
            checks["mongo"] = {
                "ok":    False,
                "error": type(exc).__name__,
            }

        # ── 2. Storage (LocalDriver or R2Driver) ──────────────────────────
        t = time.monotonic()
        try:
            from storage_service import get_storage_service
            ss = get_storage_service()
            ping_result = await ss.ping()
            checks["storage"] = {
                "ok":         ping_result.get("ok", False),
                "driver":     ping_result.get("driver", "unknown"),
                "latency_ms": ping_result.get("latency_ms"),
            }
            if not ping_result.get("ok"):
                checks["storage"]["error"] = ping_result.get("error", "ping failed")
        except Exception as exc:
            checks["storage"] = {
                "ok":    False,
                "error": type(exc).__name__,
            }

        # ── 3. Redis (soft) ───────────────────────────────────────────────
        try:
            from redis_client import ping_redis
            r = await ping_redis()
            checks["redis"] = {
                "ok":         bool(r["ok"]),
                "latency_ms": r.get("latency_ms"),
                "fallback":   r.get("fallback"),
            }
        except Exception as exc:
            checks["redis"] = {"ok": False, "error": type(exc).__name__}

        # ── 4. Worker heartbeat (soft) ────────────────────────────────────
        try:
            from redis_client import redis_client
            hb = await redis_client.get_raw("mediadview:worker:heartbeat")
            if hb:
                age = int(time.time()) - int(hb.decode() if isinstance(hb, bytes) else hb)
                checks["worker"] = {
                    "ok":                       age < 90,
                    "seconds_since_heartbeat":  age,
                }
            else:
                checks["worker"] = {
                    "ok":    env != "production",
                    "reason": "no_heartbeat",
                }
        except Exception as exc:
            checks["worker"] = {"ok": False, "error": type(exc).__name__}

        # ── Overall readiness: Mongo + Storage are HARD deps ──────────────
        mongo_ok   = checks.get("mongo",   {}).get("ok", False)
        storage_ok = checks.get("storage", {}).get("ok", False)
        ready = mongo_ok and storage_ok

        if not ready:
            response.status_code = 503

        return {
            "ok":     ready,
            "env":    env,
            "checks": checks,
            "ts":     datetime.now(timezone.utc).isoformat(),
        }

    return router
