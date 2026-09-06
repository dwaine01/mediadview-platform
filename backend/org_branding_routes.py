"""
Organization branding helpers — validate, store and delete a customer's own logo.

Files are written to backend/web/orgs/ and served publicly through the existing
/api/web static mount, so the workspace can render them without extra auth.
The endpoints that use these helpers live in workspace_routes.py (they need the
workspace role gate defined there) and in signup_routes.py (optional logo at signup).
"""
from __future__ import annotations

import base64
import os
import re
import uuid
from fastapi import HTTPException
from pydantic import BaseModel, Field

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
ORG_LOGO_DIR = os.path.join(WEB_DIR, "orgs")
PUBLIC_PREFIX = "/api/web/orgs"

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "svg"}
MAX_BYTES = 2 * 1024 * 1024


class OrgLogoUpload(BaseModel):
    logo_filename: str = Field(..., max_length=200)
    logo_base64: str = Field(..., min_length=16)


def save_org_logo(filename: str, b64: str) -> str:
    """Decode + validate a base64 logo, write it to disk, return its public URL."""
    ext = (os.path.splitext(filename or "")[1] or "").lower().lstrip(".")
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado '.{ext}'. Permitidos: {', '.join(sorted(ALLOWED_EXT))}",
        )
    payload = re.sub(r"^data:[^;]+;base64,", "", b64.strip())
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="El logo no es base64 válido")
    if not raw:
        raise HTTPException(status_code=400, detail="El archivo del logo está vacío")
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="El logo pesa más de 2 MB")

    os.makedirs(ORG_LOGO_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(ORG_LOGO_DIR, name), "wb") as fh:
        fh.write(raw)
    return f"{PUBLIC_PREFIX}/{name}"


def delete_org_logo(logo_url: str | None) -> None:
    if not logo_url or not logo_url.startswith(PUBLIC_PREFIX + "/"):
        return
    path = os.path.join(ORG_LOGO_DIR, os.path.basename(logo_url))
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
