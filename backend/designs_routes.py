"""designs_routes.py — biblioteca de plantillas profesionales y «Mis diseños».

Separación que hace que esto escale: la PLANTILLA es un JSON del catálogo de
MediaView (`signage_templates`, sembrado desde `seed_templates/*.json`), el
DISEÑO es la instancia del cliente (`designs`: qué plantilla + qué contenido), y
el render lo genera un único motor. Una plantilla nueva es un JSON nuevo.

Los productos viven dentro del diseño con un id estable, así que el motor ya
lee por referencia: cuando `products` sea una colección propia (F2), sólo
cambia de dónde se resuelve el índice, no el motor ni las plantillas.
"""
from __future__ import annotations

import json
import logging
import os
import uuid as _uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from template_engine import editor_schema, render_design

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent / "seed_templates"
SAMPLE_PHOTOS_DIR = "/api/static/template-samples"


class DesignCreate(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=80)
    name: str | None = Field(default=None, max_length=120)


class DesignPreviewPatch(BaseModel):
    """Lo que el dueño está escribiendo ahora mismo, todavía sin guardar."""
    brand: dict | None = None
    bindings: dict | None = None
    products: dict | None = None


class DesignPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    brand: dict | None = None
    bindings: dict | None = None
    overrides: dict | None = None


def _sample_photo(industry: str, key: str) -> str:
    """Foto genérica del rubro, que el cliente reemplaza por la suya.

    Se sirve como archivo estático versionado con la app: así una plantilla
    recién sembrada ya se ve con producto real y el cliente entiende qué va en
    cada hueco antes de subir nada.
    """
    return f"{SAMPLE_PHOTOS_DIR}/{industry}/{key}.jpg"


def _materialise_sample(template: dict) -> tuple[dict, dict[str, dict]]:
    """Convierte el `sample` de la plantilla en bindings + índice de productos."""
    sample = template.get("sample") or {}
    industry = str(template.get("industry") or "generic")
    products: dict[str, dict] = {}
    categories = []
    for category in sample.get("categories") or []:
        ids = []
        for item in category.get("products") or []:
            key = str(item.get("key") or _uuid.uuid4())
            product_id = f"{template['id']}:{key}"
            products[product_id] = {
                **item,
                "id": product_id,
                "image_url": item.get("image_url") or _sample_photo(industry, key),
            }
            ids.append(product_id)
        categories.append({"name": category.get("name"), "product_ids": ids})
    # Todo texto suelto de la muestra pasa a bindings tal cual: así una
    # plantilla nueva que use `hours` o `address` no necesita tocar este código.
    bindings = {key: value for key, value in sample.items()
                if isinstance(value, (str, int, float)) and key != "business_name"}
    bindings["categories"] = categories
    brand = {"business_name": sample.get("business_name", ""), "logo_url": None}
    return {"brand": brand, "bindings": bindings}, products


