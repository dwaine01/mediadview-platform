# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""playlists_routes.py -- owner-facing playlist CRUD, publish/unpublish,
delivery status, share-link creation and pending-item moderation.

Fase 2B-4 (see docs/REFACTOR_FASE2_PLAN.md and docs/AGENT_COORDINATION.md).
Pure relocation of 12 handlers out of server.py: identical paths, methods,
decorators and logic, on a router with prefix="/api". No behavior change.

Staying in server.py: the 4 anonymous /public/playlists/{token}* routes
(share-link surface, no current_user), GET /player/{screen_id}/playlist,
GET /devices/{device_id}/playlist and GET /public/playlist (the HTML shell)
-- all player/device or public domain, for 2B-5.

Dependencies: gen_id, serialize_doc, _is_platform_admin, _can_view_playlist
and _bump_playlist_screens are threaded in (the last three are already
threaded into create_menus_routes since 2B-1 and stay defined in server.py).
_can_edit_playlist, _can_publish_playlist, _safe_playlist and
_playlist_or_404 are nested in the factory because they close over those
params (same pattern as _chunk_path in media_routes.py).
_validate_playlist_refs has no closure dependency -> module level.
_public_token_hash moved to media_utils.py because server.py's
_public_playlist needs it too. bump_playlist_version is NOT imported: only
the threaded _bump_playlist_screens wrapper calls it.
"""
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from database import db
from deps import get_current_user
from managed_portal_routes import create_audit_log as _audit
from media_utils import _public_token_hash
from playlist_domain import PLAYLIST_MODES, normalize_playlist_items, normalize_schedule
from rbac import Role, get_effective_role


class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = None
    management_mode: str = "admin"
    client_user_id: Optional[str] = None
    allow_client_publish: bool = False
    allowed_screen_ids: List[str] = Field(default_factory=list)
    items: List[dict] = Field(default_factory=list)


class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    management_mode: Optional[str] = None
    client_user_id: Optional[str] = None
    allow_client_publish: Optional[bool] = None
    allowed_screen_ids: Optional[List[str]] = None
    items: Optional[List[dict]] = None


class PlaylistPublish(BaseModel):
    screen_ids: List[str]
    schedule: Optional[dict] = None
    priority: int = 10


class PlaylistShare(BaseModel):
    permission: str = "editor"
    require_approval: bool = True
    expires_days: int = 30
    allow_upload: bool = True


async def _validate_playlist_refs(items: list[dict]) -> None:
    for item in items:
        collection = db.menus if item["type"] == "menu" else db.media if item["type"] == "media" else None
        if collection is not None and not await collection.find_one({"id": item["ref_id"]}, {"_id": 0, "id": 1}):
            raise HTTPException(400, f"Missing {item['type']} content: {item['ref_id']}")


def create_playlists_routes(gen_id, serialize_doc, _is_platform_admin,
                             _can_view_playlist, _bump_playlist_screens):
    router = APIRouter(prefix="/api", tags=["Playlists"])

    def _can_edit_playlist(playlist: dict, user: dict) -> bool:
        if _is_platform_admin(user) or playlist.get("owner_user_id") == user.get("id"):
            return True
        return playlist.get("management_mode") == "client" and playlist.get("client_user_id") == user.get("id")

    def _can_publish_playlist(playlist: dict, user: dict) -> bool:
        if _is_platform_admin(user):
            return True
        # MANAGED_VIEWER is strictly read-only — cannot publish even if allow_client_publish is set
        if get_effective_role(user) == Role.MANAGED_VIEWER:
            return False
        return bool(playlist.get("allow_client_publish")) and playlist.get("client_user_id") == user.get("id")

    def _safe_playlist(playlist: dict) -> dict:
        result = serialize_doc(dict(playlist))
        if isinstance(result.get("public_access"), dict):
            result["public_access"] = {
                key: value for key, value in result["public_access"].items()
                if key not in ("token_hash", "created_by_user_id")
            }
        return result

    async def _playlist_or_404(playlist_id: str, user: dict, edit: bool = False) -> dict:
        playlist = await db.playlists.find_one({"id": playlist_id}, {"_id": 0})
        if not playlist:
            raise HTTPException(404, "Playlist not found")
        allowed = _can_edit_playlist(playlist, user) if edit else _can_view_playlist(playlist, user)
        if not allowed:
            raise HTTPException(403, "Access denied")
        return playlist

    @router.get("/playlists")
    async def list_owned_playlists(current_user: dict = Depends(get_current_user)):
        query = {} if _is_platform_admin(current_user) else {"$or": [
            {"owner_user_id": current_user["id"]}, {"client_user_id": current_user["id"]}
        ]}
        playlists = await db.playlists.find(query, {"_id": 0}).sort("updated_at", -1).to_list(500)
        return [_safe_playlist(playlist) for playlist in playlists]

    @router.post("/playlists")
    async def create_owned_playlist(data: PlaylistCreate, current_user: dict = Depends(get_current_user)):
        mode = data.management_mode if data.management_mode in PLAYLIST_MODES else "admin"
        client_user_id = data.client_user_id
        if not _is_platform_admin(current_user):
            mode = "client"
            client_user_id = current_user["id"]
        elif client_user_id and not await db.users.find_one({"id": client_user_id}, {"_id": 0, "id": 1}):
            raise HTTPException(400, "Client account not found")
        try:
            items = normalize_playlist_items(data.items)
        except ValueError as error:
            raise HTTPException(400, str(error))
        await _validate_playlist_refs(items)
        now = datetime.utcnow()
        playlist = {
            "id": gen_id(), "name": data.name.strip()[:160], "description": (data.description or "")[:500],
            "created_by_user_id": current_user["id"], "owner_user_id": current_user["id"],
            "client_user_id": client_user_id, "management_mode": mode,
            "allow_client_publish": data.allow_client_publish if _is_platform_admin(current_user) else False,
            "allowed_screen_ids": list(dict.fromkeys(data.allowed_screen_ids)), "screen_ids": [],
            "items": items, "schedule": normalize_schedule(None), "priority": 10,
            "status": "draft", "version": 1, "pending_items": [],
            "created_at": now, "updated_at": now,
        }
        if not playlist["name"]:
            raise HTTPException(400, "Playlist name is required")
        await db.playlists.insert_one(playlist)
        return serialize_doc(playlist)

    @router.get("/playlists/{playlist_id}")
    async def get_owned_playlist(playlist_id: str, current_user: dict = Depends(get_current_user)):
        return _safe_playlist(await _playlist_or_404(playlist_id, current_user))

    @router.put("/playlists/{playlist_id}")
    async def update_owned_playlist(playlist_id: str, data: PlaylistUpdate,
                                    current_user: dict = Depends(get_current_user)):
        playlist = await _playlist_or_404(playlist_id, current_user, edit=True)
        incoming = data.dict(exclude_none=True)
        if not _is_platform_admin(current_user):
            for protected in ("management_mode", "client_user_id", "allow_client_publish", "allowed_screen_ids"):
                incoming.pop(protected, None)
        if "management_mode" in incoming and incoming["management_mode"] not in PLAYLIST_MODES:
            raise HTTPException(400, "Invalid management mode")
        if "items" in incoming:
            try:
                incoming["items"] = normalize_playlist_items(incoming["items"])
            except ValueError as error:
                raise HTTPException(400, str(error))
            await _validate_playlist_refs(incoming["items"])
        if "allowed_screen_ids" in incoming:
            incoming["allowed_screen_ids"] = list(dict.fromkeys(incoming["allowed_screen_ids"]))
        incoming.update({"updated_at": datetime.utcnow()})
        if "items" in incoming:
            incoming["version"] = int(playlist.get("version") or 0) + 1
        await db.playlists.update_one({"id": playlist_id}, {"$set": incoming})
        if "items" in incoming and playlist.get("screen_ids"):
            await _bump_playlist_screens(playlist["screen_ids"], "owned playlist content updated")
        return _safe_playlist(await db.playlists.find_one({"id": playlist_id}, {"_id": 0}))

    @router.delete("/playlists/{playlist_id}")
    async def delete_owned_playlist(playlist_id: str, current_user: dict = Depends(get_current_user)):
        playlist = await _playlist_or_404(playlist_id, current_user, edit=True)
        await db.playlists.delete_one({"id": playlist_id})
        await _bump_playlist_screens(playlist.get("screen_ids", []), "owned playlist deleted")
        return {"message": "Playlist deleted"}

    @router.get("/playlists/{playlist_id}/available-screens")
    async def playlist_available_screens(playlist_id: str, current_user: dict = Depends(get_current_user)):
        playlist = await _playlist_or_404(playlist_id, current_user)
        query = {"status": {"$ne": "deleted"}}
        if not _is_platform_admin(current_user):
            query["id"] = {"$in": playlist.get("allowed_screen_ids") or playlist.get("screen_ids") or []}
        screens = await db.screens.find(query, {"_id": 0, "id": 1, "name": 1, "location": 1, "status": 1}).to_list(500)
        return screens

    @router.post("/playlists/{playlist_id}/publish")
    async def publish_owned_playlist(playlist_id: str, data: PlaylistPublish,
                                     current_user: dict = Depends(get_current_user)):
        playlist = await _playlist_or_404(playlist_id, current_user, edit=True)
        if not _can_publish_playlist(playlist, current_user):
            raise HTTPException(403, "This playlist requires administrator publishing")
        if not playlist.get("items"):
            raise HTTPException(400, "Add at least one item before publishing")
        screen_ids = list(dict.fromkeys(data.screen_ids))
        if not screen_ids:
            raise HTTPException(400, "Select at least one screen")
        if not _is_platform_admin(current_user):
            allowed = set(playlist.get("allowed_screen_ids") or playlist.get("screen_ids") or [])
            if not set(screen_ids).issubset(allowed):
                raise HTTPException(403, "One or more screens are not assigned to this client")
        found = await db.screens.count_documents({"id": {"$in": screen_ids}, "status": {"$ne": "deleted"}})
        if found != len(screen_ids):
            raise HTTPException(400, "One or more screens were not found")
        previous = playlist.get("screen_ids") or []
        now = datetime.utcnow()
        update = {
            "screen_ids": screen_ids, "schedule": normalize_schedule(data.schedule),
            "priority": max(0, min(data.priority, 100)), "status": "published",
            "published_at": now, "published_by_user_id": current_user["id"], "updated_at": now,
            "version": int(playlist.get("version") or 0) + 1,
        }
        if _is_platform_admin(current_user):
            update["allowed_screen_ids"] = list(dict.fromkeys((playlist.get("allowed_screen_ids") or []) + screen_ids))
        await db.playlists.update_one({"id": playlist_id}, {"$set": update})
        await _bump_playlist_screens(previous + screen_ids, "owned playlist published")
        # ── Fase 4: Audit log ─────────────────────────────────────────────────────
        await _audit(
            db, action="playlist.published",
            user_id=current_user.get("id"), user_email=current_user.get("email"),
            resource_type="playlist", resource_id=playlist_id,
            details={"playlist_name": playlist.get("name"), "screen_count": len(screen_ids)},
        )
        return {"message": "Playlist published", "playlist_id": playlist_id,
                "screen_ids": screen_ids, "published_at": now.isoformat()}

    @router.post("/playlists/{playlist_id}/unpublish")
    async def unpublish_owned_playlist(playlist_id: str, current_user: dict = Depends(get_current_user)):
        playlist = await _playlist_or_404(playlist_id, current_user, edit=True)
        if not _can_publish_playlist(playlist, current_user):
            raise HTTPException(403, "Administrator publishing required")
        await db.playlists.update_one({"id": playlist_id}, {"$set": {
            "screen_ids": [], "status": "draft", "updated_at": datetime.utcnow()
        }})
        await _bump_playlist_screens(playlist.get("screen_ids", []), "owned playlist unpublished")
        return {"message": "Playlist unpublished"}

    @router.get("/playlists/{playlist_id}/delivery-status")
    async def playlist_delivery_status(playlist_id: str, current_user: dict = Depends(get_current_user)):
        playlist = await _playlist_or_404(playlist_id, current_user)
        screen_ids = playlist.get("screen_ids") or []
        screens = await db.screens.find({"id": {"$in": screen_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
        devices = await db.devices.find(
            {"screen_id": {"$in": screen_ids}},
            {"_id": 0, "screen_id": 1, "status": 1, "last_heartbeat": 1},
        ).sort("last_heartbeat", -1).to_list(500)
        by_screen = {}
        for device in devices:
            by_screen.setdefault(device.get("screen_id"), device)
        now = datetime.utcnow()
        delivery = []
        for screen in screens:
            device = by_screen.get(screen["id"], {})
            last_heartbeat = device.get("last_heartbeat")
            is_online = bool(last_heartbeat and (now - last_heartbeat).total_seconds() < 120)
            delivery.append({
                **screen,
                "device_status": "online" if is_online else "offline",
                "device_state": device.get("status", "unassigned"),
                "last_seen": serialize_doc(last_heartbeat),
            })
        return delivery

    @router.post("/playlists/{playlist_id}/share")
    async def share_owned_playlist(playlist_id: str, data: PlaylistShare, request: Request,
                                   current_user: dict = Depends(get_current_user)):
        await _playlist_or_404(playlist_id, current_user, edit=True)
        token = secrets.token_urlsafe(24)
        access = {
            "enabled": True, "token_hash": _public_token_hash(token),
            "permission": "editor" if data.permission == "editor" else "uploader",
            "require_approval": data.require_approval, "allow_upload": data.allow_upload,
            "expires_at": datetime.utcnow() + timedelta(days=max(1, min(data.expires_days, 365))),
            "created_at": datetime.utcnow(), "created_by_user_id": current_user["id"],
        }
        await db.playlists.update_one({"id": playlist_id}, {"$set": {"public_access": access}})
        origin = str(request.base_url).rstrip("/")
        url = f"{origin}/api/public/playlist?token={token}"
        return {"url": url, "qr_url": f"{origin}/api/public/playlists/{token}/qr",
                "expires_at": access["expires_at"].isoformat(), "require_approval": data.require_approval}

    @router.post("/playlists/{playlist_id}/pending/{item_id}/approve")
    async def approve_public_playlist_item(playlist_id: str, item_id: str,
                                           current_user: dict = Depends(get_current_user)):
        playlist = await _playlist_or_404(playlist_id, current_user, edit=True)
        pending = next((item for item in playlist.get("pending_items", []) if item.get("id") == item_id), None)
        if not pending:
            raise HTTPException(404, "Pending item not found")
        clean = {key: value for key, value in pending.items() if key not in ("submitted_at", "submission_status")}
        clean["order"] = len(playlist.get("items") or [])
        await db.playlists.update_one({"id": playlist_id}, {
            "$set": {"updated_at": datetime.utcnow()}, "$inc": {"version": 1}, "$push": {"items": clean},
            "$pull": {"pending_items": {"id": item_id}},
        })
        await _bump_playlist_screens(playlist.get("screen_ids", []), "public submission approved")
        return {"message": "Submission approved"}

    @router.delete("/playlists/{playlist_id}/pending/{item_id}")
    async def reject_public_playlist_item(playlist_id: str, item_id: str,
                                          current_user: dict = Depends(get_current_user)):
        await _playlist_or_404(playlist_id, current_user, edit=True)
        await db.playlists.update_one({"id": playlist_id}, {"$pull": {"pending_items": {"id": item_id}}})
        return {"message": "Submission rejected"}

    return router
