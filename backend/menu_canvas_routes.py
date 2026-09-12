"""menu_canvas_routes.py — «Menú editable sobre tu propio diseño».

El restaurante ya tiene su menú diseñado (JPG/PNG/PDF). En vez de redibujarlo
con una plantilla nuestra, lo usamos TAL CUAL como fondo y la IA detecta dónde
está cada nombre, cada precio y cada foto. Cada hallazgo se convierte en un
campo editable posicionado encima del diseño original, respetando el color y el
tamaño de letra que ya tenía. El usuario cambia un precio desde el celular y el
TV lo muestra sin que el diseño se mueva un pixel.

Piezas clave:
  · import  → normaliza el archivo a PNG, lo guarda y pide a la IA el layout.
  · El color de fondo de cada caja de texto NO lo pregunta a la IA: se muestrea
    con Pillow del anillo de pixeles alrededor de la caja. Es lo que tapa el
    texto original impreso en el diseño, así que tiene que ser exacto.
  · Coordenadas en pixeles del diseño original. El render escala todo el
    escenario con un único transform, así el resultado es idéntico en 1080p,
    4K o en la vista previa del celular.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import logging
import os
import re
import uuid as _uuid
from collections import Counter
from datetime import datetime

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, ImageFont
from pydantic import BaseModel, Field

from managed_portal_routes import create_audit_log as _audit

load_dotenv()

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
LAYOUT_PROVIDER = "gemini"
LAYOUT_MODEL = "gemini-3.1-pro-preview"
MEDIA_DIR = os.environ.get("MEDIA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "media"))

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PHOTO_BYTES = 10 * 1024 * 1024
# Downscale before sending to the model: big enough to read small print, small
# enough to keep the request fast. Coordinates come back normalised so the
# resize is invisible to the caller.
MAX_ANALYSIS_SIDE = 1600
# The stage the TV renders. Anything bigger wastes bandwidth on a 4K panel that
# upscales fine anyway.
MAX_STAGE_SIDE = 2400
MAX_FIELDS = 160

IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
PDF_TYPES = {"application/pdf"}

SYSTEM_PROMPT = (
    "Eres un motor de análisis de layout de menús de restaurante. "
    "Devuelves EXCLUSIVAMENTE JSON válido, sin texto adicional y sin bloques de código."
)

LAYOUT_PROMPT = """Esta imagen es un menú de restaurante ya diseñado.

Tu tarea: localizar cada elemento EDITABLE y devolver su caja delimitadora.

Tipos de elemento:
- "name": el nombre de un producto o el título de una sección/categoría.
- "price": un número de precio (con o sin símbolo de moneda).
- "photo": una fotografía o ilustración de un producto.

Responde SOLO con este JSON:
{
  "fields": [
    {
      "kind": "name",
      "text": "el texto exacto tal como se lee, vacío si es photo",
      "box": [ymin, xmin, ymax, xmax],
      "color": "#RRGGBB",
      "font_weight": 700,
      "font_family": "sans",
      "italic": false,
      "uppercase": false,
      "align": "left",
      "radius": 0
    }
  ]
}

