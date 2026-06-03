"""
MediAd View — Automated Monthly Invoice Scheduler
- Runs on the 1st day of each month at 11:00 AM America/New_York (Ohio).
- Generates monthly invoices for all active contracts.
- Emails the invoices to clients via SMTP.
- Enqueues invoices for the local Windows print agent to pick up and print.
"""
import os
import uuid
import logging
import secrets
from datetime import datetime, date
from calendar import monthrange
from email.message import EmailMessage
from email.utils import formataddr

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("finance_scheduler")
logger.setLevel(logging.INFO)

EASTERN = pytz.timezone("America/New_York")


# =================== PRINT QUEUE HELPERS ===================
def make_print_token() -> str:
    return secrets.token_urlsafe(32)


async def enqueue_for_print(db, invoice: dict, kind: str = "invoice"):
    """Add an invoice (or contract / deposit) to the print queue."""
    job = {
        "id": str(uuid.uuid4()),
        "kind": kind,                       # 'invoice' | 'contract' | 'deposit'
        "doc_id": invoice["id"],
        "doc_number": invoice.get("invoice_number") or invoice.get("contract_number") or invoice.get("receipt_number") or "",
        "client_id": invoice.get("client_id"),
        "status": "pending",                # pending | printed | failed
        "copies": 1,
        "queued_at": datetime.utcnow().isoformat(),
        "printed_at": None,
        "attempts": 0,
        "last_error": None,
    }
    await db.fin_print_queue.insert_one(job)
    return job


# =================== MONTHLY INVOICE GENERATOR ===================
async def _generate_monthly_invoices(db, year: int, month: int):
    """Create invoices for the given period (year, month)."""
    from finance import next_doc_number, parse_date  # reuse existing helpers

    period_start = date(year, month, 1)
    period_end = date(year, month, monthrange(year, month)[1])
    days = (period_end - period_start).days + 1

    created = []
    contracts = await db.fin_contracts.find({"status": "active"}).to_list(2000)
    for ct in contracts:
        try:
            cs = parse_date(ct["start_date"]).date()
            ce = parse_date(ct["end_date"]).date()
            if cs > period_end or ce < period_start:
                continue
            existing = await db.fin_invoices.find_one({
                "contract_id": ct["id"],
                "period_start": period_start.isoformat(),
            })
            if existing:
                logger.info(f"  • Invoice for contract {ct.get('contract_number')} already exists — skipping")
                continue
            # Build line items
            items = []
            total = 0.0
            for idx, s in enumerate(ct.get("screens", []), 1):
                line_total = s["units"] * s["day_price"] * days
                items.append({
                    "line_no": f"{idx:02d}",
                    "description": f"LED Ultra Brightness {s.get('model', 'MAV-30540S')}",
                    "day_price": s["day_price"],
                    "days": days,
                    "units": s["units"],
                    "total": round(line_total, 2),
                })
                total += line_total
            inv_no = await next_doc_number(db)
            inv = {
                "id": str(uuid.uuid4()),
                "invoice_number": inv_no,
                "contract_id": ct["id"],
                "client_id": ct["client_id"],
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "issue_date": period_start.isoformat(),
                "due_date": period_start.isoformat(),
                "items": items,
                "subtotal": round(total, 2),
                "tax": 0.0,
                "total": round(total, 2),
                "amount_paid": 0.0,
                "balance": round(total, 2),
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
                "auto_generated": True,
                "email_sent": False,
                "print_queued": False,
            }
            await db.fin_invoices.insert_one(inv)
            inv.pop("_id", None)
            created.append(inv)
        except Exception as e:
            logger.exception(f"Failed to generate invoice for contract {ct.get('id')}: {e}")
    return created


# =================== EMAIL SENDING ===================
async def _send_invoice_email(db, inv: dict):
    """Send invoice via SMTP. Returns True if sent, raises on configuration errors only."""
    import aiosmtplib
    from finance_email import decrypt_password, render_invoice_email_html, fmt_money, fmt_date
    from finance_pdf import generate_invoice_pdf, COMPANY

    client = await db.fin_clients.find_one({"id": inv["client_id"]}) or {}
    to_addr = (client.get("email") or "").strip()
    if not to_addr:
        logger.warning(f"  • Skip email for {inv.get('invoice_number')} — client {client.get('business_name')} has no email")
        return False

    s = await db.fin_settings.find_one({"_id": "email"})
    if not s or not s.get("enabled"):
        logger.warning("  • Skip email — SMTP not configured/enabled in Settings → Email")
        return False

    base_url = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    pdf_bytes = generate_invoice_pdf(inv, client)
    pdf_filename = f"Invoice_{inv.get('invoice_number', '')}.pdf"

    msg = EmailMessage()
    msg["From"] = formataddr((s.get("from_name", "MediAd View Billing"), s.get("from_email") or s.get("smtp_user")))
    msg["To"] = to_addr
    if s.get("reply_to"):
        msg["Reply-To"] = s["reply_to"]
    msg["Subject"] = f"Your MediAd View Invoice {inv.get('invoice_number', '')} — {fmt_money(inv.get('balance', inv.get('total', 0)))} due"
    text_body = (
        f"Hello {client.get('representative', '')},\n\n"
        f"Your invoice {inv.get('invoice_number', '')} is attached.\n"
        f"Amount due: {fmt_money(inv.get('balance', inv.get('total', 0)))}\n"
        f"Due date: {fmt_date(inv.get('due_date', ''))}\n\n"
        f"Payment to:\n"
        f"  Bank: {COMPANY['bank_name']}\n"
        f"  Account #: {COMPANY['account_number']}\n"
        f"  Routing: {COMPANY['routing']}\n\n"
        f"Questions? {COMPANY['phone_1']}\n"
        f"{COMPANY['name']}\n"
    )
    msg.set_content(text_body)
    msg.add_alternative(render_invoice_email_html(inv, client, base_url=base_url), subtype="html")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=pdf_filename)

    pwd = decrypt_password(s.get("smtp_password", ""))
    port = int(s.get("smtp_port", 587))
    use_tls = port == 465
    await aiosmtplib.send(
        msg,
        hostname=s.get("smtp_host", "smtp.titan.email"),
        port=port,
        username=s.get("smtp_user"),
        password=pwd,
        use_tls=use_tls,
        start_tls=not use_tls,
        timeout=30,
    )
    return True


