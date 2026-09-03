# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
storage_service.py — Fase 6: Centralized Storage Abstraction
=============================================================

Provides a single StorageService interface that the rest of the application
uses for all file operations. Drivers:

  LocalDriver   — writes to filesystem; for development / testing
  R2Driver      — wraps storage.py R2 functions; for staging / production

The application code (server.py, advertising_routes.py, etc.) must ONLY
speak to StorageService — NEVER to boto3, aioboto3, or storage.py directly.

Usage:
    from storage_service import get_storage_service
    svc = get_storage_service()

    result = await svc.upload(
        data=file_bytes,
        filename="logo.png",
        content_type="image/png",
        folder="campaigns/abc123",
    )
    url = result.url  # public URL for the uploaded object
    key = result.key  # opaque storage key (used to delete/check later)

Design rules:
  - StorageService never exposes credentials, bucket names, or R2 internals
  - All object keys are UUID-based (never derived from user filename)
  - MIME, extension, size, and magic-byte validation happen BEFORE calling upload()
    (in server.py / media_validator.py); StorageService trusts pre-validated input
  - ping() is used by /api/ready to verify storage is reachable
  - R2Driver is a thin wrapper; heavy lifting stays in storage.py
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger("storage_service")


# ─── Result type ───────────────────────────────────────────────────────
@dataclass
class UploadResult:
    key: str          # opaque storage key (path/uuid.ext)
    url: str          # public-readable URL for the object
    storage: str      # "local" | "r2"
    etag: Optional[str] = None
    size_bytes: int = 0


# ─── StorageService public interface ──────────────────────────────────
class StorageService:
    """
    Thin facade. All application code talks to this; drivers are swapped
    by factory function without changing call sites.
    """

    def __init__(self, driver):
        self._driver = driver
        self.driver_name: str = getattr(driver, "NAME", "unknown")

    async def upload(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        folder: str = "uploads",
    ) -> UploadResult:
        """Store `data` and return an UploadResult with a public URL."""
        return await self._driver.upload(data, filename, content_type, folder)

    async def delete(self, key: str) -> bool:
        """Remove the object.  Returns True on success, False on not-found/error."""
        return await self._driver.delete(key)

    async def exists(self, key: str) -> bool:
        """True if the object exists in the backend."""
        return await self._driver.exists(key)

    async def get_url(self, key: str) -> str:
        """Return the public URL for an existing object key."""
        return await self._driver.get_url(key)

    async def metadata(self, key: str) -> Optional[dict]:
        """Return size, content_type, etag etc.  None if not found."""
        return await self._driver.metadata(key)

    async def ping(self) -> dict:
        """
        Readiness check.  Returns:
          {"ok": True,  "latency_ms": 12.3, "driver": "r2"}
          {"ok": False, "error": "...",      "driver": "local"}
        """
        return await self._driver.ping()


# ─── LocalDriver (development) ─────────────────────────────────────────
class _LocalDriver:
    NAME = "local"

    def __init__(self, media_dir: str):
        self._root = Path(media_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str) -> Path:
        # Only allow UUID-like keys to prevent path traversal
        safe = Path(key).name   # strip any directory components
        return self._root / safe

    def _url_for_key(self, key: str) -> str:
        return f"/api/media/serve?key={key}"

    async def upload(self, data: bytes, filename: str, content_type: str, folder: str) -> UploadResult:
        ext = Path(filename).suffix.lower() or ".bin"
        key = f"{folder}/{uuid.uuid4()}{ext}".lstrip("/")
        dest = self._root / Path(key).name   # flatten: no subdirs in local storage
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        log.debug("LocalDriver: wrote %d bytes → %s", len(data), dest)
        return UploadResult(
            key=key,
            url=self._url_for_key(key),
            storage="local",
            size_bytes=len(data),
        )

    async def delete(self, key: str) -> bool:
        path = self._key_to_path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    async def exists(self, key: str) -> bool:
        return self._key_to_path(key).exists()

    async def get_url(self, key: str) -> str:
        return self._url_for_key(key)

    async def metadata(self, key: str) -> Optional[dict]:
        path = self._key_to_path(key)
        if not path.exists():
            return None
        stat = path.stat()
        return {"size": stat.st_size, "key": key}

    async def ping(self) -> dict:
        import time
        t = time.monotonic()
        ok = self._root.exists()
        return {
            "ok": ok,
            "driver": self.NAME,
            "latency_ms": round((time.monotonic() - t) * 1000, 1),
        }


