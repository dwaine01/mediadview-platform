"""
MediAd View — Storage layer (Cloudflare R2 + graceful legacy fallback)

Responsibilities:
- Upload files to R2 (S3-compatible) using aioboto3.
- Generate presigned PUT URLs for direct browser → R2 uploads (large files).
- Read media back regardless of where it lives:
    r2       → return public URL (Cloudflare-served)
    base64   → decode from db.media.data       (legacy — Fase 4 pre-migration)
    disk     → read from MEDIA_DIR             (legacy — Fase 4 pre-migration)
- Validate MIME, extension, size, duration, and permission BEFORE writing.
- Never trust user-supplied filenames — keys are `{tenant}/{client}/campaign/{cid}/media/{uuid}.{ext}`.
- Never break existing endpoints: `open_media_for_response()` handles all 3 backends.

R2 config comes exclusively from env vars. If they are missing the module still
imports but every write operation raises RuntimeError so misconfiguration is
LOUD, never silent.
"""
from __future__ import annotations
import os, uuid, base64, mimetypes, logging, contextlib
from io import BytesIO
from pathlib import Path
from typing import Optional, Literal, Dict, Any

import aioboto3
from botocore.config import Config as BotoConfig
from fastapi import HTTPException

log = logging.getLogger("storage")

MB = 1024 * 1024
IMG_MAX = int(os.getenv("MEDIA_IMG_MAX_MB",   "20")) * MB
VID_MAX = int(os.getenv("MEDIA_VID_MAX_MB",  "500")) * MB
VID_MAX_SEC = int(os.getenv("MEDIA_VID_MAX_SEC", "1800"))    # 30 min
PRESIGN_TTL = int(os.getenv("MEDIA_PRESIGN_TTL", "600"))     # 10 min

# ─── Allowed media matrix ──────────────────────────────────────────────
ALLOWED: Dict[str, Dict[str, Any]] = {
    "image": {
        "mimes": {"image/jpeg", "image/png", "image/webp", "image/gif"},
        "exts":  {".jpg", ".jpeg", ".png", ".webp", ".gif"},
        "max":   IMG_MAX,
    },
    "video": {
        "mimes": {"video/mp4", "video/webm", "video/quicktime"},
        "exts":  {".mp4", ".webm", ".mov"},
        "max":   VID_MAX,
    },
}

# ─── R2 config (all-env, no defaults with secrets) ─────────────────────
R2_ENDPOINT       = os.getenv("R2_ENDPOINT", "").strip()
R2_ACCESS_KEY_ID  = os.getenv("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_KEY     = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET         = os.getenv("R2_BUCKET_NAME", "").strip()
R2_PUBLIC_BASE    = os.getenv("R2_PUBLIC_BASE_URL", "").strip().rstrip("/")
R2_REGION         = os.getenv("R2_REGION", "auto")

R2_ENABLED = bool(R2_ENDPOINT and R2_ACCESS_KEY_ID and R2_SECRET_KEY and R2_BUCKET)

if not R2_ENABLED:
    log.warning("R2 not configured (missing env vars) — uploads will fall back to legacy base64/disk. "
                "Reads still work for existing media.")


# ─── Client (created lazily on first use) ──────────────────────────────
_session: aioboto3.Session | None = None
_stack:   contextlib.AsyncExitStack | None = None
_client = None  # type: ignore


async def _get_client():
    """Return a cached aioboto3 S3 client. Creates it on first call."""
    global _session, _stack, _client
    if _client is not None:
        return _client
    if not R2_ENABLED:
        raise RuntimeError("R2 not configured — set R2_ENDPOINT/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET_NAME")
    _session = aioboto3.Session()
    _stack = contextlib.AsyncExitStack()
    _client = await _stack.enter_async_context(_session.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name=R2_REGION,
        config=BotoConfig(signature_version="s3v4"),
    ))
    log.info("✓ R2 S3 client initialized (bucket=%s, region=%s)", R2_BUCKET, R2_REGION)
    return _client


async def close_client():
    global _client, _stack
    if _stack:
        try: await _stack.aclose()
        except Exception: pass
    _client = None; _stack = None


