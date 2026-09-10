"""admin_devices_routes.py -- admin-panel device fleet management: CRUD,
activation, provisioning, power control, remote commands, player-release
publishing, proof-of-play logs, and the two admin dashboards (client-error
feed, platform analytics).

Fase 2B-6a of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md,
docs/FASE2B6_MAPA_RUTAS_ADMIN.md and docs/AGENT_COORDINATION.md). Pure
relocation of the 17 handlers below out of server.py: identical paths,
methods, decorators and logic, registered on a router with prefix="/api" so
the final routes match api_router exactly as before. No behavior change.

Scope: PR 1 of 3 for Fase 2B-6 (41 /admin/* + 5 /superadmin/* = 46 routes
total once 2B-6a/b/c are all done; see FASE2B6_MAPA_RUTAS_ADMIN.md for why
this is 46, not the plan's original estimate of 51). This PR takes the most
contiguous block (server.py L1887-2208, everything /admin/devices/* plus
/admin/player-release) plus 3 routes that share no helpers with 2B-6b
(campanas+widgets+pagos) or 2B-6c (superadmin+RBAC+customer-orders+vistas
HTML): list_client_errors and admin_analytics, grouped here because they
have zero shared dependencies with either other PR and keeping them out
would leave two orphan single-route files instead of one clean one.

These do NOT move (out of scope for 2B-6a, tracked for 2B-6b/c):
/admin/campaigns/*, /admin/widgets/*, /admin/payments, /admin/campaign-scheduler/*
(2B-6b); /superadmin/*, /admin/users*, /admin/rbac/*, /admin/customer-orders/*,
/admin/migrate-operation-types, /admin/*-view (2B-6c).

Dependency notes:
  - gen_id, serialize_doc and gen_activation_code are threaded in, same
    pattern as every prior phase (all three are already threaded into other
    factories too -- e.g. create_player_domain_routes -- because other,
    not-yet-moved code still needs them in server.py; moving their
    definitions would break that wiring for no benefit).
  - db (database.py) and require_admin (deps.py) are imported directly, same
    pattern as player_routes.py.
  - get_current_user (deps.py) is ALSO imported directly: set_player_release
    and get_player_release check `current_user.get("role") in (...)` by hand
    instead of using the require_admin dependency (pre-existing behavior,
    not changed here).
  - DeviceActivate and DeviceProvision move with their routes: grep-verified
    across all 141 files in backend/ that admin_activate_device and
    admin_provision_device are their only respective call sites anywhere in
    the codebase.

Known cosmetic leftover (same accepted precedent as 2B-5's three orphaned
section comments): the "# Device / Player Models" header comment in
server.py, which used to introduce DeviceActivate/DeviceProvision, is left
in place even though both models move here -- a comment-only artifact, not
touched, to keep this script a pure relocation.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from deps import get_current_user, require_admin

import logging
logger = logging.getLogger(__name__)


class DeviceActivate(BaseModel):
    activation_code: str
    screen_id: str
    device_name: Optional[str] = None
    tier: Optional[str] = None  # "tv_direct" or "player_dedicated"


class DeviceProvision(BaseModel):
    """Pre-provision a device before shipping (MediaView Player Dedicated)"""
    device_name: str
    screen_id: str
    server_url: str
    tier: str = "player_dedicated"
    reboot_time: str = "03:00"  # Nightly reboot time (HH:MM)
    notes: Optional[str] = None


def create_admin_devices_routes(gen_id, serialize_doc, gen_activation_code):
    router = APIRouter(prefix="/api", tags=["Admin Devices"])

    @router.get("/admin/client-errors")
    async def list_client_errors(limit: int = 50, admin: dict = Depends(require_admin)):
        errors = await db.client_errors.find({}).sort("created_at", -1).to_list(min(limit, 200))
        return serialize_doc(errors)

    @router.get("/admin/analytics")
    async def admin_analytics(admin: dict = Depends(require_admin)):
        total_users = await db.users.count_documents({"role": "customer"})
        total_screens = await db.screens.count_documents({})
        active_screens = await db.screens.count_documents({"status": "active"})
        total_campaigns = await db.campaigns.count_documents({})
        active_campaigns = await db.campaigns.count_documents({"status": "active"})
        pending_campaigns = await db.campaigns.count_documents({"status": "pending"})
        payments = await db.payments.find({"status": "completed"}).to_list(10000)
        total_revenue = sum(p.get("amount", 0) for p in payments)
        monthly = {}
        for p in payments:
            mk = p.get("created_at", datetime.utcnow()).strftime("%Y-%m")
            monthly[mk] = monthly.get(mk, 0) + p.get("amount", 0)
        recent = await db.campaigns.find({}).sort("created_at", -1).to_list(10)
        for c in recent:
            user = await db.users.find_one({"id": c.get("user_id")}, {"password_hash": 0})
            c["user_name"] = user.get("name", "Unknown") if user else "Unknown"
        return {
            "total_users": total_users, "total_screens": total_screens,
            "active_screens": active_screens, "total_campaigns": total_campaigns,
            "active_campaigns": active_campaigns, "pending_campaigns": pending_campaigns,
            "total_revenue": round(total_revenue, 2), "monthly_revenue": monthly,
            "recent_campaigns": serialize_doc(recent)
        }

    @router.post("/admin/player-release")
    async def set_player_release(payload: dict, current_user: dict = Depends(get_current_user)):
        """Admin: publish a new player APK release. All devices with a different version
    will be instructed to auto-update on their next heartbeat."""
        if current_user.get("role") not in ("superadmin", "admin"):
            raise HTTPException(403, "Admin required")
        required = ["version_name", "version_code", "apk_url"]
        for k in required:
            if not payload.get(k):
                raise HTTPException(400, f"Missing field: {k}")
        doc = {
            "_id": "player_release",
            "version_name": str(payload["version_name"]),
            "version_code": int(payload["version_code"]),
            "apk_url": payload["apk_url"],
            "sha256": payload.get("sha256"),
            "mandatory": bool(payload.get("mandatory", False)),
            "notes": payload.get("notes", ""),
            "published_at": datetime.utcnow().isoformat(),
            "published_by": current_user.get("email"),
        }
        await db.app_config.update_one({"_id": "player_release"}, {"$set": doc}, upsert=True)
        return {"ok": True, "release": doc}

    @router.get("/admin/player-release")
    async def get_player_release(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in ("superadmin", "admin"):
            raise HTTPException(403, "Admin required")
        cfg = await db.app_config.find_one({"_id": "player_release"})
        if cfg:
            cfg.pop("_id", None)
        return cfg or {}

    @router.get("/admin/devices/{device_id}/logs")
    async def admin_device_logs(device_id: str, limit: int = 50, admin: dict = Depends(require_admin)):
        """Get recent logs for a device."""
        logs = await db.device_logs.find({"device_id": device_id}).sort("created_at", -1).to_list(limit)
        return serialize_doc(logs)

    @router.get("/admin/devices/{device_id}/diagnostics")
    async def admin_device_diagnostics(device_id: str, admin: dict = Depends(require_admin)):
        """Get full diagnostics for a device."""
        device = await db.devices.find_one({"id": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        screen = None
        if device.get("screen_id"):
            screen = await db.screens.find_one({"id": device["screen_id"]})

        recent_logs = await db.device_logs.find({"device_id": device_id}).sort("created_at", -1).to_list(10)
        error_count = await db.device_logs.count_documents({"device_id": device_id, "level": {"$in": ["error", "crash"]}})

        return {
            "device": serialize_doc(device),
            "screen": serialize_doc(screen),
            "diagnostics": device.get("diagnostics", {}),
            "recent_logs": serialize_doc(recent_logs),
            "error_count": error_count,
            "is_online": device.get("last_heartbeat") and
                (datetime.utcnow() - device["last_heartbeat"]).total_seconds() < 120,
        }

    @router.put("/admin/devices/{device_id}/power-schedule")
    async def set_power_schedule(device_id: str, data: dict, admin: dict = Depends(require_admin)):
        """Set power on/off schedule for a device."""
        device = await db.devices.find_one({"id": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        schedule = {
            "enabled": data.get("enabled", True),
            "power_on": data.get("power_on", "08:00"),
            "power_off": data.get("power_off", "22:00"),
            "days": data.get("days", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]),
            "timezone": data.get("timezone", "America/New_York")
        }

        await db.devices.update_one({"id": device_id}, {"$set": {"power_schedule": schedule}})
        return {"message": "Power schedule updated", "schedule": schedule}

    @router.get("/admin/devices/{device_id}/power-schedule")
    async def get_power_schedule(device_id: str, admin: dict = Depends(require_admin)):
        """Get power schedule for a device."""
        device = await db.devices.find_one({"id": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return device.get("power_schedule", {"enabled": False, "power_on": "08:00", "power_off": "22:00", "days": ["mon","tue","wed","thu","fri","sat","sun"]})

    @router.post("/admin/devices/{device_id}/power")
    async def device_power_control(device_id: str, data: dict, admin: dict = Depends(require_admin)):
        """Remote power control: sleep, wake, restart."""
        device = await db.devices.find_one({"id": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        action = data.get("action", "")
        if action == "sleep":
            await db.devices.update_one({"id": device_id}, {"$set": {"pending_command": "sleep", "power_state": "sleeping"}})
        elif action == "wake":
            await db.devices.update_one({"id": device_id}, {"$set": {"pending_command": "wake", "power_state": "awake"}})
        elif action == "restart":
            await db.devices.update_one({"id": device_id}, {"$set": {"pending_command": "restart"}})
        else:
            raise HTTPException(status_code=400, detail="Invalid action. Use: sleep, wake, restart")

        return {"message": f"Command '{action}' sent to device"}

    @router.get("/admin/devices")
    async def admin_list_devices(status: Optional[str] = None, limit: int = 200,
                                 admin: dict = Depends(require_admin)):
        """List registered devices, newest first.

    PERF: the collection accumulates one `pending` document per un-activated
    player registration, so an unbounded list grew to 500 docs / ~300 KB and
    the panel spun for seconds. Default page size is 200; pass ?limit= to widen
    or ?status=active to filter.
    """
        query = {"status": status} if status else {}
        limit = max(1, min(limit, 500))
        devices = await db.devices.find(query).sort("created_at", -1).to_list(limit)
        if not devices:
            return []
        # P0 PERF FIX: batch-fetch related screens in 1 query instead of N sequential queries.
        # Before: N devices → N sequential DB round-trips
        # After:  N devices → 2 total queries (1 devices + 1 screens batch)
        screen_ids = list({d["screen_id"] for d in devices if d.get("screen_id")})
        screens_map = {s["id"]: s for s in await db.screens.find(
            {"id": {"$in": screen_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500)}
        for d in devices:
            sid = d.get("screen_id")
            d["screen_name"] = screens_map[sid].get("name", "Unknown") if (sid and sid in screens_map) else None
        return serialize_doc(devices)

    @router.post("/admin/devices/activate")
    async def admin_activate_device(data: DeviceActivate, admin: dict = Depends(require_admin)):
        """Admin enters activation code to link device to a screen."""
        device = await db.devices.find_one({
            "activation_code": data.activation_code.upper(),
            "status": "pending"
        })
        if not device:
            raise HTTPException(status_code=404, detail="Invalid or already used activation code")

        screen = await db.screens.find_one({"id": data.screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")

        # Check if screen already has a device
        existing = await db.devices.find_one({"screen_id": data.screen_id, "status": "active"})
        if existing:
            # Deactivate old device
            await db.devices.update_one(
                {"id": existing["id"]},
                {"$set": {"status": "disabled", "screen_id": None}}
            )

        await db.devices.update_one(
            {"id": device["id"]},
            {"$set": {
                "screen_id": data.screen_id,
                "status": "active",
                "device_name": data.device_name or device.get("device_name"),
                "tier": data.tier or "tv_direct",
                "reboot_time": "03:00",
                "activated_at": datetime.utcnow()
            }}
        )

        logger.info(f"Device {device['id']} activated for screen {screen.get('name')} (tier: {data.tier or 'tv_direct'})")
        return {
            "message": "Device activated successfully",
            "device_id": device["id"],
            "screen_id": data.screen_id,
            "screen_name": screen.get("name"),
            "tier": data.tier or "tv_direct"
        }

    @router.post("/admin/devices/provision")
    async def admin_provision_device(data: DeviceProvision, admin: dict = Depends(require_admin)):
        """Pre-provision a device for the MediaView Player Dedicated line.
    Creates a device record with pre-assigned screen, ready for first boot."""
        screen = await db.screens.find_one({"id": data.screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")

        code = gen_activation_code()
        device = {
            "id": gen_id(),
            "activation_code": code,
            "device_name": data.device_name,
            "device_info": {"provisioned": True, "server_url": data.server_url},
            "screen_id": data.screen_id,
            "status": "provisioned",
            "tier": data.tier,
            "reboot_time": data.reboot_time,
            "notes": data.notes,
            "last_heartbeat": None,
            "last_sync": None,
            "activated_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }
        await db.devices.insert_one(device)

        logger.info(f"Device pre-provisioned: {device['id']} for screen {screen.get('name')}")
        return {
            "message": "Device pre-provisioned",
            "device_id": device["id"],
            "activation_code": code,
            "screen_id": data.screen_id,
            "screen_name": screen.get("name"),
            "tier": data.tier,
            "setup_url": f"{data.server_url}/api/player/{data.screen_id}/web",
            "adb_command": f'adb shell am start -n com.mediaview.player/.MainActivity --es server_url "{data.server_url}" --es screen_id "{data.screen_id}"',
        }

    @router.delete("/admin/devices/{device_id}")
    async def admin_remove_device(device_id: str, admin: dict = Depends(require_admin)):
        """Remove/deactivate a device."""
        result = await db.devices.delete_one({"id": device_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"message": "Device removed"}

    @router.put("/admin/devices/{device_id}/reassign")
    async def admin_reassign_device(device_id: str, screen_id: str, admin: dict = Depends(require_admin)):
        """Reassign a device to a different screen."""
        device = await db.devices.find_one({"id": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")

        await db.devices.update_one(
            {"id": device_id},
            {"$set": {"screen_id": screen_id, "status": "active"}}
        )
        return {"message": f"Device reassigned to {screen.get('name')}"}

    @router.put("/admin/devices/{device_id}/unlink")
    async def admin_unlink_device(device_id: str, admin: dict = Depends(require_admin)):
        """Unlink a device from its screen (keep device registered)."""
        device = await db.devices.find_one({"id": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        await db.devices.update_one(
            {"id": device_id},
            {"$set": {"screen_id": None, "status": "pending"}}
        )
        return {"message": "Device unlinked from screen"}

    @router.get("/admin/playlogs")
    async def get_play_logs(screen_id: Optional[str] = None, days: int = 7, admin: dict = Depends(require_admin)):
        """Get proof of play report."""
        since = datetime.utcnow() - timedelta(days=days)
        query = {"played_at": {"$gte": since}}
        if screen_id:
            query["screen_id"] = screen_id
        logs = await db.play_logs.find(query).sort("played_at", -1).to_list(1000)
        # Enrich with media and screen names
        for log in logs:
            media = await db.media.find_one({"id": log.get("media_id")}, {"data": 0})
            screen = await db.screens.find_one({"id": log.get("screen_id")})
            log["media_name"] = media.get("filename", "Unknown") if media else "Deleted"
            log["screen_name"] = screen.get("name", "Unknown") if screen else "Unknown"

        # Stats
        total_plays = len(logs)
        unique_media = len(set(l.get("media_id") for l in logs))
        unique_screens = len(set(l.get("screen_id") for l in logs))
        total_seconds = sum(l.get("duration", 0) for l in logs)

        return {
            "stats": {
                "total_plays": total_plays,
                "unique_media": unique_media,
                "unique_screens": unique_screens,
                "total_play_time_minutes": round(total_seconds / 60, 1),
            },
            "logs": serialize_doc(logs[:200])
        }

    @router.put("/admin/devices/{device_id}/command")
    async def send_device_command(device_id: str, command: str, admin: dict = Depends(require_admin)):
        """Send an authenticated command to a paired player."""
        allowed = ["restart", "reload", "update", "clear_cache", "show_diagnostics", "hide_diagnostics"]
        if command not in allowed:
            raise HTTPException(status_code=400, detail=f"Invalid command. Use: {', '.join(allowed)}")
        device = await db.devices.find_one({"id": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        await db.devices.update_one(
            {"id": device_id},
            {"$set": {"pending_command": command, "command_sent_at": datetime.utcnow()}}
        )
        return {"message": f"Command '{command}' sent to device"}

    return router