Reglas estrictas:
- box en enteros 0-1000 normalizados sobre la imagen: ymin/ymax verticales, xmin/xmax horizontales.
- La caja debe ceñirse al texto, no a la fila completa: desde el primer glifo hasta el último.
- Un campo por cada texto. NO agrupes el nombre y el precio en una sola caja.
- "color" es el color del texto, no del fondo. Estímalo del glifo.
- "font_family": "sans", "serif" o "script" según lo que veas.
- "align": "left", "center" o "right" según cómo esté alineado dentro de su columna.
- "radius": solo para photo, 0-50 = redondeo de esquinas en porcentaje (50 = círculo).
- Ignora logos, direcciones, teléfonos, redes sociales y textos decorativos que no sean nombre de producto ni precio.
- Si la imagen no es un menú, devuelve fields como lista vacía."""


class CanvasImport(BaseModel):
    file_base64: str = Field(..., min_length=32)
    content_type: str = "image/png"


class CanvasFieldPhoto(BaseModel):
    image_base64: str = Field(..., min_length=32)
    content_type: str = "image/jpeg"


class CanvasFields(BaseModel):
    fields: list[dict]


def _decode(raw: str, limit: int) -> bytes:
    payload = raw.strip()
    if payload.startswith("data:"):
        payload = payload.split(",", 1)[-1]
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "El archivo no se pudo leer. Volvé a subirlo.")
    if not data:
        raise HTTPException(400, "El archivo llegó vacío.")
    if len(data) > limit:
        raise HTTPException(413, f"El archivo es muy grande (máximo {limit // (1024 * 1024)} MB).")
    return data


def _pdf_first_page_to_png(data: bytes) -> bytes:
    try:
        import pymupdf
    except ImportError:
        raise HTTPException(503, "El soporte de PDF no está disponible. Subí el menú como JPG o PNG.")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if not doc.page_count:
                raise HTTPException(400, "El PDF está vacío.")
            page = doc.load_page(0)
            # 2x zoom so small print survives the OCR pass.
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            return pixmap.tobytes("png")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("PDF → PNG failed")
        raise HTTPException(400, f"No pudimos abrir ese PDF: {exc}") from exc


def _normalise_background(data: bytes, content_type: str) -> tuple[bytes, int, int, Image.Image]:
    """Returns (png_bytes, width, height, PIL image) of the stage background."""
    if content_type in PDF_TYPES:
        data = _pdf_first_page_to_png(data)
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:
        raise HTTPException(400, "No pudimos abrir esa imagen. Probá con un JPG o PNG.")
    image = image.convert("RGB")
    if max(image.size) > MAX_STAGE_SIDE:
        ratio = MAX_STAGE_SIDE / max(image.size)
        image = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
                             Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), image.width, image.height, image


def _analysis_copy(image: Image.Image) -> str:
    """Base64 JPEG, downscaled, for the vision call."""
    shrunk = image
    if max(image.size) > MAX_ANALYSIS_SIDE:
        ratio = MAX_ANALYSIS_SIDE / max(image.size)
        shrunk = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
                              Image.LANCZOS)
    buffer = io.BytesIO()
    shrunk.save(buffer, format="JPEG", quality=88)
    return base64.b64encode(buffer.getvalue()).decode()


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", str(text or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(cleaned[start:end + 1])


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Liberation is metric-compatible with Arial / Times New Roman, which is what
# the renderer asks the browser for. Measuring with these locally therefore
# predicts the on-screen width closely enough to reproduce the original design.
_FONT_FILES = {
    ("sans", 400, False): "LiberationSans-Regular.ttf",
    ("sans", 400, True): "LiberationSans-Italic.ttf",
    ("sans", 700, False): "LiberationSans-Bold.ttf",
    ("sans", 700, True): "LiberationSans-BoldItalic.ttf",
    ("serif", 400, False): "LiberationSerif-Regular.ttf",
    ("serif", 400, True): "LiberationSerif-Italic.ttf",
    ("serif", 700, False): "LiberationSerif-Bold.ttf",
    ("serif", 700, True): "LiberationSerif-BoldItalic.ttf",
}
_FONT_DIRS = ("/usr/share/fonts/truetype/liberation",
              "/usr/share/fonts/truetype/liberation2")


def _font_path(family: str, weight: int, italic: bool) -> str | None:
    name = _FONT_FILES.get((family if family in ("sans", "serif") else "sans",
                            700 if weight >= 600 else 400, bool(italic)))
    if not name:
        return None
    for folder in _FONT_DIRS:
        candidate = os.path.join(folder, name)
        if os.path.exists(candidate):
            return candidate
    return None


def _fit_font_size(text: str, box_w: int, box_h: int, family: str,
                   weight: int, italic: bool) -> int:
    """Largest size at which `text` still fits the box the design already has.

    The box came from the printed design, so fitting the ORIGINAL string back
    into it recovers the size the designer used. We then keep that size when
    the owner retypes the price, instead of rescaling and breaking the look.
    """
    fallback = max(8, round(box_h * 1.12))
    path = _font_path(family, weight, italic)
    if not path or not text.strip():
        return fallback
    try:
        low, high, best = 6, max(8, round(box_h * 2.4)), 0
        while low <= high:
            mid = (low + high) // 2
            font = ImageFont.truetype(path, mid)
            left, top, right, bottom = font.getbbox(text)
            if (right - left) <= box_w and (bottom - top) <= box_h * 1.08:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best or fallback
    except OSError:
        return fallback


def _clean_color(value, fallback: str) -> str:
    text = str(value or "").strip()
    if len(text) == 4 and text.startswith("#"):
        text = "#" + "".join(c * 2 for c in text[1:])
    return text.lower() if _HEX.match(text) else fallback


def _sample_background(image: Image.Image, x: int, y: int, w: int, h: int) -> str:
    """Colour of the paper right around a text box.

    This is what paints over the price already printed in the design, so
    guessing it with the model is not good enough — we read the actual pixels
    from a thin ring just outside the box and take the dominant colour.
    """
    pad = max(2, round(min(w, h) * 0.25))
    left, top = max(0, x - pad), max(0, y - pad)
    right, bottom = min(image.width, x + w + pad), min(image.height, y + h + pad)
    if right <= left or bottom <= top:
        return "#ffffff"
    ring = image.crop((left, top, right, bottom))
    pixels: list[tuple[int, int, int]] = []
    rw, rh = ring.size
    band = max(1, pad // 2)
    for ry in range(rh):
        inside_v = band <= ry < rh - band
        for rx in range(rw):
            if inside_v and band <= rx < rw - band:
                continue  # skip the glyphs themselves
            pixels.append(ring.getpixel((rx, ry)))
    if not pixels:
        return "#ffffff"
    # Quantise so antialiasing noise collapses into one bucket.
    buckets = Counter((r // 12, g // 12, b // 12) for r, g, b in pixels)
    (qr, qg, qb), _ = buckets.most_common(1)[0]
    members = [p for p in pixels if (p[0] // 12, p[1] // 12, p[2] // 12) == (qr, qg, qb)]
    r = sum(p[0] for p in members) // len(members)
    g = sum(p[1] for p in members) // len(members)
    b = sum(p[2] for p in members) // len(members)
    return f"#{r:02x}{g:02x}{b:02x}"


def _normalise_fields(raw_fields, image: Image.Image) -> list[dict]:
    width, height = image.size
    fields: list[dict] = []
    for raw in (raw_fields or [])[:MAX_FIELDS]:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "name").lower()
        if kind not in ("name", "price", "photo"):
            continue
        box = raw.get("box") or []
        if not isinstance(box, list) or len(box) != 4:
            continue
        try:
            ymin, xmin, ymax, xmax = (max(0.0, min(1000.0, float(v))) for v in box)
        except (TypeError, ValueError):
            continue
        if ymax <= ymin or xmax <= xmin:
            continue
        x = round(xmin / 1000 * width)
        y = round(ymin / 1000 * height)
        w = max(8, round((xmax - xmin) / 1000 * width))
        h = max(8, round((ymax - ymin) / 1000 * height))
        w = min(w, width - x)
        h = min(h, height - y)
        text = str(raw.get("text") or "").strip()[:200]
        if kind != "photo" and not text:
            continue
        family = str(raw.get("font_family") or "sans").lower()
        align = str(raw.get("align") or "left").lower()
        family = family if family in ("sans", "serif", "script") else "sans"
        weight = 700 if int(raw.get("font_weight") or 400) >= 600 else 400
        italic = bool(raw.get("italic"))
        field = {
            "id": str(_uuid.uuid4()),
            "kind": kind,
            "text": text,
            # Kept so the renderer can leave untouched fields alone: if nobody
            # edited this name, the original pixels of the design are already
            # perfect and painting over them can only make it worse.
            "original_text": text,
            "x": x, "y": y, "w": w, "h": h,
            "color": _clean_color(raw.get("color"), "#111111"),
            "bg_color": "#ffffff",
            "font_family": family,
            "font_weight": weight,
            "font_size": max(8, round(h * 1.1)),
            "italic": italic,
            "uppercase": bool(raw.get("uppercase")),
            "align": align if align in ("left", "center", "right") else "left",
            "radius": max(0, min(50, int(raw.get("radius") or 0))),
            "image_url": None,
            "media_id": None,
        }
        if kind != "photo":
            field["bg_color"] = _sample_background(image, x, y, w, h)
            field["font_size"] = _fit_font_size(
                text.upper() if field["uppercase"] else text, w, h, family, weight, italic)
        fields.append(field)
    return fields


def _sanitise_fields(raw_fields, stage: dict) -> list[dict]:
    """Validates what the editor sends back after dragging / retyping."""
    width = int(stage.get("width") or 1920)
    height = int(stage.get("height") or 1080)
    out: list[dict] = []
    for raw in (raw_fields or [])[:MAX_FIELDS]:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "name").lower()
        if kind not in ("name", "price", "photo"):
            continue
        try:
            x = int(round(float(raw.get("x") or 0)))
            y = int(round(float(raw.get("y") or 0)))
            w = int(round(float(raw.get("w") or 0)))
            h = int(round(float(raw.get("h") or 0)))
        except (TypeError, ValueError):
            continue
        w = max(8, min(w, width))
        h = max(8, min(h, height))
        x = max(0, min(x, width - w))
        y = max(0, min(y, height - h))
        family = str(raw.get("font_family") or "sans").lower()
        align = str(raw.get("align") or "left").lower()
        image_url = str(raw.get("image_url") or "").strip()
        if image_url and not image_url.startswith("/api/"):
            image_url = ""
        out.append({
            "id": str(raw.get("id") or _uuid.uuid4())[:64],
            "kind": kind,
            "text": str(raw.get("text") or "").strip()[:200],
            "original_text": str(raw.get("original_text") or "")[:200],
            "x": x, "y": y, "w": w, "h": h,
            "color": _clean_color(raw.get("color"), "#111111"),
            "bg_color": _clean_color(raw.get("bg_color"), "#ffffff"),
            "font_family": family if family in ("sans", "serif", "script") else "sans",
            "font_weight": 700 if int(raw.get("font_weight") or 400) >= 600 else 400,
            "font_size": max(6, min(600, int(float(raw.get("font_size") or h * 1.1)))),
            "italic": bool(raw.get("italic")),
            "uppercase": bool(raw.get("uppercase")),
            "align": align if align in ("left", "center", "right") else "left",
            "radius": max(0, min(50, int(raw.get("radius") or 0))),
            "image_url": image_url or None,
            "media_id": str(raw.get("media_id") or "")[:64] or None,
        })
    return out


async def _store_image(db, user_id: str, data: bytes, mime: str, filename: str) -> tuple[str, str]:
    """Saves bytes as a media doc served at /api/player/media/{id}."""
    ext = ".jpg" if "jpeg" in mime or "jpg" in mime else ".webp" if "webp" in mime else ".png"
    media_id = str(_uuid.uuid4())
    stored_name = f"{media_id}{ext}"
    os.makedirs(MEDIA_DIR, exist_ok=True)
    with open(os.path.join(MEDIA_DIR, stored_name), "wb") as handle:
        handle.write(data)
    await db.media.insert_one({
        "id": media_id,
        "user_id": user_id,
        "filename": filename[:120],
        "content_type": mime,
        "size": len(data),
        "type": "image",
        "sha256": hashlib.sha256(data).hexdigest(),
        "storage": "legacy",
        "stored_filename": stored_name,
        "data": base64.b64encode(data).decode(),
        "status": "ready",
        "source": "menu_canvas",
        "created_at": datetime.utcnow(),
    })
    return media_id, f"/api/player/media/{media_id}"


def create_menu_canvas_routes(db, get_current_user, bump_playlist_version=None):
    router = APIRouter(prefix="/api/workspace", tags=["Workspace — Menú sobre tu diseño"])

    async def _owned_menu(menu_id: str, current_user: dict) -> dict:
        org_id = current_user.get("organization_id")
        if not org_id:
            raise HTTPException(403, "Tu cuenta no está asociada a un negocio.")
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id}, {"_id": 0})
        if not menu:
            raise HTTPException(404, "Menú no encontrado")
        return menu

    async def _refresh_screens(menu: dict, reason: str) -> None:
        """A canvas edit is a live edit — the TVs showing this menu must refetch."""
        if not bump_playlist_version:
            return
        for screen_id in menu.get("screen_ids") or []:
            await bump_playlist_version(screen_id, reason=reason)

    @router.post("/menus/{menu_id}/canvas/import",
                 summary="Sube tu menú diseñado y la IA lo vuelve editable")
    async def import_canvas(menu_id: str, payload: CanvasImport,
                            current_user: dict = Depends(get_current_user)):
        menu = await _owned_menu(menu_id, current_user)
        if not EMERGENT_LLM_KEY:
            raise HTTPException(503, "La función de IA no está configurada. Contacta a soporte.")

        content_type = (payload.content_type or "image/png").lower().split(";")[0].strip()
        if content_type not in IMAGE_TYPES | PDF_TYPES:
            raise HTTPException(400, "Formato no soportado. Subí tu menú en JPG, PNG o PDF.")

        data = _decode(payload.file_base64, MAX_UPLOAD_BYTES)
        png, width, height, image = _normalise_background(data, content_type)
        slug = re.sub(r"[^\w -]", "", menu.get("name") or "menu")[:40] or "menu"
        media_id, background_url = await _store_image(
            db, current_user["id"], png, "image/png", f"{slug}-diseno.png")

        from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"menu-canvas-{_uuid.uuid4()}",
            system_message=SYSTEM_PROMPT,
        ).with_model(LAYOUT_PROVIDER, LAYOUT_MODEL)

        try:
            answer = await chat.send_message(UserMessage(
                text=LAYOUT_PROMPT,
                file_contents=[ImageContent(image_base64=_analysis_copy(image))],
            ))
        except Exception as exc:
            logger.exception("Menu canvas layout detection failed")
            raise HTTPException(502, f"La IA no pudo analizar el diseño: {exc}") from exc

        try:
            parsed = _extract_json(answer if isinstance(answer, str) else str(answer))
        except (json.JSONDecodeError, ValueError):
            logger.warning("Canvas layout returned non-JSON: %s", str(answer)[:400])
            raise HTTPException(422, "No pudimos leer ese diseño. Probá con una imagen más nítida y de frente.")

        fields = _normalise_fields(parsed.get("fields"), image)
        now = datetime.utcnow()
        canvas = {
            "background_url": background_url,
            "background_media_id": media_id,
            "width": width,
            "height": height,
            "fields": fields,
            "updated_at": now,
        }
        await db.menus.update_one({"id": menu_id}, {"$set": {
            "layout_mode": "canvas",
            "canvas": canvas,
            "updated_at": now,
        }})
        await _refresh_screens(menu, "menu canvas imported")
        await _audit(
            db, "menu.canvas_imported",
            user_id=current_user["id"], user_email=current_user.get("email"),
            resource_type="menu", resource_id=menu_id,
            details={"menu_name": menu.get("name"), "fields": len(fields),
                     "size": f"{width}x{height}"},
            org_id=current_user.get("organization_id"),
        )
        return {"layout_mode": "canvas", "canvas": canvas, "detected": len(fields)}

    @router.get("/menus/{menu_id}/canvas", summary="Layout editable del menú")
    async def get_canvas(menu_id: str, current_user: dict = Depends(get_current_user)):
        menu = await _owned_menu(menu_id, current_user)
        canvas = menu.get("canvas")
        if not canvas:
            raise HTTPException(404, "Este menú todavía no tiene un diseño propio cargado.")
        return {"layout_mode": menu.get("layout_mode") or "template", "canvas": canvas,
                "menu_name": menu.get("name"), "status": menu.get("status")}

    @router.put("/menus/{menu_id}/canvas", summary="Guardar textos y posiciones editadas")
    async def save_canvas(menu_id: str, payload: CanvasFields,
                          current_user: dict = Depends(get_current_user)):
        menu = await _owned_menu(menu_id, current_user)
        canvas = menu.get("canvas")
        if not canvas:
            raise HTTPException(404, "Este menú todavía no tiene un diseño propio cargado.")
        fields = _sanitise_fields(payload.fields, canvas)
        now = datetime.utcnow()
        await db.menus.update_one({"id": menu_id}, {"$set": {
            "canvas.fields": fields,
            "canvas.updated_at": now,
            "updated_at": now,
        }})
        await _refresh_screens(menu, "menu canvas edited")
        return {"fields": fields, "saved": len(fields)}

    @router.post("/menus/{menu_id}/canvas/fields/{field_id}/photo",
                 summary="Reemplazar la foto de un recuadro sin mover el diseño")
    async def replace_field_photo(menu_id: str, field_id: str, payload: CanvasFieldPhoto,
                                  current_user: dict = Depends(get_current_user)):
        menu = await _owned_menu(menu_id, current_user)
        canvas = menu.get("canvas") or {}
        field = next((f for f in (canvas.get("fields") or []) if f.get("id") == field_id), None)
        if not field:
            raise HTTPException(404, "Recuadro no encontrado")

        content_type = (payload.content_type or "image/jpeg").lower().split(";")[0].strip()
        if content_type not in IMAGE_TYPES:
            raise HTTPException(400, "Formato no soportado. Usá JPG, PNG o WebP.")
        data = _decode(payload.image_base64, MAX_PHOTO_BYTES)
        try:
            picture = Image.open(io.BytesIO(data))
            picture.load()
        except Exception:
            raise HTTPException(400, "No pudimos abrir esa foto. Probá con otra.")

        # Fit the new photo to the hole the design already has: centre-crop to
        # the recuadro's aspect ratio so nothing stretches, then downscale to
        # 2x the slot so it stays crisp on a 4K panel without shipping 8 MB.
        box_w = max(1, int(field.get("w") or 1))
        box_h = max(1, int(field.get("h") or 1))
        picture = picture.convert("RGB")
        target = box_w / box_h
        source = picture.width / picture.height
        if source > target:
            new_w = round(picture.height * target)
            offset = (picture.width - new_w) // 2
            picture = picture.crop((offset, 0, offset + new_w, picture.height))
        elif source < target:
            new_h = round(picture.width / target)
            offset = (picture.height - new_h) // 2
            picture = picture.crop((0, offset, picture.width, offset + new_h))
        cap_w, cap_h = box_w * 2, box_h * 2
        if picture.width > cap_w:
            picture = picture.resize((cap_w, max(1, cap_h)), Image.LANCZOS)
        buffer = io.BytesIO()
        picture.save(buffer, format="JPEG", quality=88)

        media_id, image_url = await _store_image(
            db, current_user["id"], buffer.getvalue(), "image/jpeg", f"menu-foto-{field_id[:8]}.jpg")
        now = datetime.utcnow()
        await db.menus.update_one(
            {"id": menu_id, "canvas.fields.id": field_id},
            {"$set": {
                "canvas.fields.$.image_url": image_url,
                "canvas.fields.$.media_id": media_id,
                "canvas.updated_at": now,
                "updated_at": now,
            }},
        )
        await _refresh_screens(menu, "menu canvas photo replaced")
        return {"field_id": field_id, "media_id": media_id, "image_url": image_url,
                "fitted_to": f"{box_w}x{box_h}"}

    @router.delete("/menus/{menu_id}/canvas", summary="Volver a la plantilla de MediaView")
    async def drop_canvas(menu_id: str, current_user: dict = Depends(get_current_user)):
        menu = await _owned_menu(menu_id, current_user)
        await db.menus.update_one({"id": menu_id}, {"$set": {
            "layout_mode": "template",
            "updated_at": datetime.utcnow(),
        }, "$unset": {"canvas": ""}})
        await _refresh_screens(menu, "menu canvas removed")
        return {"layout_mode": "template"}

    return router
