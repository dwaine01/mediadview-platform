"""public_api_routes.py -- unauthenticated /public/* JSON+HTML surface:
the QR-scanning customer's screen catalog, and the token-based playlist
share-link flow (view, QR code, guest media upload, guest item removal, and
the HTML editor shell).

Fase 2C-1 of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md and
docs/AGENT_COORDINATION.md). These are exactly the routes Fase 2B-4's
playlists_routes.py docstring flagged as deferred ("Staying in server.py:
the 4 anonymous /public/playlists/{token}* routes ... and GET /public/playlist
(the HTML shell) -- all player/device or public domain, for 2B-5") plus the
3 /public/screens* routes, a separate small group bundled in here rather than
given its own tiny file. Pure relocation of the 8 handlers below out of
server.py: identical paths, methods, decorators and logic, registered on a
router with prefix="/api" so the final routes match api_router exactly as
before. No behavior change.

Not to be confused with public_pages_routes.py (Fase 1): that file serves
unauthenticated HTML pages on the main `app` object with no path prefix
(landing/marketing, customer SPA entry points, APK sideloading). Everything
in *this* file is registered on api_router under the "/api" prefix -- JSON
endpoints plus one HTML shell whose own QR code hardcodes "/api/public/playlist"
as its URL, so it has to stay on api_router, not get merged into that file.

Dependency notes:
  - db (database.py), HTTPException/Request/Response (fastapi/starlette),
    FileResponse (fastapi.responses), os and datetime are imported directly.
  - MediaUpload is imported directly from media_utils.py -- already a plain
    module-level import there, shared with media_routes.py.
  - _public_screen_view is imported directly from media_utils.py: it moved
    there in this same PR (was module-level in server.py) because
    _customer_screen_view, which stays in server.py until the /customer/*
    phase, calls it too.
  - _public_token_hash is imported directly from media_utils.py -- already
    shared that way with playlists_routes.py since Fase 2B-4.
  - normalize_playlist_items is imported directly from playlist_domain.py,
    exactly as server.py already does.
  - limiter (as _rl) and LIMITS (as _LIMITS) are imported directly from
    rate_limit.py, exactly as server.py already does, for the
    @_rl.limit(_LIMITS.media_upload) decorator on public_playlist_media.
  - upload_media is threaded in: it's the callable server.py gets back from
    create_media_routes(...) (Fase 2B-2), not an importable module-level
    name -- server.py already calls it directly for this exact route, per
    that phase's own comment ("public_playlist_media below still calls
    upload_media(...) directly as a plain function").
  - serialize_doc is threaded in, same pattern as every prior phase --
    public_playlist_media's pending-approval branch calls it.
  - web_dir is threaded in (server.py's WEB_DIR), same pattern
    public_pages_routes.py already uses for the same constant; the one
    reference inside serve_public_playlist_editor is mechanically renamed
    WEB_DIR -> web_dir, same as public_pages_routes.py already does.
  - _bump_playlist_screens is threaded in and NOT moved: it's already
    threaded into create_menus_routes (Fase 2B-1) and create_playlists_routes
    (Fase 2B-4), so it has to stay defined in server.py.
  - _public_playlist is NOT threaded: grep-verified its only callers are the
    4 playlist routes below, so it moves fully into this file as a plain
    module-level function (same treatment as public_pages_routes.py's own
    helper functions) -- no threaded dependency, since db and
    _public_token_hash are both plain imports here too.

2026-09: public_playlist_media now accepts multipart/form-data uploads
(a "file" field, plus optional "width"/"height") in addition to the
original JSON+base64 body, via the new _parse_media_upload() helper below.
Fixes a preexisting bug (flagged since Fase 2C-1, see
AGENT_COORDINATION.md): a multipart POST used to crash this endpoint with
an unhandled 500 UnicodeDecodeError instead of either working or failing
cleanly. public-playlist.html is unchanged and keeps sending JSON.
"""
import base64
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import ValidationError

from database import db
from media_utils import MediaUpload, _public_screen_view, _public_token_hash
from playlist_domain import normalize_playlist_items
from rate_limit import LIMITS as _LIMITS
from rate_limit import limiter as _rl


async def _public_playlist(token: str) -> dict:
    playlist = await db.playlists.find_one({"public_access.token_hash": _public_token_hash(token)}, {"_id": 0})
    if not playlist or not playlist.get("public_access", {}).get("enabled"):
        raise HTTPException(404, "Public playlist link not found")
    expires_at = playlist.get("public_access", {}).get("expires_at")
    if expires_at and expires_at < datetime.utcnow():
        raise HTTPException(410, "Public playlist link expired")
    return playlist


# ── Guest-upload multipart fix (queued since Fase 2C-1, see
# AGENT_COORDINATION.md's "Hallazgo anotado" under that phase's entry): the
# original handler declared `data: MediaUpload`, which makes FastAPI parse
# the ENTIRE body as JSON no matter what a client actually sends. A
# multipart/form-data POST (a classic HTML <form>, or a third-party
# integration that can't base64-encode client-side) crashed with an
# unhandled 500 UnicodeDecodeError instead of a clean 4xx -- and could never
# actually complete an upload either way, since nothing decoded the file
# part. This helper accepts BOTH: the original JSON+base64 contract
# (unchanged -- still exactly what public-playlist.html sends today) and a
# real multipart/form-data upload (a "file" field, plus optional "width"/
# "height" fields), normalizing either into the same MediaUpload the rest of
# the pipeline (upload_media) already expects. Anything else is a clean 415,
# never a crash. Scoped to this one public/guest endpoint -- the
# authenticated /media/upload (media_routes.py) already has its own
# chunked-upload path for large files and isn't touched by this fix.
async def _parse_media_upload(request: Request) -> MediaUpload:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type == "application/json":
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")
        try:
            return MediaUpload(**payload)
        except ValidationError as e:
            raise HTTPException(422, str(e))
    if content_type == "multipart/form-data":
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(400, "No file provided — expected a 'file' form field")
        file_bytes = await upload.read()
        if not file_bytes:
            raise HTTPException(400, "Uploaded file is empty")
        width = form.get("width")
        height = form.get("height")
        try:
            return MediaUpload(
                filename=upload.filename or "upload.bin",
                content_type=upload.content_type or "application/octet-stream",
                data=base64.b64encode(file_bytes).decode("ascii"),
                width=int(width) if width else None,
                height=int(height) if height else None,
            )
        except (TypeError, ValueError):
            raise HTTPException(400, "Invalid width/height in form data")
    raise HTTPException(415, "Unsupported content type — send application/json (base64) or multipart/form-data")


