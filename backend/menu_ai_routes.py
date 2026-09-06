"""
menu_ai_routes.py — "Importar menú con IA": el dueño sube la foto de su menú
físico y el modelo de visión devuelve los productos con nombre y precio.

El endpoint NO escribe en la base de datos: devuelve una vista previa editable.
El cliente confirma y luego se usa POST /api/workspace/menus para crearlo.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import re
import uuid as _uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException

from managed_portal_routes import create_audit_log as _audit
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
MODEL_PROVIDER = "openai"
MODEL_NAME = "gpt-5.4"
IMAGE_MODEL = "gemini-3.1-flash-image-preview"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MEDIA_DIR = os.environ.get("MEDIA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "media"))
ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

SYSTEM_PROMPT = (
    "Eres un asistente que digitaliza menús de restaurantes a partir de fotos. "
    "Devuelves EXCLUSIVAMENTE JSON válido, sin texto adicional y sin bloques de código."
)

USER_PROMPT = """Analiza esta foto de un menú físico y extrae todos los productos que puedas leer.

Responde SOLO con este JSON:
{
  "menu_name": "nombre del negocio o del menú si aparece, si no 'Menú'",
  "currency": "USD | MXN | EUR ... según los símbolos visibles, si no sabes usa 'USD'",
  "items": [
    {
      "name": "nombre del producto tal como aparece",
      "price": 12.5,
      "description": "descripción corta si aparece, si no null",
      "category": "categoría o sección del menú si aparece, si no null"
    }
  ]
}

Reglas:
- price siempre numérico sin símbolo de moneda. Si un producto no tiene precio legible, usa 0.
- Si un producto tiene varios tamaños/precios, crea una entrada por tamaño con el tamaño en el nombre.
- No inventes productos que no estén en la imagen. No traduzcas los nombres.
- Si la imagen no es un menú, devuelve items como lista vacía."""


class MenuImportRequest(BaseModel):
    image_base64: str = Field(..., min_length=32)
    content_type: str = "image/jpeg"


def _extract_json(text: str) -> dict:
    """The model is asked for pure JSON, but tolerate code fences / prose."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(cleaned[start:end + 1])


def _clean_price(value) -> float:
    if isinstance(value, (int, float)):
        return round(max(0.0, float(value)), 2)
    digits = re.sub(r"[^\d.,]", "", str(value or "")).replace(",", ".")
    try:
        return round(max(0.0, float(digits)), 2)
    except ValueError:
        return 0.0


