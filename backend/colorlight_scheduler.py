"""
MediAd View — Colorlight A40 Schedule Scheduler

Runs every minute and evaluates the sleep/wake schedule configured on every
terminal stored in db.colorlight_terminals (see colorlight_player.py).

A schedule document looks like:

    {
      "enabled":      true,
      "wakeup_time":  "07:00",   # HH:MM  (24h, America/New_York)
      "sleep_time":   "22:00",   # HH:MM  (24h)
      "days":         [1,1,1,1,1,1,1],  # Mon..Sun (1 = active)
    }

When the current local time (America/New_York) matches the wakeup_time the
scheduler queues an "api/wakeup" command for the device; when it matches the
sleep_time it queues an "api/sleep" command. The A40 polls these commands
through /api/wp-json/wp/v2/comments and executes them.

The job is idempotent: we record the last triggered action of the day per
device in `colorlight_terminals.last_schedule_action` so the same command is
not requeued repeatedly if the device stays online.
"""
import os
import uuid
import logging
from datetime import datetime
from typing import Optional

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("colorlight_scheduler")
logger.setLevel(logging.INFO)

EASTERN = pytz.timezone(os.getenv("COLORLIGHT_TZ", "America/New_York"))

_scheduler: Optional[AsyncIOScheduler] = None


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


async def _queue_command(db, device_id: str, author_url: str):
    """Insert a pending command row identical to what /api/cls/sleep|wakeup creates."""
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    cmd_id = now_ms % 1_000_000_000
    doc = {
        "command_id":  cmd_id,
        "device_id":   device_id,
        "post_id":     0,
        "author_url":  author_url,
        "content":     {},
        "status":      "pending",
        "created_at":  _now_iso(),
        "modified_at": _now_iso(),
        "source":      "scheduler",
    }
    await db.colorlight_commands.insert_one(doc)
    logger.info(f"⏰ Queued {author_url} for device {device_id}")


async def evaluate_schedules(db):
    """Check every enabled schedule and queue a wakeup/sleep command if it's the
    exact minute. Marks last_schedule_action to make the operation idempotent."""
    now_local = datetime.now(EASTERN)
    hhmm = now_local.strftime("%H:%M")
    weekday_idx = now_local.weekday()  # 0=Mon .. 6=Sun
    today_key = now_local.strftime("%Y-%m-%d")

    try:
        cursor = db.colorlight_terminals.find({
            "schedule.enabled": True,
            "mode": "direct",
        })
        triggered = 0
        async for term in cursor:
            sched = term.get("schedule") or {}
            days = sched.get("days") or [1]*7
            if len(days) < 7:
                days = (days + [1]*7)[:7]
            if not days[weekday_idx]:
                continue

            wakeup_time = sched.get("wakeup_time") or "07:00"
            sleep_time  = sched.get("sleep_time")  or "22:00"
            last_action = term.get("last_schedule_action") or {}

            device_id = term.get("device_id")

            # ---- WAKEUP ----
            if hhmm == wakeup_time:
                key = f"wakeup_{today_key}"
                if last_action.get("key") != key:
                    await _queue_command(db, device_id, "api/wakeup")
                    await db.colorlight_terminals.update_one(
                        {"device_id": device_id},
                        {"$set": {"last_schedule_action": {
                            "key": key, "type": "wakeup",
                            "fired_at": _now_iso(),
                        }}}
                    )
                    triggered += 1

            # ---- SLEEP ----
            if hhmm == sleep_time:
                key = f"sleep_{today_key}"
                if last_action.get("key") != key:
                    await _queue_command(db, device_id, "api/sleep")
                    await db.colorlight_terminals.update_one(
                        {"device_id": device_id},
                        {"$set": {"last_schedule_action": {
                            "key": key, "type": "sleep",
                            "fired_at": _now_iso(),
                        }}}
                    )
                    triggered += 1

        if triggered:
            logger.info(f"📅 Scheduler tick @ {hhmm} (EST) — fired {triggered} command(s)")
    except Exception as e:
        logger.exception(f"colorlight scheduler tick error: {e}")


def start_colorlight_scheduler(db):
    """Start the APScheduler that fires schedule evaluations every minute."""
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.info("Colorlight scheduler already running — skip")
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone=EASTERN)
    _scheduler.add_job(
        evaluate_schedules,
        CronTrigger(minute="*", timezone=EASTERN),
        args=[db],
        id="colorlight_schedule_tick",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=120,
    )
    _scheduler.start()
    logger.info("=" * 60)
    logger.info("✓ Colorlight Scheduler started")
    logger.info("  • Sleep/Wake schedule tick: every minute (TZ=%s)", EASTERN.zone)
    logger.info("=" * 60)
    return _scheduler


def get_colorlight_scheduler():
    return _scheduler