# ─── R2Driver (staging / production) ──────────────────────────────────
class _R2Driver:
    """
    Wraps the existing storage.py R2 primitives behind the StorageService
    interface.  Application code never imports storage.py directly.
    """
    NAME = "r2"

    def __init__(self):
        # Validate at construction time (not at import time)
        import storage as _s
        if not _s.R2_ENABLED:
            raise RuntimeError(
                "R2Driver requires R2_ENDPOINT, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY, and R2_BUCKET_NAME env vars."
            )
        self._s = _s

    async def upload(self, data: bytes, filename: str, content_type: str, folder: str) -> UploadResult:
        import uuid as _uuid
        from pathlib import Path as _P
        ext = _P(filename).suffix.lower() or ".bin"
        key = f"{folder}/{_uuid.uuid4()}{ext}".lstrip("/")
        info = await self._s.r2_put_bytes(key, data, content_type)
        url  = self._s.public_url_for_key(key)
        log.info("R2Driver: uploaded %d bytes → key=%s", len(data), key)
        return UploadResult(
            key=key,
            url=url,
            storage="r2",
            etag=info.get("etag"),
            size_bytes=len(data),
        )

    async def delete(self, key: str) -> bool:
        return await self._s.r2_delete(key)

    async def exists(self, key: str) -> bool:
        head = await self._s.r2_head(key)
        return head is not None

    async def get_url(self, key: str) -> str:
        return self._s.public_url_for_key(key)

    async def metadata(self, key: str) -> Optional[dict]:
        head = await self._s.r2_head(key)
        if not head:
            return None
        return {
            "size":         head.get("ContentLength"),
            "content_type": head.get("ContentType"),
            "etag":         head.get("ETag", "").strip('"'),
            "key":          key,
        }

    async def ping(self) -> dict:
        """List bucket (HeadBucket equivalent) to verify connectivity."""
        import time
        t = time.monotonic()
        try:
            s3 = await self._s._get_client()
            await s3.head_bucket(Bucket=self._s.R2_BUCKET)
            return {
                "ok": True,
                "driver": self.NAME,
                "latency_ms": round((time.monotonic() - t) * 1000, 1),
            }
        except Exception as exc:
            return {
                "ok": False,
                "driver": self.NAME,
                "error": type(exc).__name__,
                "latency_ms": round((time.monotonic() - t) * 1000, 1),
            }


# ─── In-memory driver (tests) ──────────────────────────────────────────
class _MemoryDriver:
    """Pure in-memory driver for unit tests — no filesystem, no network."""
    NAME = "memory"

    def __init__(self):
        self._store: dict[str, bytes] = {}
        self._meta:  dict[str, dict]  = {}

    async def upload(self, data: bytes, filename: str, content_type: str, folder: str) -> UploadResult:
        from pathlib import Path as _P
        ext = _P(filename).suffix.lower() or ".bin"
        key = f"{folder}/{uuid.uuid4()}{ext}".lstrip("/")
        self._store[key] = data
        self._meta[key]  = {"content_type": content_type, "size": len(data)}
        return UploadResult(key=key, url=f"/memory/{key}", storage="memory", size_bytes=len(data))

    async def delete(self, key: str) -> bool:
        removed = key in self._store
        self._store.pop(key, None)
        self._meta.pop(key, None)
        return removed

    async def exists(self, key: str) -> bool:
        return key in self._store

    async def get_url(self, key: str) -> str:
        return f"/memory/{key}"

    async def metadata(self, key: str) -> Optional[dict]:
        return self._meta.get(key)

    async def ping(self) -> dict:
        return {"ok": True, "driver": self.NAME, "latency_ms": 0.0}

    # Test helper — read bytes back
    def read(self, key: str) -> Optional[bytes]:
        return self._store.get(key)


# ─── Factory ───────────────────────────────────────────────────────────
_instance: Optional[StorageService] = None


def get_storage_service(force_driver: Optional[str] = None) -> StorageService:
    """
    Return the (singleton) StorageService.

    Driver selection (in priority order):
      1. force_driver argument  — for tests
      2. STORAGE_DRIVER env var  — local | r2 | memory
      3. Auto-detect: if R2_ENDPOINT is set → r2, else → local
    """
    global _instance
    if _instance is not None and force_driver is None:
        return _instance

    driver_name = (force_driver or os.environ.get("STORAGE_DRIVER", "")).lower()

    if not driver_name:
        # Auto-detect based on R2 config presence
        import storage as _s
        driver_name = "r2" if _s.R2_ENABLED else "local"

    if driver_name == "r2":
        driver = _R2Driver()
    elif driver_name == "memory":
        driver = _MemoryDriver()
    else:
        # Default: same directory as server.py (backend/media).
        # Using Path(__file__).parent avoids the hardcoded /app/backend/media
        # absolute path that does not exist in GitHub Actions runners.
        _default_media = str(Path(__file__).resolve().parent / "media")
        media_dir = os.environ.get("MEDIA_DIR", _default_media)
        driver = _LocalDriver(media_dir)

    svc = StorageService(driver)
    log.info("StorageService initialized: driver=%s", svc.driver_name)

    if force_driver is None:
        _instance = svc
    return svc


def reset_storage_service():
    """For tests only — reset the singleton."""
    global _instance
    _instance = None