def create_menu_ai_routes(db, get_current_user):
    router = APIRouter(prefix="/api/workspace", tags=["Workspace — Menú con IA"])

    @router.post("/menus/ai-import", summary="Extract menu items from a photo (preview only)")
    async def ai_import_menu(payload: MenuImportRequest, current_user: dict = Depends(get_current_user)):
        if not current_user.get("organization_id"):
            raise HTTPException(403, "Tu cuenta no está asociada a un negocio.")
        if not EMERGENT_LLM_KEY:
            raise HTTPException(503, "La función de IA no está configurada. Contacta a soporte.")

        content_type = (payload.content_type or "image/jpeg").lower().split(";")[0].strip()
        if content_type not in ALLOWED_TYPES:
            raise HTTPException(400, "Formato no soportado. Usa una foto JPG, PNG o WebP.")

        raw = payload.image_base64.strip()
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[-1]
        try:
            size = len(base64.b64decode(raw, validate=True))
        except (binascii.Error, ValueError):
            raise HTTPException(400, "La imagen no se pudo leer. Intenta tomar la foto de nuevo.")
        if size > MAX_IMAGE_BYTES:
            raise HTTPException(413, "La foto es muy grande (máximo 10 MB).")

        from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"menu-ai-{_uuid.uuid4()}",
            system_message=SYSTEM_PROMPT,
        ).with_model(MODEL_PROVIDER, MODEL_NAME)

        try:
            answer = await chat.send_message(UserMessage(
                text=USER_PROMPT,
                file_contents=[ImageContent(image_base64=raw)],
            ))
        except Exception as exc:  # network / provider failure
            logger.exception("AI menu import failed")
            raise HTTPException(502, f"La IA no pudo procesar la foto: {exc}") from exc

        try:
            data = _extract_json(answer if isinstance(answer, str) else str(answer))
        except (json.JSONDecodeError, ValueError):
            logger.warning("AI menu import returned non-JSON: %s", str(answer)[:400])
            raise HTTPException(422, "No pudimos leer el menú en esa foto. Intenta con más luz y de frente.")

        items = []
        for raw_item in (data.get("items") or [])[:120]:
            if not isinstance(raw_item, dict):
                continue
            name = str(raw_item.get("name") or "").strip()[:160]
            if not name:
                continue
            description = raw_item.get("description")
            category = raw_item.get("category")
            items.append({
                "name": name,
                "price": _clean_price(raw_item.get("price")),
                "description": str(description).strip()[:400] if description else None,
                "category": str(category).strip()[:80] if category else None,
                "available": True,
            })

        return {
            "menu_name": str(data.get("menu_name") or "Menú").strip()[:120],
            "currency": str(data.get("currency") or "USD").strip()[:8],
            "items": items,
            "raw_count": len(items),
        }

    @router.post("/menus/{menu_id}/items/{item_id}/ai-photo",
                 summary="Generate an appetizing photo for a menu item that has none")
    async def ai_photo_for_item(menu_id: str, item_id: str,
                                current_user: dict = Depends(get_current_user)):
        org_id = current_user.get("organization_id")
        if not org_id:
            raise HTTPException(403, "Tu cuenta no está asociada a un negocio.")
        if not EMERGENT_LLM_KEY:
            raise HTTPException(503, "La función de IA no está configurada. Contacta a soporte.")

        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(404, "Menú no encontrado")
        item = next((i for i in (menu.get("items") or []) if i.get("id") == item_id), None)
        if not item:
            raise HTTPException(404, "Producto no encontrado")

        descriptors = ", ".join(filter(None, [item.get("category"), item.get("description")]))
        prompt = (
            f"Fotografía profesional de comida de '{item.get('name')}'"
            + (f" ({descriptors})" if descriptors else "")
            + ". Un solo plato como protagonista, apetitoso y recién servido, luz natural suave, "
              "fondo desenfocado de restaurante, encuadre cuadrado, estilo de menú digital premium. "
              "Sin texto, sin logos, sin marcas de agua, sin personas."
        )

        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"menu-photo-{_uuid.uuid4()}",
            system_message="Generas fotografías de comida para menús digitales.",
        ).with_model("gemini", IMAGE_MODEL).with_params(modalities=["image", "text"])

        try:
            _text, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
        except Exception as exc:
            logger.exception("AI photo generation failed")
            raise HTTPException(502, f"La IA no pudo generar la foto: {exc}") from exc

        if not images:
            raise HTTPException(422, "La IA no devolvió ninguna imagen. Intenta de nuevo.")

        picture = images[0]
        mime = picture.get("mime_type") or "image/png"
        try:
            raw_bytes = base64.b64decode(picture["data"])
        except (binascii.Error, ValueError, KeyError):
            raise HTTPException(502, "La imagen generada llegó dañada. Intenta de nuevo.")

        ext = ".jpg" if "jpeg" in mime or "jpg" in mime else ".webp" if "webp" in mime else ".png"
        media_id = str(_uuid.uuid4())
        stored_name = f"{media_id}{ext}"
        os.makedirs(MEDIA_DIR, exist_ok=True)
        with open(os.path.join(MEDIA_DIR, stored_name), "wb") as fh:
            fh.write(raw_bytes)

        safe_name = re.sub(r"[^\w\s-]", "", str(item.get("name") or "producto")).strip()[:40] or "producto"
        await db.media.insert_one({
            "id": media_id,
            "user_id": current_user["id"],
            "filename": f"{safe_name}-ia{ext}",
            "content_type": mime,
            "size": len(raw_bytes),
            "type": "image",
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "storage": "legacy",
            "stored_filename": stored_name,
            "data": picture["data"],
            "status": "ready",
            "source": "ai_generated",
            "created_at": datetime.utcnow(),
        })

        image_url = f"/api/player/media/{media_id}"
        await db.menus.update_one(
            {"id": menu_id, "items.id": item_id},
            {"$set": {
                "items.$.image_url": image_url,
                "items.$.media_id": media_id,
                "updated_at": datetime.utcnow(),
            }},
        )
        await _audit(
            db, "menu_item.ai_photo",
            user_id=current_user["id"], user_email=current_user.get("email"),
            resource_type="menu", resource_id=menu_id,
            details={"menu_name": menu.get("name"), "item": item.get("name"), "photo_changed": True},
            org_id=org_id,
        )
        return {"item_id": item_id, "media_id": media_id, "image_url": image_url}

    return router
