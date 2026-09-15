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
import time
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


_TPL_CACHE = {"at": 0.0, "rows": []}


async def list_templates(force: bool = False) -> list:
    """Plantillas reales del WABA con su idioma y estado (caché de 5 minutos).

    Sirve para dos cosas: mostrarle al dueño qué aprobó Meta de verdad y elegir
    el idioma exacto al mandar."""
    if not (WABA_ID and ACCESS_TOKEN):
        return []
    ahora = time.time()
    if not force and _TPL_CACHE["rows"] and ahora - _TPL_CACHE["at"] < 300:
        return _TPL_CACHE["rows"]
    data = await graph("GET", f"{BASE}/{WABA_ID}/message_templates",
                       params={"fields": "name,language,status,category", "limit": "200"})
    rows = [{"name": t.get("name", ""), "language": t.get("language", ""),
             "status": t.get("status", ""), "category": t.get("category", "")}
            for t in (data.get("data") or [])]
    _TPL_CACHE.update(at=ahora, rows=rows)
    return rows


async def resolve_lang(name: str, lang: str) -> str:
    """Devuelve el código de idioma EXACTO con el que Meta aprobó la plantilla.

    Meta trata `es`, `es_MX` y `es_ES` como idiomas distintos: si se manda uno
    que no es el aprobado responde 132001 («Template name does not exist in the
    translation») aunque la plantilla exista. Así el envío no depende de qué
    variante eligió el dueño al crearla en el Administrador de WhatsApp.
    """
    quiere = LANG_CODES.get(lang, "es")
    try:
        rows = await list_templates()
    except WhatsAppError:
        return quiere
    aprobados = [r["language"] for r in rows
                 if r["name"] == name and r["status"] == "APPROVED"]
    if not aprobados or quiere in aprobados:
        return quiere
    base = quiere.split("_")[0]
    for idioma in aprobados:
        if idioma.split("_")[0] == base:
            return idioma
    return aprobados[0]


async def check_template_ready(name: str) -> None:
    """Corta el envío con un motivo claro si Meta todavía no aprobó la plantilla.

    Meta contesta `(#132001) Template name does not exist in the translation`
    tanto si la plantilla no existe como si está en revisión: un mensaje que no
    le dice nada al dueño. Acá se explica qué falta y qué esperar.
    """
    try:
        rows = await list_templates()
    except WhatsAppError:
        return          # Si Meta no responde el listado, se intenta el envío igual.
    if not rows:
        return
    mias = [r for r in rows if r["name"] == name]
    if not mias:
        raise WhatsAppError(400, {"error": {"message": (
            f"La plantilla «{name}» no existe en el Administrador de WhatsApp. "
            "Hay que crearla y esperar la aprobación de Meta.")}})
    if any(r["status"] == "APPROVED" for r in mias):
        return
    estados = ", ".join(sorted({f"{r['language']}: {r['status']}" for r in mias}))
    raise WhatsAppError(400, {"error": {"message": (
        f"Meta todavía no aprobó la plantilla «{name}» ({estados}). "
        "Mientras figure en revisión (PENDING / In review) no se puede enviar; "
        "en cuanto pase a APPROVED los envíos salen solos, sin tocar nada.")}})


async def send_template(*, to: str, template: str, params: list, lang: str = "es",
                        media_id: str = "", filename: str = "") -> str:
    tpl = TEMPLATES[template]
    await check_template_ready(tpl["name"])
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
                     "language": {"code": await resolve_lang(tpl["name"], lang)},
                     "components": componentes},
    }
    res = await graph("POST", f"{BASE}/{PHONE_NUMBER_ID}/messages", json=payload)
    return res["messages"][0]["id"]


async def send_hello(to: str) -> str:
    """Manda `hello_world`, la plantilla que Meta deja aprobada en toda cuenta.

    Sirve para comprobar token + número + webhook sin esperar la aprobación de
    las plantillas del negocio: si esto llega, lo único que falta es el visto
    bueno de Meta a las nuestras.
    """
    payload = {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
        "type": "template",
        "template": {"name": "hello_world", "language": {"code": "en_US"}},
    }
    res = await graph("POST", f"{BASE}/{PHONE_NUMBER_ID}/messages", json=payload)
    return res["messages"][0]["id"]


MEDIA_TYPES = ("image", "document", "audio", "video", "sticker", "voice")