def create_public_api_routes(upload_media, serialize_doc, web_dir, _bump_playlist_screens):
    router = APIRouter(prefix="/api", tags=["Public"])

    @router.get("/public/screens")
    async def public_screens(city: Optional[str] = None):
        """Public screen catalog for the transient QR-scanning customer.
        No auth, no prices, only marketing-safe fields."""
        query: dict = {"status": "active", "advertising.is_public": {"$ne": False}}
        if city:
            query["location.city"] = {"$regex": city, "$options": "i"}
        screens = await db.screens.find(query).to_list(200)
        return [_public_screen_view(s) for s in screens]

    @router.get("/public/screens/by-code/{code}")
    async def public_screen_by_code(code: str):
        """Look up a screen by its short pairing code (printed under the QR).
        Case-insensitive so 'mv-kd6k-twtu' == 'MV-KD6K-TWTU'."""
        screen = await db.screens.find_one({"pairing_code": {"$regex": f"^{code}$", "$options": "i"}})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen code not found")
        if (screen.get("advertising") or {}).get("is_public") is False:
            raise HTTPException(status_code=404, detail="Screen not available for public advertising")
        return _public_screen_view(screen)

    @router.get("/public/screens/{screen_id}")
    async def public_screen_detail(screen_id: str):
        """Single-screen public detail (used by the QR landing to resolve a scan by ID)."""
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        if (screen.get("advertising") or {}).get("is_public") is False:
            raise HTTPException(status_code=404, detail="Screen not available for public advertising")
        return _public_screen_view(screen)

    @router.get("/public/playlists/{token}")
    async def get_public_playlist(token: str):
        playlist = await _public_playlist(token)
        return {"id": playlist["id"], "name": playlist["name"], "description": playlist.get("description"),
                "items": playlist.get("items", []), "pending_count": len(playlist.get("pending_items", [])),
                "access": {key: value for key, value in playlist.get("public_access", {}).items()
                           if key not in ("token_hash", "created_by_user_id")}}

    @router.get("/public/playlists/{token}/qr")
    async def public_playlist_qr(token: str, request: Request):
        await _public_playlist(token)
        import io

        import qrcode
        url = f"{str(request.base_url).rstrip('/')}/api/public/playlist?token={token}"
        image = qrcode.make(url)
        buffer = io.BytesIO(); image.save(buffer, format="PNG")
        return Response(buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})

    @router.post("/public/playlists/{token}/media")
    @_rl.limit(_LIMITS.media_upload)
    async def public_playlist_media(token: str, request: Request, response: Response):
        playlist = await _public_playlist(token)
        access = playlist.get("public_access", {})
        if not access.get("allow_upload"):
            raise HTTPException(403, "Uploads are disabled for this link")
        data = await _parse_media_upload(request)
        owner = await db.users.find_one({"id": playlist.get("client_user_id") or playlist.get("owner_user_id")}, {"_id": 0})
        if not owner:
            raise HTTPException(409, "Playlist owner account is unavailable")
        uploaded = await upload_media(request=request, response=response, data=data, current_user=owner)
        item = normalize_playlist_items([{
            "type": "media", "ref_id": uploaded["id"], "title": uploaded["filename"], "duration": 15,
        }])[0]
        if access.get("require_approval", True):
            item.update({"submitted_at": datetime.utcnow(), "submission_status": "pending"})
            await db.playlists.update_one({"id": playlist["id"]}, {"$push": {"pending_items": item}})
            return {"message": "Content submitted for approval", "status": "pending", "item": serialize_doc(item)}
        item["order"] = len(playlist.get("items") or [])
        await db.playlists.update_one({"id": playlist["id"]}, {
            "$push": {"items": item}, "$inc": {"version": 1}, "$set": {"updated_at": datetime.utcnow()},
        })
        await _bump_playlist_screens(playlist.get("screen_ids", []), "public playlist upload")
        return {"message": "Content published", "status": "published", "item": item}

    @router.delete("/public/playlists/{token}/items/{item_id}")
    async def public_remove_playlist_item(token: str, item_id: str):
        playlist = await _public_playlist(token)
        if playlist.get("public_access", {}).get("permission") != "editor":
            raise HTTPException(403, "This link can upload but cannot remove content")
        if not any(item.get("id") == item_id for item in playlist.get("items", [])):
            raise HTTPException(404, "Playlist item not found")
        await db.playlists.update_one({"id": playlist["id"]}, {
            "$pull": {"items": {"id": item_id}}, "$inc": {"version": 1}, "$set": {"updated_at": datetime.utcnow()},
        })
        await _bump_playlist_screens(playlist.get("screen_ids", []), "public playlist item removed")
        return {"message": "Content removed"}

    @router.get("/public/playlist")
    async def serve_public_playlist_editor():
        return FileResponse(os.path.join(web_dir, 'public-playlist.html'), media_type='text/html')

    return router
