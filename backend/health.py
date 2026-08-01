"""
Health + readiness endpoints for /api/health and /api/ready.
"""
import os
import time
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Response

log = logging.getLogger("health")
router = APIRouter(prefix="/api")

_STARTED_AT = time.monotonic()
_APP_STARTED_ISO = datetime.now(timezone.utc).isoformat()


def build_health_router(db):

    @router.get("/livez")
    async def health():
        """Lightweight liveness probe. Should ALWAYS succeed unless the process
        is unresponsive. Never touches DB — Render / uptime pings hit this
        every few seconds so it must be O(1).

        Note: legacy /api/health also exists (kept for backwards compat with
        the Android APK); this is the modern replacement."""
        return {
            "ok":         True,
            "app":        "MediAd View",
            "env":        os.environ.get("ENVIRONMENT", "development"),
            "started_at": _APP_STARTED_ISO,
            "uptime_s":   round(time.monotonic() - _STARTED_AT, 1),
            "version":    os.environ.get("APP_RELEASE") or os.environ.get("RENDER_GIT_COMMIT") or "dev",
        }

    @router.get("/ready")
    async def ready(response: Response):
        """Deep readiness probe. Verifies:
        - MongoDB accessible (ping)
        - Redis accessible (ping) — degraded if fallback is active
        - Background worker heartbeat (< 90 s old)

        Returns 200 if healthy, 503 if any hard dependency is down.
        Never exposes secrets, hostnames, credentials or stack traces.
        """
        checks: dict = {"mongo": {"ok": False}, "redis": {"ok": False}, "worker": {"ok": False}}

        # 1) Mongo
        t = time.monotonic()
        try:
            await db.command("ping")
            checks["mongo"] = {"ok": True, "latency_ms": round((time.monotonic() - t) * 1000, 1)}
        except Exception as e:
            checks["mongo"] = {"ok": False, "error": type(e).__name__}

        # 2) Redis
        try:
            from redis_client import ping_redis
            r = await ping_redis()
            checks["redis"] = {
                "ok":         bool(r["ok"]),
                "latency_ms": r["latency_ms"],
                "fallback":   r["fallback"],
            }
        except Exception as e:
            checks["redis"] = {"ok": False, "error": type(e).__name__}

        # 3) Worker heartbeat (best-effort). Absent worker is not fatal in dev.
        try:
            from redis_client import redis_client
            hb = await redis_client.get_raw("mediadview:worker:heartbeat")
            if hb:
                last = int(hb.decode() if isinstance(hb, bytes) else hb)
                age = int(time.time()) - last
                checks["worker"] = {"ok": age < 90, "seconds_since_heartbeat": age}
            else:
                checks["worker"] = {"ok": os.environ.get("ENVIRONMENT") != "production",
                                    "reason": "no_heartbeat"}
        except Exception as e:
            checks["worker"] = {"ok": False, "error": type(e).__name__}

        # Overall: mongo is HARD, redis is HARD in prod, worker is SOFT
        env = os.environ.get("ENVIRONMENT", "development")
        hard_ok = checks["mongo"]["ok"] and (checks["redis"]["ok"] or env != "production")
        if not hard_ok:
            response.status_code = 503

        return {
            "ok":     hard_ok,
            "env":    env,
            "checks": checks,
            "ts":     datetime.now(timezone.utc).isoformat(),
        }

    return router
