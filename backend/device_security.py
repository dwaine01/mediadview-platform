"""
device_security.py — Sprint 1: identidad y autenticación real del reproductor.

El `device_id` dejaba de ser secreto en cuanto aparecía en un log o en el panel,
así que ahora cada reproductor recibe un `device_token` propio en el registro y
lo envía en cada llamada (`X-Device-Token` o `Authorization: Bearer`).

Compatibilidad hacia atrás (obligatoria: hay players ya instalados):
  • Dispositivos sin token guardado siguen aceptados y se les adopta el primer
    token que emitan (modo gracia).
  • Cuando un dispositivo YA tiene token, la petición debe traerlo o se rechaza 401.
Solo se guarda el hash SHA-256 del token, nunca el token en claro.

También define la máquina de estados del player y los umbrales de heartbeat,
para que el panel derive el estado real y no lo invente.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, Request

# ── Estados del reproductor (fuente única de verdad) ──
PLAYER_STATES = (
    "BOOTING", "INITIALIZING", "UNPAIRED", "PAIRING", "PAIRED",
    "WAITING_FOR_ASSIGNMENT", "SYNCING", "DOWNLOADING", "VALIDATING",
    "READY", "PLAYING", "OFFLINE_PLAYING_CACHE", "DEGRADED",
    "ERROR", "RECOVERING", "UPDATING", "RESTARTING",
)

# ── Umbrales de conectividad (heartbeat cada 30 s) ──
HEARTBEAT_INTERVAL_SECONDS = 30
ONLINE_MAX_AGE_SECONDS = 90       # < 90 s  → ONLINE
STALE_MAX_AGE_SECONDS = 300       # < 5 min → STALE, luego OFFLINE


def normalize_player_state(value: str | None) -> str | None:
    if not value:
        return None
    candidate = str(value).strip().upper().replace("-", "_")
    return candidate if candidate in PLAYER_STATES else None


def connectivity_from_heartbeat(last_heartbeat: datetime | None, now: datetime | None = None) -> str:
    """ONLINE / STALE / OFFLINE / NEVER — derivado del heartbeat, nunca de la BD."""
    if not last_heartbeat:
        return "NEVER"
    age = ((now or datetime.utcnow()) - last_heartbeat).total_seconds()
    if age < ONLINE_MAX_AGE_SECONDS:
        return "ONLINE"
    if age < STALE_MAX_AGE_SECONDS:
        return "STALE"
    return "OFFLINE"


def new_device_token() -> tuple[str, str]:
    """Devuelve (token en claro para el player, hash para guardar)."""
    token = secrets.token_urlsafe(32)
    return token, hash_device_token(token)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_from_request(request: Request) -> str | None:
    header = request.headers.get("x-device-token")
    if header:
        return header.strip()
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def authenticate_device(db, device_id: str, request: Request) -> dict:
    """Carga el dispositivo y valida su token. Adopta el token en modo gracia."""
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    presented = token_from_request(request)
    stored_hash = device.get("device_token_hash")

    if stored_hash:
        if not presented or not secrets.compare_digest(hash_device_token(presented), stored_hash):
            raise HTTPException(status_code=401, detail="Invalid device token")
        return device

    # ── Modo gracia: player antiguo sin token ──
    if presented:
        await db.devices.update_one({"id": device_id}, {"$set": {
            "device_token_hash": hash_device_token(presented),
            "device_token_adopted_at": datetime.utcnow(),
        }})
        device["device_token_hash"] = hash_device_token(presented)
    else:
        await db.devices.update_one({"id": device_id}, {"$set": {
            "legacy_unauthenticated_at": datetime.utcnow(),
        }})
    return device


def sync_progress_payload(data: dict | None) -> dict | None:
    """Normaliza el progreso REAL informado por el player (nunca se inventa)."""
    if not data:
        return None
    files_total = max(0, int(data.get("files_total") or 0))
    files_done = max(0, min(int(data.get("files_done") or 0), files_total or 10_000))
    bytes_total = max(0, int(data.get("bytes_total") or 0))
    bytes_done = max(0, min(int(data.get("bytes_done") or 0), bytes_total or (1 << 62)))
    if bytes_total:
        percent = round(bytes_done * 100 / bytes_total, 1)
    elif files_total:
        percent = round(files_done * 100 / files_total, 1)
    else:
        return None
    return {
        "files_done": files_done,
        "files_total": files_total,
        "bytes_done": bytes_done,
        "bytes_total": bytes_total,
        "percent": min(100.0, percent),
        "manifest_version": data.get("manifest_version"),
        "current_file": str(data.get("current_file") or "")[:160] or None,
        "reported_at": datetime.utcnow(),
    }


def progress_is_fresh(progress: dict | None, max_age_seconds: int = 180) -> bool:
    reported = (progress or {}).get("reported_at")
    if not isinstance(reported, datetime):
        return False
    return datetime.utcnow() - reported < timedelta(seconds=max_age_seconds)
