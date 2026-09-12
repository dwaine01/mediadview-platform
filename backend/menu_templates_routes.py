"""menu_templates_routes.py — biblioteca de plantillas del cliente.

Cuando el restaurante sube su menú diseñado y la IA lo vuelve editable, ese
layout queda guardado como PLANTILLA de la organización. Después puede armar un
menú nuevo desde la plantilla en dos toques y sólo cambiar nombres, precios y
fotos: el diseño, los colores y la tipografía se reusan tal cual.

Una plantilla es una copia congelada del canvas. Editar el menú que la originó
NO toca la plantilla, y usar la plantilla NO toca el menú: si compartieran el
documento, cambiar un precio en un local rompería el menú del otro.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_TEMPLATES_PER_ORG = 60


class TemplateRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


class TemplateUse(BaseModel):
    name: str | None = Field(default=None, max_length=120)


def _copy_fields(fields: list[dict]) -> list[dict]:
    """Copia profunda con ids nuevos: dos menús no pueden compartir recuadros."""
    return [{**field, "id": str(_uuid.uuid4())} for field in (fields or []) if isinstance(field, dict)]


async def save_canvas_as_template(db, org_id: str, menu: dict) -> str | None:
    """Guarda (o actualiza) la plantilla que nace de un menú con diseño propio.

    Se llama sola cuando el análisis de la IA termina bien. Si el cliente vuelve
    a subir el diseño del mismo menú, se actualiza la misma plantilla en vez de
    llenar la lista de duplicados.
    """
    canvas = menu.get("canvas") or {}
    if not canvas.get("background_url") or not canvas.get("fields"):
        return None
    now = datetime.utcnow()
    snapshot = {
        "org_id": org_id,
        "name": (menu.get("name") or "Mi diseño")[:80],
        "background_url": canvas["background_url"],
        "background_media_id": canvas.get("background_media_id"),
        "width": int(canvas.get("width") or 1920),
        "height": int(canvas.get("height") or 1080),
        "fields": canvas.get("fields") or [],
        "source_menu_id": menu["id"],
        "updated_at": now,
    }
    existing = await db.menu_templates.find_one(
        {"org_id": org_id, "source_menu_id": menu["id"]}, {"_id": 0, "id": 1})
    if existing:
        await db.menu_templates.update_one({"id": existing["id"]}, {"$set": snapshot})
        return existing["id"]
    if await db.menu_templates.count_documents({"org_id": org_id}) >= MAX_TEMPLATES_PER_ORG:
        logger.warning("Org %s hit the template cap; skipping auto-save", org_id)
        return None
    template_id = str(_uuid.uuid4())
    await db.menu_templates.insert_one({**snapshot, "id": template_id, "created_at": now})
    return template_id


def create_menu_templates_routes(db, get_current_user):
    router = APIRouter(prefix="/api/workspace", tags=["Workspace — Plantillas de menú"])

    def _org(current_user: dict) -> str:
        org_id = current_user.get("organization_id")
        if not org_id:
            raise HTTPException(403, "Tu cuenta no está asociada a un negocio.")
        return org_id

    async def _owned(template_id: str, org_id: str) -> dict:
        template = await db.menu_templates.find_one({"id": template_id, "org_id": org_id}, {"_id": 0})
        if not template:
            raise HTTPException(404, "Plantilla no encontrada")
        return template

    @router.get("/menu-templates", summary="Tus plantillas de menú")
    async def list_templates(current_user: dict = Depends(get_current_user)):
        org_id = _org(current_user)
        rows = await db.menu_templates.find({"org_id": org_id}, {"_id": 0}).to_list(MAX_TEMPLATES_PER_ORG)
        rows.sort(key=lambda row: row.get("updated_at") or row.get("created_at") or datetime.min,
                  reverse=True)
        return [{
            "id": row["id"],
            "name": row.get("name"),
            "background_url": row.get("background_url"),
            "width": row.get("width"),
            "height": row.get("height"),
            "texts": sum(1 for f in (row.get("fields") or []) if f.get("kind") != "photo"),
            "photos": sum(1 for f in (row.get("fields") or []) if f.get("kind") == "photo"),
            "updated_at": row.get("updated_at"),
        } for row in rows]

    @router.post("/menu-templates/{template_id}/use",
                 summary="Armar un menú nuevo desde una plantilla")
    async def use_template(template_id: str, payload: TemplateUse,
                           current_user: dict = Depends(get_current_user)):
        org_id = _org(current_user)
        template = await _owned(template_id, org_id)
        now = datetime.utcnow()
        menu_id = str(_uuid.uuid4())
        await db.menus.insert_one({
            "id": menu_id,
            "org_id": org_id,
            "name": (payload.name or f"{template.get('name')} (copia)")[:120],
            "description": "",
            "items": [],
            "status": "draft",
            "screen_ids": [],
            "layout_mode": "canvas",
            "canvas": {
                "background_url": template["background_url"],
                "background_media_id": template.get("background_media_id"),
                "width": template["width"],
                "height": template["height"],
                "fields": _copy_fields(template.get("fields")),
                "analysis": {"status": "ready", "error": None,
                             "detected": len(template.get("fields") or []),
                             "finished_at": now},
                "from_template_id": template_id,
                "updated_at": now,
            },
            "created_by_user_id": current_user["id"],
            "created_at": now,
            "updated_at": now,
        })
        return {"menu_id": menu_id, "template_id": template_id}

    @router.put("/menu-templates/{template_id}", summary="Renombrar una plantilla")
    async def rename_template(template_id: str, payload: TemplateRename,
                              current_user: dict = Depends(get_current_user)):
        org_id = _org(current_user)
        await _owned(template_id, org_id)
        await db.menu_templates.update_one({"id": template_id}, {"$set": {
            "name": payload.name.strip()[:80], "updated_at": datetime.utcnow(),
        }})
        return {"id": template_id, "name": payload.name.strip()[:80]}

    @router.delete("/menu-templates/{template_id}", summary="Borrar una plantilla")
    async def delete_template(template_id: str, current_user: dict = Depends(get_current_user)):
        org_id = _org(current_user)
        await _owned(template_id, org_id)
        # Los menús ya armados desde esta plantilla tienen su propia copia, así
        # que borrar la plantilla no los toca.
        await db.menu_templates.delete_one({"id": template_id})
        return {"deleted": template_id}

    return router
