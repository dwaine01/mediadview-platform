"""
workspace_routes.py — Tenant-scoped Customer Workspace API.
Phase 2C P1: Routes for SELF_SERVICE_OWNER / SELF_SERVICE_MANAGER roles.
All data is strictly scoped to user.organization_id — NO cross-tenant leakage.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from org_branding_routes import OrgLogoUpload, delete_org_logo, save_org_logo
import time as _time

from managed_portal_routes import create_audit_log as _audit
from playlist_domain import normalize_schedule, schedule_is_active, select_winning_playlist
from rbac import Role, get_effective_role

_WORKSPACE_ROLES = frozenset({
    Role.SELF_SERVICE_OWNER,
    Role.SELF_SERVICE_MANAGER,
    Role.SELF_SERVICE_STAFF,
})

# Roles allowed to add/connect screens and see billing
_SCREEN_ADMIN_ROLES = frozenset({Role.SELF_SERVICE_OWNER, Role.SELF_SERVICE_MANAGER})


def _ser(doc):
    if isinstance(doc, list):
        return [_ser(d) for d in doc]
    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            if k == "_id":
                continue
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            elif isinstance(v, (dict, list)):
                out[k] = _ser(v)
            else:
                out[k] = v
        return out
    return doc


def create_workspace_routes(db, get_current_user, require_admin, bump_playlist_version=None,
                            build_screen_items=None):
    router = APIRouter(prefix="/api/workspace", tags=["Workspace — Phase 2C"])

    async def require_workspace_user(current_user: dict = Depends(get_current_user)):
        """Gate: only SELF_SERVICE_OWNER and SELF_SERVICE_MANAGER can access workspace routes."""
        role = get_effective_role(current_user)
        if role not in _WORKSPACE_ROLES:
            raise HTTPException(
                status_code=403,
                detail="Workspace access requires a self-service role",
            )
        if current_user.get("must_change_password"):
            # Member is still using the temporary password set by the owner.
            raise HTTPException(
                status_code=428,
                detail="Debes crear tu propia contraseña antes de continuar.",
            )
        org_id = current_user.get("organization_id")
        if not org_id:
            raise HTTPException(
                status_code=403,
                detail="You must be associated with an organization. Complete account setup first.",
            )
        return current_user

    @router.get("/context", summary="Workspace context: org + subscription + plan stats")
    async def workspace_context(current_user: dict = Depends(require_workspace_user)):
        """Full workspace context: org info, subscription lifecycle, plan config, and stats."""
        org_id = current_user["organization_id"]

        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Phase 2C subscription (latest)
        sub = await db.subscriptions.find_one(
            {"org_id": org_id, "schema_version": 2},
            sort=[("created_at", -1)],
        )

        # Current pricing agreement
        pricing = None
        if sub and sub.get("current_pricing_agreement_id"):
            pricing = await db.pricing_agreements.find_one(
                {"id": sub["current_pricing_agreement_id"]}
            )

        # Plan config from plans collection
        plan_id = None
        if pricing:
            plan_id = pricing.get("plan_id")
        elif sub:
            plan_id = sub.get("plan")
        else:
            plan_id = org.get("plan", "free")

        plan_config = await db.plans.find_one({"plan_id": plan_id}) if plan_id else None

        # Stats (parallel-friendly counts)
        screen_count = await db.screens.count_documents({"organization_id": org_id})
        user_count   = await db.users.count_documents({"organization_id": org_id})

        # Devices — scoped through org screens
        org_screen_ids = [
            s["id"]
            for s in await db.screens.find(
                {"organization_id": org_id}, {"id": 1}
            ).to_list(1000)
        ]
        device_count = (
            await db.devices.count_documents({"screen_id": {"$in": org_screen_ids}})
            if org_screen_ids else 0
        )
        # Online = heartbeat within the last 2 minutes (same window the admin panel uses).
        online_count = (
            await db.devices.count_documents({
                "screen_id": {"$in": org_screen_ids},
                "last_heartbeat": {"$gte": datetime.utcnow() - timedelta(minutes=2)},
            })
            if org_screen_ids else 0
        )

        return {
            "organization": _ser(org),
            "subscription": _ser(sub),
            "pricing_agreement": _ser(pricing),
            "plan_config": _ser(plan_config),
            "stats": {
                "screens": screen_count,
                "users": user_count,
                "devices": device_count,
                "devices_online": online_count,
                "devices_offline": max(0, device_count - online_count),
            },
            "current_user": {
                "id": current_user.get("id"),
                "name": current_user.get("name"),
                "email": current_user.get("email"),
                "rbac_role": current_user.get("rbac_role"),
                "organization_id": org_id,
            },
        }

    @router.post("/logo", summary="Upload or replace the organization logo")
    async def workspace_upload_logo(data: OrgLogoUpload, current_user: dict = Depends(require_workspace_user)):
        _assert_owner(current_user, "Solo el dueño puede cambiar el logo del negocio.")
        org_id = current_user["organization_id"]
        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organización no encontrada")

        new_url = save_org_logo(data.logo_filename, data.logo_base64)
        await db.organizations.update_one(
            {"id": org_id}, {"$set": {"logo_url": new_url, "updated_at": datetime.utcnow()}}
        )
        delete_org_logo(org.get("logo_url"))
        await _log(current_user, "org.logo_updated", "organization", org_id, {})
        return {"logo_url": new_url}

    @router.delete("/logo", summary="Remove the organization logo")
    async def workspace_delete_logo(current_user: dict = Depends(require_workspace_user)):
        _assert_owner(current_user, "Solo el dueño puede cambiar el logo del negocio.")
        org_id = current_user["organization_id"]
        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organización no encontrada")

        await db.organizations.update_one(
            {"id": org_id}, {"$set": {"logo_url": None, "updated_at": datetime.utcnow()}}
        )
        delete_org_logo(org.get("logo_url"))
        await _log(current_user, "org.logo_removed", "organization", org_id, {})
        return {"logo_url": None}

    @router.get("/screens", summary="List org-scoped screens")
    async def workspace_screens(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        screens = await db.screens.find(
            {"organization_id": org_id}
        ).sort("created_at", -1).to_list(500)
        return _ser(screens)

    @router.get("/devices", summary="List org-scoped devices (via org screens)")
    async def workspace_devices(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        org_screens = await db.screens.find(
            {"organization_id": org_id}, {"id": 1, "name": 1}
        ).to_list(500)
        if not org_screens:
            return []
        screen_map = {s["id"]: s.get("name", "Unknown") for s in org_screens}
        screen_ids = list(screen_map.keys())
        devices = await db.devices.find(
            {"screen_id": {"$in": screen_ids}}
        ).sort("created_at", -1).to_list(500)
        result = []
        for d in devices:
            dd = _ser(d)
            dd["screen_name"] = screen_map.get(d.get("screen_id"), "Unknown")
            result.append(dd)
        return result

    @router.get("/media", summary="List org media library")
    async def workspace_media(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        # Collect all user IDs in this org
        org_user_ids = [
            u["id"]
            for u in await db.users.find(
                {"organization_id": org_id}, {"id": 1}
            ).to_list(500)
        ]
        # Fallback: also include the current user
        uid = current_user.get("id")
        if uid and uid not in org_user_ids:
            org_user_ids.append(uid)
        media = await db.media.find(
            {"user_id": {"$in": org_user_ids}}
        ).sort("created_at", -1).to_list(1000)
        return _ser(media)

    async def _log(user: dict, action: str, resource_type: str,
                   resource_id: str | None = None, details: dict | None = None) -> None:
        """Activity feed entry (who changed what, when). Never raises."""
        await _audit(
            db, action,
            user_id=user.get("id"), user_email=user.get("email"),
            resource_type=resource_type, resource_id=resource_id,
            details=details or {}, org_id=user.get("organization_id"),
        )

    @router.get("/now-playing", summary="Live thumbnail: what every screen is showing right now")
    async def workspace_now_playing(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        screens = await db.screens.find({"organization_id": org_id}, {"_id": 0}).to_list(200)
        devices = await db.devices.find(
            {"screen_id": {"$in": [s["id"] for s in screens]}},
            {"_id": 0, "screen_id": 1, "last_heartbeat": 1, "device_name": 1},
        ).to_list(400)
        beat_by_screen: dict[str, datetime] = {}
        for d in devices:
            hb = d.get("last_heartbeat")
            if hb and (d["screen_id"] not in beat_by_screen or hb > beat_by_screen[d["screen_id"]]):
                beat_by_screen[d["screen_id"]] = hb

        now = datetime.utcnow()
        epoch = int(_time.time())
        out = []
        for screen in screens:
            items = await build_screen_items(screen["id"]) if build_screen_items else []
            playable = [i for i in items if int(i.get("duration") or 0) > 0]
            cycle = sum(int(i.get("duration") or 0) for i in playable)
            current = None
            if cycle > 0:
                elapsed = epoch % cycle
                cursor = 0
                for index, item in enumerate(playable):
                    duration = int(item.get("duration") or 0)
                    if elapsed < cursor + duration:
                        is_menu = str(item.get("content_type")) == "widget"
                        current = {
                            "index": index + 1,
                            "total": len(playable),
                            "title": item.get("filename") or "Contenido",
                            "kind": "menu" if is_menu else ("video" if str(item.get("content_type") or "").startswith("video") else "image"),
                            "thumb_url": None if is_menu else item.get("media_url"),
                            "duration": duration,
                            "seconds_left": max(0, cursor + duration - elapsed),
                            "playlist_name": item.get("playlist_name"),
                        }
                        break
                    cursor += duration

            hb = beat_by_screen.get(screen["id"])
            out.append({
                "screen_id": screen["id"],
                "screen_name": screen.get("name") or "Pantalla",
                "location": screen.get("location"),
                "is_online": bool(hb and (now - hb).total_seconds() < 120),
                "last_seen_seconds": int((now - hb).total_seconds()) if hb else None,
                "cycle_seconds": cycle,
                "now_playing": current,
            })
        return out

    @router.get("/activity", summary="Activity feed for my organization")
    async def workspace_activity(limit: int = 60, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        events = await db.audit_logs.find(
            {"org_id": org_id}, {"_id": 0},
        ).sort("created_at", -1).to_list(max(1, min(limit, 200)))
        return _ser(events)

    async def _org_screen_ids(org_id: str) -> list[str]:
        return [
            s["id"]
            for s in await db.screens.find({"organization_id": org_id}, {"id": 1}).to_list(500)
        ]

    @router.get("/playlists", summary="List org-scoped playlists (drafts included)")
    async def workspace_playlists(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        screen_ids = await _org_screen_ids(org_id)
        query: dict = {"$or": [{"org_id": org_id}]}
        if screen_ids:
            query["$or"].append({"screen_ids": {"$in": screen_ids}})
        playlists = await db.playlists.find(query).sort("created_at", -1).to_list(500)
        return _ser(playlists)

    async def _build_playlist_items(raw_items, org_id: str) -> list[dict]:
        """Validates every item belongs to this org and normalises it for the player."""
        if raw_items is None:
            raw_items = []
        if not isinstance(raw_items, list):
            raise HTTPException(status_code=400, detail="items must be a list")

        org_user_ids = [
            u["id"] for u in await db.users.find({"organization_id": org_id}, {"id": 1}).to_list(500)
        ]
        items: list[dict] = []
        for index, raw in enumerate(raw_items[:200]):
            item_type = str((raw or {}).get("type") or "media").lower()
            ref_id = str((raw or {}).get("ref_id") or "").strip()
            if item_type not in ("media", "menu"):
                raise HTTPException(status_code=400, detail=f"Unsupported item type: {item_type}")
            if not ref_id:
                raise HTTPException(status_code=400, detail="Each item needs a ref_id")
            if item_type == "media":
                owned = await db.media.find_one(
                    {"id": ref_id, "user_id": {"$in": org_user_ids}}, {"id": 1, "filename": 1}
                )
            else:
                owned = await db.menus.find_one({"id": ref_id, "org_id": org_id}, {"id": 1, "name": 1})
            if not owned:
                raise HTTPException(status_code=404, detail="Content not found in your library")
            duration = int((raw or {}).get("duration") or 15)
            items.append({
                "id": str((raw or {}).get("id") or _uuid.uuid4()),
                "type": item_type,
                "ref_id": ref_id,
                "title": str((raw or {}).get("title") or owned.get("filename") or owned.get("name") or "Contenido")[:160],
                "duration": max(3, min(duration, 86_400)),
                "transition": "fade",
                "display_mode": str((raw or {}).get("display_mode") or "cover"),
                "order": index,
            })
        return items

    @router.post("/playlists", summary="Create an org playlist", status_code=201)
    async def workspace_create_playlist(data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        name = (data.get("name") or "").strip()[:160]
        if not name:
            raise HTTPException(status_code=400, detail="Playlist name is required")

        items = await _build_playlist_items(data.get("items"), org_id)

        now = datetime.utcnow()
        playlist = {
            "id": str(_uuid.uuid4()),
            "org_id": org_id,
            "name": name,
            "description": (data.get("description") or "")[:500],
            "created_by_user_id": current_user["id"],
            "owner_user_id": current_user["id"],
            "client_user_id": current_user["id"],
            "management_mode": "client",
            "allow_client_publish": True,
            "allowed_screen_ids": await _org_screen_ids(org_id),
            "screen_ids": [],
            "items": items,
            "schedule": {
                "mode": "always", "timezone": "America/New_York",
                "days": list(range(7)), "start_time": "00:00", "end_time": "23:59",
                "start_date": None, "end_date": None,
            },
            "priority": 10,
            "status": "draft",
            "version": 1,
            "pending_items": [],
            "created_at": now,
            "updated_at": now,
        }
        await db.playlists.insert_one(playlist)
        await _log(current_user, "playlist.created", "playlist", playlist["id"],
                   {"name": name, "items": len(items)})
        return _ser(playlist)

    @router.post("/playlists/{playlist_id}/publish", summary="Publish an org playlist to screens")
    async def workspace_publish_playlist(playlist_id: str, data: dict,
                                         current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        playlist = await db.playlists.find_one({"id": playlist_id, "org_id": org_id})
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        if not playlist.get("items"):
            raise HTTPException(status_code=400, detail="Add at least one item before publishing")

        org_screen_ids = await _org_screen_ids(org_id)
        screen_ids = [s for s in (data.get("screen_ids") or []) if s in org_screen_ids] or org_screen_ids
        if not screen_ids:
            raise HTTPException(status_code=400, detail="Connect a screen first")

        now = datetime.utcnow()
        await db.playlists.update_one({"id": playlist_id}, {"$set": {
            "screen_ids": screen_ids,
            "allowed_screen_ids": org_screen_ids,
            "status": "published",
            "published_at": now,
            "published_by_user_id": current_user["id"],
            "updated_at": now,
            "version": int(playlist.get("version") or 0) + 1,
        }})
        if bump_playlist_version:
            for sid in set((playlist.get("screen_ids") or []) + screen_ids):
                await bump_playlist_version(sid, reason="workspace playlist published")
        await _log(current_user, "playlist.published", "playlist", playlist_id,
                   {"name": playlist.get("name"), "screens": len(screen_ids)})
        return {
            "message": f"Playlist publicada en {len(screen_ids)} pantalla(s)",
            "playlist_id": playlist_id,
            "screen_ids": screen_ids,
        }

    @router.patch("/playlists/{playlist_id}", summary="Rename, reorder or retime playlist items")
    async def workspace_update_playlist(playlist_id: str, data: dict,
                                        current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        playlist = await db.playlists.find_one({"id": playlist_id, "org_id": org_id})
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        update: dict = {"updated_at": datetime.utcnow()}
        if "name" in data:
            name = (data.get("name") or "").strip()[:160]
            if not name:
                raise HTTPException(status_code=400, detail="Playlist name is required")
            update["name"] = name
        if "items" in data:
            update["items"] = await _build_playlist_items(data.get("items"), org_id)
            update["version"] = int(playlist.get("version") or 0) + 1
        if "schedule" in data:
            update["schedule"] = normalize_schedule(data.get("schedule"))
            update["version"] = int(playlist.get("version") or 0) + 1
        if "priority" in data:
            update["priority"] = max(0, min(int(data.get("priority") or 10), 100))

        await db.playlists.update_one({"id": playlist_id}, {"$set": update})
        await _log(current_user, "playlist.updated", "playlist", playlist_id, {
            "name": update.get("name", playlist.get("name")),
            "items": len(update["items"]) if "items" in update else len(playlist.get("items") or []),
        })
        if ("items" in update or "schedule" in update) and bump_playlist_version:
            for sid in set(playlist.get("screen_ids") or []):
                await bump_playlist_version(sid, reason="workspace playlist edited")
        return _ser({**playlist, **update})

    @router.delete("/playlists/{playlist_id}", summary="Delete an org playlist")
    async def workspace_delete_playlist(playlist_id: str,
                                        current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        playlist = await db.playlists.find_one({"id": playlist_id, "org_id": org_id})
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        await db.playlists.delete_one({"id": playlist_id})
        await _log(current_user, "playlist.deleted", "playlist", playlist_id,
                   {"name": playlist.get("name")})
        if bump_playlist_version:
            for sid in set(playlist.get("screen_ids") or []):
                await bump_playlist_version(sid, reason="workspace playlist deleted")
        return {"message": "Playlist eliminada", "playlist_id": playlist_id}

    @router.get("/schedules", summary="List org-scoped campaigns/schedules")
    async def workspace_schedules(current_user: dict = Depends(require_workspace_user)):
        """Dayparting view: every playlist with its time window and who is live now."""
        org_id = current_user["organization_id"]
        screens = await db.screens.find({"organization_id": org_id}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
        screen_names = {s["id"]: s.get("name") or "Pantalla" for s in screens}
        playlists = await db.playlists.find({"org_id": org_id}, {"_id": 0}).to_list(500)

        winners = {
            sid: (select_winning_playlist(
                [p for p in playlists if sid in (p.get("screen_ids") or []) and p.get("status") == "published"]
            ) or {}).get("id")
            for sid in screen_names
        }

        rows = []
        for p in sorted(playlists, key=lambda x: str(x.get("created_at") or ""), reverse=True):
            sched = normalize_schedule(p.get("schedule"))
            pl_screens = [sid for sid in (p.get("screen_ids") or []) if sid in screen_names]
            rows.append({
                "id": p["id"],
                "name": p.get("name"),
                "status": p.get("status", "draft"),
                "priority": p.get("priority", 10),
                "items_count": len(p.get("items") or []),
                "schedule": sched,
                "in_window": schedule_is_active(sched),
                "screen_ids": pl_screens,
                "screen_names": [screen_names[sid] for sid in pl_screens],
                "live_now": any(winners.get(sid) == p["id"] for sid in pl_screens),
            })
        return rows

    @router.get("/users", summary="List org users (excluding password hashes)")
    async def workspace_users(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        users = await db.users.find(
            {"organization_id": org_id},
            {"password_hash": 0, "_id": 0},
        ).sort("created_at", -1).to_list(500)
        return _ser(users)

    @router.get("/billing", summary="Billing: subscription + pricing agreement history")
    async def workspace_billing(current_user: dict = Depends(require_workspace_user)):
        _assert_owner(current_user, "Solo el dueño puede ver la facturación.")
        org_id = current_user["organization_id"]

        sub = await db.subscriptions.find_one(
            {"org_id": org_id, "schema_version": 2},
            sort=[("created_at", -1)],
        )

        pricing_history = []
        if sub:
            pas = await db.pricing_agreements.find(
                {"subscription_id": sub["id"]}
            ).sort("version", 1).to_list(50)
            pricing_history = _ser(pas)

        current_pa = None
        if sub and sub.get("current_pricing_agreement_id"):
            current_pa = await db.pricing_agreements.find_one(
                {"id": sub["current_pricing_agreement_id"]}
            )

        plan_id = (current_pa or {}).get("plan_id") or (sub or {}).get("plan")
        plan_config = await db.plans.find_one({"plan_id": plan_id}) if plan_id else None

        return {
            "subscription": _ser(sub),
            "current_pricing_agreement": _ser(current_pa),
            "pricing_history": pricing_history,
            "plan_config": _ser(plan_config),
        }

    # ══════════════════════════════════════════════════════════════════════
    # SCREEN MANAGEMENT — customer-side
    # ══════════════════════════════════════════════════════════════════════

    @router.post("/screens", summary="Create a new screen for the org", status_code=201)
    async def workspace_create_screen(data: dict, current_user: dict = Depends(require_workspace_user)):
        if get_effective_role(current_user) not in _SCREEN_ADMIN_ROLES:
            raise HTTPException(403, "Tu rol no puede agregar pantallas. Pide ayuda al dueño.")
        org_id = current_user["organization_id"]
        now = datetime.utcnow()

        screen_name = (data.get("name") or "").strip()
        if not screen_name:
            raise HTTPException(status_code=400, detail="Screen name is required")

        screen = {
            "id": str(_uuid.uuid4()),
            "name": screen_name,
            "organization_id": org_id,
            "location": data.get("location"),
            "status": "offline",
            "code": None,
            "active_menu_id": None,
            "active_playlist_id": None,
            "orientation": data.get("orientation", "landscape"),
            "created_by": current_user.get("id"),
            "created_at": now,
            "updated_at": now,
        }
        await db.screens.insert_one(screen)
        await _log(current_user, "screen.created", "screen", screen["id"], {"name": screen_name})
        return _ser(screen)

    def _assert_owner(user: dict, detail: str) -> None:
        if get_effective_role(user) != Role.SELF_SERVICE_OWNER:
            raise HTTPException(403, detail)

    @router.post("/screens/connect", summary="Connect pending device to org using 6-char activation code")
    async def workspace_connect_screen(data: dict, current_user: dict = Depends(require_workspace_user)):
        if get_effective_role(current_user) not in _SCREEN_ADMIN_ROLES:
            raise HTTPException(403, "Tu rol no puede conectar pantallas. Pide ayuda al dueño.")
        """
        Customer enters the code shown on their TV/device + a name for the screen.
        Finds the pending device, creates a screen, and links them — atomically.
        """
        org_id = current_user["organization_id"]
        now = datetime.utcnow()

        activation_code = (data.get("activation_code") or "").strip().upper()
        screen_name = (data.get("screen_name") or "").strip()

        if len(activation_code) < 6:
            raise HTTPException(status_code=400, detail="Activation code must be 6 characters")
        if not screen_name:
            raise HTTPException(status_code=400, detail="Screen name is required")

        device = await db.devices.find_one({"activation_code": activation_code, "status": "pending"})
        if not device:
            raise HTTPException(
                status_code=404,
                detail="Code not found or already used. Make sure the code on screen is correct and the device hasn't been connected yet.",
            )

        # Check plan screen limit
        sub = await db.subscriptions.find_one(
            {"org_id": org_id, "schema_version": 2}, sort=[("created_at", -1)]
        )
        current_pa = None
        if sub and sub.get("current_pricing_agreement_id"):
            current_pa = await db.pricing_agreements.find_one(
                {"id": sub["current_pricing_agreement_id"]}
            )
        plan_config = None
        if current_pa:
            plan_config = await db.plans.find_one({"plan_id": current_pa.get("plan_id")})

        current_count = await db.screens.count_documents({"organization_id": org_id})
        screens_limit = (current_pa or {}).get("screens_limit") or (plan_config or {}).get("screens_limit")
        if screens_limit and current_count >= screens_limit:
            raise HTTPException(
                status_code=400,
                detail=f"Screen limit reached ({screens_limit}). Upgrade your plan or add screen capacity.",
            )

        # Create screen
        screen = {
            "id": str(_uuid.uuid4()),
            "name": screen_name,
            "organization_id": org_id,
            "status": "active",
            "code": activation_code,
            "active_menu_id": None,
            "created_by": current_user.get("id"),
            "created_at": now,
            "updated_at": now,
        }
        await db.screens.insert_one(screen)
        await _log(current_user, "screen.connected", "screen", screen["id"], {"name": screen_name})

        # Activate device
        await db.devices.update_one(
            {"id": device["id"]},
            {"$set": {
                "screen_id": screen["id"],
                "status": "active",
                "device_name": screen_name,
                "activated_at": now,
            }},
        )

        return {
            "screen": _ser(screen),
            "device_id": device["id"],
            "message": f"Screen '{screen_name}' connected successfully!",
        }

    # ══════════════════════════════════════════════════════════════════════
    # MENU MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════

    @router.get("/menus", summary="List org menus")
    async def workspace_list_menus(current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menus = await db.menus.find({"org_id": org_id}).sort("updated_at", -1).to_list(200)
        return _ser(menus)

    @router.post("/menus", summary="Create a menu", status_code=201)
    async def workspace_create_menu(data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        now = datetime.utcnow()

        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Menu name is required")

        items = []
        for item_in in (data.get("items") or []):
            items.append({
                "id": str(_uuid.uuid4()),
                "name": (item_in.get("name") or "Item").strip(),
                "price": float(item_in.get("price", 0)),
                "description": item_in.get("description"),
                "category": item_in.get("category"),
                "available": bool(item_in.get("available", True)),
                "media_id": item_in.get("media_id"),
                "image_url": item_in.get("image_url"),
            })

        menu = {
            "id": str(_uuid.uuid4()),
            "org_id": org_id,
            "name": name,
            "description": data.get("description"),
            "items": items,
            "categories": list({i["category"] for i in items if i.get("category")}),
            "status": "draft",
            "source": data.get("source", "blank"),
            "screen_ids": [],
            "created_by": current_user.get("id"),
            "created_at": now,
            "updated_at": now,
        }
        await db.menus.insert_one(menu)
        await _log(current_user, "menu.created", "menu", menu["id"],
                   {"name": name, "items": len(items), "source": menu["source"]})
        return _ser(menu)

    @router.get("/menus/{menu_id}", summary="Get a single menu with items")
    async def workspace_get_menu(menu_id: str, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        return _ser(menu)

    @router.put("/menus/{menu_id}", summary="Update menu name/description")
    async def workspace_update_menu(menu_id: str, data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        now = datetime.utcnow()
        update: dict = {"updated_at": now}
        if "name" in data:
            update["name"] = (data["name"] or "").strip()
        if "description" in data:
            update["description"] = data["description"]
        await db.menus.update_one({"id": menu_id}, {"$set": update})
        await _log(current_user, "menu.updated", "menu", menu_id,
                   {"name": update.get("name", menu.get("name"))})
        return _ser({**menu, **update})

    @router.delete("/menus/{menu_id}", summary="Delete a menu")
    async def workspace_delete_menu(menu_id: str, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        await db.menus.delete_one({"id": menu_id})
        await _log(current_user, "menu.deleted", "menu", menu_id, {"name": menu.get("name")})
        return {"message": "Menu deleted", "menu_id": menu_id}

    @router.post("/menus/{menu_id}/items", summary="Add item to menu", status_code=201)
    async def workspace_add_menu_item(menu_id: str, data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Item name is required")
        item = {
            "id": str(_uuid.uuid4()),
            "name": name,
            "price": float(data.get("price", 0)),
            "description": data.get("description"),
            "category": data.get("category"),
            "available": bool(data.get("available", True)),
            "media_id": data.get("media_id"),
            "image_url": data.get("image_url"),
        }
        now = datetime.utcnow()
        await db.menus.update_one(
            {"id": menu_id},
            {"$push": {"items": item}, "$set": {"updated_at": now}},
        )
        await _log(current_user, "menu_item.added", "menu", menu_id,
                   {"menu_name": menu.get("name"), "item": item["name"], "price": item["price"]})
        return _ser(item)

    @router.put("/menus/{menu_id}/items/{item_id}", summary="Update a menu item")
    async def workspace_update_menu_item(
        menu_id: str, item_id: str, data: dict, current_user: dict = Depends(require_workspace_user)
    ):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        now = datetime.utcnow()
        upd: dict = {"updated_at": now}
        for f in ["name", "price", "description", "category", "available", "media_id", "image_url"]:
            if f in data:
                upd[f"items.$.{f}"] = data[f]
        await db.menus.update_one(
            {"id": menu_id, "items.id": item_id},
            {"$set": upd},
        )
        previous = next((i for i in (menu.get("items") or []) if i.get("id") == item_id), {})
        details = {"menu_name": menu.get("name"), "item": data.get("name") or previous.get("name")}
        if "price" in data and float(data["price"]) != float(previous.get("price") or 0):
            details["price_from"] = previous.get("price")
            details["price_to"] = data["price"]
        if "image_url" in data or "media_id" in data:
            details["photo_changed"] = True
        await _log(current_user, "menu_item.updated", "menu", menu_id, details)
        return {"message": "Item updated", "item_id": item_id}

    @router.delete("/menus/{menu_id}/items/{item_id}", summary="Remove a menu item")
    async def workspace_delete_menu_item(
        menu_id: str, item_id: str, current_user: dict = Depends(require_workspace_user)
    ):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        now = datetime.utcnow()
        await db.menus.update_one(
            {"id": menu_id},
            {"$pull": {"items": {"id": item_id}}, "$set": {"updated_at": now}},
        )
        removed = next((i for i in (menu.get("items") or []) if i.get("id") == item_id), {})
        await _log(current_user, "menu_item.deleted", "menu", menu_id,
                   {"menu_name": menu.get("name"), "item": removed.get("name")})
        return {"message": "Item removed", "item_id": item_id}

    @router.post("/menus/{menu_id}/publish", summary="Publish menu to screens")
    async def workspace_publish_menu(menu_id: str, data: dict, current_user: dict = Depends(require_workspace_user)):
        org_id = current_user["organization_id"]
        menu = await db.menus.find_one({"id": menu_id, "org_id": org_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        screen_ids = data.get("screen_ids") or []
        # Default: publish to all org screens
        if not screen_ids:
            org_screens = await db.screens.find({"organization_id": org_id}, {"id": 1}).to_list(100)
            screen_ids = [s["id"] for s in org_screens]
        now = datetime.utcnow()
        await db.menus.update_one(
            {"id": menu_id},
            {"$set": {"status": "published", "screen_ids": screen_ids, "published_at": now, "updated_at": now}},
        )
        if screen_ids:
            await db.screens.update_many(
                {"id": {"$in": screen_ids}, "organization_id": org_id},
                {"$set": {"active_menu_id": menu_id, "updated_at": now}},
            )
        await _log(current_user, "menu.published", "menu", menu_id,
                   {"name": menu.get("name"), "screens": len(screen_ids)})
        return {
            "message": f"Menu '{menu['name']}' published to {len(screen_ids)} screen(s)",
            "menu_id": menu_id,
            "screen_ids": screen_ids,
        }

    # ══════════════════════════════════════════════════════════════════════
    # BILLING — add screens + cost preview
    # ══════════════════════════════════════════════════════════════════════

    @router.get("/billing/screen-cost", summary="Preview cost for adding more screens")
    async def workspace_screen_cost(additional_screens: int = 1, current_user: dict = Depends(require_workspace_user)):
        _assert_owner(current_user, "Solo el dueño puede ver los costos del plan.")
        org_id = current_user["organization_id"]
        if additional_screens < 1:
            raise HTTPException(status_code=400, detail="Must specify at least 1 additional screen")
        sub = await db.subscriptions.find_one({"org_id": org_id, "schema_version": 2}, sort=[("created_at", -1)])
        if not sub:
            raise HTTPException(status_code=404, detail="No subscription found")
        pa = None
        if sub.get("current_pricing_agreement_id"):
            pa = await db.pricing_agreements.find_one({"id": sub["current_pricing_agreement_id"]})
        if not pa:
            raise HTTPException(status_code=400, detail="No pricing agreement found")
        plan_config = await db.plans.find_one({"plan_id": pa.get("plan_id")}) if pa.get("plan_id") else None
        current_count = await db.screens.count_documents({"organization_id": org_id})
        new_total = current_count + additional_screens
        extra_price = float(pa.get("overage_price_per_screen") or (plan_config or {}).get("price_per_extra_screen") or 0)
        base_price = float(pa.get("agreed_monthly_price") or 0)
        added_cost = extra_price * additional_screens
        new_monthly = base_price + added_cost
        screens_limit = pa.get("screens_limit") or (plan_config or {}).get("screens_limit")
        if screens_limit and new_total > screens_limit:
            raise HTTPException(
                status_code=400,
                detail=f"Adding {additional_screens} screen(s) would exceed your plan limit ({screens_limit}).",
            )
        return {
            "current_screens": current_count,
            "additional_screens": additional_screens,
            "new_total_screens": new_total,
            "current_monthly": base_price,
            "added_cost": added_cost,
            "new_monthly": new_monthly,
            "extra_price_per_screen": extra_price,
            "screens_included": pa.get("screens_included", 0),
            "screens_limit": screens_limit,
            "currency": "USD",
        }

    @router.post("/billing/add-screens", summary="Add screens — creates new PricingAgreement version")
    async def workspace_add_screens(data: dict, current_user: dict = Depends(require_workspace_user)):
        _assert_owner(current_user, "Solo el dueño puede cambiar el plan.")
        org_id = current_user["organization_id"]
        additional_screens = int(data.get("additional_screens", 1))
        if additional_screens < 1:
            raise HTTPException(status_code=400, detail="Must add at least 1 screen")
        sub = await db.subscriptions.find_one({"org_id": org_id, "schema_version": 2}, sort=[("created_at", -1)])
        if not sub:
            raise HTTPException(status_code=404, detail="No active subscription found")
        pa = None
        if sub.get("current_pricing_agreement_id"):
            pa = await db.pricing_agreements.find_one({"id": sub["current_pricing_agreement_id"]})
        if not pa:
            raise HTTPException(status_code=400, detail="No pricing agreement found")
        plan_config = await db.plans.find_one({"plan_id": pa.get("plan_id")}) if pa.get("plan_id") else None
        screens_limit = pa.get("screens_limit") or (plan_config or {}).get("screens_limit")
        current_count = await db.screens.count_documents({"organization_id": org_id})
        if screens_limit and (current_count + additional_screens) > screens_limit:
            raise HTTPException(status_code=400, detail=f"Screen limit {screens_limit} would be exceeded")
        extra_price = float(pa.get("overage_price_per_screen") or (plan_config or {}).get("price_per_extra_screen") or 0)
        base_price = float(pa.get("agreed_monthly_price") or 0)
        added_cost = extra_price * additional_screens
        new_monthly = base_price + added_cost
        new_screens_included = (pa.get("screens_included") or 0) + additional_screens
        now = datetime.utcnow()
        # Create new PA version (preserves history)
        new_pa = {
            k: v for k, v in pa.items() if k != "_id"
        }
        new_pa.update({
            "id": str(_uuid.uuid4()),
            "version": (pa.get("version") or 1) + 1,
            "screens_included": new_screens_included,
            "agreed_monthly_price": new_monthly,
            "effective_from": now.isoformat(),
            "created_at": now,
            "notes": f"Added {additional_screens} screen(s). Was: {pa.get('screens_included')} screens @ ${base_price:.2f}/mo",
            "created_by": current_user.get("email", "workspace"),
        })
        await db.pricing_agreements.insert_one(new_pa)
        await db.subscriptions.update_one(
            {"id": sub["id"]},
            {"$set": {"current_pricing_agreement_id": new_pa["id"], "updated_at": now}},
        )
        return {
            "message": f"Added {additional_screens} screen(s). New monthly: ${new_monthly:.2f}",
            "added_screens": additional_screens,
            "new_monthly": new_monthly,
            "new_screens_included": new_screens_included,
            "pricing_agreement": _ser(new_pa),
        }

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC: Player content endpoint (device_id as auth token)
    # ══════════════════════════════════════════════════════════════════════

    @router.get("/player/{device_id}/content", summary="Player fetches its active content (public)")
    async def player_content(device_id: str):
        """No auth — device_id (UUID) acts as the access token. Returns pending code or active menu."""
        device = await db.devices.find_one({"id": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        if device.get("status") != "active" or not device.get("screen_id"):
            return {
                "status": "pending",
                "activation_code": device.get("activation_code"),
                "device_id": device_id,
                "message": "Enter this code in your MediaView workspace to activate this screen.",
            }
        screen = await db.screens.find_one({"id": device["screen_id"]})
        if not screen:
            return {"status": "no_screen", "device_id": device_id}
        menu = None
        if screen.get("active_menu_id"):
            menu = await db.menus.find_one({"id": screen["active_menu_id"]})
        if menu:
            return {"status": "menu", "screen": _ser(screen), "menu": _ser(menu)}
        return {"status": "no_content", "screen": _ser(screen), "device_id": device_id,
                "message": "Connected! Waiting for content to be published."}

    return router