# ─── Validation ────────────────────────────────────────────────────────
def _ext_of(filename: str, mime: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext:
        return ext
    return (mimetypes.guess_extension(mime or "") or "").lower()


def classify(mime: str, ext: str) -> Literal["image", "video"]:
    for kind, spec in ALLOWED.items():
        if mime in spec["mimes"] and ext in spec["exts"]:
            return kind  # type: ignore
    raise HTTPException(400, "Unsupported MIME type or extension")


def validate_upload(*, filename: str, mime: str, size: int,
                    duration_seconds: Optional[float] = None) -> str:
    """Raise HTTPException(400) if the upload is not allowed. Returns 'image'|'video'."""
    ext = _ext_of(filename, mime)
    kind = classify(mime, ext)
    spec = ALLOWED[kind]
    if size <= 0:
        raise HTTPException(400, "Empty file")
    if size > spec["max"]:
        raise HTTPException(400, f"{kind.capitalize()} exceeds max {spec['max']//MB} MB")
    if kind == "video":
        if duration_seconds is None or duration_seconds <= 0:
            raise HTTPException(400, "Video duration is required")
        if duration_seconds > VID_MAX_SEC:
            raise HTTPException(400, f"Video exceeds {VID_MAX_SEC}s")
    return kind


def build_key(*, tenant_id: str, client_id: str, campaign_id: str,
              screen_id: Optional[str] = None, ext: str = "") -> str:
    """
    tenant/client/campaign/media/{uuid}.{ext}
    Optionally scoped by screen: tenant/client/screen/{sid}/media/{uuid}.{ext}
    Backend never trusts user filename; key is opaque.
    """
    ext = ext.lower()
    if not ext.startswith("."):
        ext = "." + ext if ext else ""
    if screen_id:
        return f"{tenant_id}/{client_id}/screen/{screen_id}/media/{uuid.uuid4()}{ext}"
    return f"{tenant_id}/{client_id}/campaign/{campaign_id}/media/{uuid.uuid4()}{ext}"


def public_url_for_key(key: str) -> str:
    """URL cached and served by Cloudflare (media.mediadview.com)."""
    if not R2_PUBLIC_BASE:
        # Fallback to signed URL model in dev
        return f"/api/media/serve?key={key}"
    return f"{R2_PUBLIC_BASE}/{key.lstrip('/')}"


# ─── R2 operations ─────────────────────────────────────────────────────
async def r2_put_bytes(key: str, data: bytes, content_type: str) -> Dict[str, Any]:
    s3 = await _get_client()
    resp = await s3.put_object(
        Bucket=R2_BUCKET, Key=key, Body=data,
        ContentType=content_type, CacheControl="public, max-age=31536000, immutable",
    )
    return {"etag": resp.get("ETag", "").strip('"')}


async def r2_upload_fileobj(key: str, file_obj, content_type: str) -> Dict[str, Any]:
    s3 = await _get_client()
    await s3.upload_fileobj(file_obj, R2_BUCKET, key,
                            ExtraArgs={"ContentType": content_type,
                                       "CacheControl": "public, max-age=31536000, immutable"})
    return {"etag": None}


async def r2_head(key: str) -> Optional[Dict[str, Any]]:
    s3 = await _get_client()
    try:
        return await s3.head_object(Bucket=R2_BUCKET, Key=key)
    except Exception:
        return None


async def r2_delete(key: str) -> bool:
    s3 = await _get_client()
    try:
        await s3.delete_object(Bucket=R2_BUCKET, Key=key)
        return True
    except Exception as e:
        log.warning("r2_delete %s failed: %s", key, e)
        return False


async def r2_presign_put(key: str, content_type: str,
                         ttl: int = PRESIGN_TTL) -> Dict[str, Any]:
    """Return a presigned URL for direct browser → R2 PUT.
    IMPORTANT: signs the exact Content-Type; the client MUST send that same header."""
    s3 = await _get_client()
    url = await s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": R2_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=ttl,
    )
    return {"url": url, "method": "PUT",
            "headers": {"Content-Type": content_type},
            "expires_in": ttl}


# ─── Universal read (works for r2/base64/disk regardless) ──────────────
def open_media_for_response(doc: dict, media_dir: Optional[str] = None):
    """
    Return one of:
      {"type": "url",   "value": "<public url>"}   → redirect the client to Cloudflare
      {"type": "bytes", "value": b"...", "mime": "..."}  → serve inline
    """
    if doc.get("r2_key"):
        return {"type": "url", "value": doc.get("public_url") or public_url_for_key(doc["r2_key"])}
    if doc.get("data"):
        raw = base64.b64decode(doc["data"])
        return {"type": "bytes", "value": raw, "mime": doc.get("content_type", "application/octet-stream")}
    if doc.get("stored_filename") and media_dir:
        path = Path(media_dir) / doc["stored_filename"]
        if path.exists():
            return {"type": "bytes", "value": path.read_bytes(), "mime": doc.get("content_type", "application/octet-stream")}
    raise HTTPException(404, "Media unavailable")
