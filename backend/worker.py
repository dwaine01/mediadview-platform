"""
MediAd View — ARQ background worker (production-ready)

Runs the heavy / recurring work outside the HTTP request cycle:
- Email delivery (SMTP retries)
- Invoice PDF generation
- Media processing (thumbnail, transcode later)
- Screen sync push (invalidate cache, broadcast WS)
- Cron-style scheduled jobs (monthly billing, overdue reminders, A40 sleep/wake)

Features:
- Idempotency: every job accepts an `_idem` key; a second dispatch with the same
  key inside `IDEM_TTL` seconds is deduped in Redis.
- Retries with exponential backoff (arq built-in) up to MAX_RETRIES.
- Rich structured logging (JSON in prod).
- Health check via `worker_health()` helper and `arq --check` compatibility.
- Self-monitors via Sentry if SENTRY_DSN is set.

Deployment:
  Local:   arq worker.WorkerSettings
  Render:  Background Worker service starting arq worker.WorkerSettings
"""
import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

# ─── Observability first ──────────────────────────────────────────────
from observability import setup_logging, init_sentry
setup_logging()
init_sentry()
log = logging.getLogger("worker")

# ─── Config ───────────────────────────────────────────────────────────
REDIS_URL       = os.environ.get("REDIS_URL", "redis://localhost:6379")
MONGO_URL       = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME         = os.environ.get("DB_NAME", "mediadview")
MAX_RETRIES     = int(os.environ.get("WORKER_MAX_RETRIES", "5"))
JOB_TIMEOUT     = int(os.environ.get("WORKER_JOB_TIMEOUT", "300"))     # 5 min
IDEM_TTL        = int(os.environ.get("WORKER_IDEM_TTL", "3600"))       # 1 h
KEEP_RESULT     = int(os.environ.get("WORKER_KEEP_RESULT", "86400"))   # 24 h

# ─── ARQ import (soft — allow this module to be imported without arq) ─
try:
    from arq import cron
    from arq.connections import RedisSettings
    HAS_ARQ = True
except Exception:
    HAS_ARQ = False
    cron = None
    RedisSettings = None

# ─── Idempotency helper ───────────────────────────────────────────────
async def _idem_seen(ctx: dict, key: str) -> bool:
    """Return True if job with this idem key already ran recently."""
    if not key:
        return False
    redis = ctx["redis"]
    full = f"mediadview:idem:{key}"
    # SET NX so only the first caller wins.
    ok = await redis.set(full, "1", ex=IDEM_TTL, nx=True)
    return not ok  # True = duplicate

# ─── Startup / shutdown ───────────────────────────────────────────────
async def startup(ctx: dict):
    """Called by arq worker on start. Wire Motor + shared state."""
    ctx["mongo"]  = AsyncIOMotorClient(MONGO_URL, tz_aware=True)
    ctx["db"]     = ctx["mongo"][DB_NAME]
    ctx["started_at"] = datetime.now(timezone.utc)
    log.info("worker startup: mongo=%s db=%s redis=%s",
             MONGO_URL.split("@")[-1], DB_NAME, REDIS_URL.split("@")[-1])
    # Publish liveness ping (readable by /api/ready)
    try:
        await ctx["redis"].set("mediadview:worker:heartbeat",
                               str(int(ctx["started_at"].timestamp())), ex=90)
    except Exception:
        pass

async def shutdown(ctx: dict):
    log.info("worker shutdown")
    try: ctx["mongo"].close()
    except Exception: pass

# ─── Periodic heartbeat (updates Redis every 30s) ────────────────────
async def heartbeat(ctx: dict):
    try:
        await ctx["redis"].set("mediadview:worker:heartbeat",
                               str(int(datetime.now(timezone.utc).timestamp())), ex=90)
    except Exception as e:
        log.warning("heartbeat failed: %s", e)

# ═══════════════════════════════════════════════════════════════════════
# JOBS
# ═══════════════════════════════════════════════════════════════════════

async def send_email_job(ctx, to: str, subject: str, body_html: str,
                         attachments: list | None = None,
                         _idem: Optional[str] = None) -> dict:
    """Send transactional email via SMTP. Retried by arq on failure."""
    if await _idem_seen(ctx, _idem):
        log.info("send_email_job dedup by idem=%s", _idem)
        return {"status": "duplicate"}
    from finance_email import send_email_raw  # existing helper
    try:
        result = await send_email_raw(to=to, subject=subject, body_html=body_html,
                                      attachments=attachments or [])
        return {"status": "sent", "provider_id": result.get("id") if isinstance(result, dict) else None}
    except Exception as e:
        log.exception("send_email failed to=%s", to)
        raise  # arq will retry with exponential backoff


