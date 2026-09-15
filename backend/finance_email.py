# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
MediAd View — Finance Extensions: Email/SMTP, Settings, Users, Exports, Signatures, AR
"""
import asyncio
import base64
import csv
import hashlib
import os
import re
import smtplib
import uuid
from calendar import monthrange
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import formataddr
from io import BytesIO
from typing import List, Optional

import aiosmtplib
import openpyxl
from cryptography.fernet import Fernet, MultiFernet
from fastapi import APIRouter, Body, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from finance_pdf import (
    COMPANY,
    generate_invoice_pdf,
)
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from pydantic import BaseModel, EmailStr

ext_router = APIRouter(prefix="/api/finance")

# ============ ENCRYPTION (for SMTP password) ============
# La contraseña SMTP se guarda cifrada. La llave se derivaba SÓLO del
# `JWT_SECRET`: cuando ese secreto cambia (un redespliegue, una rotación de
# credenciales) la contraseña guardada deja de poder leerse y el envío de
# facturas falla con un «535 authentication failed» que no dice nada. Pasó:
# la contraseña cargada el 03/06/2026 quedó ilegible.
#
# Ahora se prueban varias llaves al descifrar (`MultiFernet`) y se cifra con la
# primera. Poniendo `FERNET_KEY` en el entorno, la contraseña sobrevive a
# cualquier cambio futuro del `JWT_SECRET`.
def _derive(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def _fernet_keys() -> List[bytes]:
    keys, seen = [], set()
    explicit = os.environ.get("FERNET_KEY")
    if explicit:
        keys.append(explicit.encode() if isinstance(explicit, str) else explicit)
    for secret in (os.environ.get("JWT_SECRET"), "fallback-secret-key-mediadview"):
        if secret:
            keys.append(_derive(secret))
    unique = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def _get_fernet() -> MultiFernet:
    return MultiFernet([Fernet(k) for k in _fernet_keys()])

def encrypt_password(plain: str) -> str:
    if not plain:
        return ""
    return _get_fernet().encrypt(plain.encode()).decode()

def decrypt_password(token: str) -> str:
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except Exception:
        return ""


def password_is_readable(token: str) -> bool:
    """Si hay contraseña guardada pero no se puede descifrar, hay que avisarlo.

    Devolver una contraseña vacía y dejar que el servidor de correo conteste
    «authentication failed» esconde el problema real: la contraseña está ahí,
    pero cifrada con una llave que ya no existe. Hay que volver a escribirla."""
    return bool(token) and bool(decrypt_password(token))


SMTP_PASSWORD_UNREADABLE = (
    "No se puede leer la contraseña SMTP guardada: fue cifrada con una llave "
    "del servidor que ya cambió. Volvé a escribirla en Finance & CRM → Email "
    "Settings y guardá para que los correos salgan de nuevo."
)

SMTP_PASSWORD_MISSING = (
    "Falta la contraseña SMTP del correo de facturación. Cargala en "
    "Finance & CRM → Email Settings y guardá para que los correos salgan."
)

# Las dos son problemas de configuración del dueño, no fallas del servidor:
# los endpoints responden 400 con el texto, no 500.
SMTP_CONFIG_ERRORS = (SMTP_PASSWORD_UNREADABLE, SMTP_PASSWORD_MISSING)


# ============ MODELS ============
class SmtpSettings(BaseModel):
    smtp_host: str = "smtp.titan.email"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    from_name: str = "MediAd View Billing"
    from_email: str = ""
    reply_to: Optional[str] = ""
    enabled: bool = False

class SendInvoiceRequest(BaseModel):
    to: Optional[str] = None  # override recipient
    cc: Optional[str] = None
    custom_message: Optional[str] = ""

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str  # superadmin, admin, accounting, sales, technical, viewer
    phone: Optional[str] = ""

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


# ============ EMAIL HTML TEMPLATE ============
def fmt_money(v):
    return "$" + f"{float(v or 0):,.2f}"

EMAIL_LOGO_CID = "mavlogo"
EMAIL_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "logo-email.png")


def attach_email_logo(msg) -> bool:
    """Incrusta el logo en la cabecera azul del correo.

    Va como imagen **inline (CID)** y no como `<img src="https://…">` a
    propósito: Gmail, Outlook y Hotmail bloquean las imágenes remotas hasta que
    el usuario aprieta «mostrar imágenes», y el cliente abría la factura con un
    cuadro roto arriba. Adjunta, se ve siempre.

    Se llama DESPUÉS de `add_alternative(html)` y ANTES de adjuntar el PDF.
    """
    try:
        with open(EMAIL_LOGO_PATH, "rb") as fh:
            data = fh.read()
    except OSError:
        return False
    for part in msg.iter_parts():
        if part.get_content_type() == "text/html":
            part.add_related(data, maintype="image", subtype="png",
                             cid=f"<{EMAIL_LOGO_CID}>", filename="mediadview-logo.png")
            return True
    return False


def tracking_pixel(base_url: str, track_id: str) -> str:
    """Píxel de 1x1 que avisa cuándo el cliente ABRE el correo.

    Es la única forma de saberlo: el correo, una vez enviado, está en el buzón
    del cliente. Al abrirlo, el lector pide esta imagen y el servidor anota la
    fecha. OJO: si el cliente tiene las imágenes bloqueadas (Gmail las carga por
    su proxy, Outlook a veces las bloquea) la apertura no se registra — por eso
    además se rastrea el click en «View Invoice Online», que no se puede
    bloquear y es prueba más fuerte de que la vio.
    """
    if not (base_url and track_id):
        return ""
    return (f'<img src="{base_url}/api/finance/email-log/{track_id}/open.png" '
            'width="1" height="1" alt="" style="display:block;width:1px;height:1px;border:0">')


def fmt_date(s):
    if not s: return ""
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%B %d, %Y")
    except Exception:
        return s

def render_invoice_email_html(inv: dict, client: dict, base_url: str = "",
                              track_id: str = "") -> str:
    """Intermedia-style branded invoice email.

    `track_id` es el id de la fila del historial: cuelga el píxel de apertura y
    marca el link «View Invoice Online» para saber cuándo el cliente lo vio.
    """
    period = ""
    if inv.get("period_start") and inv.get("period_end"):
        period = f"{fmt_date(inv['period_start'])} – {fmt_date(inv['period_end'])}"
    pixel = tracking_pixel(base_url, track_id)
    track_qs = f"?t={track_id}" if track_id else ""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<style>
  body,table,td{{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}}
  img{{border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic}}
  /* En el celular la tarjeta tenía 600px fijos y el correo se abría «gigante»:
     el cliente tenía que alejar el zoom para leerlo. Acá se estira al ancho de
     la pantalla y se achican los rellenos y los títulos. */
  @media only screen and (max-width:620px){{
    .mv-wrap{{padding:10px 6px !important}}
    .mv-card{{width:100% !important;border-radius:10px !important}}
    .mv-head{{padding:22px 18px 16px !important}}
    .mv-pad{{padding-left:18px !important;padding-right:18px !important}}
    .mv-logo{{width:175px !important;max-width:62% !important}}
    .mv-title{{font-size:19px !important;line-height:1.3 !important}}
    .mv-sub{{font-size:12.5px !important}}
    .mv-amount{{font-size:19px !important}}
    .mv-btn{{display:block !important;padding:14px 10px !important}}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Helvetica','Arial',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" class="mv-wrap" style="background:#f1f5f9;padding:24px 12px">
  <tr><td align="center">
    <table width="100%" cellpadding="0" cellspacing="0" class="mv-card" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 16px rgba(15,23,42,.08);max-width:600px">
      <!-- Header: fondo BLANCO con el logo. Antes era una banda azul con el
           logo en blanco encima y la combinación quedaba pesada. -->
      <tr><td class="mv-head" style="background:#ffffff;padding:30px 32px 22px;text-align:center;border-bottom:1px solid #e2e8f0">
        <img src="cid:{EMAIL_LOGO_CID}" alt="MediAd View · Advertising Solution" width="230"
             class="mv-logo" style="display:block;margin:0 auto 18px;width:230px;max-width:72%;height:auto;border:0">
        <div class="mv-title" style="font-size:22px;font-weight:700;color:#0f172a;margin-bottom:6px">Your Monthly Invoice</div>
        <div class="mv-sub" style="font-size:13px;color:#475569">Invoice #{inv.get('invoice_number','')} · Period {period}</div>
      </td></tr>

      <!-- Greeting -->
      <tr><td class="mv-pad" style="padding:32px 32px 0">
        <div style="font-size:14px;color:#0f172a;margin-bottom:18px">Hello <strong>{client.get('representative','—')}</strong>,</div>
        <div style="font-size:13.5px;color:#334155;line-height:1.6">Thank you for your continued business with <strong>MediAd View</strong>. Below is your invoice summary for this billing period. The detailed PDF is attached to this email.</div>
      </td></tr>

      <!-- Summary box -->
      <tr><td class="mv-pad" style="padding:24px 32px 0">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px">
          <tr><td style="padding:18px 22px">
            <div style="font-size:10.5px;font-weight:700;color:#1e40af;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:14px">INVOICE SUMMARY</div>
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr><td style="padding:5px 0;font-size:13px;color:#475569">Client</td><td align="right" style="padding:5px 0;font-size:13px;font-weight:600;color:#0f172a">{client.get('business_name','—')}</td></tr>
              <tr><td style="padding:5px 0;font-size:13px;color:#475569">Invoice #</td><td align="right" style="padding:5px 0;font-size:13px;font-weight:600;color:#0f172a">{inv.get('invoice_number','')}</td></tr>
              <tr><td style="padding:5px 0;font-size:13px;color:#475569">Issue Date</td><td align="right" style="padding:5px 0;font-size:13px;font-weight:600;color:#0f172a">{fmt_date(inv.get('issue_date',''))}</td></tr>
              <tr><td style="padding:5px 0;font-size:13px;color:#475569">Due Date</td><td align="right" style="padding:5px 0;font-size:13px;font-weight:600;color:#0f172a">{fmt_date(inv.get('due_date',''))}</td></tr>
              <tr><td colspan="2" style="padding:10px 0 0"><div style="border-top:1px solid #bfdbfe"></div></td></tr>
              <tr><td style="padding:10px 0 0;font-size:15px;font-weight:700;color:#0f172a">Amount Due</td><td align="right" class="mv-amount" style="padding:10px 0 0;font-size:22px;font-weight:800;color:#1e40af">{fmt_money(inv.get('balance', inv.get('total',0)))}</td></tr>
            </table>
          </td></tr>
        </table>
      </td></tr>

      <!-- CTA Button -->
      <tr><td class="mv-pad" style="padding:24px 32px;text-align:center">
        <a href="{base_url}/api/finance/invoices/{inv.get('id','')}/render{track_qs}" class="mv-btn" style="display:inline-block;background:#2563eb;color:#fff;padding:13px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;box-shadow:0 4px 12px rgba(37,99,235,.3)">View Invoice Online</a>
      </td></tr>

      <!-- Payment info -->
      <tr><td class="mv-pad" style="padding:0 32px 24px">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">
          <tr><td style="padding:16px 20px">
            <div style="font-size:11px;font-weight:700;color:#1e40af;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Payment Methods</div>
            <div style="font-size:12.5px;color:#334155;line-height:1.7">
              <strong>Bank:</strong> {COMPANY['bank_name']}<br>
              <strong>Account #:</strong> {COMPANY['account_number']}<br>
              <strong>Routing #:</strong> {COMPANY['routing']}<br>
              Make payable to: <strong>{COMPANY['name']}</strong>
            </div>
          </td></tr>
        </table>
      </td></tr>

      <!-- Inquiries -->
      <tr><td class="mv-pad" style="padding:0 32px 28px">
        <div style="font-size:12px;color:#64748b;line-height:1.6;text-align:center">
          <strong style="color:#0f172a">Billing Inquiries</strong><br>
          Phone: <strong>{COMPANY['phone_1']}</strong> · {COMPANY['phone_2']}<br>
          <a href="https://{COMPANY['website']}" style="color:#2563eb;text-decoration:none">{COMPANY['website']}</a>
        </div>
      </td></tr>

      <!-- Footer -->
      <tr><td class="mv-pad" style="background:#0f172a;padding:18px 32px;text-align:center">
        <div style="font-size:11px;color:#94a3b8;line-height:1.5">
          © {datetime.utcnow().year} {COMPANY['name']} · {COMPANY['address_line1']}, {COMPANY['address_line2']}
        </div>
      </td></tr>
    </table>
  </td></tr>
</table>
{pixel}
</body></html>"""