def parse_inbound(m: dict) -> dict:
    """Saca el texto y, si viene, el archivo de un mensaje del cliente.

    El cliente manda fotos del local, comprobantes de pago en PDF y notas de
    voz. Meta no manda el archivo: manda un `id` que hay que bajar con el token
    (y que caduca), así que se guarda el id y el panel lo pide cuando lo abre.
    """
    tipo = m.get("type") or "text"
    if tipo == "text":
        return {"text": (m.get("text") or {}).get("body") or "", "media": None}
    if tipo in MEDIA_TYPES:
        cuerpo = m.get(tipo) or {}
        return {"text": cuerpo.get("caption") or "", "media": {
            "media_id": cuerpo.get("id") or "", "kind": tipo,
            "mime_type": cuerpo.get("mime_type") or "",
            "filename": cuerpo.get("filename") or "",
        }}
    if tipo == "location":
        loc = m.get("location") or {}
        return {"text": f"📍 {loc.get('name') or ''} {loc.get('address') or ''}".strip()
                        or f"📍 {loc.get('latitude')}, {loc.get('longitude')}", "media": None}
    if tipo == "button":
        return {"text": (m.get("button") or {}).get("text") or "[botón]", "media": None}
    if tipo == "interactive":
        it = m.get("interactive") or {}
        elegido = it.get("button_reply") or it.get("list_reply") or {}
        return {"text": elegido.get("title") or "[respuesta]", "media": None}
    if tipo == "contacts":
        return {"text": "[contacto compartido]", "media": None}
    return {"text": f"[{tipo}]", "media": None}


