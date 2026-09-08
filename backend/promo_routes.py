"""
promo_routes.py — "Promo Instantánea": el dueño lanza una promoción a todas sus
pantallas con un solo toque desde el celular.

Una promo es una playlist normal con prioridad alta (90) y, opcionalmente,
`expires_at`. El motor de playlists ya elige la de mayor prioridad, así que la
promo tapa el contenido normal y al expirar todo vuelve solo.

Dos tipos:
  • image → usa una foto de la biblioteca del negocio
  • text  → se genera una tarjeta con el mensaje (Pillow) y se guarda como media
"""
from __future__ import annotations

import hashlib
import io
import os
import uuid as _uuid
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from managed_portal_routes import create_audit_log as _audit
from rbac import Role, get_effective_role

MEDIA_DIR = os.environ.get("MEDIA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "media"))
PROMO_PRIORITY = 90
NAVY = (15, 23, 42)
CYAN = (6, 182, 212)
WHITE = (255, 255, 255)
ALLOWED_DURATIONS = {15, 60, 240, 480}


class PromoCreate(BaseModel):
    kind: Literal["image", "text"] = "text"
    text: Optional[str] = Field(None, max_length=120)
    subtitle: Optional[str] = Field(None, max_length=160)
    media_id: Optional[str] = None
    duration_minutes: Optional[int] = None  # None = hasta que la apague
    screen_ids: list[str] = []
    item_seconds: int = 12


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:4]


def render_promo_card(text: str, subtitle: str | None) -> bytes:
    """1920x1080 promo card in MediaView colours."""
    width, height = 1920, 1080
    img = Image.new("RGB", (width, height), NAVY)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, 14], fill=CYAN)
    draw.rectangle([0, height - 14, width, height], fill=CYAN)

    title_font = _font(150)
    lines = _wrap(draw, text.upper(), title_font, width - 260)
    while len(lines) > 2 and title_font.size > 90:
        title_font = _font(title_font.size - 20)
        lines = _wrap(draw, text.upper(), title_font, width - 260)

    line_height = int(title_font.size * 1.18)
    sub_font = _font(58)
    sub_lines = _wrap(draw, subtitle, sub_font, width - 320) if subtitle else []
    block = line_height * len(lines) + (len(sub_lines) * 74 + 50 if sub_lines else 0)
    y = (height - block) // 2

    for line in lines:
        draw.text(((width - draw.textlength(line, font=title_font)) / 2, y), line, font=title_font, fill=WHITE)
        y += line_height

    if sub_lines:
        y += 40
        for line in sub_lines:
            draw.text(((width - draw.textlength(line, font=sub_font)) / 2, y), line, font=sub_font, fill=CYAN)
            y += 74

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


