"""Cobranza: recordar, cobrar, agradecer y dejar constancia de todo.

Una factura enviada no es una factura cobrada. Este módulo pone por escrito
cómo se cobra en MediaView:

1. La factura se emite y se manda el **día 25**, por el mes siguiente, y vence
   el **día 1** (`finance_scheduler.monthly_billing_job`). El cliente la recibe
   con una semana de anticipación, no el mismo día que vence.
2. Si no la pagan, el sistema recuerda **por etapas y una sola vez cada una**:
   tres días antes de vencer, el día que vence, y a los 7, 15 y 30 días de
   atraso. El tono sube de «aviso amable» a «cuenta suspendida», nunca al
   insulto: el cliente se queda o se va, y un cobro grosero lo ahuyenta.
3. Cuando pagan, los recordatorios **paran solos** (la factura sale del filtro)
   y se manda un **recibo de agradecimiento**.
4. Cada correo queda en la bitácora del cliente (`fin_email_log`), con fecha,
   destinatario y si salió o falló. Es lo que se mira cuando el cliente dice
   «a mí nunca me avisaron».
"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

# Etapas de recordatorio: (clave, días respecto al vencimiento, asunto, tono)
# Negativo = antes de vencer. Se manda una vez por etapa y nunca se repite.
STAGES = [
    ("pre_due", -3, "Su factura {number} vence en 3 días",
     "Le recordamos que la factura <b>{number}</b> por <b>{amount}</b> vence el "
     "<b>{due}</b>. Si ya la pagó, ignore este aviso y gracias."),
    ("due", 0, "Su factura {number} vence hoy",
     "La factura <b>{number}</b> por <b>{amount}</b> vence <b>hoy</b>. "
     "Puede pagarla hoy mismo y evitar recargos."),
    ("late_7", 7, "Factura {number} vencida — 7 días",
     "La factura <b>{number}</b> por <b>{amount}</b> venció el <b>{due}</b> y "
     "sigue pendiente. Le pedimos regularizarla esta semana."),
    ("late_15", 15, "Factura {number} vencida — 15 días",
     "Van 15 días de atraso en la factura <b>{number}</b> por <b>{amount}</b>. "
     "Para no interrumpir el servicio de sus pantallas, necesitamos el pago o "
     "que nos escriba para acordar una fecha."),
    ("late_30", 30, "Factura {number} — 30 días de atraso",
     "La factura <b>{number}</b> por <b>{amount}</b> tiene <b>30 días</b> de "
     "atraso. Si no recibimos el pago o una respuesta, su publicidad queda "
     "suspendida hasta regularizar la cuenta."),
]
STAGE_BY_KEY = {s[0]: s for s in STAGES}


def money(value) -> str:
    return f"${float(value or 0):,.2f}"


def due_date_of(invoice: dict) -> Optional[datetime]:
    raw = invoice.get("due_date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def stage_due_today(invoice: dict, today: datetime) -> Optional[tuple]:
    """Qué recordatorio toca hoy, si toca alguno.

    Se elige la etapa más avanzada que ya corresponda y que todavía no se haya
    mandado: si el sistema estuvo caído una semana, el cliente recibe UN correo
    al día siguiente, no cinco de golpe."""
    due = due_date_of(invoice)
    if not due or float(invoice.get("balance") or 0) <= 0.01:
        return None
    if str(invoice.get("status")) in ("paid", "cancelled", "void"):
        return None
    days_late = (today.date() - due.date()).days
    already = {r.get("stage") for r in (invoice.get("reminders_sent") or [])}
    candidate = None
    for stage in STAGES:
        if days_late >= stage[1] and stage[0] not in already:
            candidate = stage
    return candidate


def reminder_body(invoice: dict, client: dict, stage: tuple) -> tuple:
    """Asunto y cuerpo del recordatorio, en el idioma del cliente: español."""
    number = invoice.get("invoice_number") or invoice.get("id", "")[:8]
    due = due_date_of(invoice)
    values = {
        "number": number,
        "amount": money(invoice.get("balance") or invoice.get("total")),
        "due": due.strftime("%d/%m/%Y") if due else "—",
    }
    subject = stage[2].format(**values)
    greeting = client.get("contact_name") or client.get("name") or "Estimado cliente"
    # Misma hoja que el correo de la factura (cabecera blanca con el logo).
    from finance_email import render_email_shell
    cuerpo = f"""
      <p style="font-size:15px;color:#0f172a;margin:0 0 12px">Hola {greeting},</p>
      <p style="font-size:14.5px;color:#334155;line-height:1.7;margin:0 0 18px">{stage[3].format(**values)}</p>
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;margin-bottom:18px">
        <tr><td style="padding:16px 20px">
          <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13.5px">
            <tr><td style="padding:6px 0;color:#475569">Factura</td><td align="right" style="padding:6px 0;font-weight:700;color:#0f172a">{values['number']}</td></tr>
            <tr><td style="padding:6px 0;color:#475569">Vencimiento</td><td align="right" style="padding:6px 0;font-weight:700;color:#0f172a">{values['due']}</td></tr>
            <tr><td style="padding:6px 0;color:#475569">Saldo pendiente</td><td align="right" style="padding:6px 0;font-weight:800;color:#b91c1c">{values['amount']}</td></tr>
          </table>
        </td></tr>
      </table>
      <p style="font-size:13px;color:#64748b;line-height:1.6;margin:0">Si ya realizó el pago, escríbanos y lo aplicamos de inmediato.
      Si necesita otra fecha, respóndanos este correo y lo acordamos.</p>"""
    html = render_email_shell("Recordatorio de pago",
                              f"Factura {values['number']} · vence {values['due']}", cuerpo)
    return subject, html


def receipt_body(invoice: dict, client: dict, amount: float, fully_paid: bool) -> tuple:
    """El «gracias por su pago». Cobrar sin agradecer es perder al cliente."""
    number = invoice.get("invoice_number") or invoice.get("id", "")[:8]
    greeting = client.get("contact_name") or client.get("name") or "Estimado cliente"
    balance = float(invoice.get("balance") or 0)
    subject = (f"¡Gracias por su pago! Factura {number}" if fully_paid
               else f"Pago recibido — factura {number}")
    closing = ("Su factura queda <b>pagada</b>. Gracias por la confianza: su publicidad "
               "sigue al aire sin interrupciones."
               if fully_paid else
               f"Aplicamos su pago de <b>{money(amount)}</b>. Queda un saldo pendiente de "
               f"<b>{money(balance)}</b>.")
    html = f"""
      <div style="font-size:34px;text-align:center;margin-bottom:6px">✅</div>
      <p style="font-size:17px;font-weight:700;color:#0f172a;margin:0 0 10px;text-align:center">¡Gracias por su pago, {greeting}!</p>
      <p style="font-size:14.5px;color:#334155;line-height:1.7;margin:0 0 18px">{closing}</p>
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:10px;margin-bottom:18px">
        <tr><td style="padding:16px 20px">
          <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13.5px">
            <tr><td style="padding:6px 0;color:#475569">Factura</td><td align="right" style="padding:6px 0;font-weight:700;color:#0f172a">{number}</td></tr>
            <tr><td style="padding:6px 0;color:#475569">Pago recibido</td><td align="right" style="padding:6px 0;font-weight:800;color:#047857">{money(amount)}</td></tr>
            <tr><td style="padding:6px 0;color:#475569">Saldo</td><td align="right" style="padding:6px 0;font-weight:700;color:#0f172a">{money(0 if fully_paid else balance)}</td></tr>
          </table>
        </td></tr>
      </table>"""
    from finance_email import render_email_shell
    html = render_email_shell(
        "Pago recibido" if not fully_paid else "¡Factura pagada!",
        f"Factura {number} · {money(amount)}", html)
    return subject, html


async def log_email(db, *, client_id: str, invoice_id: Optional[str], kind: str,
                    to: str, subject: str, ok: bool, error: str = "") -> None:
    """Bitácora por cliente. Sin registro, la cobranza es palabra contra palabra."""
    await db.fin_email_log.insert_one({
        "id": str(uuid4()),
        "client_id": client_id,
        "invoice_id": invoice_id,
        "kind": kind,                     # invoice · reminder:<etapa> · receipt · test
        "to": to,
        "subject": subject,
        "ok": bool(ok),
        "error": error or "",
        "sent_at": datetime.utcnow().isoformat(),
    })


def next_reminder_hint(invoice: dict) -> Optional[str]:
    """Cuándo le toca el próximo recordatorio, para mostrarlo en el panel."""
    due = due_date_of(invoice)
    if not due or float(invoice.get("balance") or 0) <= 0.01:
        return None
    already = {r.get("stage") for r in (invoice.get("reminders_sent") or [])}
    for key, offset, _subject, _body in STAGES:
        if key in already:
            continue
        return (due + timedelta(days=offset)).strftime("%Y-%m-%d")
    return None