# =================== MAIN MONTHLY JOB ===================
async def monthly_billing_job(db):
    """Run on day 1 of each month at 11:00 AM Eastern (Ohio time).
    1. Generate invoices for current month.
    2. Email each to the client.
    3. Enqueue for local printer.
    """
    now_et = datetime.now(EASTERN)
    logger.info("=" * 60)
    logger.info(f"[Monthly Billing] Starting — {now_et.strftime('%Y-%m-%d %H:%M %Z')}")

    created = await _generate_monthly_invoices(db, now_et.year, now_et.month)
    logger.info(f"  ✓ Generated {len(created)} new invoice(s)")

    sent_email = 0
    queued_print = 0
    for inv in created:
        # 1) Email
        try:
            ok = await _send_invoice_email(db, inv)
            if ok:
                sent_email += 1
                await db.fin_invoices.update_one(
                    {"id": inv["id"]},
                    {"$set": {"email_sent": True, "email_sent_at": datetime.utcnow().isoformat()}}
                )
        except Exception as e:
            logger.exception(f"  ✗ Email failed for {inv.get('invoice_number')}: {e}")
            await db.fin_invoices.update_one(
                {"id": inv["id"]},
                {"$set": {"email_error": str(e)}}
            )
        # 2) Print queue
        try:
            await enqueue_for_print(db, inv, kind="invoice")
            await db.fin_invoices.update_one(
                {"id": inv["id"]}, {"$set": {"print_queued": True}}
            )
            queued_print += 1
        except Exception as e:
            logger.exception(f"  ✗ Print queue failed for {inv.get('invoice_number')}: {e}")

    # Record run history
    await db.fin_scheduler_log.insert_one({
        "id": str(uuid.uuid4()),
        "job": "monthly_billing",
        "ran_at": datetime.utcnow().isoformat(),
        "period": f"{now_et.year}-{now_et.month:02d}",
        "generated": len(created),
        "emailed": sent_email,
        "queued_print": queued_print,
    })
    logger.info(f"[Monthly Billing] Done — emailed {sent_email}, queued for print {queued_print}")
    logger.info("=" * 60)


# =================== OVERDUE REMINDERS (DAILY) ===================
async def overdue_reminder_job(db):
    """Daily at 10:00 AM Eastern — mark overdue + send reminder email (1 per invoice per week)."""
    now = datetime.utcnow().date()
    cursor = db.fin_invoices.find({"status": {"$in": ["pending", "overdue"]}})
    n_marked = 0
    n_emailed = 0
    async for inv in cursor:
        try:
            due = inv.get("due_date")
            if not due:
                continue
            due_d = datetime.fromisoformat(due[:10]).date()
            if due_d < now and inv.get("balance", 0) > 0:
                # mark overdue
                if inv.get("status") != "overdue":
                    await db.fin_invoices.update_one({"id": inv["id"]}, {"$set": {"status": "overdue"}})
                    n_marked += 1
                # Throttle reminders: at most 1 per 7 days
                last = inv.get("last_reminder_at")
                send = True
                if last:
                    try:
                        ld = datetime.fromisoformat(last).date()
                        if (now - ld).days < 7:
                            send = False
                    except Exception:
                        pass
                if send:
                    try:
                        ok = await _send_invoice_email(db, inv)
                        if ok:
                            n_emailed += 1
                            await db.fin_invoices.update_one(
                                {"id": inv["id"]}, {"$set": {"last_reminder_at": datetime.utcnow().isoformat()}}
                            )
                    except Exception as e:
                        logger.warning(f"Reminder email failed for {inv.get('invoice_number')}: {e}")
        except Exception as e:
            logger.exception(f"Overdue check error: {e}")
    if n_marked or n_emailed:
        logger.info(f"[Overdue] Marked {n_marked} as overdue · Sent {n_emailed} reminder(s)")


# =================== SCHEDULER BOOTSTRAP ===================
_scheduler = None


def start_scheduler(db):
    """Initialize and start the APScheduler instance (singleton)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.info("Scheduler already running — skip")
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone=EASTERN)
    # Day 1 at 11:00 AM Eastern
    _scheduler.add_job(
        monthly_billing_job, CronTrigger(day=1, hour=11, minute=0, timezone=EASTERN),
        args=[db], id="monthly_billing", replace_existing=True, misfire_grace_time=3600,
    )
    # Daily at 10:00 AM Eastern — overdue reminders
    _scheduler.add_job(
        overdue_reminder_job, CronTrigger(hour=10, minute=0, timezone=EASTERN),
        args=[db], id="overdue_reminders", replace_existing=True, misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info("=" * 60)
    logger.info("✓ Finance Scheduler started")
    logger.info("  • Monthly billing: day 1 at 11:00 AM America/New_York")
    logger.info("  • Overdue reminders: daily at 10:00 AM America/New_York")
    logger.info("=" * 60)
    return _scheduler


def get_scheduler():
    return _scheduler