def create_promo_routes(db, get_current_user, bump_playlist_version=None):
    router = APIRouter(prefix="/api/workspace", tags=["Workspace — Promo Instantánea"])

    async def require_promo_user(current_user: dict = Depends(get_current_user)):
        if get_effective_role(current_user) not in (
            Role.SELF_SERVICE_OWNER, Role.SELF_SERVICE_MANAGER, Role.SELF_SERVICE_STAFF,
        ):
            raise HTTPException(403, "Tu cuenta no tiene acceso al panel del negocio.")
        if not current_user.get("organization_id"):
            raise HTTPException(403, "Tu cuenta no está asociada a un negocio.")
        if current_user.get("must_change_password"):
            raise HTTPException(428, "Debes crear tu propia contraseña antes de continuar.")
        return current_user

    async def _org_screen_ids(org_id: str) -> list[str]:
        return [s["id"] for s in await db.screens.find({"organization_id": org_id}, {"id": 1}).to_list(500)]

    def _public(promo: dict) -> dict:
        expires = promo.get("expires_at")
        remaining = None
        if expires:
            remaining = max(0, int((expires - datetime.utcnow()).total_seconds()))
        return {
            "id": promo["id"],
            "name": promo.get("name"),
            "kind": promo.get("promo_kind", "text"),
            "text": promo.get("promo_text"),
            "screen_ids": promo.get("screen_ids") or [],
            "expires_at": expires.isoformat() if isinstance(expires, datetime) else expires,
            "seconds_remaining": remaining,
            "created_at": promo["created_at"].isoformat() if isinstance(promo.get("created_at"), datetime) else None,
        }

    @router.get("/promos/active", summary="Promos currently on air")
    async def active_promos(current_user: dict = Depends(require_promo_user)):
        now = datetime.utcnow()
        promos = await db.playlists.find({
            "org_id": current_user["organization_id"],
            "is_promo": True,
            "status": "published",
            "$or": [{"expires_at": None}, {"expires_at": {"$exists": False}}, {"expires_at": {"$gt": now}}],
        }, {"_id": 0}).sort("created_at", -1).to_list(20)
        return [_public(p) for p in promos]

    @router.post("/promos", summary="Launch an instant promo to every screen", status_code=201)
    async def launch_promo(data: PromoCreate, current_user: dict = Depends(require_promo_user)):
        org_id = current_user["organization_id"]
        org_screens = await _org_screen_ids(org_id)
        if not org_screens:
            raise HTTPException(400, "Conecta una pantalla antes de lanzar una promo.")
        screen_ids = [s for s in data.screen_ids if s in org_screens] or org_screens

        now = datetime.utcnow()
        if data.kind == "image":
            if not data.media_id:
                raise HTTPException(400, "Elige una foto para la promo.")
            org_user_ids = [u["id"] for u in await db.users.find({"organization_id": org_id}, {"id": 1}).to_list(500)]
            media = await db.media.find_one(
                {"id": data.media_id, "user_id": {"$in": org_user_ids}}, {"_id": 0, "id": 1, "filename": 1}
            )
            if not media:
                raise HTTPException(404, "Esa foto no está en tu biblioteca.")
            media_id = media["id"]
            promo_name = f"Promo · {media.get('filename') or 'Foto'}"
            promo_text = None
        else:
            text = (data.text or "").strip()
            if len(text) < 2:
                raise HTTPException(400, "Escribe el mensaje de la promo.")
            picture = render_promo_card(text, (data.subtitle or "").strip() or None)
            media_id = str(_uuid.uuid4())
            stored_name = f"{media_id}.jpg"
            os.makedirs(MEDIA_DIR, exist_ok=True)
            with open(os.path.join(MEDIA_DIR, stored_name), "wb") as fh:
                fh.write(picture)
            await db.media.insert_one({
                "id": media_id,
                "user_id": current_user["id"],
                "filename": f"promo-{text[:24]}.jpg",
                "content_type": "image/jpeg",
                "size": len(picture),
                "type": "image",
                "sha256": hashlib.sha256(picture).hexdigest(),
                "storage": "legacy",
                "stored_filename": stored_name,
                "status": "ready",
                "source": "promo_card",
                "created_at": now,
            })
            promo_name = f"Promo · {text[:40]}"
            promo_text = text

        minutes = data.duration_minutes
        if minutes is not None and minutes not in ALLOWED_DURATIONS:
            raise HTTPException(400, "Duración no permitida.")
        expires_at = now + timedelta(minutes=minutes) if minutes else None
        seconds = max(5, min(int(data.item_seconds or 12), 120))

        promo = {
            "id": str(_uuid.uuid4()),
            "org_id": org_id,
            "name": promo_name,
            "description": "Promo instantánea",
            "is_promo": True,
            "promo_kind": data.kind,
            "promo_text": promo_text,
            "created_by_user_id": current_user["id"],
            "owner_user_id": current_user["id"],
            "client_user_id": current_user["id"],
            "management_mode": "client",
            "allow_client_publish": True,
            "allowed_screen_ids": org_screens,
            "screen_ids": screen_ids,
            "items": [{
                "id": str(_uuid.uuid4()),
                "type": "media",
                "ref_id": media_id,
                "title": promo_name,
                "duration": seconds,
                "transition": "fade",
                "display_mode": "cover",
                "order": 0,
            }],
            "schedule": {
                "mode": "always", "timezone": "America/New_York",
                "days": list(range(7)), "start_time": "00:00", "end_time": "23:59",
                "start_date": None, "end_date": None,
            },
            "priority": PROMO_PRIORITY,
            "status": "published",
            "version": 1,
            "expires_at": expires_at,
            "published_at": now,
            "created_at": now,
            "updated_at": now,
        }
        await db.playlists.insert_one(promo)

        if bump_playlist_version:
            for sid in screen_ids:
                await bump_playlist_version(sid, reason="instant promo launched")
        await _audit(
            db, "promo.launched",
            user_id=current_user["id"], user_email=current_user.get("email"),
            resource_type="playlist", resource_id=promo["id"],
            details={"name": promo_name, "screens": len(screen_ids),
                     "minutes": minutes, "kind": data.kind},
            org_id=org_id,
        )
        return {**_public(promo), "media_id": media_id, "screens": len(screen_ids)}

    @router.delete("/promos/{promo_id}", summary="Turn a promo off and go back to normal content")
    async def stop_promo(promo_id: str, current_user: dict = Depends(require_promo_user)):
        org_id = current_user["organization_id"]
        promo = await db.playlists.find_one({"id": promo_id, "org_id": org_id, "is_promo": True})
        if not promo:
            raise HTTPException(404, "Promo no encontrada")
        await db.playlists.update_one({"id": promo_id}, {"$set": {
            "status": "stopped",
            "expires_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }})
        if bump_playlist_version:
            for sid in promo.get("screen_ids") or []:
                await bump_playlist_version(sid, reason="instant promo stopped")
        await _audit(
            db, "promo.stopped",
            user_id=current_user["id"], user_email=current_user.get("email"),
            resource_type="playlist", resource_id=promo_id,
            details={"name": promo.get("name")}, org_id=org_id,
        )
        return {"message": "Promo apagada", "promo_id": promo_id}

    return router