async def fetch_media(media_id: str) -> tuple:
    """Baja un archivo que mandó el cliente. Devuelve (bytes, mime, nombre)."""
    info = await graph("GET", f"{BASE}/{media_id}")
    url = info.get("url")
    if not url:
        raise WhatsAppError(404, {"error": {"message": "El archivo ya no está disponible en Meta"}})
    async with httpx.AsyncClient(timeout=90) as cli:
        r = await cli.get(url, headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
    if r.status_code >= 400:
        raise WhatsAppError(r.status_code, {"error": {"message": "No se pudo bajar el archivo"}})
    mime = info.get("mime_type") or r.headers.get("content-type") or "application/octet-stream"
    return r.content, mime.split(";")[0].strip(), info.get("file_name") or ""


async def send_text(*, to: str, body: str) -> str:
    """Texto libre. Meta SÓLO lo permite dentro de las 24 h desde el último
    mensaje del cliente; fuera de esa ventana hay que usar plantilla."""
    res = await graph("POST", f"{BASE}/{PHONE_NUMBER_ID}/messages", json={
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
        "type": "text", "text": {"preview_url": False, "body": body}})
    return res["messages"][0]["id"]


WINDOW_HOURS = 24


def window_open(conv: dict) -> bool:
    """¿Se puede contestar con texto libre? Se mide desde el ÚLTIMO mensaje
    entrante del cliente, no desde el último nuestro."""
    ultimo = (conv or {}).get("last_inbound_at")
    if not ultimo:
        return False
    try:
        return (datetime.utcnow() - datetime.fromisoformat(ultimo)).total_seconds() < WINDOW_HOURS * 3600
    except ValueError:
        return False


async def upsert_conversation(db, phone: str, *, text: str = "", inbound: bool = True,
                              client: dict = None) -> dict:
    """Una conversación por número. Guarda a quién pertenece (si es cliente) y
    cuándo escribió por última vez, que es lo que abre la ventana de 24 h."""
    ahora = datetime.utcnow().isoformat()
    upd = {"last_message": (text or "")[:300], "last_at": ahora,
           "last_direction": "in" if inbound else "out"}
    if inbound:
        upd["last_inbound_at"] = ahora
    if client:
        upd["client_id"] = client.get("id")
        upd["client_name"] = client.get("business_name") or client.get("representative") or ""
    inc = {"unread": 1} if inbound else {}
    if not inbound:
        upd["unread"] = 0
    await db.wa_conversations.update_one(
        {"phone": phone},
        {"$set": upd, "$inc": inc,
         "$setOnInsert": {"id": str(uuid4()), "phone": phone, "created_at": ahora}},
        upsert=True)
    return await db.wa_conversations.find_one({"phone": phone})


async def find_client_by_phone(db, phone: str) -> dict:
    """Engancha el número con el cliente: se comparan los últimos 10 dígitos
    porque el dueño carga los teléfonos en cualquier formato."""
    cola = phone[-10:]
    if len(cola) < 10:
        return {}
    async for cl in db.fin_clients.find({}, {"id": 1, "business_name": 1, "representative": 1,
                                             "phone": 1, "whatsapp": 1, "country_code": 1}):
        for campo in ("whatsapp", "phone"):
            if re.sub(r"\D", "", cl.get(campo) or "")[-10:] == cola:
                return cl
    return {}


# ---------------------------------------------------------------- Bitácora
async def log_wa(db, *, client_id: str, invoice_id: str, kind: str, to: str,
                 template: str, ok: bool, message_id: str = "", error: str = "",
                 dedupe_key: str = "", text: str = "") -> str:
    doc = {
        "id": str(uuid4()), "client_id": client_id, "invoice_id": invoice_id,
        "kind": kind, "to": to, "template": template,
        "direction": "out", "text": text or "", "media": None,
        "message_id": message_id or None,
        "status": "accepted" if ok else "failed",
        "ok": bool(ok), "error": error or "",
        "dedupe_key": dedupe_key or "",
        "sent_at": datetime.utcnow().isoformat(),
        "delivered_at": None, "read_at": None, "failed_at": None,
    }
    await db.wa_messages.insert_one(doc)
    # Que lo enviado también aparezca en el hilo de la bandeja: si no, el dueño
    # ve la respuesta del cliente sin saber qué se le había mandado.
    if ok and to:
        await upsert_conversation(db, to, text=text or template, inbound=False)
        if client_id:
            await db.wa_conversations.update_one({"phone": to},
                                                 {"$set": {"client_id": client_id}})
    return doc["id"]


async def send_reply(db, phone: str, text: str, sent_by: str = "") -> dict:
    """Respuesta manual del panel (texto libre, dentro de la ventana de 24 h)."""
    if not is_configured():
        return {"ok": False, "reason": missing_config()}
    to = normalize_phone(phone)
    if not to:
        return {"ok": False, "reason": "Número inválido."}
    if not (text or "").strip():
        return {"ok": False, "reason": "Escribí el mensaje."}
    conv = await db.wa_conversations.find_one({"phone": to})
    if not window_open(conv):
        return {"ok": False, "window_closed": True,
                "reason": ("Pasaron más de 24 h desde el último mensaje del cliente. "
                           "WhatsApp sólo permite plantillas aprobadas fuera de esa ventana.")}
    try:
        msg_id = await send_text(to=to, body=text.strip())
    except WhatsAppError as exc:
        return {"ok": False, "reason": exc.detail}
    ahora = datetime.utcnow().isoformat()
    await db.wa_messages.insert_one({
        "id": str(uuid4()), "message_id": msg_id,
        "client_id": (conv or {}).get("client_id"), "invoice_id": None,
        "kind": "reply", "direction": "out", "to": to, "from": PHONE_NUMBER_ID,
        "text": text.strip(), "media": None, "template": "", "ok": True, "error": "",
        "status": "accepted", "sent_by": sent_by, "sent_at": ahora,
        "delivered_at": None, "read_at": None, "failed_at": None,
    })
    await upsert_conversation(db, to, text=text.strip(), inbound=False)
    return {"ok": True, "message_id": msg_id}


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
                valor = change.get("value") or {}
                for m in valor.get("messages", []):
                    # Mensaje del cliente. Antes se descartaba: si el número se
                    # migra a la API y esto no se guarda, nadie puede leer las
                    # respuestas (Meta no guarda historial recuperable).
                    desde = re.sub(r"\D", "", m.get("from") or "")
                    if not desde:
                        continue
                    if await db.wa_messages.find_one({"message_id": m.get("id")}):
                        continue          # Meta reintenta: no duplicar
                    parsed = parse_inbound(m)
                    media = parsed["media"]
                    texto = parsed["text"] or (
                        f"[{media['kind']}]" if media else f"[{m.get('type','mensaje')}]")
                    cliente = await find_client_by_phone(db, desde)
                    await db.wa_messages.insert_one({
                        "id": str(uuid4()), "message_id": m.get("id"),
                        "client_id": cliente.get("id"), "invoice_id": None,
                        "kind": "inbound", "direction": "in", "to": desde, "from": desde,
                        "text": texto, "media": media, "msg_type": m.get("type") or "text",
                        "template": "", "ok": True, "error": "",
                        "status": "received", "sent_at": ahora,
                        "delivered_at": ahora, "read_at": None, "failed_at": None,
                    })
                    await upsert_conversation(db, desde, text=texto, inbound=True,
                                              client=cliente or None)
                for st in valor.get("statuses", []):
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
