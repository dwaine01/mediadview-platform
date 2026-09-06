"""
menu_ai_routes.py — "Importar menú con IA": el dueño sube la foto de su menú
físico y el modelo de visión devuelve los productos con nombre y precio.

El endpoint NO escribe en la base de datos: devuelve una vista previa editable.
El cliente confirma y luego se usa POST /api/workspace/menus para crearlo.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import re
import uuid as _uuid

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
MODEL_PROVIDER = "openai"
MODEL_NAME = "gpt-5.4"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
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

    return router
