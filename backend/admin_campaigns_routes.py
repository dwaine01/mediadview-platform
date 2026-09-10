"""admin_campaigns_routes.py -- admin-panel campaign moderation (list/
approve/reject/repair/remove-media), widgets CRUD, admin payments view, and
Campaign Scheduler monitoring (status/run-now).

Fase 2B-6b of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md,
docs/FASE2B6_MAPA_RUTAS_ADMIN.md and docs/AGENT_COORDINATION.md). Pure
relocation of the 12 handlers below out of server.py: identical paths,
methods, decorators and logic, registered on a router with prefix="/api" so
the final routes match api_router exactly as before. No behavior change.

Scope: PR 2 of 3 for Fase 2B-6. These do NOT move (out of scope for 2B-6b,
tracked for 2B-6c or a future PR): /superadmin/*, /admin/users*, /admin/rbac/*,
/admin/customer-orders/*, /admin/migrate-operation-types, /admin/*-view
(2B-6c); the 6 /campaigns/* CLIENT-facing routes stay in server.py -- see
dependency note on normalise_schedule below for why they can't move
independently of this decision.

Dependency notes:
  - gen_id, serialize_doc and MEDIA_DIR are threaded in, same pattern as
    every prior phase (MEDIA_DIR is already threaded into media_routes.py
    and player_routes.py for the same reason: other, not-yet-moved code
    still needs it in server.py).
  - db (database.py) and require_admin (deps.py) are imported directly.
  - bump_playlist_version and PLAYABLE_STATUSES (media_utils.py) are
    imported directly, exactly as server.py already does since Fase 2A/2B-2.
  - _media_has_inline_bytes (media_utils.py) is imported directly: needed
    only by _media_is_available (see below), same pattern server.py itself
    uses.
  - _media_is_available moves here as a plain module-level function
    (dependency-free beyond MEDIA_DIR, os and _media_has_inline_bytes, all
    imported/threaded): grep-verified across every file in backend/ that
    admin_list_campaigns is its only call site anywhere in the codebase.
  - WIDGET_TYPES and WidgetCreate move here as a plain constant and model:
    grep-verified across every file in backend/ that create_widget is their
    only respective call site anywhere in the codebase.
  - normalise_schedule moved to media_utils.py instead of being threaded: it
    is used both by admin_repair_campaigns (moving here) and by
    create_campaign/update_campaign (client-facing, staying in server.py) --
    relocating it to the shared dependency-free module lets both sides
    import it directly, same treatment as _norm_date in Fase 2B-5. This one
    is load-bearing, not just cosmetic: backend/tests/test_playlist_pipeline.py
    does `from server import (..., normalise_schedule, ...)` directly, so
    server.py's copy is replaced with a one-line re-import rather than just
    deleted. Dependency-free beyond _norm_date, which media_utils.py has
    held since 2B-5 -- no new import needed there.
  - get_campaign_scheduler and run_campaign_scheduler (campaign_scheduler.py)
    are imported directly. The `from campaign_scheduler import
    run_campaign_scheduler, get_campaign_scheduler` line in server.py is
    deleted entirely: grep-verified both names have zero remaining call
    sites in server.py once campaign_scheduler_status/run_now move (they
    were used by no other route) -- this is dead-import cleanup, not a
    behavior change, same discipline as the device_security/storage blocks
    deleted in Fase 2B-5.

Known cosmetic leftovers (same accepted precedent as 2B-5's three orphaned
section comments -- comments themselves are never touched, to keep this
script a pure relocation): the "# ============ WIDGETS / INTEGRATIONS
============" section header and the "# -- Fase 3: Campaign Scheduler
monitoring endpoints --" section header both become orphaned in server.py
(everything they introduced moves here), left in place untouched.
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from campaign_scheduler import get_campaign_scheduler, run_campaign_scheduler
from database import db
from deps import require_admin
from media_utils import (
    MEDIA_METADATA_PROJECTION,
    PLAYABLE_STATUSES,
    _media_has_inline_bytes,
    bump_playlist_version,
    normalise_schedule,
)


WIDGET_TYPES = ["weather", "clock", "ticker", "qrcode", "countdown", "slides", "youtube", "webpage", "menu", "calendar"]


class WidgetCreate(BaseModel):
    screen_id: str
    widget_type: str
    name: str
    config: dict = {}
    duration: int = 30
    enabled: bool = True


def create_admin_campaigns_routes(gen_id, serialize_doc, MEDIA_DIR):
    router = APIRouter(prefix="/api", tags=["Admin Campaigns"])

    async def _media_is_available(media: dict) -> bool:
        """True when the bytes can still be served to a player or the panel.

    Object storage keeps a public URL; legacy media needs either the disk copy
    (which Render wipes on every deploy) or the base64 mirror in Mongo.
    """
        if media.get("public_url") or media.get("storage") in ("r2", "s3"):
            return True
        stored = media.get("stored_filename")
        if stored and os.path.isfile(os.path.join(MEDIA_DIR, stored)):
            return True
        return await _media_has_inline_bytes(media["id"])

    @router.get("/admin/campaigns")
    async def admin_list_campaigns(status: Optional[str] = None, admin: dict = Depends(require_admin)):
        query = {}
        if status:
            query["status"] = status
        campaigns = await db.campaigns.find(query).sort("created_at", -1).to_list(500)
        if not campaigns:
            return []
        # P0 PERF FIX: batch-fetch related screens and users in 2 queries
        # instead of the previous 2×N sequential queries (N=number of campaigns).
        # Before: 15 campaigns → 30 sequential DB round-trips → 15-30 s on Atlas
        # After:  15 campaigns → 3 total queries             → < 500 ms
        screen_ids = list({c.get("screen_id") for c in campaigns if c.get("screen_id")})
        user_ids   = list({c.get("user_id")   for c in campaigns if c.get("user_id")})
        screens_map = {s["id"]: s for s in await db.screens.find({"id": {"$in": screen_ids}},
            # PERF: the embedded screen is only used for name/location/pricing.
            # Dropping `advertising` removes a ~100 KB base64 photo per campaign
            # (11 campaigns previously produced a 5.4 MB response).
            {"advertising": 0}).to_list(500)}
        users_map   = {u["id"]: u for u in await db.users.find(
            {"id": {"$in": user_ids}}, {"password_hash": 0}).to_list(500)}
        media_ids = list({m for c in campaigns for m in (c.get("media_ids") or [])})
        media_map = {m["id"]: m for m in await db.media.find(
            {"id": {"$in": media_ids}}, MEDIA_METADATA_PROJECTION).to_list(1000)}
        for c in campaigns:
            c["screen"] = serialize_doc(screens_map.get(c.get("screen_id")))
            c["user"]   = serialize_doc(users_map.get(c.get("user_id")))
            # The panel needs to know the kind (a video cannot render in an <img>)
            # and whether the file is still there, so it can ask the customer to
            # re-upload instead of showing an empty box.
            info = []
            for mid in (c.get("media_ids") or []):
                media = media_map.get(mid)
                if not media:
                    info.append({"id": mid, "type": None, "available": False})
                    continue
                info.append({
                    "id": mid,
                    "filename": media.get("filename"),
                    "type": media.get("type"),
                    "content_type": media.get("content_type"),
                    "orientation": media.get("orientation"),
                    "available": await _media_is_available(media),
                })
            c["media_info"] = info
            c["media_available"] = all(i["available"] for i in info) if info else False
        return serialize_doc(campaigns)

    @router.put("/admin/campaigns/{campaign_id}/approve")
    async def admin_approve(campaign_id: str, admin: dict = Depends(require_admin)):
        campaign = await db.campaigns.find_one({"id": campaign_id})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if campaign["status"] != "pending":
            raise HTTPException(status_code=400, detail="Only pending campaigns can be approved")
        new_status = "approved"
        try:
            start = datetime.strptime(campaign.get("schedule", {}).get("start_date", ""), "%Y-%m-%d")
            if start.date() <= datetime.utcnow().date():
                new_status = "active"
        except Exception:
            pass
        await db.campaigns.update_one(
            {"id": campaign_id},
            {"$set": {"status": new_status, "admin_notes": f"Approved by {admin['name']}",
                      "updated_at": datetime.utcnow()}}
        )
        await bump_playlist_version(campaign.get("screen_id"), reason=f"campaign {new_status}")
        return {"message": f"Campaign {new_status}"}

    @router.put("/admin/campaigns/{campaign_id}/reject")
    async def admin_reject(campaign_id: str, notes: Optional[str] = None, admin: dict = Depends(require_admin)):
        campaign = await db.campaigns.find_one({"id": campaign_id})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        was_playable = campaign.get("status") in PLAYABLE_STATUSES
        await db.campaigns.update_one(
            {"id": campaign_id},
            {"$set": {"status": "rejected",
                      "admin_notes": notes or f"Rejected by {admin['name']}",
                      "updated_at": datetime.utcnow()}}
        )
        if was_playable:
            await bump_playlist_version(campaign.get("screen_id"), reason="campaign rejected")
        return {"message": "Campaign rejected"}

    @router.get("/admin/payments")
    async def admin_list_payments(admin: dict = Depends(require_admin)):
        """List ALL payments (admin view)."""
        payments = await db.payments.find({}).sort("created_at", -1).to_list(500)
        enriched = []
        for p in payments:
            campaign = await db.campaigns.find_one({"id": p.get("campaign_id")})
            user = await db.users.find_one({"id": p.get("user_id")}, {"password_hash": 0})
            if campaign:
                screen = await db.screens.find_one({"id": campaign.get("screen_id")})
                p["campaign_name"] = campaign.get("name", "")
                p["screen_name"] = screen.get("name", "") if screen else ""
            p["user_name"] = user.get("name", "") if user else ""
            enriched.append(p)
        return serialize_doc(enriched)

    @router.post("/admin/campaigns/repair")
    async def admin_repair_campaigns(admin: dict = Depends(require_admin)):
        """MAINTENANCE: normalise every campaign's schedule (empty '' -> None)
    and prune media_ids that reference deleted media. Campaigns that end
    up without any media are FLAGGED with needs_attention=True instead of
    being silently emptied — the admin dashboard should surface them.
    """
        report = {"total": 0, "date_normalised": 0, "media_pruned": 0,
                  "flagged_needs_attention": 0, "details": []}
        campaigns = await db.campaigns.find({}).to_list(2000)
        report["total"] = len(campaigns)

        for c in campaigns:
            cid = c.get("id")
            sched_before = c.get("schedule", {}) or {}
            sched = normalise_schedule(sched_before)
            updates = {}
            changes = []

            if sched != sched_before:
                updates["schedule"] = sched
                report["date_normalised"] += 1
                if sched.get("start_date") != sched_before.get("start_date"):
                    changes.append(f"start_date {sched_before.get('start_date')!r} -> {sched.get('start_date')!r}")
                if sched.get("end_date") != sched_before.get("end_date"):
                    changes.append(f"end_date {sched_before.get('end_date')!r} -> {sched.get('end_date')!r}")

            mids = c.get("media_ids", []) or []
            clean_mids = []
            removed = []
            for mid in mids:
                if await db.media.find_one({"id": mid}, {"_id": 1}):
                    clean_mids.append(mid)
                else:
                    removed.append(mid)
            if removed:
                updates["media_ids"] = clean_mids
                report["media_pruned"] += len(removed)
                changes.append(f"removed {len(removed)} missing media id(s)")

            # Flag campaigns that end up with no valid media so an admin can act.
            needs_flag = (not clean_mids) and c.get("status") in PLAYABLE_STATUSES
            if needs_flag and not c.get("needs_attention"):
                updates["needs_attention"] = True
                report["flagged_needs_attention"] += 1
                changes.append("flagged needs_attention=true (no valid media)")

            if updates:
                updates["updated_at"] = datetime.utcnow()
                await db.campaigns.update_one({"id": cid}, {"$set": updates})
                await bump_playlist_version(c.get("screen_id"), reason="repair")
                report["details"].append({
                    "campaign_id": cid,
                    "name": c.get("name"),
                    "changes": changes,
                })

        return report

    @router.post("/admin/widgets")
    async def create_widget(data: WidgetCreate, admin: dict = Depends(require_admin)):
        if data.widget_type not in WIDGET_TYPES:
            raise HTTPException(status_code=400, detail=f"Type must be: {', '.join(WIDGET_TYPES)}")
        widget = {
            "id": gen_id(), "screen_id": data.screen_id, "widget_type": data.widget_type,
            "name": data.name, "config": data.config, "duration": data.duration,
            "enabled": data.enabled, "created_at": datetime.utcnow()
        }
        await db.widgets.insert_one(widget)
        return serialize_doc(widget)

    @router.get("/admin/widgets")
    async def list_widgets(screen_id: Optional[str] = None, admin: dict = Depends(require_admin)):
        query = {"screen_id": screen_id} if screen_id else {}
        widgets = await db.widgets.find(query).sort("created_at", -1).to_list(100)
        return serialize_doc(widgets)

    @router.delete("/admin/widgets/{widget_id}")
    async def delete_widget(widget_id: str, admin: dict = Depends(require_admin)):
        w = await db.widgets.find_one({"id": widget_id})
        await db.widgets.delete_one({"id": widget_id})
        # Force reload on devices showing this widget
        if w and w.get("screen_id"):
            await db.devices.update_many({"screen_id": w["screen_id"], "status": "active"}, {"$set": {"pending_command": "reload"}})
        return {"message": "Widget deleted"}

    @router.put("/admin/widgets/{widget_id}/toggle")
    async def toggle_widget(widget_id: str, admin: dict = Depends(require_admin)):
        w = await db.widgets.find_one({"id": widget_id})
        if not w: raise HTTPException(status_code=404, detail="Widget not found")
        new_state = not w.get("enabled", True)
        await db.widgets.update_one({"id": widget_id}, {"$set": {"enabled": new_state}})
        # Force reload on devices
        if w.get("screen_id"):
            await db.devices.update_many({"screen_id": w["screen_id"], "status": "active"}, {"$set": {"pending_command": "reload"}})
        return {"message": f"Widget {'enabled' if new_state else 'disabled'}"}

    @router.delete("/admin/campaigns/{campaign_id}/media/{media_id}")
    async def admin_remove_media_from_campaign(campaign_id: str, media_id: str, admin: dict = Depends(require_admin)):
        """Remove a specific media from a campaign's playlist."""
        campaign = await db.campaigns.find_one({"id": campaign_id})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        media_ids = campaign.get("media_ids", [])
        if media_id in media_ids:
            media_ids.remove(media_id)
            await db.campaigns.update_one({"id": campaign_id}, {"$set": {"media_ids": media_ids}})
        return {"message": "Media removed from campaign"}

    @router.get("/admin/campaign-scheduler/status")
    async def campaign_scheduler_status(admin: dict = Depends(require_admin)):
        """Estado y estadísticas del Campaign Scheduler."""
        sched = get_campaign_scheduler()
        pending = await db.ad_campaigns.count_documents({"status": "PENDING_REVIEW"})
        approved = await db.ad_campaigns.count_documents({"status": "APPROVED"})
        scheduled = await db.ad_campaigns.count_documents({"status": "SCHEDULED"})
        active = await db.ad_campaigns.count_documents({"status": "ACTIVE"})
        completed = await db.ad_campaigns.count_documents({"status": "COMPLETED"})
        last_transitions = await db.campaign_transitions.find().sort("transition_time", -1).to_list(10)
        return {
            "scheduler_running": sched.running if sched else False,
            "counts": {
                "PENDING_REVIEW": pending,
                "APPROVED": approved,
                "SCHEDULED": scheduled,
                "ACTIVE": active,
                "COMPLETED": completed,
            },
            "last_transitions": [
                {
                    "campaign_id": t.get("campaign_id"),
                    "old_status": t.get("old_status"),
                    "new_status": t.get("new_status"),
                    "transition_time": t.get("transition_time").isoformat() if isinstance(t.get("transition_time"), datetime) else str(t.get("transition_time")),
                    "reason": t.get("reason"),
                }
                for t in last_transitions
            ],
        }

    @router.post("/admin/campaign-scheduler/run-now")
    async def campaign_scheduler_run_now(admin: dict = Depends(require_admin)):
        """Fuerza una ejecución inmediata del scheduler (útil para testing)."""
        result = await run_campaign_scheduler(db)
        return {
            "message": f"Scheduler executed: {result['total']} transition(s)",
            "result": result,
        }

    return router
