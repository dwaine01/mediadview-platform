"""
Client logos — social proof managed from the admin panel.

Public:  GET  /api/client-logos                → active logos, display order
Admin:   GET  /api/admin/client-logos          → all logos
         POST /api/admin/client-logos          → create (base64 image upload)
         PATCH/DELETE /api/admin/client-logos/{logo_id}

Logo files are written to backend/web/clients/ and served publicly through the
existing /api/web static mount, so the marketing pages need no auth to show them.
"""
from __future__ import annotations

import base64
import os
import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
LOGO_DIR = os.path.join(WEB_DIR, "clients")
PUBLIC_PREFIX = "/api/web/clients"

ALLOWED_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
               "webp": "image/webp", "svg": "image/svg+xml"}
MAX_BYTES = 2 * 1024 * 1024  # 2 MB is plenty for a logo


def _ser(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    return {k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in doc.items() if k != "_id"}


class ClientLogoCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    industry: Optional[str] = Field(None, max_length=120)
    city: Optional[str] = Field(None, max_length=120)
    website: Optional[str] = Field(None, max_length=400)
    display_order: int = Field(0, ge=0, le=999)
    is_active: bool = True
    # Either provide an already-hosted URL, or upload a file as base64.
    logo_url: Optional[str] = Field(None, max_length=600)
    logo_filename: Optional[str] = Field(None, max_length=200)
    logo_base64: Optional[str] = None


class ClientLogoUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    industry: Optional[str] = Field(None, max_length=120)
    city: Optional[str] = Field(None, max_length=120)
    website: Optional[str] = Field(None, max_length=400)
    display_order: Optional[int] = Field(None, ge=0, le=999)
    is_active: Optional[bool] = None
    logo_url: Optional[str] = Field(None, max_length=600)
    logo_filename: Optional[str] = Field(None, max_length=200)
    logo_base64: Optional[str] = None


def _save_logo(filename: str | None, b64: str) -> str:
    """Decode a base64 logo, validate it, write it to disk, return its public URL."""
    ext = (os.path.splitext(filename or "")[1] or "").lower().lstrip(".")
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported logo format '.{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXT))}",
        )
    payload = re.sub(r"^data:[^;]+;base64,", "", b64.strip())
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="logo_base64 is not valid base64 data")
    if not raw:
        raise HTTPException(status_code=400, detail="Logo file is empty")
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Logo is larger than 2 MB")

    os.makedirs(LOGO_DIR, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(LOGO_DIR, safe_name), "wb") as fh:
        fh.write(raw)
    return f"{PUBLIC_PREFIX}/{safe_name}"


def _delete_local_logo(logo_url: str | None) -> None:
    if not logo_url or not logo_url.startswith(PUBLIC_PREFIX + "/"):
        return
    path = os.path.join(LOGO_DIR, os.path.basename(logo_url))
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def create_client_logos_routes(db, require_admin):
    router = APIRouter(tags=["Client Logos"])

    @router.get("/api/client-logos", summary="Public client logos (no auth)")
    async def list_public_logos():
        docs = await db.client_logos.find({"is_active": True}).sort("display_order", 1).to_list(60)
        return [_ser(d) for d in docs]

    @router.get("/api/admin/client-logos", summary="List all client logos (admin)")
    async def list_all_logos(admin=Depends(require_admin)):
        docs = await db.client_logos.find({}).sort("display_order", 1).to_list(200)
        return [_ser(d) for d in docs]

    @router.post("/api/admin/client-logos", summary="Create a client logo (admin)", status_code=201)
    async def create_logo(data: ClientLogoCreate, admin=Depends(require_admin)):
        logo_url = data.logo_url
        if data.logo_base64:
            logo_url = _save_logo(data.logo_filename, data.logo_base64)
        if not logo_url:
            raise HTTPException(status_code=400, detail="Provide either logo_base64 or logo_url")

        now = datetime.utcnow()
        doc = {
            "id": str(uuid.uuid4()),
            "name": data.name.strip(),
            "industry": (data.industry or "").strip() or None,
            "city": (data.city or "").strip() or None,
            "website": (data.website or "").strip() or None,
            "logo_url": logo_url,
            "display_order": data.display_order,
            "is_active": data.is_active,
            "created_at": now,
            "updated_at": now,
        }
        await db.client_logos.insert_one(doc)
        return _ser(doc)

    @router.patch("/api/admin/client-logos/{logo_id}", summary="Update a client logo (admin)")
    async def update_logo(logo_id: str, data: ClientLogoUpdate, admin=Depends(require_admin)):
        existing = await db.client_logos.find_one({"id": logo_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Client logo not found")

        patch = {k: v for k, v in data.model_dump(exclude_unset=True).items()
                 if k not in ("logo_base64", "logo_filename")}
        if data.logo_base64:
            patch["logo_url"] = _save_logo(data.logo_filename, data.logo_base64)
            _delete_local_logo(existing.get("logo_url"))
        for field in ("industry", "city", "website"):
            if field in patch and isinstance(patch[field], str):
                patch[field] = patch[field].strip() or None
        patch["updated_at"] = datetime.utcnow()

        await db.client_logos.update_one({"id": logo_id}, {"$set": patch})
        return _ser(await db.client_logos.find_one({"id": logo_id}))

    @router.delete("/api/admin/client-logos/{logo_id}", summary="Delete a client logo (admin)")
    async def delete_logo(logo_id: str, admin=Depends(require_admin)):
        existing = await db.client_logos.find_one({"id": logo_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Client logo not found")
        await db.client_logos.delete_one({"id": logo_id})
        _delete_local_logo(existing.get("logo_url"))
        return {"message": "Client logo deleted", "id": logo_id}

    return router
