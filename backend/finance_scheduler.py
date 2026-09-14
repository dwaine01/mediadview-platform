# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
MediAd View — Automated Monthly Invoice Scheduler
- Runs on the 1st day of each month at 11:00 AM America/New_York (Ohio).
- Generates monthly invoices for all active contracts.
- Emails the invoices to clients via SMTP.
- Enqueues invoices for the local Windows print agent to pick up and print.
"""
import logging
import os
import secrets
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta
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
async def _generate_monthly_invoices(db, year: int, month: int, client_id: str = "",
                                     statuses: tuple = ("active",)):
    """Create invoices for the given period (year, month).

    `client_id` limita la generación a un solo cliente y `statuses` a ciertos
    estados de contrato: los usa
    `POST /api/finance/invoices/generate-for-client` para facturar los meses
    atrasados de alguien que se dio de alta debiendo (ahí también valen los
    contratos `draft` y `expired`, porque un mes viejo lo cubre un contrato que
    ya venció). El cron mensual sigue mirando sólo los `active`.

    FACTURACIÓN ANTICIPADA (decisión del dueño, 2026-06): el período siempre es
    el mes completo y el **vencimiento es el día 1 de ese mes**, pero la factura
    se emite y se manda el **25 del mes anterior**. Así el cliente la recibe con
    una semana de anticipación, el recordatorio de «vence en 3 días» sirve de
    verdad, y el dinero entra el día 1. `issue_date` es la fecha real de emisión
    (hoy), no el día 1: si no, la factura salía fechada el mismo día que vencía.
    """
    from finance import next_doc_number, parse_date  # reuse existing helpers

    period_start = date(year, month, 1)
    period_end = date(year, month, monthrange(year, month)[1])
    days = (period_end - period_start).days + 1
    issue_date = min(datetime.now(EASTERN).date(), period_start)

    created = []
    query = {"status": {"$in": list(statuses)}}
    if client_id:
        query["client_id"] = client_id
    contracts = await db.fin_contracts.find(query).to_list(2000)
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
                "issue_date": issue_date.isoformat(),
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
    """Send invoice via SMTP. Returns True if sent, raises on configuration errors only.

    Todo envío queda en `fin_email_log` (bien o mal): es el historial que se ve
    en el panel, y lo que se le muestra al cliente que dice «nunca me llegó»."""
    import aiosmtplib
    from collections_engine import log_email
    from finance_email import (
        attach_email_logo,
        decrypt_password,
        fmt_date,
        fmt_money,
        render_invoice_email_html,
    )
    from finance_pdf import COMPANY, generate_invoice_pdf

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
    attach_email_logo(msg)
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=pdf_filename)

    pwd = decrypt_password(s.get("smtp_password", ""))
    if not pwd:
        # La contraseña falta o está cifrada con una llave que ya cambió. Sin
        # esto el envío mensual fallaba todos los meses con un «535
        # authentication failed» y nadie sabía qué había que corregir. Queda
        # anotado en el historial para que el panel lo muestre.
        from finance_email import SMTP_PASSWORD_MISSING, SMTP_PASSWORD_UNREADABLE
        reason = SMTP_PASSWORD_UNREADABLE if s.get("smtp_password") else SMTP_PASSWORD_MISSING
        await log_email(db, client_id=inv.get("client_id", ""), invoice_id=inv.get("id"),
                        kind="invoice", to=to_addr, subject=msg["Subject"], ok=False,
                        error=reason)
        raise RuntimeError(reason)
    port = int(s.get("smtp_port", 587))
    use_tls = port == 465
    try:
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
    except Exception as exc:
        await log_email(db, client_id=inv.get("client_id", ""), invoice_id=inv.get("id"),
                        kind="invoice", to=to_addr, subject=msg["Subject"], ok=False,
                        error=str(exc))
        raise
    await log_email(db, client_id=inv.get("client_id", ""), invoice_id=inv.get("id"),
                    kind="invoice", to=to_addr, subject=msg["Subject"], ok=True)
    return True



async def _send_plain_email(db, client: dict, subject: str, html: str, *,
                            kind: str, invoice_id=None) -> bool:
    """Manda un correo de cobranza (recordatorio o recibo) y lo deja anotado.

    Sin adjunto: el recordatorio no necesita repetir el PDF, necesita que el
    cliente recuerde que debe. El PDF va en la factura original."""
    from collections_engine import log_email
    from finance_email import (
        SMTP_PASSWORD_MISSING,
        SMTP_PASSWORD_UNREADABLE,
        attach_email_logo,
        decrypt_password,
    )

    to_addr = (client.get("email") or "").strip()
    if not to_addr:
        return False
    s = await db.fin_settings.find_one({"_id": "email"})
    if not s or not s.get("enabled"):
        return False

    msg = EmailMessage()
    msg["From"] = formataddr((s.get("from_name", "MediAd View Billing"),
                              s.get("from_email") or s.get("smtp_user")))
    msg["To"] = to_addr
    if s.get("reply_to"):
        msg["Reply-To"] = s["reply_to"]
    msg["Subject"] = subject
    msg.set_content("Este correo se ve mejor en formato HTML.")
    msg.add_alternative(html, subtype="html")
    # Recordatorios y recibos llevan la misma cabecera que la factura, así que
    # también necesitan el logo incrustado.
    attach_email_logo(msg)

    pwd = decrypt_password(s.get("smtp_password", ""))
    if not pwd:
        # Sin contraseña usable el servidor SMTP contesta «535 authentication
        # failed», que no le dice nada al dueño. Se corta acá con el motivo real:
        # o falta cargarla, o está cifrada con una llave que ya cambió.
        reason = SMTP_PASSWORD_UNREADABLE if s.get("smtp_password") else SMTP_PASSWORD_MISSING
        await log_email(db, client_id=client.get("id", ""), invoice_id=invoice_id,
                        kind=kind, to=to_addr, subject=subject, ok=False,
                        error=reason)
        raise RuntimeError(reason)

    import aiosmtplib
    port = int(s.get("smtp_port", 587))
    use_tls = port == 465
    try:
        await aiosmtplib.send(
            msg, hostname=s.get("smtp_host", "smtp.titan.email"), port=port,
            username=s.get("smtp_user"), password=pwd,
            use_tls=use_tls, start_tls=not use_tls, timeout=30,
        )
    except Exception as exc:
        await log_email(db, client_id=client.get("id", ""), invoice_id=invoice_id,
                        kind=kind, to=to_addr, subject=subject, ok=False, error=str(exc))
        raise
    await log_email(db, client_id=client.get("id", ""), invoice_id=invoice_id,
                    kind=kind, to=to_addr, subject=subject, ok=True)
    return True


async def send_payment_receipt(db, invoice: dict, amount: float) -> bool:
    """El «gracias por su pago», con el saldo que quede."""
    from collections_engine import receipt_body

    client = await db.fin_clients.find_one({"id": invoice.get("client_id")}) or {}
    fully_paid = float(invoice.get("balance") or 0) <= 0.01
    subject, html = receipt_body(invoice, client, amount, fully_paid)
    return await _send_plain_email(db, client, subject, html,
                                   kind="receipt", invoice_id=invoice.get("id"))


# =================== MAIN MONTHLY JOB ===================
async def monthly_billing_job(db):
    """Corre el **25 de cada mes a las 11:00 AM** (hora de Ohio).

    1. Genera las facturas del MES SIGUIENTE (vencen el día 1 de ese mes).
    2. Manda cada una por correo con el PDF adjunto.
    3. Las encola para la impresora local.

    Si se dispara a mano en la primera mitad del mes, factura el mes en curso
    (útil para regularizar un mes que quedó sin facturar).
    """
    now_et = datetime.now(EASTERN)
    logger.info("=" * 60)
    logger.info(f"[Monthly Billing] Starting — {now_et.strftime('%Y-%m-%d %H:%M %Z')}")

    # Facturación anticipada: del día 15 en adelante se factura el mes que viene.
    if now_et.day >= 15:
        target = (date(now_et.year, now_et.month, 1) + timedelta(days=31)).replace(day=1)
    else:
        target = date(now_et.year, now_et.month, 1)
    logger.info(f"[Monthly Billing] Período facturado: {target.isoformat()[:7]} (vence {target})")

    created = await _generate_monthly_invoices(db, target.year, target.month)
    logger.info(f"  ✓ Generated {len(created)} new invoice(s)")

    sent_email = 0
    queued_print = 0
    for inv in created:
        # 1) Email
        try:
            ok = await _send_invoice_email(db, inv)
            if ok:
                sent_email += 1
                from collections_engine import log_email
                client = await db.fin_clients.find_one({"id": inv.get("client_id")}) or {}
                await log_email(db, client_id=inv.get("client_id", ""), invoice_id=inv["id"],
                                kind="invoice", to=client.get("email", ""),
                                subject=f"Factura {inv.get('invoice_number', '')}", ok=True)
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
    """Diario a las 10:00 (Ohio): marca vencidas y recuerda POR ETAPAS.

    Cada etapa se manda una sola vez (tres días antes, el día del vencimiento,
    y a los 7, 15 y 30 días). Si la factura se paga, sale del filtro y los
    recordatorios paran solos."""
    from collections_engine import reminder_body, stage_due_today

    today = datetime.utcnow()
    marked = reminded = failed = 0
    async for inv in db.fin_invoices.find({"status": {"$in": ["pending", "overdue", "partial"]}}):
        try:
            due = inv.get("due_date")
            if not due:
                continue
            due_d = datetime.fromisoformat(str(due)[:10]).date()
            if due_d < today.date() and float(inv.get("balance") or 0) > 0.01 \
                    and inv.get("status") != "overdue":
                await db.fin_invoices.update_one({"id": inv["id"]},
                                                 {"$set": {"status": "overdue"}})
                inv["status"] = "overdue"
                marked += 1

            stage = stage_due_today(inv, today)
            if not stage:
                continue
            client = await db.fin_clients.find_one({"id": inv.get("client_id")}) or {}
            subject, html = reminder_body(inv, client, stage)
            try:
                sent = await _send_plain_email(db, client, subject, html,
                                               kind=f"reminder:{stage[0]}",
                                               invoice_id=inv["id"])
            except Exception as exc:
                failed += 1
                logger.warning(f"Recordatorio {stage[0]} falló para "
                               f"{inv.get('invoice_number')}: {exc}")
                continue
            if not sent:
                continue
            reminded += 1
            await db.fin_invoices.update_one({"id": inv["id"]}, {
                "$set": {"last_reminder_at": today.isoformat(),
                         "last_reminder_stage": stage[0]},
                "$push": {"reminders_sent": {"stage": stage[0],
                                             "at": today.isoformat()}},
            })
        except Exception as exc:
            logger.exception(f"Error revisando factura vencida: {exc}")

    if marked or reminded or failed:
        logger.info(f"[Cobranza] {marked} marcadas vencidas · {reminded} recordatorios "
                    f"enviados · {failed} fallidos")
    await db.fin_scheduler_log.insert_one({
        "id": str(uuid.uuid4()), "job": "collections",
        "ran_at": datetime.utcnow().isoformat(),
        "marked_overdue": marked, "reminders_sent": reminded, "failed": failed,
    })


# =================== SCHEDULER BOOTSTRAP ===================
_scheduler = None


def start_scheduler(db):
    """Initialize and start the APScheduler instance (singleton)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.info("Scheduler already running — skip")
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone=EASTERN)
    # Día 25 a las 11:00 AM Eastern — se facturan por adelantado las del mes
    # siguiente, que vencen el día 1 (decisión del dueño: «como lo hacen los
    # grandes», el cliente recibe la factura una semana antes del vencimiento).
    _scheduler.add_job(
        monthly_billing_job, CronTrigger(day=25, hour=11, minute=0, timezone=EASTERN),
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
    logger.info("  • Monthly billing: day 25 at 11:00 AM America/New_York (mes siguiente, vence el 1)")
    logger.info("  • Overdue reminders: daily at 10:00 AM America/New_York")
    logger.info("=" * 60)
    return _scheduler


def get_scheduler():
    return _scheduler
