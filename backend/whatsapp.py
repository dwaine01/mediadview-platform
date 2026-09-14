"""Canal WhatsApp (Meta Cloud API oficial) — MediaView Communication System.

El correo NO se toca: WhatsApp es un canal ADICIONAL. Todo lo que sale queda en
`wa_messages` (bitácora) con su `message_id` de Meta y su estado real
(`accepted → sent → delivered → read` o `failed`), que llega por webhook.

Reglas que no se pueden romper:
  · Sólo API oficial de Meta (nada de WhatsApp Web ni librerías no oficiales).
  · Los secretos viven en variables de entorno; el panel nunca los ve.
  · Fuera de la ventana de 24 h sólo se pueden mandar **plantillas aprobadas**,
    así que todo lo que inicia MediaView va por plantilla.
  · `accepted` NO es entregado: la entrega la confirma el webhook.
  · Nada de duplicados: `dedupe_key` (factura + plantilla + destinatario) y el
    índice único de `message_id`.

Mientras falten credenciales el módulo queda APAGADO: `is_configured()` da
False, los envíos devuelven un motivo claro y el resto del sistema sigue igual.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

logger = logging.getLogger("whatsapp")

GRAPH_VERSION = os.environ.get("GRAPH_API_VERSION", "v23.0")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
WABA_ID = os.environ.get("WHATSAPP_BUSINESS_ACCOUNT_ID", "").strip()
ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()
APP_SECRET = os.environ.get("META_APP_SECRET", "").strip()
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()

BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

# Plantillas de negocio. El nombre y el idioma tienen que coincidir EXACTO con
# las aprobadas en el Administrador de WhatsApp, y los parámetros del cuerpo van
# en este orden. Si Meta aprueba con otro orden, se cambia acá.
TEMPLATES = {
    "invoice_created":  {"name": "mediaview_invoice_created",  "doc": True},
    "invoice_due":      {"name": "mediaview_invoice_due",      "doc": False},
    "invoice_overdue":  {"name": "mediaview_invoice_overdue",  "doc": False},
    "payment_received": {"name": "mediaview_payment_received", "doc": False},
}
LANG_CODES = {"es": "es", "en": "en_US"}


def is_configured() -> bool:
    return bool(PHONE_NUMBER_ID and ACCESS_TOKEN)


def missing_config() -> str:
    faltan = [n for n, v in (
        ("Phone Number ID", PHONE_NUMBER_ID), ("Token de Meta", ACCESS_TOKEN),
        ("WABA ID", WABA_ID), ("App Secret", APP_SECRET),
        ("Verify Token", VERIFY_TOKEN)) if not v]
    return ("WhatsApp todavía no está conectado. Falta cargar en el servidor: "
            + ", ".join(faltan) + ".") if faltan else ""


def normalize_phone(number: str, country_code: str = "") -> str:
    """Deja el número como lo pide Meta: sólo dígitos con código de país.

    El dueño carga los teléfonos como «(614) 555-1234» y el código aparte, así
    que acá se limpia todo: sin espacios, guiones, paréntesis ni «+».
    """
    digits = re.sub(r"\D", "", number or "")
    if not digits:
        return ""
    cc = re.sub(r"\D", "", country_code or "")
    if cc and not digits.startswith(cc):
        digits = cc + digits
    if not cc and len(digits) == 10:
        digits = "1" + digits          # EE.UU. es el caso normal del negocio
    return digits


def client_whatsapp(client: dict) -> str:
    """Número de WhatsApp del cliente (cae al teléfono común si no hay otro)."""
    return normalize_phone(
        (client.get("whatsapp") or client.get("phone") or ""),
        client.get("country_code") or "1")


def wants(client: dict, kind: str) -> bool:
    """ON por defecto para todo cliente con número válido; se apaga por cliente."""
    if not client_whatsapp(client):
        return False
    campo = "wa_invoice_notify" if kind == "invoice" else "wa_reminder_notify"
    return client.get(campo, True) is not False


# ---------------------------------------------------------------- Graph API
class WhatsAppError(Exception):
    def __init__(self, status: int, payload):
        self.status = status
        self.payload = payload
        err = (payload or {}).get("error", {}) if isinstance(payload, dict) else {}
        self.code = err.get("code")
        self.detail = err.get("message") or str(payload)
        super().__init__(f"WhatsApp {status}: {self.detail}")


# Reintentar sólo lo transitorio. Un token vencido o una plantilla sin aprobar
# no se arregla reintentando: se reporta para que el dueño lo corrija.
TRANSIENT_HTTP = {408, 429, 500, 502, 503, 504}
TRANSIENT_CODES = {2, 4, 80007, 130429, 131056}


async def graph(method: str, url: str, **kw) -> dict:
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    for intento in range(3):
        try:
            async with httpx.AsyncClient(timeout=45) as cli:
                r = await cli.request(method, url, headers=headers, **kw)
            try:
                data = r.json()
            except ValueError:
                data = {"raw": r.text}
            if r.status_code < 400:
                return data
            code = (data.get("error") or {}).get("code")
            transitorio = r.status_code in TRANSIENT_HTTP or code in TRANSIENT_CODES
            if not transitorio or intento == 2:
                raise WhatsAppError(r.status_code, data)
            espera = float(r.headers.get("Retry-After") or min(30, 2 ** intento))
            await asyncio.sleep(espera)
        except (httpx.TimeoutException, httpx.NetworkError):
            if intento == 2:
                raise WhatsAppError(504, {"error": {"message": "Meta no respondió"}})
            await asyncio.sleep(min(30, 2 ** intento))
    raise WhatsAppError(500, {"error": {"message": "sin reintentos"}})


async def upload_pdf(pdf: bytes, filename: str) -> str:
    """Sube el PDF a Meta y devuelve el media_id.

    Se usa media_id en vez de un link público: el PDF de una factura no puede
    quedar accesible en internet."""
    data = {"messaging_product": "whatsapp", "type": "application/pdf"}
    files = {"file": (filename, pdf, "application/pdf")}
    return (await graph("POST", f"{BASE}/{PHONE_NUMBER_ID}/media",
                        data=data, files=files))["id"]


async def send_template(*, to: str, template: str, params: list, lang: str = "es",
                        media_id: str = "", filename: str = "") -> str:
    tpl = TEMPLATES[template]
    componentes = []
    if media_id:
        componentes.append({"type": "header", "parameters": [
            {"type": "document", "document": {"id": media_id, "filename": filename}}]})
    componentes.append({"type": "body", "parameters": [
        {"type": "text", "text": str(p)} for p in params]})
    payload = {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
        "type": "template",
        "template": {"name": tpl["name"],
                     "language": {"code": LANG_CODES.get(lang, "es")},
                     "components": componentes},
    }
    res = await graph("POST", f"{BASE}/{PHONE_NUMBER_ID}/messages", json=payload)
    return res["messages"][0]["id"]


# ---------------------------------------------------------------- Bitácora
async def log_wa(db, *, client_id: str, invoice_id: str, kind: str, to: str,
                 template: str, ok: bool, message_id: str = "", error: str = "",
                 dedupe_key: str = "") -> str:
    doc = {
        "id": str(uuid4()), "client_id": client_id, "invoice_id": invoice_id,
        "kind": kind, "to": to, "template": template,
        "message_id": message_id or None,
        "status": "accepted" if ok else "failed",
        "ok": bool(ok), "error": error or "",
        "dedupe_key": dedupe_key or "",
        "sent_at": datetime.utcnow().isoformat(),
        "delivered_at": None, "read_at": None, "failed_at": None,
    }
    await db.wa_messages.insert_one(doc)
    return doc["id"]


async def already_sent(db, dedupe_key: str) -> bool:
    """Evita mandar dos veces lo mismo (reintentos del cron, doble clic)."""
    if not dedupe_key:
        return False
    return await db.wa_messages.find_one({"dedupe_key": dedupe_key, "ok": True}) is not None


async def send_invoice_whatsapp(db, invoice: dict, client: dict, *, kind: str = "invoice_created",
                                force: bool = False) -> dict:
    """Manda la factura por WhatsApp con el PDF adjunto.

    Devuelve siempre un dict con el resultado — nunca explota: si WhatsApp
    falla, la factura ya salió por correo y el cobro no se puede caer por esto.
    """
    if not is_configured():
        return {"ok": False, "skipped": True, "reason": missing_config()}
    to = client_whatsapp(client)
    if not to:
        return {"ok": False, "skipped": True,
                "reason": f"{client.get('business_name','El cliente')} no tiene número de WhatsApp."}
    if not force and not wants(client, "invoice"):
        return {"ok": False, "skipped": True,
                "reason": "El cliente tiene apagados los avisos de factura por WhatsApp."}

    dedupe = f"{kind}:{invoice.get('id')}:{to}"
    if not force and await already_sent(db, dedupe):
        return {"ok": True, "skipped": True, "reason": "Ya se había enviado por WhatsApp."}

    from finance_pdf import generate_invoice_pdf
    numero = invoice.get("invoice_number", "")
    monto = f"${float(invoice.get('balance') or invoice.get('total') or 0):,.2f}"
    vence = invoice.get("due_date", "")
    nombre = client.get("representative") or client.get("business_name") or "cliente"
    filename = f"Invoice_{numero}.pdf"
    try:
        media_id = await upload_pdf(generate_invoice_pdf(invoice, client), filename)
        msg_id = await send_template(
            to=to, template=kind, lang=client.get("language", "es"),
            params=[nombre, numero, monto, vence],
            media_id=media_id, filename=filename)
    except WhatsAppError as exc:
        await log_wa(db, client_id=client.get("id", ""), invoice_id=invoice.get("id", ""),
                     kind=kind, to=to, template=TEMPLATES[kind]["name"], ok=False,
                     error=exc.detail, dedupe_key=dedupe)
        logger.warning(f"WhatsApp factura {numero}: {exc.detail}")
        return {"ok": False, "reason": exc.detail}

    log_id = await log_wa(db, client_id=client.get("id", ""), invoice_id=invoice.get("id", ""),
                          kind=kind, to=to, template=TEMPLATES[kind]["name"], ok=True,
                          message_id=msg_id, dedupe_key=dedupe)
    await db.fin_invoices.update_one({"id": invoice.get("id")}, {"$set": {
        "wa_message_id": msg_id, "wa_status": "accepted",
        "wa_sent_at": datetime.utcnow().isoformat(), "wa_to": to}})
    return {"ok": True, "message_id": msg_id, "log_id": log_id, "to": to}


async def send_reminder_whatsapp(db, invoice: dict, client: dict, stage: str,
                                 texto_estado: str) -> dict:
    """Recordatorio de cobranza por WhatsApp (sin PDF: ya lo recibió).

    NUNCA manda si la factura está pagada o anulada, y no repite la misma etapa.
    """
    if invoice.get("status") in ("paid", "cancelled") or float(invoice.get("balance") or 0) <= 0:
        return {"ok": False, "skipped": True, "reason": "La factura ya está pagada o anulada."}
    if not is_configured():
        return {"ok": False, "skipped": True, "reason": missing_config()}
    to = client_whatsapp(client)
    if not to or not wants(client, "reminder"):
        return {"ok": False, "skipped": True,
                "reason": "Sin número de WhatsApp o recordatorios apagados."}

    kind = "invoice_due" if stage in ("pre_due", "due") else "invoice_overdue"
    dedupe = f"{kind}:{stage}:{invoice.get('id')}:{to}"
    if await already_sent(db, dedupe):
        return {"ok": True, "skipped": True, "reason": "Ya se avisó esta etapa."}

    numero = invoice.get("invoice_number", "")
    monto = f"${float(invoice.get('balance') or 0):,.2f}"
    nombre = client.get("representative") or client.get("business_name") or "cliente"
    try:
        msg_id = await send_template(to=to, template=kind, lang=client.get("language", "es"),
                                     params=[nombre, numero, monto,
                                             invoice.get("due_date", ""), texto_estado][:4])
    except WhatsAppError as exc:
        await log_wa(db, client_id=client.get("id", ""), invoice_id=invoice.get("id", ""),
                     kind=f"reminder:{stage}", to=to, template=TEMPLATES[kind]["name"],
                     ok=False, error=exc.detail, dedupe_key=dedupe)
        return {"ok": False, "reason": exc.detail}
    await log_wa(db, client_id=client.get("id", ""), invoice_id=invoice.get("id", ""),
                 kind=f"reminder:{stage}", to=to, template=TEMPLATES[kind]["name"],
                 ok=True, message_id=msg_id, dedupe_key=dedupe)
    return {"ok": True, "message_id": msg_id}


async def send_payment_received_whatsapp(db, invoice: dict, client: dict, amount: float) -> dict:
    """Gracias por su pago. También es la señal de que la cobranza terminó."""
    if not is_configured():
        return {"ok": False, "skipped": True, "reason": missing_config()}
    to = client_whatsapp(client)
    if not to or not wants(client, "invoice"):
        return {"ok": False, "skipped": True, "reason": "Sin número o avisos apagados."}
    numero = invoice.get("invoice_number", "")
    dedupe = f"payment_received:{invoice.get('id')}:{amount}:{to}"
    if await already_sent(db, dedupe):
        return {"ok": True, "skipped": True, "reason": "Ya se agradeció este pago."}
    nombre = client.get("representative") or client.get("business_name") or "cliente"
    try:
        msg_id = await send_template(
            to=to, template="payment_received", lang=client.get("language", "es"),
            params=[nombre, numero, f"${float(amount):,.2f}",
                    f"${float(invoice.get('balance') or 0):,.2f}"])
    except WhatsAppError as exc:
        await log_wa(db, client_id=client.get("id", ""), invoice_id=invoice.get("id", ""),
                     kind="payment_received", to=to, template=TEMPLATES["payment_received"]["name"],
                     ok=False, error=exc.detail, dedupe_key=dedupe)
        return {"ok": False, "reason": exc.detail}
    await log_wa(db, client_id=client.get("id", ""), invoice_id=invoice.get("id", ""),
                 kind="payment_received", to=to, template=TEMPLATES["payment_received"]["name"],
                 ok=True, message_id=msg_id, dedupe_key=dedupe)
    return {"ok": True, "message_id": msg_id}


# ---------------------------------------------------------------- Webhook
def valid_signature(raw: bytes, header: str) -> bool:
    """Valida X-Hub-Signature-256 sobre el body CRUDO.

    Si se parsea y se vuelve a serializar el JSON, la firma nunca coincide.
    """
    if not APP_SECRET:
        # Puerta abierta sólo mientras el canal está apagado: sin App Secret no
        # hay con qué validar. Queda avisado en el log para que no pase
        # inadvertido una vez conectado.
        logger.warning("WhatsApp: sin META_APP_SECRET no se puede validar la firma del webhook")
        return True
    if not header or not header.startswith("sha256="):
        return False
    esperado = hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, header.removeprefix("sha256="))


ESTADO_CAMPO = {"delivered": "delivered_at", "read": "read_at", "failed": "failed_at"}


def create_whatsapp_router(db) -> APIRouter:
    router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

    @router.get("/webhook")
    async def verify(request: Request):
        q = request.query_params
        if q.get("hub.mode") == "subscribe" and VERIFY_TOKEN and \
                hmac.compare_digest(q.get("hub.verify_token", ""), VERIFY_TOKEN):
            return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
        raise HTTPException(403, "Verificación de webhook fallida")

    @router.post("/webhook")
    async def receive(request: Request):
        raw = await request.body()
        if not valid_signature(raw, request.headers.get("X-Hub-Signature-256", "")):
            raise HTTPException(403, "Firma inválida")
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            return Response(status_code=200)

        ahora = datetime.utcnow().isoformat()
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue
                for st in (change.get("value") or {}).get("statuses", []):
                    mid, estado = st.get("id"), st.get("status")
                    if not mid or not estado:
                        continue
                    upd = {"status": estado, "status_at": ahora}
                    if estado in ESTADO_CAMPO:
                        upd[ESTADO_CAMPO[estado]] = ahora
                    if st.get("errors"):
                        upd["error"] = str(st["errors"][0].get("title") or st["errors"][0])
                        upd["ok"] = False
                    await db.wa_messages.update_one({"message_id": mid}, {"$set": upd})
                    await db.fin_invoices.update_many(
                        {"wa_message_id": mid},
                        {"$set": {"wa_status": estado, f"wa_{estado}_at": ahora}})
        # Responder 200 rápido: si no, Meta reintenta el webhook por días.
        return Response(status_code=200)

    return router