async def generate_invoice_pdf_job(ctx, invoice_id: str,
                                   _idem: Optional[str] = None) -> dict:
    """Regenerate an invoice PDF and cache it (Redis)."""
    if await _idem_seen(ctx, _idem):
        return {"status": "duplicate"}
    from finance_pdf import render_invoice_pdf
    inv = await ctx["db"].fin_invoices.find_one({"id": invoice_id})
    if not inv:
        return {"status": "not_found"}
    pdf_bytes = await render_invoice_pdf(ctx["db"], inv)
    # Cache in Redis for 24h so the API can serve it without regenerating
    await ctx["redis"].set(f"mediadview:invoice_pdf:{invoice_id}",
                           pdf_bytes, ex=86400)
    return {"status": "ok", "bytes": len(pdf_bytes)}


async def process_media_job(ctx, media_id: str, _idem: Optional[str] = None) -> dict:
    """Placeholder: image/video optimization (thumbnails, metadata, etc.)"""
    if await _idem_seen(ctx, _idem):
        return {"status": "duplicate"}
    m = await ctx["db"].media.find_one({"id": media_id})
    if not m:
        return {"status": "not_found"}
    # Full logic will be filled in during Fase 4 (R2 upload).
    log.info("process_media_job scheduled for media %s (placeholder)", media_id)
    return {"status": "scheduled"}


async def sync_screen_job(ctx, screen_id: str, _idem: Optional[str] = None) -> dict:
    """Invalidate any screen cache and broadcast a reload signal via Redis pub/sub.
    The web-api's WebSocket manager will pick it up when we implement the pub/sub
    bridge; in single-instance dev it also works via direct call."""
    if await _idem_seen(ctx, _idem):
        return {"status": "duplicate"}
    # Purge any cached playlist entries
    try:
        from redis_client import cache
        await cache.delete_prefix(f"screen:{screen_id}")
    except Exception:
        pass
    # Publish to redis channel for future multi-instance broadcast
    try:
        await ctx["redis"].publish("mediadview:screen:reload", screen_id)
    except Exception:
        pass
    return {"status": "ok", "screen_id": screen_id}


# ═══════════════════════════════════════════════════════════════════════
# CRON JOBS (embedded in same worker for now)
# When volume grows split to a dedicated cron worker — API stays unchanged.
# ═══════════════════════════════════════════════════════════════════════

async def cron_monthly_billing(ctx):
    """Trigger the monthly invoice generation on the 1st of every month, 15:00 UTC (=11 EDT)."""
    try:
        from finance_scheduler import monthly_billing_job
        await monthly_billing_job(ctx["db"])
        log.info("cron_monthly_billing OK")
    except Exception:
        log.exception("cron_monthly_billing failed")
        raise

async def cron_overdue_reminders(ctx):
    """Daily reminder pass at 14:00 UTC (=10 EDT)."""
    try:
        from finance_scheduler import overdue_reminder_job
        await overdue_reminder_job(ctx["db"])
    except Exception:
        log.exception("cron_overdue_reminders failed")
        raise

async def cron_a40_schedule_tick(ctx):
    """Every minute — evaluate A40 sleep/wake schedule."""
    try:
        from colorlight_scheduler import evaluate_schedules
        await evaluate_schedules(ctx["db"])
    except Exception:
        log.exception("cron_a40_schedule_tick failed")


# ═══════════════════════════════════════════════════════════════════════
# ARQ WORKER SETTINGS
# ═══════════════════════════════════════════════════════════════════════

if HAS_ARQ:
    class WorkerSettings:
        """Loaded by `arq worker.WorkerSettings`."""
        # Connection
        redis_settings = RedisSettings.from_dsn(REDIS_URL) if REDIS_URL else RedisSettings()

        # Job list
        functions = [
            send_email_job,
            generate_invoice_pdf_job,
            process_media_job,
            sync_screen_job,
        ]

        # Lifecycle hooks
        on_startup  = startup
        on_shutdown = shutdown

        # Reliability
        max_tries     = MAX_RETRIES         # exponential backoff by arq
        job_timeout   = JOB_TIMEOUT
        keep_result   = KEEP_RESULT
        max_jobs      = int(os.environ.get("WORKER_MAX_JOBS", "10"))
        health_check_interval = 30
        allow_abort_jobs = True

        # Scheduled jobs (all times UTC; adjust if your Render region drifts)
        cron_jobs = [
            # Monthly billing — 1st of the month at 15:00 UTC (11 AM Eastern)
            cron(cron_monthly_billing, month=None, day=1, hour=15, minute=0, keep_result=0),
            # Daily overdue reminders — every day at 14:00 UTC (10 AM Eastern)
            cron(cron_overdue_reminders, hour=14, minute=0, keep_result=0),
            # A40 sleep/wake — every minute
            cron(cron_a40_schedule_tick, minute=set(range(60)), keep_result=0, unique=False),
            # Worker heartbeat every 30s
            cron(heartbeat, second={0, 30}, keep_result=0, unique=False),
        ]