def render_email_shell(title: str, subtitle: str, body_html: str,
                       base_url: str = "", track_id: str = "") -> str:
    """La misma hoja que el correo de la factura, para recordatorios y recibos.

    Cabecera blanca con el logo incrustado (CID), tarjeta de 600px y el pie
    oscuro con la dirección. Antes los correos de cobranza salían como texto
    suelto con un «MediAd View» escrito a mano: parecían de otra empresa.
    Quien use esto tiene que llamar `attach_email_logo(msg)` al armar el mensaje.
    """
    pixel = tracking_pixel(base_url, track_id)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<style>
  body,table,td{{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}}
  img{{border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic}}
  /* En el celular la tarjeta tenía 600px fijos y el correo se abría «gigante»:
     el cliente tenía que alejar el zoom para leerlo. Acá se estira al ancho de
     la pantalla y se achican los rellenos y los títulos. */
  @media only screen and (max-width:620px){{
    .mv-wrap{{padding:10px 6px !important}}
    .mv-card{{width:100% !important;border-radius:10px !important}}
    .mv-head{{padding:22px 18px 16px !important}}
    .mv-pad{{padding-left:18px !important;padding-right:18px !important}}
    .mv-logo{{width:175px !important;max-width:62% !important}}
    .mv-title{{font-size:19px !important;line-height:1.3 !important}}
    .mv-sub{{font-size:12.5px !important}}
    .mv-amount{{font-size:19px !important}}
    .mv-btn{{display:block !important;padding:14px 10px !important}}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Helvetica','Arial',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" class="mv-wrap" style="background:#f1f5f9;padding:24px 12px">
  <tr><td align="center">
    <table width="100%" cellpadding="0" cellspacing="0" class="mv-card" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 16px rgba(15,23,42,.08);max-width:600px">
      <tr><td class="mv-head" style="background:#ffffff;padding:30px 32px 22px;text-align:center;border-bottom:1px solid #e2e8f0">
        <img src="cid:{EMAIL_LOGO_CID}" alt="MediAd View · Advertising Solution" width="230"
             class="mv-logo" style="display:block;margin:0 auto 18px;width:230px;max-width:72%;height:auto;border:0">
        <div class="mv-title" style="font-size:22px;font-weight:700;color:#0f172a;margin-bottom:6px">{title}</div>
        <div class="mv-sub" style="font-size:13px;color:#475569">{subtitle}</div>
      </td></tr>
      <tr><td class="mv-pad" style="padding:28px 32px 8px">{body_html}</td></tr>
      <tr><td class="mv-pad" style="padding:0 32px 28px">
        <div style="font-size:12px;color:#64748b;line-height:1.6;text-align:center">
          <strong style="color:#0f172a">Consultas de facturación</strong><br>
          {COMPANY['phone_1']} · {COMPANY['phone_2']}<br>
          <a href="https://{COMPANY['website']}" style="color:#2563eb;text-decoration:none">{COMPANY['website']}</a>
        </div>
      </td></tr>
      <tr><td class="mv-pad" style="background:#0f172a;padding:18px 32px;text-align:center">
        <div style="font-size:11px;color:#94a3b8;line-height:1.5">
          © {datetime.utcnow().year} {COMPANY['name']} · {COMPANY['address_line1']}, {COMPANY['address_line2']}
        </div>
      </td></tr>
    </table>
  </td></tr>
</table>
{pixel}
</body></html>"""


# ============ ROUTES FACTORY ============
def create_finance_extensions(db, get_current_user):
    async def require_finance(user: dict = Depends(get_current_user)):
        if user.get("role") not in ("superadmin", "admin", "accounting", "sales", "viewer", "technical"):
            raise HTTPException(403, "Finance access required")
        return user

    async def require_admin(user: dict = Depends(get_current_user)):
        if user.get("role") not in ("superadmin", "admin"):
            raise HTTPException(403, "Admin access required")
        return user

    # ============ SMTP SETTINGS ============
    @ext_router.get("/settings/email")
    async def get_email_settings(user: dict = Depends(require_admin)):
        s = await db.fin_settings.find_one({"_id": "email"})
        if not s:
            return SmtpSettings(smtp_user="", from_email="").dict()
        s.pop("_id", None)
        # Don't return the encrypted password
        if s.get("smtp_password"):
            readable = password_is_readable(s["smtp_password"])
            s["smtp_password"] = "********"  # placeholder showing it's set
            s["password_set"] = True
            s["password_readable"] = readable
            if not readable:
                s["password_warning"] = SMTP_PASSWORD_UNREADABLE
        else:
            s["password_set"] = False
            s["password_readable"] = False
        return s

    @ext_router.put("/settings/email")
    async def update_email_settings(data: SmtpSettings, user: dict = Depends(require_admin)):
        doc = data.dict()
        # Encrypt password if provided (and not placeholder)
        if doc.get("smtp_password") and doc["smtp_password"] != "********":
            doc["smtp_password"] = encrypt_password(doc["smtp_password"])
        else:
            # Keep existing
            existing = await db.fin_settings.find_one({"_id": "email"})
            if existing and existing.get("smtp_password"):
                doc["smtp_password"] = existing["smtp_password"]
            else:
                doc["smtp_password"] = ""
        doc["updated_at"] = datetime.utcnow().isoformat()
        doc["updated_by"] = user.get("email", "")
        await db.fin_settings.update_one({"_id": "email"}, {"$set": doc}, upsert=True)
        return {"ok": True}

    @ext_router.post("/settings/email/test")
    async def test_email(payload: dict = Body(...), user: dict = Depends(require_admin)):
        to_addr = payload.get("to") or user.get("email")
        s = await db.fin_settings.find_one({"_id": "email"})
        if not s:
            raise HTTPException(400, "Email settings not configured")
        try:
            msg = EmailMessage()
            msg["From"] = formataddr((s.get("from_name", "MediAd View"), s.get("from_email") or s.get("smtp_user")))
            msg["To"] = to_addr
            msg["Subject"] = "MediAd View — SMTP Test Email"
            msg.set_content("This is a test email from your MediAd View system. SMTP is configured correctly!")
            msg.add_alternative(
                '<div style="font-family:Arial;padding:20px"><h2 style="color:#2563eb">✓ SMTP Test Successful</h2>'
                '<p>Your MediAd View email integration is working correctly.</p>'
                '<p style="font-size:12px;color:#64748b">Sent from your billing system.</p></div>',
                subtype="html",
            )
            await _send_email_async(s, msg, to_addr)
            return {"ok": True, "message": f"Test email sent to {to_addr}"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"SMTP error: {str(e)}")

    async def _send_email_async(s, msg, to_addr):
        pwd = decrypt_password(s.get("smtp_password", ""))
        if not pwd:
            # Intentar el envío con la contraseña vacía sólo produce un 535 que
            # manda al dueño a buscar el problema en su proveedor de correo.
            raise HTTPException(
                400,
                SMTP_PASSWORD_UNREADABLE if s.get("smtp_password") else SMTP_PASSWORD_MISSING,
            )
        port = int(s.get("smtp_port", 587))
        use_tls = port == 465
        start_tls = not use_tls
        await aiosmtplib.send(
            msg,
            hostname=s.get("smtp_host", "smtp.titan.email"),
            port=port,
            username=s.get("smtp_user"),
            password=pwd,
            use_tls=use_tls,
            start_tls=start_tls,
            timeout=30,
        )

    # Los 3 endpoints `/{doc}/pdf` vivían también acá, pero finance.py se
    # registra antes en server.py, así que estas copias nunca se ejecutaban.
    # Código muerto eliminado: el PDF lo sirve finance.py.

    # ============ SEND INVOICE BY EMAIL ============
    @ext_router.post("/invoices/{invoice_id}/send")
    async def send_invoice_email(invoice_id: str, payload: SendInvoiceRequest = Body(...),
                                  user: dict = Depends(require_admin)):
        from collections_engine import log_email

        inv = await db.fin_invoices.find_one({"id": invoice_id})
        if not inv:
            raise HTTPException(404, "Invoice not found")
        client = await db.fin_clients.find_one({"id": inv["client_id"]}) or {}

        to_addr = (payload.to or "").strip() or client.get("email", "")
        if not to_addr:
            raise HTTPException(400, "Recipient email not provided. Please add one to the client profile or pass 'to' in request.")

        s = await db.fin_settings.find_one({"_id": "email"})
        if not s or not s.get("enabled"):
            raise HTTPException(400, "Email is not enabled. Configure SMTP in Settings → Email first.")

        # Build base URL for "View Online" link
        base_url = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

        # Generate PDF attachment
        pdf_bytes = generate_invoice_pdf(inv, client)
        pdf_filename = f"Invoice_{inv.get('invoice_number','')}.pdf"

        # Build message
        msg = EmailMessage()
        msg["From"] = formataddr((s.get("from_name", "MediAd View Billing"), s.get("from_email") or s.get("smtp_user")))
        msg["To"] = to_addr
        if payload.cc:
            msg["Cc"] = payload.cc
        if s.get("reply_to"):
            msg["Reply-To"] = s["reply_to"]
        msg["Subject"] = f"Your MediAd View Invoice {inv.get('invoice_number','')} — {fmt_money(inv.get('balance', inv.get('total',0)))} due"

        # Plain text fallback
        text_body = (
            f"Hello {client.get('representative','')},\n\n"
            f"Your invoice {inv.get('invoice_number','')} is attached.\n"
            f"Amount due: {fmt_money(inv.get('balance', inv.get('total',0)))}\n"
            f"Due date: {fmt_date(inv.get('due_date',''))}\n\n"
            f"Payment to:\n"
            f"  Bank: {COMPANY['bank_name']}\n"
            f"  Account #: {COMPANY['account_number']}\n"
            f"  Routing: {COMPANY['routing']}\n\n"
            f"Questions? {COMPANY['phone_1']}\n"
            f"{COMPANY['name']}\n"
        )
        if payload.custom_message:
            text_body = payload.custom_message + "\n\n" + text_body
        msg.set_content(text_body)

        # El id del historial va DENTRO del correo (píxel + link rastreado).
        log_id = str(uuid.uuid4())
        html_body = render_invoice_email_html(inv, client, base_url=base_url, track_id=log_id)
        if payload.custom_message:
            html_body = html_body.replace(
                '<div style="font-size:13.5px;color:#334155;line-height:1.6">',
                f'<div style="font-size:13.5px;color:#334155;line-height:1.6;padding:14px;background:#fef9c3;border-left:3px solid #f59e0b;border-radius:6px;margin-bottom:14px">{payload.custom_message}</div><div style="font-size:13.5px;color:#334155;line-height:1.6">',
                1,
            )
        msg.add_alternative(html_body, subtype="html")
        attach_email_logo(msg)
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=pdf_filename)

        try:
            await _send_email_async(s, msg, to_addr)
        except HTTPException as exc:
            await log_email(db, client_id=inv.get("client_id", ""), invoice_id=invoice_id,
                            kind="invoice", to=to_addr, subject=msg["Subject"], ok=False,
                            error=str(exc.detail), log_id=log_id)
            raise
        except Exception as e:
            await log_email(db, client_id=inv.get("client_id", ""), invoice_id=invoice_id,
                            kind="invoice", to=to_addr, subject=msg["Subject"], ok=False,
                            error=str(e), log_id=log_id)
            raise HTTPException(500, f"Failed to send: {str(e)}")
        # El envío manual también va al historial: el panel muestra una sola
        # bitácora, no importa si el correo lo disparó el cron o una persona.
        await log_email(db, client_id=inv.get("client_id", ""), invoice_id=invoice_id,
                        kind="invoice", to=to_addr, subject=msg["Subject"], ok=True,
                        log_id=log_id)

        # Log the send
        await db.fin_invoices.update_one(
            {"id": invoice_id},
            {"$set": {"last_sent_at": datetime.utcnow().isoformat(),
                      "last_sent_to": to_addr,
                      "sent_count": inv.get("sent_count", 0) + 1}},
        )
        return {"ok": True, "sent_to": to_addr}

    # ============ FACTURAR MESES ATRASADOS DE UN CLIENTE ============
    class BackfillRequest(BaseModel):
        client_id: str
        periods: list[str]          # ["2026-07", "2026-08", "2026-09"]
        send_email: bool = True

    @ext_router.post("/invoices/generate-for-client")
    async def generate_invoices_for_client(payload: BackfillRequest = Body(...),
                                           user: dict = Depends(require_admin)):
        """Genera (y opcionalmente manda) las facturas de varios meses de UN cliente.

        Caso real: un cliente que se dio de alta debiendo julio, agosto y
        septiembre. El generador mensual sólo hace el mes que corresponde, así
        que había que crear las tres a mano. Acá se eligen los meses, se crean
        con el mismo formato que las automáticas (mismo período, mismo
        vencimiento el día 1) y salen por correo con el PDF adjunto.

        Nunca duplica: si ya existe la factura de ese contrato y ese mes, la
        reporta como `skipped` con su número.
        """
        from finance_scheduler import _generate_monthly_invoices, _send_invoice_email

        client = await db.fin_clients.find_one({"id": payload.client_id})
        if not client:
            raise HTTPException(404, "Client not found")
        if payload.send_email and not (client.get("email") or "").strip():
            raise HTTPException(400, f"{client.get('business_name','El cliente')} no tiene "
                                     "correo cargado. Agregalo en su ficha o desmarcá el envío.")
        if not payload.periods:
            raise HTTPException(400, "Elegí al menos un mes.")

        # Para explicar bien por qué un mes no se facturó hace falta saber qué
        # contratos tiene el cliente. Antes el mensaje era siempre «el contrato
        # no cubre este mes (o no hay contrato activo)» y el dueño no sabía si
        # el problema era el estado, las fechas o que el contrato estaba colgado
        # de otro cliente.
        contracts = await db.fin_contracts.find({"client_id": payload.client_id}).to_list(200)
        usable = [c for c in contracts if c.get("status") != "cancelled"]

        def _porque_no(period_start_iso: str) -> str:
            if not contracts:
                return ("Este cliente no tiene ningún contrato cargado. Creá el contrato "
                        "primero (Contracts → + New Contract).")
            if not usable:
                return (f"El contrato {contracts[0].get('contract_number','')} está cancelado. "
                        "Reactivalo o creá uno nuevo.")
            detalle = "; ".join(
                f"{c.get('contract_number','')} cubre del {fmt_date(c.get('start_date',''))} "
                f"al {fmt_date(c.get('end_date',''))}" for c in usable[:3])
            return (f"Este mes queda fuera de las fechas del contrato ({detalle}). "
                    "Editá el contrato (✏️) y corregí la fecha de inicio o el plazo.")

        results = []
        for period in sorted(payload.periods):
            try:
                year, month = (int(x) for x in period.split("-")[:2])
                date(year, month, 1)
            except (ValueError, TypeError):
                raise HTTPException(400, f"Período inválido: {period} (se espera 2026-07)")

            # En el backfill manual también valen los contratos `draft` y
            # `expired`: un mes viejo lo cubre un contrato que ya venció.
            created = await _generate_monthly_invoices(
                db, year, month, client_id=payload.client_id,
                statuses=("active", "draft", "expired"))
            if not created:
                period_start = date(year, month, 1).isoformat()
                existing = await db.fin_invoices.find_one({
                    "client_id": payload.client_id,
                    "period_start": period_start,
                })
                results.append({
                    "period": period,
                    "status": "skipped",
                    "invoice_number": (existing or {}).get("invoice_number", ""),
                    "detail": "Ya existía la factura de este mes" if existing
                              else _porque_no(period_start),
                })
                continue

            for inv in created:
                row = {"period": period, "status": "created",
                       "invoice_number": inv.get("invoice_number"),
                       "invoice_id": inv["id"], "total": inv.get("total"),
                       "emailed": False, "detail": ""}
                if payload.send_email:
                    try:
                        row["emailed"] = await _send_invoice_email(db, inv)
                        if row["emailed"]:
                            await db.fin_invoices.update_one(
                                {"id": inv["id"]},
                                {"$set": {"email_sent": True,
                                          "last_sent_at": datetime.utcnow().isoformat(),
                                          "last_sent_to": client.get("email", "")}})
                    except Exception as exc:
                        row["detail"] = str(exc)
                results.append(row)

        return {
            "client": client.get("business_name", ""),
            "email": client.get("email", ""),
            "created": sum(1 for r in results if r["status"] == "created"),
            "emailed": sum(1 for r in results if r.get("emailed")),
            "skipped": sum(1 for r in results if r["status"] == "skipped"),
            "results": results,
        }

    # ============ CANAL WHATSAPP (Meta Cloud API) ============
    @ext_router.get("/whatsapp/status")
    async def whatsapp_status(user: dict = Depends(require_finance)):
        """Estado de la conexión para Settings → Integraciones → WhatsApp.

        NUNCA devuelve el token ni el App Secret: sólo si están cargados."""
        import whatsapp as wa
        total = await db.wa_messages.count_documents({})
        entregados = await db.wa_messages.count_documents(
            {"status": {"$in": ["delivered", "read"]}})
        fallidos = await db.wa_messages.count_documents({"ok": False})
        return {
            "connected": wa.is_configured(),
            "reason": wa.missing_config(),
            "phone_number_id": wa.PHONE_NUMBER_ID or "",
            "waba_id": wa.WABA_ID or "",
            "graph_version": wa.GRAPH_VERSION,
            "has_token": bool(wa.ACCESS_TOKEN),
            "has_app_secret": bool(wa.APP_SECRET),
            "webhook_ready": bool(wa.VERIFY_TOKEN),
            "webhook_url": ((os.environ.get("PANEL_BASE_URL")
                             or os.environ.get("PUBLIC_BASE_URL", "")).rstrip("/")
                            + "/api/whatsapp/webhook"),
            "templates": [t["name"] for t in wa.TEMPLATES.values()],
            "templates_meta": await _templates_meta(),
            "stats": {"total": total, "delivered": entregados, "failed": fallidos},
        }

    async def _templates_meta() -> list:
        """Lo que Meta aprobó de verdad: nombre, idioma y estado.

        Es el diagnóstico que faltaba: un error 132001 casi siempre es una
        plantilla creada con otra variante de idioma (es vs es_MX)."""
        import whatsapp as wa
        if not wa.is_configured() or not wa.WABA_ID:
            return []
        try:
            rows = await wa.list_templates(force=True)
        except wa.WhatsAppError as exc:
            return [{"name": "", "language": "", "status": "ERROR",
                     "category": str(exc.detail)[:200]}]
        nuestras = {t["name"] for t in wa.TEMPLATES.values()}
        return [r for r in rows if r["name"] in nuestras]

    @ext_router.post("/whatsapp/test")
    async def whatsapp_test(payload: dict = Body(...), user: dict = Depends(require_admin)):
        """Manda un mensaje de prueba al número que indique el dueño."""
        import whatsapp as wa
        if not wa.is_configured():
            raise HTTPException(400, wa.missing_config())
        to = wa.normalize_phone(payload.get("to", ""), payload.get("country_code", "1"))
        if not to:
            raise HTTPException(400, "Escribí el número con código de país.")
        try:
            # La prueba usa el mismo camino que una factura real (PDF subido a
            # Meta + plantilla con encabezado de documento): si esto llega, el
            # envío de facturas funciona.
            from finance_pdf import generate_invoice_pdf
            hoy = datetime.utcnow().date().isoformat()
            muestra_inv = {"invoice_number": "TEST-0001", "issue_date": hoy, "due_date": hoy,
                           "period_label": "Mensaje de prueba", "items": [],
                           "subtotal": 0.0, "tax": 0.0, "total": 0.0,
                           "amount_paid": 0.0, "balance": 0.0, "status": "pending"}
            muestra_cli = {"business_name": "Prueba de conexión", "representative": "Prueba",
                           "phone": to, "address_line1": "", "city": "", "state": "",
                           "zip": "", "country": ""}
            media_id = await wa.upload_pdf(generate_invoice_pdf(muestra_inv, muestra_cli),
                                           "MediaView_Prueba.pdf")
            msg_id = await wa.send_template(
                to=to, template="invoice_created", lang=payload.get("lang", "es"),
                params=["Prueba", "TEST-0001", "$0.00", hoy],
                media_id=media_id, filename="MediaView_Prueba.pdf")
        except wa.WhatsAppError as exc:
            raise HTTPException(400, exc.detail)
        await wa.log_wa(db, client_id="", invoice_id="", kind="test", to=to,
                        template=wa.TEMPLATES["invoice_created"]["name"], ok=True,
                        message_id=msg_id)
        return {"ok": True, "message_id": msg_id, "to": to}

    @ext_router.post("/whatsapp/test-hello")
    async def whatsapp_test_hello(payload: dict = Body(...),
                                  user: dict = Depends(require_admin)):
        """Prueba de conexión con `hello_world` (aprobada por Meta de fábrica).

        Deja comprobar token, número y webhook sin depender de que Meta haya
        aprobado las plantillas del negocio."""
        import whatsapp as wa
        if not wa.is_configured():
            raise HTTPException(400, wa.missing_config())
        to = wa.normalize_phone(payload.get("to", ""), payload.get("country_code", "1"))
        if not to:
            raise HTTPException(400, "Escribí el número con código de país.")
        try:
            msg_id = await wa.send_hello(to)
        except wa.WhatsAppError as exc:
            raise HTTPException(400, exc.detail)
        await wa.log_wa(db, client_id="", invoice_id="", kind="test", to=to,
                        template="hello_world", ok=True, message_id=msg_id,
                        text="Prueba de conexión (hello_world)")
        return {"ok": True, "message_id": msg_id, "to": to}

    @ext_router.post("/invoices/{invoice_id}/whatsapp")
    async def send_invoice_by_whatsapp(invoice_id: str, user: dict = Depends(require_admin)):
        """Reenvío manual de la factura por WhatsApp (con el PDF adjunto)."""
        import whatsapp as wa
        inv = await db.fin_invoices.find_one({"id": invoice_id})
        if not inv:
            raise HTTPException(404, "Invoice not found")
        client = await db.fin_clients.find_one({"id": inv["client_id"]}) or {}
        res = await wa.send_invoice_whatsapp(db, inv, client, force=True)
        if not res.get("ok"):
            raise HTTPException(400, res.get("reason", "No se pudo enviar por WhatsApp"))
        return res

    @ext_router.get("/invoices/{invoice_id}/communications")
    async def invoice_communications(invoice_id: str, user: dict = Depends(require_finance)):
        """Historial de comunicación de la factura: EMAIL y WHATSAPP.

        Es lo que se mira cuando el cliente dice «no me llegó la factura»."""
        emails = await db.fin_email_log.find({"invoice_id": invoice_id}) \
            .sort("sent_at", -1).to_list(100)
        was = await db.wa_messages.find({"invoice_id": invoice_id}) \
            .sort("sent_at", -1).to_list(100)
        for r in emails + was:
            r.pop("_id", None)
        return {"email": emails, "whatsapp": was}

    # ============ BANDEJA DE ENTRADA DE WHATSAPP ============
    # Sin esto, migrar el número a la API oficial significa perder lo que
    # escriben los clientes: Meta no guarda un historial que se pueda recuperar
    # después. Todo lo que entra se lee y se contesta acá.
    def _digits(v: str) -> str:
        return re.sub(r"\D", "", v or "")

    async def _client_snapshot(client: dict) -> dict:
        """Ficha corta del cliente para el panel del chat: saldo y qué debe."""
        if not client:
            return None
        invs = await db.fin_invoices.find(
            {"client_id": client["id"], "status": {"$in": ["pending", "overdue"]}}
        ).sort("due_date", 1).to_list(50)
        return {
            "id": client["id"],
            "business_name": client.get("business_name", ""),
            "representative": client.get("representative", ""),
            "email": client.get("email", ""),
            "phone": client.get("phone", ""),
            "whatsapp": client.get("whatsapp", ""),
            "open_count": len(invs),
            "balance": round(sum(float(i.get("balance") or 0) for i in invs), 2),
            "invoices": [{"id": i["id"], "invoice_number": i.get("invoice_number", ""),
                          "due_date": i.get("due_date", ""), "status": i.get("status", ""),
                          "balance": float(i.get("balance") or 0)} for i in invs],
        }

    @ext_router.get("/whatsapp/inbox")
    async def wa_inbox(user: dict = Depends(require_finance)):
        import whatsapp as wa
        convs = await db.wa_conversations.find().sort("last_at", -1).to_list(300)
        rows = []
        for c in convs:
            c.pop("_id", None)
            c["unread"] = int(c.get("unread") or 0)
            c["window_open"] = wa.window_open(c)
            rows.append(c)
        return {
            "rows": rows,
            "unread_total": sum(r["unread"] for r in rows),
            "connected": wa.is_configured(),
            "reason": wa.missing_config(),
        }

    @ext_router.get("/whatsapp/inbox/{phone}")
    async def wa_thread(phone: str, limit: int = 300, user: dict = Depends(require_finance)):
        import whatsapp as wa
        tel = _digits(phone)
        if not tel:
            raise HTTPException(400, "Número inválido")
        msgs = await db.wa_messages.find(
            {"$or": [{"to": tel}, {"from": tel}]}).sort("sent_at", 1).to_list(limit)
        for m in msgs:
            m.pop("_id", None)
            m.setdefault("direction", "out")
            m.setdefault("text", "")
        conv = await db.wa_conversations.find_one({"phone": tel}) or {"phone": tel}
        conv.pop("_id", None)
        client = None
        if conv.get("client_id"):
            client = await db.fin_clients.find_one({"id": conv["client_id"]})
        if not client:
            encontrado = await wa.find_client_by_phone(db, tel)
            if encontrado:
                client = await db.fin_clients.find_one({"id": encontrado["id"]})
        return {
            "phone": tel, "conversation": conv, "messages": msgs,
            "client": await _client_snapshot(client),
            "window_open": wa.window_open(conv),
            "connected": wa.is_configured(),
        }

    @ext_router.post("/whatsapp/inbox/{phone}/read")
    async def wa_mark_read(phone: str, user: dict = Depends(require_finance)):
        await db.wa_conversations.update_one({"phone": _digits(phone)},
                                             {"$set": {"unread": 0}})
        return {"ok": True}

    @ext_router.post("/whatsapp/inbox/{phone}/reply")
    async def wa_reply(phone: str, payload: dict = Body(...),
                       user: dict = Depends(require_finance)):
        import whatsapp as wa
        res = await wa.send_reply(db, phone, payload.get("text", ""),
                                  sent_by=user.get("email", ""))
        if not res.get("ok"):
            raise HTTPException(400, res.get("reason", "No se pudo enviar"))
        return res

    @ext_router.post("/whatsapp/inbox/{phone}/link")
    async def wa_link_client(phone: str, payload: dict = Body(...),
                             user: dict = Depends(require_finance)):
        """Engancha el número con un cliente que ya existe, o lo da de alta.

        Un número desconocido que escribe es un cliente nuevo o un cliente
        cargado con otro teléfono: en los dos casos se resuelve desde el chat.
        """
        tel = _digits(phone)
        if not tel:
            raise HTTPException(400, "Número inválido")
        client_id = (payload.get("client_id") or "").strip()
        if client_id:
            client = await db.fin_clients.find_one({"id": client_id})
            if not client:
                raise HTTPException(404, "Cliente no encontrado")
            if not _digits(client.get("whatsapp") or "") == tel:
                await db.fin_clients.update_one({"id": client_id},
                                                 {"$set": {"whatsapp": tel}})
        else:
            nombre = (payload.get("business_name") or "").strip()
            if not nombre:
                raise HTTPException(400, "Escribí el nombre del negocio")
            client = {
                "id": str(uuid.uuid4()), "business_name": nombre,
                "representative": (payload.get("representative") or "").strip(),
                "email": (payload.get("email") or "").strip(),
                "phone": tel, "whatsapp": tel,
                "country_code": payload.get("country_code") or "1",
                "language": payload.get("language") or "es",
                "wa_invoice_notify": True, "wa_reminder_notify": True,
                "address_line1": (payload.get("address_line1") or "").strip(),
                "city": "", "state": "", "zip": "", "country": "USA",
                "notes": "Dado de alta desde la bandeja de WhatsApp",
                "status": "active", "locations": [],
                "created_at": datetime.utcnow().isoformat(),
                "created_by": user.get("email", ""),
            }
            await db.fin_clients.insert_one(client)
            client.pop("_id", None)
            client_id = client["id"]
        nombre_conv = client.get("business_name") or client.get("representative") or ""
        await db.wa_conversations.update_one(
            {"phone": tel},
            {"$set": {"client_id": client_id, "client_name": nombre_conv},
             "$setOnInsert": {"id": str(uuid.uuid4()), "phone": tel,
                              "created_at": datetime.utcnow().isoformat()}},
            upsert=True)
        await db.wa_messages.update_many({"$or": [{"to": tel}, {"from": tel}]},
                                         {"$set": {"client_id": client_id}})
        return {"ok": True, "client_id": client_id, "client_name": nombre_conv}

    @ext_router.get("/whatsapp/media/{media_id}")
    async def wa_media(media_id: str, user: dict = Depends(require_finance)):
        """Sirve la foto o el archivo que mandó el cliente.

        Va por el servidor a propósito: el link de Meta necesita el token y no
        se puede exponer en el navegador."""
        import whatsapp as wa
        if not wa.is_configured():
            raise HTTPException(400, wa.missing_config())
        try:
            data, mime, nombre = await wa.fetch_media(media_id)
        except wa.WhatsAppError as exc:
            raise HTTPException(400, exc.detail)
        headers = {"Cache-Control": "private, max-age=86400"}
        if nombre:
            headers["Content-Disposition"] = f'inline; filename="{nombre}"'
        return Response(content=data, media_type=mime, headers=headers)

    # ---- Respuestas rápidas (frases guardadas para contestar en la bandeja) --
    RESPUESTAS_BASE = [
        {"title": "Recibimos el pago",
         "text": "¡Gracias {nombre}! Ya registramos tu pago. Cualquier cosa, escribinos por acá."},
        {"title": "Pago pendiente",
         "text": "Hola {nombre}, tenés un saldo pendiente de {saldo} (factura {factura}). "
                 "¿Te sirve que lo coordinemos para esta semana?"},
        {"title": "Cómo pagar",
         "text": "Hola {nombre}, podés pagar por transferencia, Zelle o tarjeta. "
                 "Decime cuál te queda más cómodo y te paso los datos."},
        {"title": "Ya lo revisamos",
         "text": "Hola {nombre}, gracias por avisar. Ya lo estamos revisando y te confirmo hoy mismo."},
        {"title": "Horario de atención",
         "text": "Hola {nombre}, nuestro horario es de lunes a viernes de 9 a 6. "
                 "Te contestamos en cuanto abrimos."},
    ]

    @ext_router.get("/whatsapp/quick-replies")
    async def quick_replies(user: dict = Depends(require_finance)):
        """Frases guardadas. La primera vez se cargan unas cuantas ya escritas:
        una lista vacía no le sirve a nadie."""
        rows = await db.wa_quick_replies.find().sort("sort", 1).to_list(200)
        if not rows:
            await db.wa_quick_replies.insert_many([
                {"id": str(uuid.uuid4()), "title": r["title"], "text": r["text"],
                 "sort": i, "created_at": datetime.utcnow().isoformat()}
                for i, r in enumerate(RESPUESTAS_BASE)])
            rows = await db.wa_quick_replies.find().sort("sort", 1).to_list(200)
        for r in rows:
            r.pop("_id", None)
        return rows

    @ext_router.post("/whatsapp/quick-replies")
    async def quick_reply_create(payload: dict = Body(...),
                                 user: dict = Depends(require_finance)):
        titulo = (payload.get("title") or "").strip()
        texto = (payload.get("text") or "").strip()
        if not titulo or not texto:
            raise HTTPException(400, "Poné un nombre corto y el texto del mensaje")
        doc = {"id": str(uuid.uuid4()), "title": titulo, "text": texto,
               "sort": int(payload.get("sort") or 99),
               "created_at": datetime.utcnow().isoformat(),
               "created_by": user.get("email", "")}
        await db.wa_quick_replies.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @ext_router.patch("/whatsapp/quick-replies/{qr_id}")
    async def quick_reply_update(qr_id: str, payload: dict = Body(...),
                                 user: dict = Depends(require_finance)):
        cambios = {k: (payload[k] or "").strip() for k in ("title", "text") if k in payload}
        if not cambios:
            raise HTTPException(400, "Nada para cambiar")
        r = await db.wa_quick_replies.update_one({"id": qr_id}, {"$set": cambios})
        if not r.matched_count:
            raise HTTPException(404, "Respuesta no encontrada")
        return {"ok": True}

    @ext_router.delete("/whatsapp/quick-replies/{qr_id}")
    async def quick_reply_delete(qr_id: str, user: dict = Depends(require_finance)):
        r = await db.wa_quick_replies.delete_one({"id": qr_id})
        if not r.deleted_count:
            raise HTTPException(404, "Respuesta no encontrada")
        return {"ok": True}

    # ---- Aviso por correo de mensajes sin responder -------------------------
    @ext_router.get("/whatsapp/alerts")
    async def wa_alerts_get(user: dict = Depends(require_finance)):
        s = await db.fin_settings.find_one({"_id": "wa_alerts"}) or {}
        correo = await db.fin_settings.find_one({"_id": "email"}) or {}
        return {
            "enabled": s.get("enabled", True),
            "minutes": int(s.get("minutes") or 60),
            "to_email": s.get("to_email") or correo.get("from_email")
                        or correo.get("smtp_user") or "",
            "last_run": s.get("last_run"),
            "last_sent": s.get("last_sent"),
        }

    @ext_router.put("/whatsapp/alerts")
    async def wa_alerts_put(payload: dict = Body(...), user: dict = Depends(require_admin)):
        minutos = int(payload.get("minutes") or 60)
        if minutos < 5 or minutos > 1440:
            raise HTTPException(400, "El tiempo de espera va de 5 minutos a 24 horas")
        await db.fin_settings.update_one({"_id": "wa_alerts"}, {"$set": {
            "enabled": bool(payload.get("enabled")),
            "minutes": minutos,
            "to_email": (payload.get("to_email") or "").strip(),
        }}, upsert=True)
        return {"ok": True}

    # ============ ACCOUNTS RECEIVABLE ============
    @ext_router.get("/accounts-receivable")
    async def accounts_receivable(user: dict = Depends(require_finance)):
        today = datetime.utcnow().date().isoformat()
        # Mark overdue
        await db.fin_invoices.update_many(
            {"status": "pending", "due_date": {"$lt": today}},
            {"$set": {"status": "overdue"}},
        )
        # Get all unpaid invoices
        invs = await db.fin_invoices.find({"status": {"$in": ["pending", "overdue"]}}).sort("due_date", 1).to_list(2000)
        client_ids = list({i["client_id"] for i in invs})
        clients = {c["id"]: c for c in await db.fin_clients.find({"id": {"$in": client_ids}}).to_list(2000)}
        # Group by client
        by_client = {}
        for i in invs:
            i.pop("_id", None)
            cid = i["client_id"]
            cl = clients.get(cid, {})
            if cid not in by_client:
                by_client[cid] = {
                    "client_id": cid,
                    "client_name": cl.get("business_name", "—"),
                    "representative": cl.get("representative", ""),
                    "email": cl.get("email", ""),
                    "phone": cl.get("phone", ""),
                    "invoices": [],
                    "total_due": 0,
                    "overdue_count": 0,
                    "oldest_due": None,
                }
            balance = i.get("balance", i.get("total", 0))
            by_client[cid]["invoices"].append(i)
            by_client[cid]["total_due"] += balance
            if i["status"] == "overdue":
                by_client[cid]["overdue_count"] += 1
            if not by_client[cid]["oldest_due"] or i.get("due_date", "") < by_client[cid]["oldest_due"]:
                by_client[cid]["oldest_due"] = i.get("due_date")
        result = sorted(by_client.values(), key=lambda x: x["total_due"], reverse=True)
        summary = {
            "total_clients_owing": len(result),
            "total_ar": sum(c["total_due"] for c in result),
            "total_overdue_invoices": sum(c["overdue_count"] for c in result),
            "total_open_invoices": sum(len(c["invoices"]) for c in result),
        }
        return {"summary": summary, "clients": result}

    # ============ CONTRACT SIGNATURE ============
    # La firma de contratos la sirve finance.py (versión completa: valida
    # contrato existente, marca `active` al tener las dos firmas). Esta copia
    # quedaba sombreada por el orden de registro de los routers.

    # ============ USER MANAGEMENT ============
    # 1x1 PNG transparente (43 bytes). Va inline para no depender de ningún
    # archivo en disco: si el píxel no responde, el correo muestra un hueco.
    _PIXEL_PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")

    @ext_router.get("/email-log/{log_id}/open.png")
    async def track_email_open(log_id: str):
        """Marca que el cliente ABRIÓ el correo (lo pide su lector de correo).

        Sin autenticación a propósito: lo llama el buzón del cliente. Se guarda
        la primera apertura y se cuenta cada una. Nunca falla ni devuelve error:
        si el id no existe, igual entrega el píxel (un correo viejo no puede
        romperle la vista a nadie).
        """
        now = datetime.utcnow().isoformat()
        await db.fin_email_log.update_one(
            {"id": log_id},
            {"$set": {"last_opened_at": now},
             "$inc": {"open_count": 1},
             "$setOnInsert": {}},
        )
        await db.fin_email_log.update_one(
            {"id": log_id, "opened_at": None}, {"$set": {"opened_at": now}})
        return Response(content=_PIXEL_PNG, media_type="image/png", headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        })

    # ============ COBRANZA: BITÁCORA Y ESTADO ============
    @ext_router.get("/email-log")
    async def email_log(limit: int = 200, client_id: str = "", kind: str = "",
                        only_errors: bool = False, user: dict = Depends(require_finance)):
        """Historial de TODO lo que salió por correo: facturas automáticas,
        recordatorios de cobranza y recibos de pago.

        El dueño necesita poder abrir el panel y ver «a este cliente se le mandó
        la factura tal día y el recordatorio de 7 días tal otro». Sin esto la
        cobranza es palabra contra palabra."""
        q: dict = {}
        if client_id:
            q["client_id"] = client_id
        if kind:
            # `reminder` trae todas las etapas (reminder:pre_due, reminder:late_7…)
            q["kind"] = {"$regex": f"^{kind}"}
        if only_errors:
            q["ok"] = False
        rows = await db.fin_email_log.find(q).sort("sent_at", -1) \
            .to_list(max(1, min(int(limit), 500)))
        client_names = {}
        invoice_numbers = {}
        for row in rows:
            row.pop("_id", None)
            cid = row.get("client_id")
            if cid and cid not in client_names:
                cl = await db.fin_clients.find_one({"id": cid}) or {}
                client_names[cid] = cl.get("business_name") or cl.get("email") or "—"
            iid = row.get("invoice_id")
            if iid and iid not in invoice_numbers:
                inv = await db.fin_invoices.find_one({"id": iid}) or {}
                invoice_numbers[iid] = inv.get("invoice_number") or ""
            row["client_name"] = client_names.get(cid) or row.get("client_name") or "—"
            # Si la factura se borró, el número quedó copiado en la fila (ver
            # purge_invoice): así el historial no pierde la constancia.
            row["invoice_number"] = invoice_numbers.get(iid) or row.get("invoice_number") or ""
        return {
            "rows": rows,
            "total_ok": sum(1 for r in rows if r.get("ok")),
            "total_failed": sum(1 for r in rows if not r.get("ok")),
            "total_seen": sum(1 for r in rows if r.get("opened_at") or r.get("viewed_at")),
        }

    @ext_router.get("/clients/{client_id}/email-log")
    async def client_email_log(client_id: str, limit: int = 100,
                               user: dict = Depends(require_finance)):
        """Todo lo que se le mandó a este cliente: facturas, recordatorios y recibos.

        Es lo que se abre cuando el cliente dice «a mí nunca me avisaron»."""
        rows = await db.fin_email_log.find({"client_id": client_id}) \
            .sort("sent_at", -1).to_list(max(1, min(int(limit), 300)))
        for row in rows:
            row.pop("_id", None)
        return rows

    @ext_router.get("/collections")
    async def collections_status(user: dict = Depends(require_finance)):
        """Estado de cobranza: quién debe, cuánto, desde cuándo y qué se le mandó."""
        from collections_engine import due_date_of, next_reminder_hint

        invoices = await db.fin_invoices.find({
            "status": {"$in": ["pending", "overdue", "partial"]},
        }).to_list(500)
        today = datetime.utcnow().date()
        rows = []
        for inv in invoices:
            balance = float(inv.get("balance") or 0)
            if balance <= 0.01:
                continue
            client = await db.fin_clients.find_one({"id": inv.get("client_id")}) or {}
            due = due_date_of(inv)
            reminders = inv.get("reminders_sent") or []
            rows.append({
                "invoice_id": inv["id"],
                "invoice_number": inv.get("invoice_number"),
                "client_id": inv.get("client_id"),
                "client": client.get("business_name") or client.get("name"),
                "client_email": client.get("email"),
                "balance": round(balance, 2),
                "due_date": inv.get("due_date"),
                "days_late": (today - due.date()).days if due else None,
                "status": inv.get("status"),
                "reminders_sent": len(reminders),
                "last_reminder_stage": inv.get("last_reminder_stage"),
                "last_reminder_at": inv.get("last_reminder_at"),
                "next_reminder_on": next_reminder_hint(inv),
            })
        rows.sort(key=lambda r: -(r["days_late"] or -999))
        return {"rows": rows,
                "total_due": round(sum(r["balance"] for r in rows), 2),
                "overdue_count": sum(1 for r in rows if (r["days_late"] or 0) > 0)}

    @ext_router.post("/invoices/{invoice_id}/reminder")
    async def send_reminder_now(invoice_id: str, user: dict = Depends(require_finance)):
        """Mandar el recordatorio que toque, sin esperar al robot de las 10."""
        from collections_engine import STAGES, reminder_body, stage_due_today
        from finance_scheduler import _send_plain_email

        inv = await db.fin_invoices.find_one({"id": invoice_id})
        if not inv:
            raise HTTPException(404, "Invoice not found")
        if float(inv.get("balance") or 0) <= 0.01:
            raise HTTPException(400, "Esta factura ya está pagada: no hay nada que recordar")
        client = await db.fin_clients.find_one({"id": inv.get("client_id")}) or {}
        if not (client.get("email") or "").strip():
            raise HTTPException(400, "Este cliente no tiene correo cargado")
        stage = stage_due_today(inv, datetime.utcnow()) or STAGES[0]
        subject, html = reminder_body(inv, client, stage)
        try:
            await _send_plain_email(db, client, subject, html,
                                    kind=f"reminder:{stage[0]}", invoice_id=invoice_id)
        except HTTPException:
            raise
        except Exception as exc:
            # La contraseña ilegible es un problema de configuración del dueño,
            # no una falla del servidor: 400 con instrucciones.
            code = 400 if str(exc) in SMTP_CONFIG_ERRORS else 500
            raise HTTPException(code, str(exc))
        await db.fin_invoices.update_one({"id": invoice_id}, {
            "$set": {"last_reminder_at": datetime.utcnow().isoformat(),
                     "last_reminder_stage": stage[0]},
            "$push": {"reminders_sent": {"stage": stage[0],
                                         "at": datetime.utcnow().isoformat()}},
        })
        return {"ok": True, "stage": stage[0], "to": client.get("email"),
                "subject": subject}

    @ext_router.get("/users")
    async def list_users(user: dict = Depends(require_admin)):
        items = await db.users.find({}, {"password_hash": 0}).sort("created_at", -1).to_list(500)
        for u in items:
            u.pop("_id", None)
        return items

    @ext_router.post("/users")
    async def create_user(data: UserCreate, user: dict = Depends(require_admin)):
        # Verify role allowed
        allowed_roles = {"admin", "accounting", "sales", "technical", "viewer"}
        if user.get("role") == "superadmin":
            allowed_roles.add("superadmin")
        if data.role not in allowed_roles:
            raise HTTPException(400, f"Invalid role. Allowed: {sorted(allowed_roles)}")
        # Check email unique
        if await db.users.find_one({"email": data.email}):
            raise HTTPException(400, "Email already registered")
        import bcrypt
        password_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
        doc = {
            "id": str(uuid.uuid4()),
            "name": data.name,
            "email": data.email,
            "phone": data.phone or "",
            "password_hash": password_hash,
            "role": data.role,
            "active": True,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": user.get("email", ""),
        }
        await db.users.insert_one(doc)
        doc.pop("password_hash", None)
        doc.pop("_id", None)
        return doc

    @ext_router.put("/users/{user_id}")
    async def update_user(user_id: str, data: UserUpdate, user: dict = Depends(require_admin)):
        upd = {k: v for k, v in data.dict().items() if v is not None and k != "password"}
        if data.password:
            import bcrypt
            upd["password_hash"] = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
        if upd:
            upd["updated_at"] = datetime.utcnow().isoformat()
            await db.users.update_one({"id": user_id}, {"$set": upd})
        return {"ok": True}

    @ext_router.delete("/users/{user_id}")
    async def delete_user(user_id: str, user: dict = Depends(require_admin)):
        u = await db.users.find_one({"id": user_id})
        if not u:
            raise HTTPException(404, "User not found")
        if u.get("email") == user.get("email"):
            raise HTTPException(400, "Cannot delete yourself")
        await db.users.update_one({"id": user_id}, {"$set": {"active": False}})
        return {"ok": True}

    # ============ EXPORTS (Excel / CSV) ============
    def _xlsx_response(rows: List[List], headers: List[str], sheet_name: str, filename: str):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_name[:31]
        ws.append(headers)
        header_fill = PatternFill("solid", fgColor="0F172A")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        for col in range(1, len(headers)+1):
            cell = ws.cell(row=1, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="left", vertical="center")
        for r in rows:
            ws.append(r)
        for i, h in enumerate(headers, 1):
            maxw = max([len(str(h))] + [len(str(r[i-1])) if i-1 < len(r) and r[i-1] is not None else 0 for r in rows])
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(max(maxw + 3, 12), 60)
        buf = BytesIO()
        wb.save(buf); buf.seek(0)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'})

    @ext_router.get("/export/invoices.xlsx")
    async def export_invoices(user: dict = Depends(require_finance)):
        items = await db.fin_invoices.find().sort("issue_date", -1).to_list(5000)
        client_map = {c["id"]: c for c in await db.fin_clients.find().to_list(5000)}
        rows = []
        for i in items:
            cl = client_map.get(i.get("client_id"), {})
            rows.append([
                i.get("invoice_number",""), cl.get("business_name",""),
                cl.get("representative",""), cl.get("email",""),
                i.get("issue_date",""), i.get("due_date",""),
                i.get("period_start",""), i.get("period_end",""),
                float(i.get("subtotal",0)), float(i.get("tax",0)),
                float(i.get("total",0)), float(i.get("amount_paid",0)),
                float(i.get("balance",0)), i.get("status",""),
            ])
        return _xlsx_response(rows, [
            "Invoice #","Client","Representative","Email","Issue Date","Due Date",
            "Period Start","Period End","Subtotal","Tax","Total","Amount Paid","Balance","Status"
        ], "Invoices", f"Invoices_{datetime.utcnow().strftime('%Y%m%d')}")

    @ext_router.get("/export/payments.xlsx")
    async def export_payments(user: dict = Depends(require_finance)):
        items = await db.fin_payments.find().sort("date", -1).to_list(5000)
        cm = {c["id"]: c.get("business_name","") for c in await db.fin_clients.find().to_list(5000)}
        rows = [[i.get("date",""), cm.get(i.get("client_id"),""), i.get("method",""), i.get("reference",""),
                 float(i.get("amount",0)), i.get("notes","")] for i in items]
        return _xlsx_response(rows, ["Date","Client","Method","Reference","Amount","Notes"], "Payments",
                              f"Payments_{datetime.utcnow().strftime('%Y%m%d')}")

    @ext_router.get("/export/expenses.xlsx")
    async def export_expenses(user: dict = Depends(require_finance)):
        items = await db.fin_expenses.find().sort("date", -1).to_list(5000)
        rows = [[i.get("date",""), i.get("category",""), i.get("description",""), i.get("vendor",""),
                 float(i.get("amount",0)), i.get("payment_method",""), i.get("notes","")] for i in items]
        return _xlsx_response(rows, ["Date","Category","Description","Vendor","Amount","Method","Notes"],
                              "Expenses", f"Expenses_{datetime.utcnow().strftime('%Y%m%d')}")

    @ext_router.get("/export/clients.xlsx")
    async def export_clients(user: dict = Depends(require_finance)):
        items = await db.fin_clients.find().sort("business_name", 1).to_list(5000)
        rows = []
        for c in items:
            total_screens = sum(sum(sc.get("units",1) for sc in (loc.get("screens",[]) or [])) for loc in (c.get("locations",[]) or []))
            rows.append([
                c.get("business_name",""), c.get("representative",""), c.get("email",""),
                c.get("phone",""), c.get("address_line1",""), c.get("city",""), c.get("state",""),
                c.get("zip",""), len(c.get("locations",[]) or []), total_screens, c.get("status",""),
                c.get("created_at","")[:10],
            ])
        return _xlsx_response(rows, [
            "Business","Representative","Email","Phone","Address","City","State","Zip",
            "Locations","Total Screens","Status","Created"
        ], "Clients", f"Clients_{datetime.utcnow().strftime('%Y%m%d')}")

    @ext_router.get("/export/accounts-receivable.xlsx")
    async def export_ar(user: dict = Depends(require_finance)):
        ar_data = await accounts_receivable(user)
        rows = []
        for c in ar_data["clients"]:
            for inv in c["invoices"]:
                rows.append([
                    c["client_name"], c["representative"], c["email"], c["phone"],
                    inv["invoice_number"], inv.get("issue_date",""), inv.get("due_date",""),
                    float(inv.get("total",0)), float(inv.get("balance", inv.get("total",0))),
                    inv["status"],
                ])
        return _xlsx_response(rows, [
            "Client","Representative","Email","Phone","Invoice #","Issue Date","Due Date",
            "Total","Balance Due","Status"
        ], "Accounts Receivable", f"AR_{datetime.utcnow().strftime('%Y%m%d')}")

    return ext_router