async def seed_signage_templates(db) -> int:
    """Carga el catálogo desde el repo. Idempotente: se corre en cada arranque.

    El catálogo es de MediaView, no del cliente, así que vive versionado en
    `seed_templates/*.json` y se despliega solo. Nadie edita plantillas a mano
    en la base.
    """
    if not SEED_DIR.is_dir():
        return 0
    loaded = 0
    index: dict[str, dict] = {}
    for path in sorted(SEED_DIR.glob("*.json")):
        try:
            for template in json.loads(path.read_text()):
                index[template["id"]] = template
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.error("Bad template seed %s: %s", path.name, exc)
    for template_id, template in index.items():
        inherit = template.pop("sample_from", None)
        if inherit and inherit in index:
            template["sample"] = index[inherit].get("sample")
        await db.signage_templates.update_one(
            {"id": template_id},
            {"$set": {**template, "updated_at": datetime.utcnow()},
             "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True,
        )
        loaded += 1
    logger.info("✓ %d plantillas profesionales en el catálogo", loaded)
    return loaded


def create_designs_routes(db, get_current_user, bump_playlist_version=None):
    router = APIRouter(prefix="/api", tags=["Plantillas profesionales"])

    def _org(current_user: dict) -> str:
        org_id = current_user.get("organization_id")
        if not org_id:
            raise HTTPException(403, "Tu cuenta no está asociada a un negocio.")
        return org_id

    async def _owned_design(design_id: str, org_id: str) -> dict:
        design = await db.designs.find_one({"id": design_id, "org_id": org_id}, {"_id": 0})
        if not design:
            raise HTTPException(404, "Diseño no encontrado")
        return design

    async def _template(template_id: str) -> dict:
        template = await db.signage_templates.find_one({"id": template_id}, {"_id": 0})
        if not template:
            raise HTTPException(404, "Plantilla no encontrada")
        return template

    # ── Catálogo ──────────────────────────────────────────────────────────
    @router.get("/workspace/signage-templates", summary="Catálogo de plantillas profesionales")
    async def list_signage_templates(industry: str = "", kind: str = "",
                                     orientation: str = "",
                                     current_user: dict = Depends(get_current_user)):
        _org(current_user)
        query: dict = {}
        if industry:
            query["industry"] = industry[:40]
        if kind in ("menu_board", "flash_offer"):
            query["kind"] = kind
        if orientation in ("landscape", "portrait"):
            query["canvas.orientation"] = orientation
        rows = await db.signage_templates.find(query, {"_id": 0}).to_list(400)
        return [{
            "id": row["id"], "name": row.get("name"), "tagline": row.get("tagline"),
            "kind": row.get("kind"), "industry": row.get("industry"),
            "orientation": (row.get("canvas") or {}).get("orientation"),
            "products": (row.get("capacity") or {}).get("products"),
            "animated": bool(row.get("animated")),
            "preview_url": f"/api/signage-templates/{row['id']}/preview",
        } for row in rows]

    @router.get("/workspace/signage-industries", summary="Rubros con plantillas disponibles")
    async def list_industries(current_user: dict = Depends(get_current_user)):
        _org(current_user)
        rows = await db.signage_templates.find({}, {"_id": 0, "industry": 1, "kind": 1}).to_list(400)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.get("industry") or "generic"] = counts.get(row.get("industry") or "generic", 0) + 1
        return sorted(({"industry": key, "templates": value} for key, value in counts.items()),
                      key=lambda row: -row["templates"])

    @router.get("/signage-templates/{template_id}/preview", response_class=HTMLResponse,
                summary="Vista previa de la plantilla con contenido de muestra")
    async def preview_template(template_id: str):
        """Pública a propósito: es el catálogo de MediaView con contenido de
        muestra, no datos de ningún cliente."""
        template = await _template(template_id)
        design, products = _materialise_sample(template)
        return HTMLResponse(render_design({**design, "name": template.get("name")},
                                          template, products),
                            headers={"Cache-Control": "public, max-age=300"})

    # ── Mis diseños ───────────────────────────────────────────────────────
    @router.post("/workspace/designs", summary="Usar una plantilla profesional")
    async def create_design(payload: DesignCreate, current_user: dict = Depends(get_current_user)):
        org_id = _org(current_user)
        template = await _template(payload.template_id)
        seed, products = _materialise_sample(template)
        now = datetime.utcnow()
        design_id = str(_uuid.uuid4())
        await db.designs.insert_one({
            "id": design_id,
            "org_id": org_id,
            "template_id": template["id"],
            "name": (payload.name or template.get("name") or "Mi diseño")[:120],
            "brand": seed["brand"],
            "bindings": seed["bindings"],
            "products": products,     # contenido de muestra, listo para reemplazar
            "overrides": {},
            "status": "draft",
            "screen_ids": [],
            "created_by_user_id": current_user["id"],
            "created_at": now,
            "updated_at": now,
        })
        return {"design_id": design_id, "template_id": template["id"]}

    @router.get("/workspace/designs", summary="Mis diseños")
    async def list_designs(current_user: dict = Depends(get_current_user)):
        org_id = _org(current_user)
        rows = await db.designs.find(
            {"org_id": org_id},
            {"_id": 0, "id": 1, "name": 1, "template_id": 1, "status": 1,
             "screen_ids": 1, "updated_at": 1},
        ).to_list(200)
        rows.sort(key=lambda row: row.get("updated_at") or datetime.min, reverse=True)
        return rows

    @router.get("/workspace/designs/{design_id}", summary="Contenido editable de un diseño")
    async def get_design(design_id: str, current_user: dict = Depends(get_current_user)):
        design = await _owned_design(design_id, _org(current_user))
        template = await _template(design["template_id"])
        return {"design": design, "template": {
            "id": template["id"], "name": template.get("name"),
            "canvas": template.get("canvas"), "capacity": template.get("capacity"),
            "theme": template.get("theme"),
        }, "editor": editor_schema(template)}

    @router.put("/workspace/designs/{design_id}", summary="Guardar contenido del diseño")
    async def update_design(design_id: str, payload: DesignPatch,
                            current_user: dict = Depends(get_current_user)):
        org_id = _org(current_user)
        design = await _owned_design(design_id, org_id)
        update: dict = {"updated_at": datetime.utcnow()}
        if payload.name:
            update["name"] = payload.name.strip()[:120]
        if payload.brand is not None:
            update["brand"] = payload.brand
        if payload.bindings is not None:
            update["bindings"] = payload.bindings
        if payload.overrides is not None:
            # Sólo el tema es negociable: la geometría profesional no se toca.
            update["overrides"] = {key: value for key, value in payload.overrides.items()
                                   if str(key).startswith("theme.")}
        await db.designs.update_one({"id": design_id}, {"$set": update})
        if bump_playlist_version:
            for screen_id in design.get("screen_ids") or []:
                await bump_playlist_version(screen_id, reason="design edited")
        return {**design, **update}

    @router.post("/workspace/designs/{design_id}/preview", response_class=HTMLResponse,
                 summary="Vista previa de lo que estoy escribiendo, sin guardar")
    async def preview_design_draft(design_id: str, payload: DesignPreviewPatch,
                                   current_user: dict = Depends(get_current_user)):
        """El mismo render que ve el TV, pero con los valores del borrador.

        Sin esto el dueño tiene que guardar para enterarse de si el precio le
        entra en la tarjeta. Y guardar, en un diseño en vivo, es mandarlo al
        TV: la vista previa NO toca la base ni el playlist.
        """
        design = await _owned_design(design_id, _org(current_user))
        template = await _template(design["template_id"])
        draft = dict(design)
        if payload.brand:
            draft["brand"] = {**(design.get("brand") or {}), **payload.brand}
        if payload.bindings:
            draft["bindings"] = {**(design.get("bindings") or {}), **payload.bindings}
        products = dict(design.get("products") or {})
        for product_id, patch in (payload.products or {}).items():
            current = products.get(str(product_id))
            if current and isinstance(patch, dict):
                products[str(product_id)] = {**current, **patch}
        return HTMLResponse(render_design(draft, template, products),
                            headers={"Cache-Control": "no-store"})

    @router.put("/workspace/designs/{design_id}/products/{product_id}",
                summary="Cambiar nombre, precio o foto de un producto del diseño")
    async def update_design_product(design_id: str, product_id: str, patch: dict,
                                    current_user: dict = Depends(get_current_user)):
        org_id = _org(current_user)
        design = await _owned_design(design_id, org_id)
        product = (design.get("products") or {}).get(product_id)
        if not product:
            raise HTTPException(404, "Producto no encontrado en este diseño")
        allowed = ("name", "description", "price", "sale_price", "variants",
                   "image_url", "video_url", "available", "featured", "badge")
        merged = {**product, **{k: v for k, v in patch.items() if k in allowed}}
        await db.designs.update_one({"id": design_id}, {"$set": {
            f"products.{product_id}": merged, "updated_at": datetime.utcnow(),
        }})
        if bump_playlist_version:
            for screen_id in design.get("screen_ids") or []:
                await bump_playlist_version(screen_id, reason="design product edited")
        return merged

    @router.post("/workspace/designs/{design_id}/products/{product_id}/photo",
                 summary="Subir la foto real de un producto")
    async def upload_design_photo(design_id: str, product_id: str, payload: dict,
                                  current_user: dict = Depends(get_current_user)):
        """La foto del cliente reemplaza la genérica del rubro.

        Se recorta al aspecto del hueco que la plantilla ya reserva, así la
        composición profesional no se deforma con una foto vertical.
        """
        from menu_canvas_routes import _decode, _store_image
        org_id = _org(current_user)
        design = await _owned_design(design_id, org_id)
        if product_id not in (design.get("products") or {}):
            raise HTTPException(404, "Producto no encontrado en este diseño")
        mime = str(payload.get("content_type") or "image/jpeg").lower().split(";")[0]
        if mime not in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
            raise HTTPException(400, "Formato no soportado. Usá JPG, PNG o WebP.")
        data = _decode(str(payload.get("image_base64") or ""), 10 * 1024 * 1024)

        import io
        from PIL import Image
        try:
            picture = Image.open(io.BytesIO(data))
            picture.load()
        except Exception:
            raise HTTPException(400, "No pudimos abrir esa foto. Probá con otra.")
        picture = picture.convert("RGB")
        target = 4 / 3  # el hueco de foto de las tarjetas
        source = picture.width / picture.height
        if source > target:
            new_w = round(picture.height * target)
            left = (picture.width - new_w) // 2
            picture = picture.crop((left, 0, left + new_w, picture.height))
        elif source < target:
            new_h = round(picture.width / target)
            top = (picture.height - new_h) // 2
            picture = picture.crop((0, top, picture.width, top + new_h))
        if picture.width > 900:
            picture = picture.resize((900, round(900 / target)), Image.LANCZOS)
        buffer = io.BytesIO()
        picture.save(buffer, format="JPEG", quality=86, optimize=True)
        _media_id, url = await _store_image(db, current_user["id"], buffer.getvalue(),
                                            "image/jpeg", f"design-{product_id[:12]}.jpg")
        merged = {**design["products"][product_id], "image_url": url}
        await db.designs.update_one({"id": design_id}, {"$set": {
            f"products.{product_id}": merged, "updated_at": datetime.utcnow()}})
        if bump_playlist_version:
            for screen_id in design.get("screen_ids") or []:
                await bump_playlist_version(screen_id, reason="design photo changed")
        return merged

    @router.post("/workspace/designs/{design_id}/categories/{index}/products",
                 summary="Agregar un producto a una sección del diseño")
    async def add_design_product(design_id: str, index: int, payload: dict | None = None,
                                 current_user: dict = Depends(get_current_user)):
        """Un producto más en esa sección, vacío y listo para escribirle encima."""
        org_id = _org(current_user)
        design = await _owned_design(design_id, org_id)
        categories = list((design.get("bindings") or {}).get("categories") or [])
        if index < 0 or index >= len(categories):
            raise HTTPException(404, "Esa sección no existe en este diseño")
        products = design.get("products") or {}
        if len(products) >= 120:
            raise HTTPException(400, "Demasiados productos en este diseño.")
        data = payload or {}
        product_id = f"{design['template_id']}:new-{_uuid.uuid4().hex[:8]}"
        product = {
            "id": product_id,
            "name": str(data.get("name") or "Producto nuevo")[:120],
            "description": str(data.get("description") or "")[:400],
            "price": data.get("price"),
            "image_url": None,
            "available": True,
        }
        categories[index]["product_ids"] = list(categories[index].get("product_ids") or []) + [product_id]
        await db.designs.update_one({"id": design_id}, {"$set": {
            f"products.{product_id}": product,
            "bindings.categories": categories,
            "updated_at": datetime.utcnow(),
        }})
        if bump_playlist_version:
            for screen_id in design.get("screen_ids") or []:
                await bump_playlist_version(screen_id, reason="design product added")
        return product

    @router.delete("/workspace/designs/{design_id}/products/{product_id}",
                   summary="Quitar un producto del diseño")
    async def delete_design_product(design_id: str, product_id: str,
                                    current_user: dict = Depends(get_current_user)):
        org_id = _org(current_user)
        design = await _owned_design(design_id, org_id)
        if product_id not in (design.get("products") or {}):
            raise HTTPException(404, "Producto no encontrado en este diseño")
        categories = [
            {**category,
             "product_ids": [pid for pid in (category.get("product_ids") or []) if pid != product_id]}
            for category in ((design.get("bindings") or {}).get("categories") or [])
        ]
        await db.designs.update_one({"id": design_id}, {
            "$unset": {f"products.{product_id}": ""},
            "$set": {"bindings.categories": categories, "updated_at": datetime.utcnow()},
        })
        if bump_playlist_version:
            for screen_id in design.get("screen_ids") or []:
                await bump_playlist_version(screen_id, reason="design product removed")
        return {"deleted": product_id}

    @router.post("/workspace/designs/{design_id}/logo", summary="Subir el logo del negocio")
    async def upload_design_logo(design_id: str, payload: dict,
                                 current_user: dict = Depends(get_current_user)):
        """El logo va sin recortar: un logo recortado es un logo arruinado.

        Se guarda en PNG para no perder la transparencia, que es lo que hace
        que se vea apoyado sobre el fondo de la plantilla y no en una caja.
        """
        import io
        from PIL import Image

        from menu_canvas_routes import _decode, _store_image
        org_id = _org(current_user)
        design = await _owned_design(design_id, org_id)
        mime = str(payload.get("content_type") or "image/png").lower().split(";")[0]
        if mime not in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
            raise HTTPException(400, "Formato no soportado. Usá PNG, JPG o WebP.")
        data = _decode(str(payload.get("image_base64") or ""), 6 * 1024 * 1024)
        try:
            picture = Image.open(io.BytesIO(data))
            picture.load()
        except Exception:
            raise HTTPException(400, "No pudimos abrir ese logo. Probá con otro.")
        picture = picture.convert("RGBA")
        if picture.height > 400:
            picture = picture.resize(
                (max(1, round(picture.width * 400 / picture.height)), 400), Image.LANCZOS)
        buffer = io.BytesIO()
        picture.save(buffer, format="PNG", optimize=True)
        _media_id, url = await _store_image(db, current_user["id"], buffer.getvalue(),
                                            "image/png", f"logo-{design_id[:8]}.png")
        brand = {**(design.get("brand") or {}), "logo_url": url}
        await db.designs.update_one({"id": design_id}, {"$set": {
            "brand": brand, "updated_at": datetime.utcnow()}})
        if bump_playlist_version:
            for screen_id in design.get("screen_ids") or []:
                await bump_playlist_version(screen_id, reason="design logo changed")
        return brand

    @router.delete("/workspace/designs/{design_id}", summary="Borrar un diseño")
    async def delete_design(design_id: str, current_user: dict = Depends(get_current_user)):
        org_id = _org(current_user)
        design = await _owned_design(design_id, org_id)
        await db.playlists.delete_many({"org_id": org_id, "source_design_id": design_id})
        if bump_playlist_version:
            for screen_id in design.get("screen_ids") or []:
                await bump_playlist_version(screen_id, reason="design deleted")
        await db.designs.delete_one({"id": design_id})
        return {"deleted": design_id}

    @router.post("/workspace/designs/{design_id}/publish",
                 summary="Publicar el diseño en pantallas")
    async def publish_design(design_id: str, data: dict,
                             current_user: dict = Depends(get_current_user)):
        """Mismo camino que los menús: el diseño viaja dentro de un playlist.

        Así hereda gratis los horarios, la prioridad y el versionado que ya
        existen, y el reproductor Android no necesita ningún cambio.
        """
        org_id = _org(current_user)
        design = await _owned_design(design_id, org_id)
        requested = [str(sid) for sid in (data.get("screen_ids") or [])][:60]
        if not requested:
            raise HTTPException(400, "Elegí al menos una pantalla.")
        owned = {row["id"] for row in await db.screens.find(
            {"organization_id": org_id}, {"_id": 0, "id": 1}).to_list(200)}
        unknown = [sid for sid in requested if sid not in owned]
        if unknown:
            raise HTTPException(404, "Alguna de esas pantallas no es tuya.")

        now = datetime.utcnow()
        await db.designs.update_one({"id": design_id}, {"$set": {
            "status": "published", "screen_ids": requested, "updated_at": now,
        }})
        design["updated_at"] = now
        item = {**design_playlist_item(design), "id": str(_uuid.uuid4()),
                "type": "design", "ref_id": design_id, "order": 0,
                "duration": int(data.get("duration") or 60),
                "transition": "fade", "display_mode": "cover"}
        existing = await db.playlists.find_one({"org_id": org_id, "source_design_id": design_id})
        payload = {
            "name": f"{design.get('name')} — pantalla",
            "items": [{"id": item["id"], "type": "design", "ref_id": design_id, "order": 0,
                       "duration": item["duration"], "transition": "fade",
                       "display_mode": "cover", "title": design.get("name")}],
            "screen_ids": requested,
            "allowed_screen_ids": sorted(owned),
            "status": "published",
            "priority": 10,
            "published_at": now,
            "published_by_user_id": current_user["id"],
            "updated_at": now,
        }
        if existing:
            await db.playlists.update_one({"id": existing["id"]}, {
                "$set": payload, "$inc": {"version": 1}})
        else:
            await db.playlists.insert_one({
                **payload, "id": str(_uuid.uuid4()), "org_id": org_id,
                "source_design_id": design_id, "description": "Playlist generada por el diseño",
                "created_by_user_id": current_user["id"], "owner_user_id": current_user["id"],
                "client_user_id": current_user["id"], "management_mode": "client",
                "allow_client_publish": True, "schedule": None, "version": 1,
                "pending_items": [], "created_at": now,
            })
        if bump_playlist_version:
            for screen_id in set((design.get("screen_ids") or []) + requested):
                await bump_playlist_version(screen_id, reason="design published")
        return {"published_to": len(requested), "design_id": design_id}

    @router.get("/designs/{design_id}/render", response_class=HTMLResponse,
                summary="Lo que muestra el TV")
    async def render(design_id: str, preview: str = ""):
        design = await db.designs.find_one({"id": design_id}, {"_id": 0})
        if not design:
            raise HTTPException(404, "Diseño no encontrado")
        template = await _template(design["template_id"])
        html = render_design(design, template, design.get("products") or {})
        return HTMLResponse(html, headers={"Cache-Control": "no-store, must-revalidate"})

    return router


def design_playlist_item(design: dict) -> dict:
    """Ítem de playlist para un diseño, con la misma forma que espera el APK.

    El `checksum` lleva la última edición: es lo que hace que el player recargue
    el WebView cuando cambia un precio (compara
    `media_id:checksum:duration:rotation:display_mode`).
    """
    import hashlib
    edited = design.get("updated_at")
    stamp = edited.isoformat() if edited else ""
    url = f"/api/designs/{design['id']}/render"
    if edited:
        url += f"?v={int(edited.timestamp() * 1000)}"
    return {
        "media_id": f"design:{design['id']}",
        "filename": design.get("name") or "Diseño",
        "content_type": "widget",
        "media_url": url,
        "download_url": url,
        "checksum": hashlib.sha256(f"design:{design['id']}:{stamp}".encode()).hexdigest(),
    }


__all__ = ["create_designs_routes", "seed_signage_templates", "design_playlist_item",
           "SAMPLE_PHOTOS_DIR", "os"]
