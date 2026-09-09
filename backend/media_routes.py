# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""media_routes.py -- media upload (direct + chunked + R2 presign/finalize),
listing, serving, deletion and rotation/animation metadata.

Fase 2B-2 of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md and
docs/AGENT_COORDINATION.md). Pure relocation of 13 /media/* route handlers
out of server.py: identical paths, methods, decorators and logic, registered
on a router with prefix="/api" so the final routes match api_router exactly
as before. No behavior change.

Route-order note (the point of the shadowing test added in Fase 2B-1):
GET /media/serve MUST be registered before GET /media/{media_id}, or the
parametric route swallows "serve" as a media_id. This file preserves the
original relative order of all 13 routes, so registration order at
app.include_router() time is unaffected -- verify this stays true after any
future edit to this file.

Out of scope / not touched here: PUT /campaigns/{campaign_id}/media (campaign
domain), DELETE /admin/campaigns/{campaign_id}/media/{media_id} (admin
domain), GET /player/media/{media_id} and the play-log endpoint (player
domain, pending its own later phase), and POST
/public/playlists/{token}/media (public/marketplace domain, see below).

Dependency note: gen_id and serialize_doc are still shared with other,
non-media code in server.py, so they are threaded in as
create_media_routes(...) factory parameters -- same pattern as
create_workspace_routes(...) / create_menus_routes(...). MEDIA_DIR is
threaded in too (rather than imported back from server.py) to avoid a
circular import, since server.py is the one importing create_media_routes
from here; MEDIA_DIR itself is unchanged and still used in many other places
in server.py. Everything else needed here -- db, get_current_user,
media_orientation, bump_playlist_version, MediaUpload, PLAYABLE_STATUSES,
MEDIA_METADATA_PROJECTION, the rbac/rate-limit/audit-log helpers, the
storage.py/R2 helpers -- is imported directly at module level.

_sha256_of_file, MediaPresignRequest, ChunkedUploadInit and
MediaFinalizeRequest were used ONLY by the routes moving here, so they moved
here verbatim. _chunk_path and _load_upload_session are nested inside the
factory instead of being plain module functions, because _chunk_path closes
over CHUNK_TMP_DIR, which is itself derived from the threaded-in MEDIA_DIR.

Two names moved to media_utils.py instead of here, because server.py's
public_playlist_media (a separate, not-yet-extracted domain) also needs them
directly: MediaUpload, and the PLAYABLE_STATUSES/MEDIA_METADATA_PROJECTION
constants that other not-yet-extracted code in server.py reads too.

Cross-domain coupling note: server.py's public_playlist_media calls
upload_media(...) directly as a plain function (not through routing) to
reuse its upload logic. Since upload_media is defined inside this factory
(it closes over gen_id/serialize_doc/MEDIA_DIR like every other route here),
create_media_routes() returns (router, upload_media) instead of just router,
and server.py keeps a module-level `upload_media` name bound from that
tuple for public_playlist_media to call, exactly as before.
"""
import base64
import hashlib
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from database import db
from deps import get_current_user
from managed_portal_routes import create_audit_log as _audit
from media_utils import (
    MEDIA_METADATA_PROJECTION,
    MediaUpload,
    PLAYABLE_STATUSES,
    bump_playlist_version,
    media_orientation,
)
from rate_limit import LIMITS as _LIMITS
from rate_limit import limiter as _rl
from rbac import Role, get_effective_role, has_permission
from storage import (
    R2_BUCKET,
    R2_ENABLED,
    _ext_of,
    build_key,
    open_media_for_response,
    public_url_for_key,
    r2_delete,
    r2_head,
    r2_presign_put,
    r2_put_bytes,
    validate_upload,
)

logger = logging.getLogger(__name__)


def _sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MediaPresignRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    duration_seconds: Optional[float] = None
    campaign_id: Optional[str] = None
    screen_id:   Optional[str] = None


class ChunkedUploadInit(BaseModel):
    filename: str
    content_type: str
    size: int
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None


class MediaFinalizeRequest(BaseModel):
    upload_id: str


def create_media_routes(MEDIA_DIR, gen_id, serialize_doc):
    router = APIRouter(prefix="/api", tags=["Media"])

    CHUNK_TMP_DIR = os.path.join(MEDIA_DIR, "_chunks")

    def _chunk_path(upload_id: str) -> str:
        return os.path.join(CHUNK_TMP_DIR, f"{upload_id}.part")

    async def _load_upload_session(upload_id: str, current_user: dict) -> dict:
        session = await db.media_uploads.find_one({"id": upload_id, "user_id": current_user["id"]})
        if not session:
            raise HTTPException(404, "Upload session not found")
        return session

    @router.post("/media/upload")
    @_rl.limit(_LIMITS.media_upload)
    async def upload_media(request: Request, response: Response, data: MediaUpload,
                           current_user: dict = Depends(get_current_user)):
        """Legacy small-file upload. Accepts base64 JSON; stores in R2 if configured,
        otherwise writes to legacy disk + base64 (backwards-compat). Big files should
        use /media/presign instead."""
        # ── Fase 4: MANAGED_VIEWER is strictly read-only — no uploads ────────────
        if get_effective_role(current_user) == Role.MANAGED_VIEWER:
            raise HTTPException(
                status_code=403,
                detail="Managed Viewer accounts cannot upload media. Contact your MediaView administrator."
            )
        try:
            file_bytes = base64.b64decode(data.data)
        except Exception:
            raise HTTPException(400, "Invalid base64 data")
        size = len(file_bytes)

        # ── Fase 6: SEC — Filename sanitization (path traversal + dangerous names) ─
        raw_fn = data.filename or ""
        # Strip any directory components — only the basename is safe
        safe_fn = os.path.basename(raw_fn.replace("\\", "/").replace("..", ""))
        if not safe_fn or safe_fn.startswith(".") or ".." in raw_fn:
            raise HTTPException(400, "Invalid filename — path traversal detected")
        # Reject executables and script extensions
        _BLOCKED_EXTS = {
            ".exe", ".dll", ".bat", ".sh", ".php", ".py", ".rb", ".pl",
            ".js", ".ts", ".bin", ".com", ".msi", ".dmg", ".apk", ".deb",
            ".rpm", ".jar", ".war", ".ear", ".ps1", ".vbs", ".cmd",
        }
        fn_ext = os.path.splitext(safe_fn)[1].lower()
        if fn_ext in _BLOCKED_EXTS:
            raise HTTPException(415, f"File type {fn_ext!r} not allowed")
        # Assign the sanitized filename back
        data.filename = safe_fn

        # P0-A3: MAGIC-NUMBER validation — verify the actual bytes match the
        # declared content_type. Rejects MIME-spoofed uploads (e.g. .exe
        # pretending to be image/jpeg, or SVG with <script>).
        from media_validator import validate_magic_bytes
        try:
            trusted_mime = validate_magic_bytes(
                file_bytes, declared_mime=data.content_type, filename=data.filename)
        except ValueError as e:
            raise HTTPException(415, f"Upload rejected: {e}")
        # Overwrite declared type with the SERVER-TRUSTED one.
        data.content_type = trusted_mime

        # Validation — MIME + size + (video duration bypass here since we don't
        # know it in a base64 upload; presign flow enforces it).
        kind = validate_upload(filename=data.filename, mime=data.content_type,
                               size=size, duration_seconds=(1 if data.content_type.startswith("video/") else None))

        file_id = gen_id()
        ext = _ext_of(data.filename, data.content_type)
        tenant_id = current_user.get("company_name") or current_user["id"]
        tenant = re.sub(r"[^a-zA-Z0-9_-]", "_", str(tenant_id))[:40] or "default"

        media_doc: dict = {
            "id": file_id, "user_id": current_user["id"],
            "filename": data.filename, "content_type": data.content_type,
            "size": size, "type": kind,
            "sha256": hashlib.sha256(file_bytes).hexdigest(),
            "created_at": datetime.utcnow(),
        }

        # Pixel size + orientation. Images are measured server-side (never trust the
        # client); for video we keep the size the browser reported, if any.
        width, height = data.width, data.height
        if kind == "image":
            try:
                import io

                from PIL import Image
                with Image.open(io.BytesIO(file_bytes)) as im:
                    width, height = im.size
            except Exception as exc:
                logger.warning("Could not read image size for %s: %s", data.filename, exc)
        media_doc["width"] = width
        media_doc["height"] = height
        media_doc["orientation"] = media_orientation(width, height)

        if R2_ENABLED:
            # ── Modern path: put in R2 via StorageService ─────────────────────
            from storage_service import get_storage_service as _get_ss
            ss = _get_ss()
            folder = f"{tenant}/{current_user['id']}/campaign/unassigned"
            try:
                result = await ss.upload(
                    data=file_bytes,
                    filename=data.filename,
                    content_type=data.content_type,
                    folder=folder,
                )
            except Exception as e:
                logger.exception("StorageService upload failed: %s", e)
                raise HTTPException(502, "Media storage temporarily unavailable")
            media_doc.update({
                "storage":    "r2",
                "r2_key":     result.key,
                "r2_etag":    result.etag,
                "public_url": result.url,
                "status":     "ready",
            })
        else:
            # ── Legacy path (dev / no R2 configured): disk + base64 mirror ─
            stored_name = f"{file_id}{ext or '.bin'}"
            file_path = os.path.join(MEDIA_DIR, stored_name)
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            media_doc.update({
                "storage":         "legacy",
                "stored_filename": stored_name,
                "data":            data.data if kind == "image" else None,
                "status":          "ready",
            })

        await db.media.insert_one(media_doc)
        if current_user.get("organization_id"):
            await _audit(
                db, "media.uploaded",
                user_id=current_user["id"], user_email=current_user.get("email"),
                resource_type="media", resource_id=file_id,
                details={"filename": data.filename, "size": size},
                org_id=current_user["organization_id"],
            )
        return {"id": file_id, "filename": data.filename, "size": size,
                "content_type": data.content_type, "type": kind,
                "width": media_doc.get("width"), "height": media_doc.get("height"),
                "orientation": media_doc.get("orientation"),
                "storage": media_doc["storage"],
                "public_url": media_doc.get("public_url")}

    @router.post("/media/chunk/init")
    async def init_chunked_upload(data: ChunkedUploadInit,
                                  current_user: dict = Depends(get_current_user)):
        """Start a chunked upload.

        A phone video is far too big for the base64 JSON endpoint: the browser has
        to hold the whole file in memory and the request dies at the proxy (Safari
        just says "Load failed"). Chunks of a couple of megabytes always get
        through, so videos are uploaded this way.
        """
        if get_effective_role(current_user) == Role.MANAGED_VIEWER:
            raise HTTPException(403, "Managed Viewer accounts cannot upload media.")
        safe_fn = os.path.basename((data.filename or "").replace("\\", "/").replace("..", ""))
        if not safe_fn or safe_fn.startswith("."):
            raise HTTPException(400, "Invalid filename")
        if data.size <= 0:
            raise HTTPException(400, "Empty file")
        # Reject oversized / too long files before a single byte is transferred.
        kind = validate_upload(filename=safe_fn, mime=data.content_type, size=data.size,
                               duration_seconds=(data.duration_seconds or 1)
                               if data.content_type.startswith("video/") else None)
        upload_id = str(uuid.uuid4())
        os.makedirs(CHUNK_TMP_DIR, exist_ok=True)
        await db.media_uploads.insert_one({
            "id": upload_id,
            "user_id": current_user["id"],
            "filename": safe_fn,
            "content_type": data.content_type,
            "size": data.size,
            "kind": kind,
            "width": data.width,
            "height": data.height,
            "duration_seconds": data.duration_seconds,
            "received": 0,
            "created_at": datetime.utcnow(),
        })
        return {"upload_id": upload_id, "chunk_size": 2 * 1024 * 1024, "kind": kind}

    @router.post("/media/chunk/{upload_id}")
    async def append_chunk(upload_id: str, request: Request,
                           current_user: dict = Depends(get_current_user)):
        """Append the raw bytes of the request body to the pending upload."""
        session = await _load_upload_session(upload_id, current_user)
        chunk = await request.body()
        if not chunk:
            raise HTTPException(400, "Empty chunk")
        # Writing at an explicit offset keeps retries idempotent: a phone that
        # re-sends a chunk after a dropped response must not duplicate bytes.
        try:
            offset = int(request.headers.get("x-chunk-offset", session.get("received", 0)))
        except ValueError:
            raise HTTPException(400, "Invalid chunk offset")
        if offset < 0 or offset + len(chunk) > int(session["size"]):
            raise HTTPException(400, "Chunk falls outside the announced size")
        os.makedirs(CHUNK_TMP_DIR, exist_ok=True)
        path = _chunk_path(upload_id)
        with open(path, "r+b" if os.path.exists(path) else "wb") as handle:
            handle.seek(offset)
            handle.write(chunk)
        received = max(int(session.get("received", 0)), offset + len(chunk))
        await db.media_uploads.update_one({"id": upload_id}, {"$set": {"received": received}})
        return {"received": received, "size": session["size"],
                "percent": round(received * 100 / int(session["size"]), 1)}

    @router.post("/media/chunk/{upload_id}/complete")
    async def complete_chunked_upload(upload_id: str,
                                      current_user: dict = Depends(get_current_user)):
        """Validate the assembled file and register it like a normal upload."""
        session = await _load_upload_session(upload_id, current_user)
        part = _chunk_path(upload_id)
        if not os.path.isfile(part):
            raise HTTPException(400, "No chunks were uploaded")
        actual = os.path.getsize(part)
        if actual != int(session["size"]):
            os.remove(part)
            await db.media_uploads.delete_one({"id": upload_id})
            raise HTTPException(400, f"Incomplete upload: got {actual} of {session['size']} bytes")

        from media_validator import validate_magic_bytes
        with open(part, "rb") as handle:
            head = handle.read(64 * 1024)
        try:
            trusted_mime = validate_magic_bytes(head, declared_mime=session["content_type"],
                                                filename=session["filename"])
        except ValueError as exc:
            os.remove(part)
            await db.media_uploads.delete_one({"id": upload_id})
            raise HTTPException(415, f"Upload rejected: {exc}")

        digest = await run_in_threadpool(_sha256_of_file, part)
        file_id = str(uuid.uuid4())
        ext = os.path.splitext(session["filename"])[1].lower()

        media_doc = {
            "id": file_id,
            "user_id": current_user["id"],
            "filename": session["filename"],
            "content_type": trusted_mime,
            "size": actual,
            "type": session["kind"],
            "sha256": digest,
            "width": session.get("width"),
            "height": session.get("height"),
            "orientation": media_orientation(session.get("width"), session.get("height")),
            "duration_seconds": session.get("duration_seconds"),
            "data": None,
            "status": "ready",
            "created_at": datetime.utcnow(),
        }

        if R2_ENABLED:
            # Los videos son justo lo que no cabe en el disco efímero: se suben a R2
            # en streaming (nunca se carga el archivo completo en memoria).
            from storage import build_key, public_url_for_key, r2_upload_fileobj
            tenant = current_user.get("organization_id") or "public"
            key = build_key(tenant_id=tenant, client_id=current_user["id"],
                            campaign_id="unassigned", ext=ext)
            try:
                with open(part, "rb") as handle:
                    await r2_upload_fileobj(key, handle, trusted_mime)
            except Exception as exc:
                logger.exception("R2 chunked upload failed: %s", exc)
                raise HTTPException(502, "Media storage temporarily unavailable")
            os.remove(part)
            media_doc.update({
                "storage": "r2",
                "r2_key": key,
                "public_url": public_url_for_key(key),
            })
        else:
            stored_name = f"{file_id}{ext or '.bin'}"
            os.replace(part, os.path.join(MEDIA_DIR, stored_name))
            media_doc.update({"storage": "legacy", "stored_filename": stored_name})

        await db.media.insert_one(media_doc)
        await db.media_uploads.delete_one({"id": upload_id})
        return {"id": file_id, "filename": session["filename"], "size": actual,
                "content_type": trusted_mime, "type": session["kind"],
                "width": media_doc["width"], "height": media_doc["height"],
                "orientation": media_doc["orientation"],
                "storage": "legacy", "public_url": None}

    @router.post("/media/presign")
    @_rl.limit(_LIMITS.media_upload)
    async def presign_media(request: Request, response: Response, body: MediaPresignRequest,
                            current_user: dict = Depends(get_current_user)):
        """Return a short-lived (10 min) presigned PUT URL. Client uploads directly
        to R2, then calls /media/finalize to attach it to a campaign/screen."""
        if not R2_ENABLED:
            raise HTTPException(503, "Direct uploads not available — use /media/upload")
        kind = validate_upload(filename=body.filename, mime=body.content_type,
                               size=body.size_bytes, duration_seconds=body.duration_seconds)
        ext = _ext_of(body.filename, body.content_type)
        tenant = re.sub(r"[^a-zA-Z0-9_-]", "_",
                        str(current_user.get("company_name") or current_user["id"]))[:40] or "default"
        key = build_key(tenant_id=tenant, client_id=current_user["id"],
                        campaign_id=body.campaign_id or "unassigned",
                        screen_id=body.screen_id, ext=ext)
        upload_id = gen_id()
        await db.media.insert_one({
            "id": upload_id, "user_id": current_user["id"],
            "filename": body.filename, "content_type": body.content_type,
            "size": body.size_bytes, "type": kind,
            "duration_seconds": body.duration_seconds,
            "campaign_id": body.campaign_id, "screen_id": body.screen_id,
            "storage": "pending", "r2_key": key,
            "status": "pending", "created_at": datetime.utcnow(),
        })
        signed = await r2_presign_put(key, body.content_type)
        return {"upload_id": upload_id, "key": key, **signed}

    @router.post("/media/finalize")
    async def finalize_media(request: Request, body: MediaFinalizeRequest,
                             current_user: dict = Depends(get_current_user)):
        """Verify the object landed in R2, then mark media as ready."""
        doc = await db.media.find_one({"id": body.upload_id, "user_id": current_user["id"]})
        if not doc or doc.get("status") != "pending":
            raise HTTPException(404, "Upload not found or already finalized")
        head = await r2_head(doc["r2_key"])
        if not head:
            raise HTTPException(400, "R2 object not found — did the upload complete?")
        # Server-side verification: MIME + size within declared bounds
        got_size = int(head.get("ContentLength") or 0)
        got_mime = head.get("ContentType") or doc["content_type"]
        if got_size > doc["size"] * 1.05 + 1024:      # allow ~5% slack for streaming
            await r2_delete(doc["r2_key"])
            raise HTTPException(400, "Uploaded size does not match declared")
        if got_mime != doc["content_type"]:
            await r2_delete(doc["r2_key"])
            raise HTTPException(400, "Uploaded MIME does not match declared")
        public_url = public_url_for_key(doc["r2_key"])
        await db.media.update_one({"id": doc["id"]}, {"$set": {
            "storage": "r2", "status": "ready",
            "r2_etag": (head.get("ETag") or "").strip('"'),
            "size":    got_size,
            "public_url": public_url,
        }})
        return {"id": doc["id"], "public_url": public_url, "status": "ready"}

    @router.get("/media")
    async def list_media(current_user: dict = Depends(get_current_user)):
        media = await db.media.find(
            {"user_id": current_user["id"], "status": {"$ne": "pending"}},
            {"data": 0}   # never send base64 in listings
        ).sort("created_at", -1).to_list(100)
        return serialize_doc(media)

    @router.get("/media/serve")
    async def serve_r2_media(key: str):
        """Stream an object out of R2 when the bucket has no public domain yet.

        `storage.public_url_for_key()` points here while R2_PUBLIC_BASE_URL is
        empty. The key must belong to a registered media document, so the bucket
        cannot be browsed through this endpoint. Declared BEFORE
        `/media/{media_id}` or that route would swallow the path.
        """
        media = await db.media.find_one({"r2_key": key})
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")

        from storage import r2_get_stream, r2_head
        if await r2_head(key) is None:
            # Migración gradual: si el objeto todavía no está en R2 (o la subida
            # quedó a medias) seguimos sirviendo la copia local/base64 en vez de
            # devolver un 404 a la pantalla.
            legacy = {k: v for k, v in media.items() if k != "r2_key"}
            result = await run_in_threadpool(open_media_for_response, legacy, MEDIA_DIR)
            if result.get("type") == "url":
                return RedirectResponse(url=result["value"], status_code=302)
            return Response(
                content=result["value"],
                media_type=result.get("mime") or media.get("content_type", "application/octet-stream"),
                headers={"Content-Disposition": "inline", "Cache-Control": "public, max-age=300"},
            )

        body, content_type, length = await r2_get_stream(key)
        headers = {"Cache-Control": "public, max-age=86400", "Content-Disposition": "inline"}
        if length:
            headers["Content-Length"] = str(length)
        return StreamingResponse(
            body,
            media_type=content_type or media.get("content_type") or "application/octet-stream",
            headers=headers,
        )

    @router.get("/media/{media_id}")
    async def get_media(media_id: str):
        media = await db.media.find_one({"id": media_id}, MEDIA_METADATA_PROJECTION)
        if not media:
            raise HTTPException(404, "Media not found")
        # Strip base64 payload from metadata responses
        media.pop("data", None)
        return serialize_doc(media)

    @router.get("/media/{media_id}/file")
    async def get_media_file(media_id: str):
        """Universal read — returns 302 to Cloudflare when in R2, or raw bytes otherwise."""
        media = await db.media.find_one({"id": media_id})
        if not media:
            raise HTTPException(404, "Media not found")
        result = open_media_for_response(media, media_dir=MEDIA_DIR)
        if result["type"] == "url":
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=result["value"], status_code=302)
        return Response(content=result["value"], media_type=result["mime"])

    @router.delete("/media/{media_id}")
    async def delete_media(media_id: str, force: bool = False, current_user: dict = Depends(get_current_user)):
        """Delete a media asset.

        By default this is REFUSED if the media is referenced by any campaign
        (returns HTTP 409 with the list of campaigns). Passing ?force=true
        performs a cascade: the media is removed from every campaign's
        media_ids and any campaign left without media is flagged
        needs_attention=true so the admin dashboard can surface it.
        """
        media = await db.media.find_one({"id": media_id, "user_id": current_user["id"]})
        if not media:
            raise HTTPException(404, "Media not found")

        # Referential integrity check
        using = await db.campaigns.find({"media_ids": media_id}).to_list(200)
        if using and not force:
            raise HTTPException(status_code=409, detail={
                "message": f"This media is used by {len(using)} campaign(s). Pass force=true to cascade delete.",
                "used_by": [{"campaign_id": c["id"], "name": c.get("name"), "status": c.get("status")} for c in using],
            })

        # Force cascade: remove media_id from every campaign, flag those left empty
        if using and force:
            for c in using:
                new_mids = [m for m in (c.get("media_ids") or []) if m != media_id]
                update = {"media_ids": new_mids, "updated_at": datetime.utcnow()}
                if not new_mids and c.get("status") in PLAYABLE_STATUSES:
                    update["needs_attention"] = True
                await db.campaigns.update_one({"id": c["id"]}, {"$set": update})
                await bump_playlist_version(c.get("screen_id"), reason="media deleted (force)")

        # Remove R2 object if present
        if media.get("r2_key"):
            await r2_delete(media["r2_key"])
        # Remove legacy disk copy if present
        if media.get("stored_filename"):
            file_path = os.path.join(MEDIA_DIR, media["stored_filename"])
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except Exception: pass
        await db.media.delete_one({"id": media_id})
        return {"message": "Media deleted", "cascaded_campaigns": len(using) if force else 0}

    @router.put("/media/{media_id}/rotate")
    async def rotate_media(media_id: str, rotation: int = 0, current_user: dict = Depends(get_current_user)):
        """Set rotation angle and force refresh on all devices showing this media."""
        if rotation not in [0, 90, 180, 270]:
            raise HTTPException(status_code=400, detail="Rotation must be 0, 90, 180 or 270")
        media = await db.media.find_one({"id": media_id})
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        # ── FASE 1: ownership check ─────────────────────────────────────────────
        # Platform admins can rotate any media; other users can only rotate their own.
        if not has_permission(current_user, "admin.all_screens"):
            if media.get("user_id") != current_user.get("id"):
                raise HTTPException(status_code=403, detail="You do not own this media item")
        await db.media.update_one({"id": media_id}, {"$set": {"rotation": rotation}})

        # Find all campaigns using this media and force restart their devices
        campaigns = await db.campaigns.find({"media_ids": media_id}).to_list(100)
        restarted = 0
        for camp in campaigns:
            devices = await db.devices.find({"screen_id": camp.get("screen_id"), "status": "active"}).to_list(10)
            for dev in devices:
                await db.devices.update_one({"id": dev["id"]}, {"$set": {"pending_command": "reload"}})
                restarted += 1

        return {"message": f"Rotation set to {rotation}. {restarted} device(s) will refresh."}

    @router.put("/media/{media_id}/animation")
    async def set_media_animation(media_id: str, animation: str = "fade", current_user: dict = Depends(get_current_user)):
        """Set animation type: fade, slide, zoom, none."""
        if animation not in ["fade", "slide", "zoom", "none"]:
            raise HTTPException(status_code=400, detail="Animation must be fade, slide, zoom, or none")
        await db.media.update_one({"id": media_id}, {"$set": {"animation": animation}})
        return {"message": f"Animation set to {animation}"}

    return router, upload_media
