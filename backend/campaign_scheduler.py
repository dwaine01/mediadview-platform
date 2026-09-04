# ruff: noqa: E501,E701,E702
"""
campaign_scheduler.py — MediaView Fase 3: Campaign Lifecycle Automation
────────────────────────────────────────────────────────────────────────
Runs every minute via APScheduler (AsyncIOScheduler) embedded in the FastAPI
process. Follows the exact same pattern as colorlight_scheduler.py.

State Machine (all UTC, idempotent):
  APPROVED   → SCHEDULED  (start_date >  today, valid payment)
  APPROVED   → ACTIVE     (start_date <= today AND end_date > today)
  SCHEDULED  → ACTIVE     (start_date <= today AND end_date > today)
  ACTIVE     → COMPLETED  (end_date   <= today)

Guard rules:
  • REJECTED / CANCELLED / REFUNDED / PENDING_REVIEW / DRAFT  →  NEVER auto-activate
  • payment_status must be in VALID_PAYMENT_STATUSES
  • All DB updates are atomic: filter on current status prevents race conditions
    (two concurrent scheduler ticks cannot double-transition the same document)

Observability:
  • Writes to `campaign_transitions` collection on every state change
  • Fields: campaign_id, old_status, new_status, transition_time, source, reason
  • Logs info only when transitions happen (no log spam on idle ticks)
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("campaign_scheduler")
logger.setLevel(logging.INFO)

# ── Constants ──────────────────────────────────────────────────────────────────
VALID_PAYMENT_STATUSES = {"mocked_paid", "paid", "stripe_paid"}

# Statuses that can NEVER auto-activate
BLOCKED_FROM_ACTIVATION = {
    "REJECTED", "CANCELLED", "REFUNDED",
    "PENDING_REVIEW", "DRAFT", "COMPLETED",
}

ACTIVATABLE_STATUSES = {"APPROVED", "SCHEDULED"}

# ── Singleton scheduler reference ─────────────────────────────────────────────
_scheduler: Optional[AsyncIOScheduler] = None


# ── Observability helper ───────────────────────────────────────────────────────
async def _log_transition(
    db,
    campaign_id: str,
    old_status: str,
    new_status: str,
    now: datetime,
    reason: str,
    affected_screens: list = None,
):
    """Write a campaign_transitions document for auditability."""
    record = {
        "id": str(uuid.uuid4()),
        "campaign_id": campaign_id,
        "old_status": old_status,
        "new_status": new_status,
        "transition_time": now,
        "source": "campaign_scheduler",
        "reason": reason,
        "affected_screens": affected_screens or [],
    }
    try:
        await db.campaign_transitions.insert_one(record)
    except Exception as e:
        logger.warning("Failed to write campaign_transitions log: %s", e)


# ── Core scheduler function ────────────────────────────────────────────────────
async def run_campaign_scheduler(db) -> dict:
    """
    Main scheduler tick — idempotent and concurrency-safe.

    Uses MongoDB atomic update_one with a status guard:
        filter = {"id": X, "status": expected_old}
    so only the FIRST concurrent caller can modify a given document.
    Subsequent callers silently skip (modified_count == 0).

    Returns a summary dict with all transitions made during this tick.
    """
    now_utc = datetime.utcnow()
    today = now_utc.strftime("%Y-%m-%d")   # "2026-09-03" — UTC date for comparisons
    transitions = []

    # ── Step 1: APPROVED/SCHEDULED → ACTIVE ───────────────────────────────────
    # Conditions:
    #   - status in {APPROVED, SCHEDULED}
    #   - payment_status is valid
    #   - start_date <= today (campaign should be running)
    #   - end_date > today   (campaign hasn't ended yet)
    candidates_to_activate = await db.ad_campaigns.find({
        "status": {"$in": list(ACTIVATABLE_STATUSES)},
        "payment_status": {"$in": list(VALID_PAYMENT_STATUSES)},
        "start_date": {"$lte": today},
        "end_date":   {"$gt":  today},
    }).to_list(500)

    for c in candidates_to_activate:
        old_status = c["status"]
        result = await db.ad_campaigns.update_one(
            {
                "id": c["id"],
                "status": old_status,          # Atomic guard — concurrency-safe
            },
            {"$set": {
                "status": "ACTIVE",
                "status_changed_at": now_utc,
                "scheduler_source": "campaign_scheduler",
                "activated_at": now_utc,
            }}
        )
        if result.modified_count > 0:
            screens = c.get("selected_screens") or []
            logger.info(
                "📢 Campaign ACTIVATED: %s | %s → ACTIVE | screens=%s | start=%s end=%s",
                c.get("name"), old_status, screens, c.get("start_date"), c.get("end_date")
            )
            await _log_transition(
                db, c["id"], old_status, "ACTIVE", now_utc,
                "start_date reached",
                affected_screens=screens,
            )
            transitions.append({
                "campaign_id": c["id"],
                "campaign_name": c.get("name"),
                "old_status": old_status,
                "new_status": "ACTIVE",
            })

    # ── Step 2: APPROVED → SCHEDULED (future campaigns) ───────────────────────
    # Conditions:
    #   - status == APPROVED
    #   - payment_status is valid
    #   - start_date > today (not yet started)
    candidates_to_schedule = await db.ad_campaigns.find({
        "status": "APPROVED",
        "payment_status": {"$in": list(VALID_PAYMENT_STATUSES)},
        "start_date": {"$gt": today},
    }).to_list(500)

    for c in candidates_to_schedule:
        result = await db.ad_campaigns.update_one(
            {"id": c["id"], "status": "APPROVED"},  # Atomic guard
            {"$set": {
                "status": "SCHEDULED",
                "status_changed_at": now_utc,
                "scheduler_source": "campaign_scheduler",
                "scheduled_at": now_utc,
            }}
        )
        if result.modified_count > 0:
            logger.info(
                "📅 Campaign SCHEDULED: %s | APPROVED → SCHEDULED | start=%s",
                c.get("name"), c.get("start_date")
            )
            await _log_transition(
                db, c["id"], "APPROVED", "SCHEDULED", now_utc,
                "start_date is in the future",
                affected_screens=c.get("selected_screens") or [],
            )
            transitions.append({
                "campaign_id": c["id"],
                "campaign_name": c.get("name"),
                "old_status": "APPROVED",
                "new_status": "SCHEDULED",
            })

    # ── Step 3: ACTIVE → COMPLETED ────────────────────────────────────────────
    # Conditions:
    #   - status == ACTIVE
    #   - end_date <= today (campaign window closed)
    candidates_to_complete = await db.ad_campaigns.find({
        "status": "ACTIVE",
        "end_date": {"$lte": today},
    }).to_list(500)

    for c in candidates_to_complete:
        result = await db.ad_campaigns.update_one(
            {"id": c["id"], "status": "ACTIVE"},  # Atomic guard
            {"$set": {
                "status": "COMPLETED",
                "status_changed_at": now_utc,
                "scheduler_source": "campaign_scheduler",
                "completed_at": now_utc,
            }}
        )
        if result.modified_count > 0:
            screens = c.get("selected_screens") or []
            logger.info(
                "✅ Campaign COMPLETED: %s | ACTIVE → COMPLETED | screens=%s | end=%s",
                c.get("name"), screens, c.get("end_date")
            )
            await _log_transition(
                db, c["id"], "ACTIVE", "COMPLETED", now_utc,
                "end_date reached",
                affected_screens=screens,
            )
            transitions.append({
                "campaign_id": c["id"],
                "campaign_name": c.get("name"),
                "old_status": "ACTIVE",
                "new_status": "COMPLETED",
            })

    if transitions:
        logger.info(
            "Campaign scheduler tick @ %s UTC — %d transition(s): %s",
            today,
            len(transitions),
            [(t["campaign_name"], t["old_status"] + "→" + t["new_status"]) for t in transitions],
        )

    return {
        "transitions": transitions,
        "total": len(transitions),
        "checked_at": now_utc.isoformat() + "Z",
    }


# ── Cron tick wrapper (called by APScheduler every minute) ────────────────────
async def _scheduler_tick(db):
    """Thin wrapper around run_campaign_scheduler for APScheduler."""
    try:
        await run_campaign_scheduler(db)
    except Exception as e:
        logger.exception("campaign_scheduler tick error: %s", e)


# ── APScheduler lifecycle ──────────────────────────────────────────────────────
def start_campaign_scheduler(db):
    """
    Start the APScheduler that fires campaign state transitions every minute.
    Safe to call multiple times — only one instance runs at a time.

    max_instances=1 ensures a long-running tick won't overlap with the next.
    misfire_grace_time=120 allows recovery after a brief server restart.
    """
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.info("Campaign scheduler already running — skip")
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _scheduler_tick,
        CronTrigger(minute="*", timezone="UTC"),
        args=[db],
        id="campaign_lifecycle_tick",
        replace_existing=True,
        max_instances=1,          # No overlapping executions
        misfire_grace_time=120,   # Catch up if backend restarted
    )
    _scheduler.start()
    logger.info("=" * 60)
    logger.info("✓ Campaign Scheduler started")
    logger.info("  • Lifecycle tick: every minute (UTC)")
    logger.info("  • Transitions: APPROVED→SCHEDULED→ACTIVE→COMPLETED")
    logger.info("  • Concurrency: atomic MongoDB status guards")
    logger.info("  • Observability: campaign_transitions collection")
    logger.info("=" * 60)
    return _scheduler


def stop_campaign_scheduler():
    """Graceful shutdown — called on FastAPI shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Campaign scheduler stopped")


def get_campaign_scheduler():
    """Return the running scheduler instance (or None if not started)."""
    return _scheduler
