"""player_routes.py -- the player/device contract: playlist delivery,
diagnostics, the HTML5 web player, the A35 bridge export, device pairing,
registration, activation polling, heartbeat, update-check and logging.

Fase 2B-5 of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md and
docs/AGENT_COORDINATION.md). Pure relocation of the 16 handlers below out of
server.py: identical paths, methods, decorators and logic, registered on a
router with prefix="/api" so the final routes match api_router exactly as
before. No behavior change.

RISK NOTE (from the plan, verbatim): this is "el contrato con el APK en la
calle: se prueba con un dispositivo real antes de fusionar". Automated
verification here (AST byte-comparison, flake8 F821, the full test suite) is
necessary but NOT sufficient for this phase -- do not merge to trunk without
an actual TV box / Player App exercising /devices/register, /devices/{id}/
check, /devices/{id}/heartbeat and /player/{screen_id}/playlist end to end.

Scope: 9 /player/* + 7 /devices/* routes, matching docs/REFACTOR_FASE2_PLAN.md's
original count exactly (re-derived independently via AST against the real
de45af4 commit, not assumed from any chat summary). /player-activate does NOT
move -- it is an unrelated static-file route (serve_player_activate, stays in
server.py with /public/playlist, /download, /screen, /marketplace). The four
/admin/devices/* routes and /admin/player-release also stay -- they belong to
Fase 2B-6 (admin_panel_routes.py).

Dependency notes:
  - gen_id and serialize_doc are threaded in, same pattern as every prior
    phase.
  - gen_activation_code, build_screen_playlist_items and MEDIA_DIR are ALSO
    threaded in rather than moved: all three stay defined/set in server.py
    because other, not-(yet-)moved code still needs them --
    gen_activation_code is called by admin_activate_device (2B-6 scope) and
    is already threaded into create_screens_routes(...) since Fase 2B-3;
    build_screen_playlist_items is already threaded into
    create_workspace_routes(...) since the Phase 2C wiring; MEDIA_DIR is
    already threaded into create_media_routes(...) since Fase 2B-2. Moving
    any of the three would break that already-merged wiring for no benefit.
  - screen_orientation is threaded in for the same reason, for the first
    time in this refactor: it is used by campaign/marketplace code that
    hasn't moved yet (grep-verified) AND by 3 of the routes moving here
    (get_playlist, export_playlist_for_bridge, device_playlist) -- this is
    exactly the deferral Emergent called out in the Fase 2B-3 report
    ("deberia threadearse cuando la fase que la use de verdad la necesite").
  - effective_playlist_schedule_key is used ONLY by routes moving here and
    has no closure dependency (only needs db and scheduled_playlist_key,
    both imported directly) -- plain module-level function, not threaded.
  - _norm_date moved to media_utils.py instead of being threaded: it is used
    both by diagnose_playlist (moving here) and by normalise_schedule
    (staying in server.py) -- relocating it to the shared dependency-free
    module lets both sides import it directly, same treatment as
    _public_token_hash in Fase 2B-4. This one is load-bearing, not just
    cosmetic: backend/tests/test_playlist_pipeline.py does
    `from server import (..., _norm_date, ...)` directly, so server.py's
    copy is replaced with a one-line re-import rather than just deleted.
  - PLAYABLE_STATUSES and MEDIA_METADATA_PROJECTION (media_utils.py) are
    imported directly, exactly as server.py already does.
  - authenticate_device, new_device_token, normalize_player_state,
    sync_progress_payload and HEARTBEAT_INTERVAL_SECONDS (device_security.py)
    move their import here from server.py: grep-verified that all 5 names
    were used ONLY inside the 16 routes moving in this phase, so the
    `from device_security import (...)` block is deleted from server.py
    entirely rather than left dangling. connectivity_from_heartbeat, which
    was in that same import block, is NOT re-added here: grep-verified it
    has zero call sites anywhere in server.py (a pre-existing dead import,
    unrelated to this phase) -- dropping it is a no-op, not a behavior
    change.
  - open_media_for_response (storage.py) moves its import here the same
    way: grep-verified every other name in server.py's
    `from storage import (...)` block (R2_BUCKET, R2_ENABLED, _ext_of,
    build_key, public_url_for_key, r2_delete, r2_head, r2_presign_put,
    r2_put_bytes, validate_upload) has zero remaining call sites in
    server.py -- leftover from Fase 2B-2's media_routes.py extraction,
    which already has its own copy of this same import. The whole block is
    deleted from server.py; only open_media_for_response is re-imported
    here, where it is actually used (player_media).
  - _audit (managed_portal_routes.create_audit_log) is imported directly,
    same pattern as every prior phase; only device_pair uses it.
  - require_admin (deps.py) is imported directly; only diagnose_playlist
    uses it (admin-only diagnostic endpoint).

Safety note on web_player: its HTML/JS payload is built as one large raw
triple-quoted string (`r\"\"\"...\"\"\"`) spanning ~67 physical lines. A naive
"add N spaces to every line" reindent -- the one used in every prior phase
of this refactor -- would silently prepend those spaces INSIDE the string's
runtime value too, corrupting every line the Player App's browser actually
renders, without any route-shape test ever catching it (this is the general
version of the risk Emergent flagged and fixed by hand for a different
reason in Fase 2B-4's blank-line cleanup). This script's reindent() is
tokenize-aware: it finds every multi-line STRING token and never pads its
interior rows, then proves the fix with a byte-for-byte round-trip check
(reindent -> dedent -> compare to the @router.-swapped original) for all 16
routes before writing the file, not just for web_player.

Known cosmetic leftovers (both harmless, matching the accepted precedent from
prior phases of not chasing every blank-line/comment artifact of a pure
deletion): three now-empty section-header comments remain in server.py where
these routes used to be ("WEB PLAYER ENGINE", "A35 BRIDGE", "ROUTES: DEVICE
MANAGEMENT"); and deleting the 5 models/helper leaves a handful of splice
points with more than 2 consecutive blank lines (flake8 E303), same class of
artifact Emergent found and fixed BY HAND in Fase 2B-4's own blank-line
cleanup -- confirmed via a before/after flake8 --select=E3,W3 diff against
the pristine pre-2B-5 server.py that these are the ONLY new style artifacts
introduced (5 occurrences, all pure whitespace, none touching a string
literal); every other E302/E303/E305 hit is a pre-existing, unrelated style
issue already present before this phase and intentionally left alone, to
keep this script a pure relocation rather than an unrelated style pass over
the whole file.
"""
import base64
import html as html_lib
import json
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from database import db
from deps import require_admin
from device_security import (
    HEARTBEAT_INTERVAL_SECONDS,
    authenticate_device,
    new_device_token,
    normalize_player_state,
    sync_progress_payload,
)
from managed_portal_routes import create_audit_log as _audit
from media_utils import MEDIA_METADATA_PROJECTION, PLAYABLE_STATUSES, _norm_date
from playlist_domain import scheduled_playlist_key
from storage import open_media_for_response

logger = __import__("logging").getLogger(__name__)


class DeviceRegister(BaseModel):
    device_name: Optional[str] = None
    device_model: Optional[str] = None
    model: Optional[str] = None  # alias for device_model (legacy client field)
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    resolution: Optional[str] = None
    platform: Optional[str] = None  # android_tv, fire_tv, tizen, webos
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    # Stable per-device UUID generated by the Player App. Used to keep
    # /register idempotent so the activation code doesn't change on every relaunch.
    client_uuid: Optional[str] = None
    device_id: Optional[str] = None  # alias for client_uuid (legacy client field)


class DeviceSyncProgress(BaseModel):
    files_done: Optional[int] = 0
    files_total: Optional[int] = 0
    bytes_done: Optional[int] = 0
    bytes_total: Optional[int] = 0
    manifest_version: Optional[str] = None
    current_file: Optional[str] = None


class DeviceHeartbeat(BaseModel):
    status: str = "online"
    player_state: Optional[str] = None
    sync_progress: Optional[DeviceSyncProgress] = None
    current_media_id: Optional[str] = None
    uptime_seconds: Optional[int] = None
    free_storage_mb: Optional[int] = None
    cached_media_count: Optional[int] = None
    last_error: Optional[str] = None
    ip_address: Optional[str] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    app_version: Optional[str] = None
    temperature: Optional[float] = None
    device_id: Optional[str] = None
    screen_id: Optional[str] = None
    current_playlist: Optional[str] = None
    network: Optional[str] = None
    storage: Optional[str] = None
    resolution: Optional[str] = None
    orientation: Optional[str] = None
    last_sync: Optional[str] = None


class DeviceLog(BaseModel):
    level: str = "info"
    message: str
    details: Optional[str] = None


class DevicePair(BaseModel):
    pairing_code: str
    pairing_secret: str
    device_model: Optional[str] = ""
    device_name: Optional[str] = ""
    os_version: Optional[str] = ""
    app_version: Optional[str] = ""
    app_version_code: Optional[int] = 0
    resolution: Optional[str] = ""
    client_uuid: Optional[str] = ""


async def effective_playlist_schedule_key(screen_id: str) -> str:
    playlists = await db.playlists.find(
        {"screen_ids": screen_id, "status": "published"}, {"_id": 0, "id": 1, "priority": 1, "schedule": 1,
                                                                  "published_at": 1, "updated_at": 1}
    ).to_list(200)
    return scheduled_playlist_key(playlists)


def create_player_domain_routes(gen_id, serialize_doc, MEDIA_DIR, gen_activation_code,
                          build_screen_playlist_items, screen_orientation):
    router = APIRouter(prefix="/api", tags=["Player"])

    @router.post("/devices/pair")
    async def device_pair(data: DevicePair):
        """Customer-facing pairing endpoint.
    The player calls this with the Device ID + Secret Key the admin gave the customer.
    Links the physical device to the screen and returns the backend device_id."""
        code = (data.pairing_code or "").strip().upper()
        secret = (data.pairing_secret or "").strip()
        if not code or not secret:
            raise HTTPException(400, "pairing_code and pairing_secret are required")
        screen = await db.screens.find_one({"pairing_code": code})
        if not screen:
            raise HTTPException(404, "Device ID not found. Check the code provided by your administrator.")
        if screen.get("pairing_secret") != secret:
            raise HTTPException(401, "Invalid Secret Key. Please verify the credentials.")
        # If already paired to a different physical device, allow re-pairing (returns same screen)
        device_id = screen.get("paired_device_id") or gen_id()
        device_info = {
            "model": data.device_model or "Unknown",
            "name": data.device_name or "MediAd View Player",
            "os": data.os_version or "",
            "app_version": data.app_version or "",
            "app_version_code": data.app_version_code or 0,
            "resolution": data.resolution or "",
            "client_uuid": data.client_uuid or "",
        }
        device_doc = {
            "id": device_id,
            "screen_id": screen["id"],
            "device_info": device_info,
            "status": "active",
            "paired_at": datetime.utcnow(),
            "last_heartbeat": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "pairing_code": code,
        }
        # Upsert device
        await db.devices.update_one({"id": device_id}, {"$set": device_doc}, upsert=True)
        # Mark screen as paired
        await db.screens.update_one(
            {"id": screen["id"]},
            {"$set": {"paired_device_id": device_id, "paired_at": datetime.utcnow()}}
        )
        logger.info(f"✓ Device paired: code={code} → screen={screen['id'][:8]} ({screen.get('name')})")
        # ── Fase 4: Audit log ─────────────────────────────────────────────────────
        await _audit(
            db, action="device.paired",
            resource_type="screen", resource_id=screen["id"],
            org_id=screen.get("organization_id"),
            details={"device_id": device_id, "screen_name": screen.get("name"), "code": code},
        )
        return {
            "ok": True,
            "device_id": device_id,
            "screen_id": screen["id"],
            "screen_name": screen.get("name"),
            "location_code": screen.get("location_code"),
            "player_url": f"/api/player/{screen['id']}/web",
            "message": f"Connected to screen: {screen.get('name')}",
        }

    @router.get("/player/{screen_id}/playlist")
    async def get_playlist(screen_id: str):
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        now = datetime.utcnow()
        items = await build_screen_playlist_items(screen_id)

        return {
            "screen_id": screen_id,
            "screen_name": screen.get("name"),
            "resolution": screen.get("specs", {}).get("resolution", "1920x1080"),
            "orientation": screen_orientation(screen),
            "playlist_version": screen.get("playlist_version", 0),
            "schedule_key": await effective_playlist_schedule_key(screen_id),
            "generated_at": now.isoformat(),
            "total_items": len(items),
            "items": items,
        }

    @router.get("/player/{screen_id}/version")
    async def get_playlist_version(screen_id: str):
        """Lightweight endpoint the player polls every 15s to detect changes.

    Response:
        { "playlist_version": <int>, "server_time": "<iso>" }
    The player compares the returned number against its cached one and
    only re-fetches /playlist when it changed. Cheap, cache-friendly.
    """
        screen = await db.screens.find_one({"id": screen_id}, {"playlist_version": 1})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        return {
            "screen_id": screen_id,
            "playlist_version": screen.get("playlist_version", 0),
            "schedule_key": await effective_playlist_schedule_key(screen_id),
            "server_time": datetime.utcnow().isoformat(),
        }

    @router.get("/player/{screen_id}/diagnose")
    async def diagnose_playlist(screen_id: str, admin: dict = Depends(require_admin)):
        """DIAGNOSTIC ENDPOINT (admin only): explains exactly WHY a playlist is empty.

    Returns every campaign attached to the screen and, for each one, whether
    it is currently visible to the player and — if not — the reason.
    Also verifies media_ids resolve to actual media files on disk.
    """
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            return {"screen_id": screen_id, "screen_exists": False,
                    "reason": "screen not found in DB (was it deleted?)"}

        now = datetime.utcnow()
        today = now.strftime("%Y-%m-%d")
        now_hm = now.strftime("%H:%M")

        all_campaigns = await db.campaigns.find({"screen_id": screen_id}).to_list(500)
        diag_campaigns = []
        visible_count = 0

        for c in all_campaigns:
            cid = c.get("id")
            status = c.get("status")
            sched = c.get("schedule", {}) or {}
            mids = c.get("media_ids", []) or []
            reasons = []

            if status not in PLAYABLE_STATUSES:
                reasons.append(f"status='{status}' (need {'/'.join(sorted(PLAYABLE_STATUSES))})")

            sd = _norm_date(sched.get("start_date"))
            ed = _norm_date(sched.get("end_date"))
            if sd is not None and sd > today:
                reasons.append(f"schedule.start_date={sd!r} > today({today})")
            if ed is not None and ed < today:
                reasons.append(f"schedule.end_date={ed!r} < today({today})")

            st = sched.get("start_time", "00:00")
            et = sched.get("end_time", "23:59")
            if not (st <= now_hm <= et):
                reasons.append(f"time {now_hm!r} not in [{st!r}, {et!r}]")

            if not mids:
                reasons.append("media_ids array is empty (no media assigned)")

            # verify each media resolves
            media_status = []
            for mid in mids:
                m = await db.media.find_one({"id": mid}, MEDIA_METADATA_PROJECTION)
                if not m:
                    media_status.append({"media_id": mid, "ok": False, "reason": "media doc missing in DB"})
                    reasons.append(f"media_id {mid!r} not found in media collection")
                    continue
                stored = m.get("stored_filename")
                fp = os.path.join(MEDIA_DIR, stored or "")
                file_ok = bool(stored) and os.path.exists(fp)
                size = os.path.getsize(fp) if file_ok else 0
                media_status.append({
                    "media_id": mid, "ok": file_ok,
                    "filename": m.get("filename"),
                    "content_type": m.get("content_type"),
                    "stored_filename": stored,
                    "file_exists": file_ok,
                    "file_size_bytes": size,
                })
                if not file_ok:
                    reasons.append(f"media_id {mid!r} file missing on disk: {fp}")

            is_visible = len(reasons) == 0
            if is_visible:
                visible_count += 1

            diag_campaigns.append({
                "campaign_id": cid,
                "name": c.get("name"),
                "status": status,
                "schedule": sched,
                "media_ids": mids,
                "media_status": media_status,
                "needs_attention": c.get("needs_attention", False),
                "will_play_now": is_visible,
                "excluded_reasons": reasons,
            })

        return {
            "screen_id": screen_id,
            "screen_name": screen.get("name"),
            "screen_status": screen.get("status"),
            "playlist_version": screen.get("playlist_version", 0),
            "server_time_utc": now.isoformat(),
            "server_date": today,
            "server_time_hm": now_hm,
            "total_campaigns": len(all_campaigns),
            "visible_now": visible_count,
            "campaigns": diag_campaigns,
            "hint": (
                "If visible_now == 0, no content will play. Check the "
                "'excluded_reasons' array on each campaign to see exactly what "
                "condition failed."
            ),
        }

    @router.get("/player/{screen_id}/schedule")
    async def get_schedule(screen_id: str, date: Optional[str] = None):
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        td = date or datetime.utcnow().strftime("%Y-%m-%d")
        campaigns = await db.campaigns.find({
            "screen_id": screen_id, "status": {"$in": ["approved", "active"]},
            "schedule.start_date": {"$lte": td}, "schedule.end_date": {"$gte": td}
        }).to_list(100)
        entries = []
        for c in campaigns:
            s = c.get("schedule", {})
            for mid in c.get("media_ids", []):
                media = await db.media.find_one({"id": mid}, MEDIA_METADATA_PROJECTION)
                entries.append({
                    "campaign_id": c["id"], "campaign_name": c.get("name"),
                    "time_start": s.get("start_time", "08:00"),
                    "time_end": s.get("end_time", "22:00"),
                    "duration": s.get("slot_duration", 15),
                    "frequency_minutes": s.get("frequency", 5),
                    "media_id": mid, "media_url": f"/api/player/media/{mid}",
                    "filename": media.get("filename") if media else None,
                    "content_type": media.get("content_type") if media else None
                })
        return {"screen_id": screen_id, "date": td, "entries": entries}

    @router.get("/player/media/{media_id}")
    async def player_media(media_id: str):
        media = await db.media.find_one({"id": media_id})
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        if media.get("r2_key"):
            result = open_media_for_response(media, media_dir=MEDIA_DIR)
            return RedirectResponse(
                url=result["value"],
                status_code=302,
                headers={"Cache-Control": "public, max-age=300"},
            )
        stored = media.get("stored_filename")
        if stored:
            path = os.path.join(MEDIA_DIR, stored)
            if os.path.isfile(path):
                return FileResponse(
                    path,
                    media_type=media.get("content_type", "application/octet-stream"),
                    filename=media.get("filename") or "media",
                    content_disposition_type="inline",
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        result = await run_in_threadpool(open_media_for_response, media, MEDIA_DIR)
        return Response(
            content=result["value"],
            media_type=result.get("mime") or media.get("content_type", "application/octet-stream"),
            headers={"Content-Disposition": "inline", "Cache-Control": "public, max-age=86400"},
        )

    @router.get("/player/{screen_id}/web", response_class=HTMLResponse)
    async def web_player(screen_id: str):
        """Production-grade HTML5 signage player. 24/7 capable with offline cache, video preload, heartbeat, auto-recovery, diagnostics HUD (press 'i')."""
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        sn = screen.get('name', 'Screen')
        res = screen.get('specs', {}).get('resolution', '1920x1080')
        sn_html = html_lib.escape(str(sn))
        res_html = html_lib.escape(str(res))
        sid_js, sn_js, res_js = json.dumps(screen_id), json.dumps(sn), json.dumps(res)
        html = '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no"><meta name="mobile-web-app-capable" content="yes"><title>MediaView - ' + sn_html + '</title>'
        html += '<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:100%;height:100%;overflow:hidden;background:#000;font-family:Segoe UI,Arial,sans-serif;cursor:none}body.sc{cursor:default}#ml{width:100%;height:100%;position:absolute;top:0;left:0;display:flex;align-items:center;justify-content:center}#ml img,#ml video{width:100%;height:100%;object-fit:contain;position:absolute;top:0;left:0}video::-webkit-media-controls{display:none!important}video::-webkit-media-controls-play-button{display:none!important}video::-webkit-media-controls-overlay-play-button{display:none!important}video::-webkit-media-controls-start-playback-button{display:none!important}@keyframes fi{from{opacity:0}to{opacity:1}}.fi{animation:fi .8s ease}@keyframes sl{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}.sl{animation:sl .6s ease}@keyframes zm{from{transform:scale(1.2);opacity:0}to{transform:scale(1);opacity:1}}.zm{animation:zm .8s ease}'
        html += '#fb{position:absolute;top:0;left:0;width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;background:linear-gradient(135deg,#0F172A,#312E81 45%,#5B21B6);text-align:center;padding:40px;z-index:100}#fb .lg{width:110px;height:110px;border-radius:26px;background:linear-gradient(135deg,#EC4899,#8B5CF6);display:flex;align-items:center;justify-content:center;margin-bottom:28px;box-shadow:0 0 80px rgba(139,92,246,.5)}#fb .lg span{font-size:52px;font-weight:900;color:#fff;letter-spacing:-2px}#fb h1{font-size:56px;font-weight:900;color:#fff;letter-spacing:-1px;margin-bottom:8px;text-shadow:0 4px 20px rgba(0,0,0,.5)}#fb h2{font-size:22px;color:#C4B5FD;margin-top:4px;font-weight:600}#fb .dv{width:120px;height:3px;background:linear-gradient(90deg,#EC4899,#8B5CF6,#06B6D4);border-radius:2px;margin:32px 0}#fb .st{font-size:20px;color:#E9D5FF;font-weight:600;letter-spacing:.5px}#fb .su{font-size:15px;color:#A78BFA;margin-top:12px;letter-spacing:.3px;max-width:600px}#fb .bd{margin-top:36px;padding:10px 22px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);border-radius:100px;font-size:12px;color:#DDD6FE;letter-spacing:2px;text-transform:uppercase;font-weight:700}.pu{animation:pu 2s ease-in-out infinite}@keyframes pu{0%,100%{opacity:1}50%{opacity:.55}}'
        html += '#hud{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.9);color:#E2E8F0;font-size:13px;padding:24px 32px;display:none;overflow-y:auto;z-index:1000}#hud.v{display:block}#hud h2{font-size:20px;font-weight:700;color:#A5B4FC;margin-bottom:16px;border-bottom:1px solid #1E293B;padding-bottom:8px}#hud .s{margin-bottom:14px}#hud .s h3{font-size:11px;font-weight:700;color:#6366F1;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:6px}#hud .r{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #111827}#hud .r .l{color:#64748B}#hud .r .vl{color:#E2E8F0;font-weight:600;text-align:right;max-width:60%}.g{color:#10B981!important}.rd{color:#EF4444!important}.y{color:#F59E0B!important}#hud .le{padding:3px 0;border-bottom:1px solid #111827;font-family:monospace;font-size:11px}#hud .le.er{color:#FCA5A5}#hud .ch{position:fixed;bottom:16px;right:24px;font-size:12px;color:#475569}'
        html += '#sb{position:fixed;bottom:0;left:0;right:0;background:rgba(0,0,0,.7);color:#fff;padding:8px 20px;font-size:12px;display:flex;justify-content:space-between;align-items:center;opacity:0;transition:opacity .4s;z-index:500}#sb.v{opacity:1}#sb .br{display:flex;align-items:center;gap:8px}#sb .dt{width:8px;height:8px;border-radius:4px}'
        html += '</style></head><body><div id="player"><div id="ml"></div><div id="fb"><div class="lg"><span>MV</span></div><h1>MediAd View</h1><h2>' + sn_html + '</h2><div class="dv"></div><p class="st pu" id="fbs">Connecting to server\u2026</p><p class="su" id="fbu">Waiting for content</p><div class="bd">Screen ready \u00b7 ' + res_html + '</div></div></div>'
        html += '<div id="sb"><div class="br"><span class="dt" id="sbd" style="background:#10B981"></span><span>MediAd View</span><span style="color:#6366F1">' + sn_html + '</span></div><span id="sbi">Loading...</span><span id="sbt"></span></div>'
        html += '<div id="hud"><h2>MediAd View Player - Diagnostics</h2><div id="hc"></div><div class="ch">Press i or click to close</div></div>'
        html += """<script>
(function(){
var SID=""" + sid_js + """,SN=""" + sn_js + """,RES=""" + res_js + r""",AB=location.origin,PI=15000,HI=30000,V='3.0.0';
var pl=[],ci=-1,ip=false,io=false,ls=null,le=null,st=Date.now(),rc=0,tp=0,lg=[],mc={},pt=null,hv=false,pv='',DEV=(location.search.indexOf('dev=1')>=0);
function log(l,m){lg.unshift({t:new Date().toISOString(),l:l,m:m});if(lg.length>100)lg.pop();console[l==='error'?'error':'log']('[MV]',m)}
// Lightweight version check: only fetch full playlist if it actually changed.
async function fv(){try{var r=await fetch(AB+'/api/player/'+SID+'/version');if(!r.ok)throw new Error('HTTP '+r.status);var d=await r.json();var v=String(d.playlist_version)+':'+(d.schedule_key||'');io=false;if(v!==pv){log('info','version '+pv+' -> '+v);pv=v;await fp()}else{ls=new Date();rc=0}}catch(e){io=true;rc++;le=e.message;log('warn','version fetch failed: '+e.message);if(pl.length===0){await fp()}}}
async function fp(){try{var r=await fetch(AB+'/api/player/'+SID+'/playlist');if(!r.ok)throw new Error('HTTP '+r.status);var d=await r.json();var it=d.items||[];io=false;ls=new Date();rc=0;le=null;if(d.playlist_version!=null)pv=String(d.playlist_version)+':'+(d.schedule_key||'');try{localStorage.setItem('mvp_'+SID,JSON.stringify(it))}catch(e){}
var ni=it.map(function(i){return i.media_id}).join(',');var oi=pl.map(function(i){return i.media_id}).join(',');
if(ni!==oi){log('info','Playlist updated: '+it.length+' items');pl=it;ci=-1;it.forEach(function(i){pm(i)})}
if(pl.length>0&&!ip){pn();pdc()}else if(pl.length===0){fdr()}
}catch(e){io=true;rc++;le=e.message;log('warn','Fetch failed: '+e.message+' (#'+rc+')');
if(pl.length===0){try{var c=localStorage.getItem('mvp_'+SID);if(c){var it=JSON.parse(c);if(it.length>0){pl=it;log('info','Cache loaded: '+it.length);pn()}}}catch(x){}}
if(pl.length===0){sf(true,'Waiting for content','Auto-retry active')}}}
// Diagnostic fallback: in DEV mode call /diagnose to explain why the
// playlist is empty. In production show a clean customer-friendly message
// and log the technical details silently.
async function fdr(){if(!DEV){sf(true,'Waiting for content','MediAd View is ready');return}
try{var r=await fetch(AB+'/api/player/'+SID+'/diagnose');if(!r.ok){sf(true,'Waiting for content','MediAd View is ready');return}
var d=await r.json();var msg='Waiting for content',sub='MediAd View is ready';
if(d.total_campaigns===0){msg='No campaigns yet';sub='Create a campaign and assign this screen'}
else if(d.visible_now===0){
  var reasons={};(d.campaigns||[]).forEach(function(c){(c.excluded_reasons||[]).forEach(function(r){reasons[r]=(reasons[r]||0)+1})});
  var topR=Object.keys(reasons).sort(function(a,b){return reasons[b]-reasons[a]})[0]||'';
  log('info','Diagnose top reason: '+topR);
  if(/media_id.*not found/i.test(topR)){msg='Media missing';sub='Re-upload media and re-assign'}
  else if(/media_ids array is empty/i.test(topR)){msg='Campaign has no media';sub='Open the campaign and assign a file'}
  else if(/status=/.test(topR)){msg='Waiting for approval';sub='An admin must approve the campaign'}
  else if(/schedule\.start_date/.test(topR)||/schedule\.end_date/.test(topR)){msg='Outside date range';sub='Adjust the campaign date range'}
  else if(/time .* not in/.test(topR)){msg='Outside scheduled hours';sub='Content will resume during scheduled time'}
  else{msg='Waiting for content';sub=topR}
}
sf(true,msg,sub)
}catch(e){sf(true,'Waiting for content','MediAd View is ready')}}
function pm(i){if(mc[i.media_id])return;var u=AB+i.media_url;if(i.content_type&&i.content_type.startsWith('image/')){var img=new Image();img.src=u;mc[i.media_id]={t:'image',u:u}}else{mc[i.media_id]={t:'video',u:u}}}
function pn(){if(pl.length===0)return;ci=(ci+1)%pl.length;var it=pl[ci],u=AB+it.media_url,ii=it.content_type&&it.content_type.startsWith('image/');ip=true;tp++;clearTimeout(pt);
var c=document.getElementById('ml');c.innerHTML='';
if(ii){var img=document.createElement('img');img.src=gcu(it);var ac=it.animation==='slide'?'sl':it.animation==='zoom'?'zm':it.animation==='none'?'':'fi';img.className=ac;img.onload=function(){sf(false)};img.onerror=function(){log('error','Img fail: '+it.filename);sf(true,'Image unavailable','Trying the next item');pt=setTimeout(pn,2e3)};c.appendChild(img);pt=setTimeout(pn,(it.duration||15)*1e3)}
else{var vid=document.createElement('video');vid.src=u;vid.autoplay=true;vid.muted=true;vid.playsInline=true;vid.setAttribute('playsinline','');vid.setAttribute('webkit-playsinline','');vid.preload='auto';vid.poster='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';var vac=it.animation==='slide'?'sl':it.animation==='zoom'?'zm':it.animation==='none'?'':'fi';vid.className=vac;vid.onplaying=function(){sf(false)};vid.onended=pn;vid.onerror=function(){log('error','Vid fail: '+it.filename);sf(true,'Video unavailable','Trying the next item');pt=setTimeout(pn,2e3)};c.appendChild(vid);vid.play().catch(function(){vid.muted=true;vid.play().catch(function(){vid.onerror()})});pt=setTimeout(pn,Math.max((it.duration||15)*1e3,6e4))}
usb();log('info','Play: '+it.filename+' ('+(ci+1)+'/'+pl.length+')')}
function sf(s,m,su){var el=document.getElementById('fb');el.style.display=s?'flex':'none';if(m)document.getElementById('fbs').textContent=m;if(su)document.getElementById('fbu').textContent=su;if(s)ip=false}
async function hb(){try{await fetch(AB+'/api/player/'+SID+'/status')}catch(e){}}
function usb(){var i=pl.length>0?'Item '+(ci+1)+'/'+pl.length+(io?' [OFFLINE]':''):'No content';document.getElementById('sbi').textContent=i;document.getElementById('sbd').style.background=io?'#F59E0B':'#10B981'}
function ssb(){var b=document.getElementById('sb');b.classList.add('v');document.body.classList.add('sc');clearTimeout(window._sbt);window._sbt=setTimeout(function(){b.classList.remove('v');document.body.classList.remove('sc')},6e3)}
function th(){hv=!hv;document.getElementById('hud').classList.toggle('v',hv);if(hv)rh()}
function rh(){var ut=Math.floor((Date.now()-st)/1e3),h=Math.floor(ut/3600),m=Math.floor((ut%3600)/60),s=ut%60;
var x='<div class="s"><h3>Device</h3>';
[['Screen ID',SID],['Screen',SN],['Resolution',RES],['Version',V],['Platform',navigator.userAgent.indexOf('Android')>=0?'Android TV':navigator.platform],['Viewport',innerWidth+'x'+innerHeight]].forEach(function(r){x+='<div class="r"><span class="l">'+r[0]+'</span><span class="vl">'+r[1]+'</span></div>'});
x+='</div><div class="s"><h3>Status</h3>';
[['Playing',ip?'Yes':'No',ip?'g':'y'],['Connection',io?'Offline':'Online',io?'rd':'g'],['Uptime',h+'h '+m+'m '+s+'s',''],['Last Sync',ls?ls.toLocaleString():'Never',ls?'g':'y'],['Retries',rc+'',rc>0?'y':'g'],['Total Plays',tp+'',''],['Playlist',pl.length+' items',''],['Current',pl[ci]?pl[ci].filename:'None',''],['Cached',Object.keys(mc).length+'',''],['Last Error',le||'None',le?'rd':'g']].forEach(function(r){x+='<div class="r"><span class="l">'+r[0]+'</span><span class="vl '+r[2]+'">'+r[1]+'</span></div>'});
x+='</div><div class="s"><h3>Logs (last 20)</h3>';
lg.slice(0,20).forEach(function(l){x+='<div class="le'+(l.l==='error'?' er':'')+'">'+l.t.substring(11,19)+' ['+l.l+'] '+l.m+'</div>'});
x+='</div>';document.getElementById('hc').innerHTML=x}
document.addEventListener('mousemove',ssb);document.addEventListener('touchstart',ssb);
document.addEventListener('keydown',function(e){if(e.key==='i'||e.key==='I')th();else if(e.key==='Escape'&&hv)th()});
document.getElementById('hud').addEventListener('click',function(){if(hv)th()});
setInterval(function(){document.getElementById('sbt').textContent=new Date().toLocaleTimeString();if(hv)rh()},1e3);
document.addEventListener('visibilitychange',function(){if(!document.hidden){log('info','Resumed');fp()}});
window.onerror=function(m,u,l){log('error','JS: '+m);setTimeout(pn,3e3);return true};
log('info','MediAd View Player v'+V+' started: '+SN);
// Nightly reboot
var rbt='03:00';
setInterval(function(){var n=new Date(),h=String(n.getHours()).padStart(2,'0'),m=String(n.getMinutes()).padStart(2,'0');if(h+':'+m===rbt){log('info','Nightly reboot');window.location.reload(true)}},60000);
// Content pre-download cache
var mdc={};
async function pdc(){for(var i of pl){if(mdc[i.media_id])continue;try{var r=await fetch(AB+i.media_url);var b=await r.blob();mdc[i.media_id]=URL.createObjectURL(b);log('info','Cached: '+i.filename)}catch(e){}}}
function gcu(it){return mdc[it.media_id]||(AB+it.media_url)};
fp();setInterval(fv,PI);setInterval(hb,HI);
})();
</script></body></html>"""
        return HTMLResponse(content=html, headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        })

    @router.get("/player/{screen_id}/export")
    async def export_playlist_for_bridge(screen_id: str, date: Optional[str] = None):
        """Export playlist in a format optimized for the A35 Bridge script.
    Returns full media data (base64) for offline caching, plus metadata.
    Used by the bridge script that pushes content to PlayerMaster/ColorlightCloud."""
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")

        now = datetime.utcnow()
        td = date or now.strftime("%Y-%m-%d")
        ct = now.strftime("%H:%M")

        campaigns = await db.campaigns.find({
            "screen_id": screen_id, "status": {"$in": ["approved", "active"]},
            "schedule.start_date": {"$lte": td}, "schedule.end_date": {"$gte": td}
        }).to_list(100)

        export_items = []
        for c in campaigns:
            s = c.get("schedule", {})
            for mid in c.get("media_ids", []):
                media = await db.media.find_one({"id": mid}, MEDIA_METADATA_PROJECTION)
                if not media:
                    continue
                # Read file for base64 export
                fp = os.path.join(MEDIA_DIR, media.get("stored_filename", ""))
                file_base64 = None
                if os.path.exists(fp):
                    with open(fp, "rb") as f:
                        file_base64 = base64.b64encode(f.read()).decode()

                export_items.append({
                    "campaign_id": c["id"],
                    "campaign_name": c.get("name"),
                    "media_id": mid,
                    "filename": media.get("filename"),
                    "stored_filename": media.get("stored_filename"),
                    "content_type": media.get("content_type"),
                    "size": media.get("size"),
                    "duration": s.get("slot_duration", 15),
                    "time_start": s.get("start_time", "08:00"),
                    "time_end": s.get("end_time", "22:00"),
                    "frequency_minutes": s.get("frequency", 5),
                    "file_base64": file_base64,
                    "download_url": f"/api/player/media/{mid}"
                })

        return {
            "screen_id": screen_id,
            "screen_name": screen.get("name"),
            "resolution": screen.get("specs", {}).get("resolution", "1920x1080"),
            "orientation": screen_orientation(screen),
            "export_date": td,
            "generated_at": now.isoformat(),
            "total_items": len(export_items),
            "items": export_items
        }

    @router.get("/player/{screen_id}/status")
    async def player_heartbeat(screen_id: str):
        """Endpoint for player devices to report status / check connectivity."""
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")

        now = datetime.utcnow()
        td = now.strftime("%Y-%m-%d")
        active_count = await db.campaigns.count_documents({
            "screen_id": screen_id, "status": {"$in": ["approved", "active"]},
            "schedule.start_date": {"$lte": td}, "schedule.end_date": {"$gte": td}
        })

        return {
            "screen_id": screen_id,
            "screen_name": screen.get("name"),
            "server_time": now.isoformat(),
            "active_campaigns": active_count,
            "status": "online",
            "resolution": screen.get("specs", {}).get("resolution", "1920x1080")
        }

    @router.post("/devices/register")
    async def register_device(data: DeviceRegister):
        """Called by the Player App on first launch.

    IDEMPOTENT: if the same device (identified by client_uuid) has already
    registered, returns the SAME device_id and activation_code so the code
    stays stable across app relaunches, rotations and reboots.
    """
        # Normalise the client-side stable UUID (may come in as `client_uuid` or
        # legacy `device_id` field from older builds).
        client_uuid = (data.client_uuid or data.device_id or "").strip()

        # Fast-path: existing device with same client_uuid → return it as-is.
        if client_uuid:
            existing = await db.devices.find_one({"client_uuid": client_uuid})
            if existing:
                # Refresh last_seen and hand out a fresh device token (enrollment point)
                rotated, rotated_hash = new_device_token()
                existing["device_token"] = rotated
                await db.devices.update_one(
                    {"id": existing["id"]},
                    {"$set": {
                        "last_heartbeat": datetime.utcnow(),
                        "device_token_hash": rotated_hash,
                        "device_token_issued_at": datetime.utcnow(),
                    }}
                )
                logger.info(
                    f"Device re-register (idempotent): {existing['id']} "
                    f"code={existing.get('activation_code')} status={existing.get('status')}"
                )
                return {
                    "device_id": existing["id"],
                    "device_token": rotated,
                    "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
                    "activation_code": existing.get("activation_code"),
                    "status": existing.get("status", "pending"),
                    "screen_id": existing.get("screen_id"),
                    "message": "Device already registered"
                }

        code = gen_activation_code()
        # Ensure code is unique across pending devices
        while await db.devices.find_one({"activation_code": code, "status": "pending"}):
            code = gen_activation_code()

        device = {
            "id": gen_id(),
            "client_uuid": client_uuid or None,
            "activation_code": code,
            "device_name": data.device_name or "MediaView Player",
            "device_info": {
                "model": data.device_model or data.model,
                "os_version": data.os_version,
                "app_version": data.app_version,
                "resolution": data.resolution,
            },
            "screen_id": None,
            "status": "pending",  # pending | active | offline | disabled
            "last_heartbeat": datetime.utcnow(),
            "last_sync": None,
            "activated_at": None,
            "errors": [],
            "created_at": datetime.utcnow()
        }
        token, token_hash = new_device_token()
        device["device_token_hash"] = token_hash
        device["device_token_issued_at"] = datetime.utcnow()
        await db.devices.insert_one(device)
        logger.info(f"Device registered: {device['id']} code={code} client_uuid={client_uuid}")
        return {
            "device_id": device["id"],
            "device_token": token,
            "activation_code": code,
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "status": "pending",
            "message": "Device registered. Enter the activation code in the admin panel to link this device to a screen."
        }

    @router.get("/devices/{device_id}/check")
    async def check_device_activation(device_id: str):
        """Polled by Player App to check if device has been activated by admin.

    Accepts either the server-generated device id OR the client_uuid, so both
    old builds (which polled with client_uuid) and new builds keep working.

    Also auto-heals zombie state: if the device is 'active' but its screen
    was deleted, we reset it back to 'pending' with a fresh activation code
    so the Player App re-pairs cleanly instead of black-screening on a
    dead screen_id.
    """
        device = await db.devices.find_one({"id": device_id})
        if not device:
            # Fallback: legacy clients poll with their local client_uuid
            device = await db.devices.find_one({"client_uuid": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        # Auto-heal orphan device: screen was deleted / never linked but device
        # is stuck in a non-pending state → reset to pending with a fresh code
        # so the Player App re-pairs cleanly instead of black-screening.
        needs_heal = False
        if device.get("screen_id"):
            screen_exists = await db.screens.find_one({"id": device["screen_id"]})
            if not screen_exists:
                needs_heal = True
        elif device.get("status") == "active":
            # active but no screen_id at all → definitely broken
            needs_heal = True

        if needs_heal:
            new_code = gen_activation_code()
            while await db.devices.find_one({"activation_code": new_code, "status": "pending"}):
                new_code = gen_activation_code()
            await db.devices.update_one(
                {"id": device["id"]},
                {"$set": {
                    "screen_id": None,
                    "status": "pending",
                    "activation_code": new_code,
                    "activated_at": None,
                }}
            )
            logger.info(f"Device {device['id']} auto-healed. New code: {new_code}")
            device["screen_id"] = None
            device["status"] = "pending"
            device["activation_code"] = new_code
            device["activated_at"] = None

        result = {
            "device_id": device["id"],
            "activation_code": device.get("activation_code"),
            "status": device.get("status"),
            "screen_id": device.get("screen_id"),
            "screen_name": None,
            "activated_at": serialize_doc(device.get("activated_at")),
        }

        if device.get("screen_id"):
            screen = await db.screens.find_one({"id": device["screen_id"]})
            if screen:
                result["screen_name"] = screen.get("name")
                result["screen_resolution"] = screen.get("specs", {}).get("resolution", "1920x1080")

        return result

    @router.post("/devices/{device_id}/heartbeat")
    async def device_heartbeat(device_id: str, data: DeviceHeartbeat, request: Request):
        """Called periodically by the Player App to report status and diagnostics."""
        device = await authenticate_device(db, device_id, request)

        update = {
            "last_heartbeat": datetime.utcnow(),
            "status": "active" if device.get("screen_id") else "pending",
            "diagnostics.reported_at": datetime.utcnow(),
            "diagnostics.device_id": data.device_id or device_id,
            "diagnostics.screen_id": data.screen_id or device.get("screen_id"),
        }

        # ── Sprint 1: estado real del player + progreso real de sincronización ──
        reported_state = normalize_player_state(data.player_state)
        if reported_state:
            update["player_state"] = reported_state
            update["player_state_at"] = datetime.utcnow()
        progress = sync_progress_payload(data.sync_progress.dict() if data.sync_progress else None)
        if progress:
            update["sync_progress"] = progress
        elif reported_state in ("PLAYING", "READY", "OFFLINE_PLAYING_CACHE"):
            update["sync_progress"] = None
        diagnostic_fields = {
            "uptime_seconds": data.uptime_seconds,
            "free_storage_mb": data.free_storage_mb,
            "cached_media_count": data.cached_media_count,
            "cpu_usage": data.cpu_usage,
            "memory_usage": data.memory_usage,
            "ip_address": data.ip_address,
            "app_version": data.app_version,
            "temperature": data.temperature,
            "current_playlist": data.current_playlist,
            "current_media_id": data.current_media_id,
            "network": data.network,
            "storage": data.storage,
            "resolution": data.resolution,
            "orientation": data.orientation,
            "last_sync": data.last_sync,
        }
        for field, value in diagnostic_fields.items():
            if value is not None:
                update[f"diagnostics.{field}"] = value
        if data.last_error:
            update["last_error"] = data.last_error

        # Auto-heal zombie state: if this device has screen_id set but the screen
        # was deleted, clear the pairing and force the player to re-pair.
        if device.get("screen_id"):
            screen_exists = await db.screens.find_one({"id": device["screen_id"]})
            if not screen_exists:
                new_code = gen_activation_code()
                while await db.devices.find_one({"activation_code": new_code, "status": "pending"}):
                    new_code = gen_activation_code()
                update["screen_id"] = None
                update["status"] = "pending"
                update["activation_code"] = new_code
                update["activated_at"] = None
                device["screen_id"] = None
                device["status"] = "pending"
                logger.info(f"Device {device_id} auto-healed via heartbeat (screen missing). New code: {new_code}")

        await db.devices.update_one({"id": device_id}, {"$set": update})

        # Return instructions for the player
        response = {
            "status": "ok",
            "server_time": datetime.utcnow().isoformat(),
            "poll_interval_seconds": 60,
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        }
        if device.get("screen_id"):
            response["action"] = "play"
            response["screen_id"] = device["screen_id"]
        else:
            response["action"] = "wait"

        # Check for pending commands (remote restart, etc.)
        pending_cmd = device.get("pending_command")
        if pending_cmd:
            response["command"] = pending_cmd
            # Clear the command after sending
            await db.devices.update_one({"id": device_id}, {"$unset": {"pending_command": ""}})

        # Include power schedule if exists
        power_schedule = device.get("power_schedule")
        if power_schedule and power_schedule.get("enabled"):
            response["power_schedule"] = power_schedule

        # ====== AUTO-UPDATE CHECK ======
        # If a target_apk_version is set globally or per-device, instruct the player to update
        try:
            cfg = await db.app_config.find_one({"_id": "player_release"}) or {}
            latest_version = cfg.get("version_name")
            latest_code = int(cfg.get("version_code") or 0)
            apk_url = cfg.get("apk_url")
            device_version = (data.app_version or "").strip()
            device_code = int(device.get("device_info", {}).get("app_version_code") or 0)
            # Allow per-device pinning
            pinned_skip = device.get("disable_auto_update", False)
            if latest_version and apk_url and not pinned_skip:
                should_update = False
                if latest_code and device_code and latest_code > device_code:
                    should_update = True
                elif latest_version and device_version and latest_version != device_version:
                    should_update = True
                if should_update:
                    response["update_available"] = {
                        "version_name": latest_version,
                        "version_code": latest_code,
                        "apk_url": apk_url,
                        "sha256": cfg.get("sha256"),
                        "mandatory": cfg.get("mandatory", False),
                        "notes": cfg.get("notes", ""),
                    }
        except Exception as e:
            logger.warning(f"Update check error for device {device_id}: {e}")

        return response

    @router.get("/devices/{device_id}/update-check")
    async def device_update_check(device_id: str, current_version: str = "", current_code: int = 0):
        """Lightweight endpoint the player can poll to see if an update is needed."""
        device = await db.devices.find_one({"id": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        cfg = await db.app_config.find_one({"_id": "player_release"}) or {}
        latest_version = cfg.get("version_name")
        latest_code = int(cfg.get("version_code") or 0)
        apk_url = cfg.get("apk_url")
        needs = False
        if latest_version and apk_url and not device.get("disable_auto_update", False):
            if latest_code and current_code and latest_code > current_code:
                needs = True
            elif latest_version and current_version and latest_version != current_version:
                needs = True
        return {
            "update_available": needs,
            "version_name": latest_version,
            "version_code": latest_code,
            "apk_url": apk_url if needs else None,
            "sha256": cfg.get("sha256") if needs else None,
            "mandatory": cfg.get("mandatory", False) if needs else False,
            "notes": cfg.get("notes", "") if needs else "",
        }

    @router.post("/devices/{device_id}/log")
    async def device_log(device_id: str, data: DeviceLog, request: Request):
        """Player App sends logs (errors, crashes, info) to server."""
        device = await authenticate_device(db, device_id, request)

        log_entry = {
            "id": gen_id(),
            "device_id": device_id,
            "level": data.level,
            "message": data.message,
            "details": data.details,
            "created_at": datetime.utcnow()
        }
        await db.device_logs.insert_one(log_entry)

        # If crash, update device status
        if data.level == "crash":
            await db.devices.update_one(
                {"id": device_id},
                {"$set": {"last_error": data.message}}
            )

        return {"status": "logged"}

    @router.get("/devices/{device_id}/playlist")
    async def device_playlist(device_id: str, request: Request):
        """Get playlist for an activated device. Used by the Player App."""
        device = await authenticate_device(db, device_id, request)
        if not device.get("screen_id"):
            return {"device_id": device_id, "status": "not_activated", "items": []}

        screen_id = device["screen_id"]
        screen = await db.screens.find_one({"id": screen_id})

        now = datetime.utcnow()
        items = await build_screen_playlist_items(screen_id, include_widgets=True)

        # Update last_sync
        await db.devices.update_one({"id": device_id}, {"$set": {"last_sync": datetime.utcnow()}})

        return {
            "device_id": device_id,
            "screen_id": screen_id,
            "screen_name": screen.get("name") if screen else "Unknown",
            "resolution": screen.get("specs", {}).get("resolution", "1920x1080") if screen else "1920x1080",
            # The player rotates itself to this value, so the admin never has to
            # touch the TV: whatever orientation the screen was created with wins.
            "orientation": screen_orientation(screen),
            "generated_at": now.isoformat(),
            "playlist_version": screen.get("playlist_version", 0) if screen else 0,
            "schedule_key": await effective_playlist_schedule_key(screen_id),
            "total_items": len(items),
            "items": items,
            "loop": True,
            "poll_interval_seconds": 60,
            "config": {
                "reboot_time": device.get("reboot_time", "03:00"),
                "tier": device.get("tier", "tv_direct"),
            }
        }

    @router.get("/player/{screen_id}/test", response_class=HTMLResponse)
    async def certification_test(screen_id: str):
        """Extended certification test: automated tests + 10-min stability + manual checklist. Results submitted to server."""
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        sn = screen.get('name', 'Screen')
        html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MediaView Cert Test</title>'
        html += '<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#09090F;color:#E2E8F0;font-family:Segoe UI,Arial,sans-serif;padding:20px 28px;overflow-y:auto}h1{font-size:22px;color:#A5B4FC;margin-bottom:2px}h2{font-size:13px;color:#64748B;margin-bottom:16px}.sec{margin-bottom:20px}.sec h3{font-size:11px;font-weight:700;color:#6366F1;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid #1E293B}'
        html += '.t{display:flex;align-items:center;padding:8px 12px;border-bottom:1px solid #111827;gap:10px}.t .i{width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;flex-shrink:0}.i.p{background:#064E3B;color:#10B981}.i.f{background:#450A0A;color:#EF4444}.i.r{background:#1E293B;color:#64748B}.i.w{background:#422006;color:#F59E0B}.t .n{flex:1;font-size:13px}.t .d{font-size:11px;color:#64748B;text-align:right;max-width:45%}'
        html += '.bar{margin:12px 0;height:4px;background:#1E293B;border-radius:2px}.bar div{height:100%;background:#6366F1;border-radius:2px;transition:width .3s}.sum{margin:16px 0;padding:16px;border-radius:10px;text-align:center}.sum.ok{background:#064E3B;border:1px solid #10B981}.sum.no{background:#450A0A;border:1px solid #EF4444}.sum h3{font-size:18px}.sum p{font-size:12px;color:#94A3B8}'
        html += '.chk{padding:10px 12px;border-bottom:1px solid #111827;display:flex;align-items:center;gap:10px;cursor:pointer}.chk input{width:18px;height:18px;accent-color:#6366F1}.chk label{font-size:13px;flex:1;cursor:pointer}.chk .st{font-size:11px;color:#64748B}'
        html += '.inf{padding:12px;background:#1E293B;border-radius:8px;font-size:11px;color:#94A3B8;margin-top:12px}.inf b{color:#E2E8F0}btn,.btn{display:inline-block;padding:12px 24px;border-radius:8px;border:none;font-size:14px;font-weight:600;cursor:pointer;margin-top:12px}.btn-p{background:#4F46E5;color:#fff}.btn-s{background:#1E293B;color:#A5B4FC;margin-left:8px}</style></head><body>'
        html += '<h1>MediaView - Certification Test Suite</h1><h2>Screen: ' + sn + '</h2>'
        html += '<div class="bar"><div id="pg" style="width:0%"></div></div>'
        html += '<div class="sec"><h3>Phase 1: Automated Tests</h3><div id="tests"></div></div>'
        html += '<div id="stab-sec" style="display:none" class="sec"><h3>Phase 2: Stability Test (10 minutes)</h3><div id="stab"></div></div>'
        html += '<div id="manual-sec" style="display:none" class="sec"><h3>Phase 3: Manual Validation</h3><p style="font-size:12px;color:#94A3B8;margin-bottom:10px">Complete these checks and mark each one:</p><div id="manual"></div></div>'
        html += '<div id="result"></div>'
        html += '<div class="inf"><b>Device:</b> <span id="di">Detecting...</span> | <b>Screen:</b> ' + screen_id + ' | <b>Time:</b> <span id="ti"></span></div>'
        js = '<script>\nvar SID="' + screen_id + '",AB=location.origin,tests=[],passed=0,failed=0;\n'
        js += 'document.getElementById("di").textContent=navigator.platform+(navigator.userAgent.includes("Android")?" (Android TV)":"");\n'
        js += 'document.getElementById("ti").textContent=new Date().toLocaleString();\n'
        js += 'function at(n,s,d){var idx=tests.length;tests.push({n:n,s:s,d:d||""});rn();return idx}\n'
        js += 'function ut(i,s,d){tests[i].s=s;if(d)tests[i].d=d;if(s==="p")passed++;if(s==="f")failed++;rn()}\n'
        js += 'function rn(){var h="";tests.forEach(function(t){var ic=t.s==="p"?"p":t.s==="f"?"f":t.s==="w"?"w":"r";var tx=t.s==="p"?"OK":t.s==="f"?"X":t.s==="w"?"!":"...";h+=\'<div class="t"><div class="i \'+ic+\'">\'+tx+\'</div><div class="n">\'+t.n+\'</div><div class="d">\'+t.d+\'</div></div>\'});document.getElementById("tests").innerHTML=h;document.getElementById("pg").style.width=Math.round((passed+failed)/Math.max(tests.length,1)*100)+"%"}\n'
        js += 'async function phase1(){\n'
        js += 'var names=["Server Connectivity","Screen Data","Playlist API","Media Download","localStorage Write/Read","localStorage 5KB","Image Render","Video Codec","Timer 3s","Network Latency","Concurrent 3x","Resolution","Heartbeat"];\n'
        js += 'var fns=[\n'
        js += 'async function(){var r=await fetch(AB+"/api/health");var d=await r.json();return[d.status==="healthy","API "+d.status]},\n'
        js += 'async function(){var r=await fetch(AB+"/api/screens/' + screen_id + '");var d=await r.json();return[!!d.id,d.name||"Error"]},\n'
        js += 'async function(){var r=await fetch(AB+"/api/player/' + screen_id + '/playlist");var d=await r.json();return[true,d.total_items+" items"]},\n'
        js += 'async function(){var r=await fetch(AB+"/api/player/' + screen_id + '/playlist");var d=await r.json();if(d.items&&d.items.length>0){var m=await fetch(AB+d.items[0].media_url);return[m.ok,"HTTP "+m.status]}return[true,"Empty playlist"]},\n'
        js += 'async function(){localStorage.setItem("mv_ct","ok");var v=localStorage.getItem("mv_ct");localStorage.removeItem("mv_ct");return[v==="ok","OK"]},\n'
        js += 'async function(){var b="x".repeat(5000);localStorage.setItem("mv_5k",b);var v=localStorage.getItem("mv_5k");localStorage.removeItem("mv_5k");return[v&&v.length===5000,"5KB OK"]},\n'
        js += 'async function(){var img=new Image();await new Promise(function(ok,no){img.onload=ok;img.onerror=no;img.src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="});return[true,"PNG OK"]},\n'
        js += 'async function(){var v=document.createElement("video");return[true,"MP4:"+v.canPlayType("video/mp4")+" WebM:"+v.canPlayType("video/webm")]},\n'
        js += 'async function(){var s=Date.now();await new Promise(function(ok){setTimeout(ok,3000)});var d=Math.abs(Date.now()-s-3000);return[d<500,"Drift:"+d+"ms"]},\n'
        js += 'async function(){var s=Date.now();await fetch(AB+"/api/health");return[true,(Date.now()-s)+"ms"]},\n'
        js += 'async function(){var r=await Promise.all([fetch(AB+"/api/health"),fetch(AB+"/api/screens/' + screen_id + '"),fetch(AB+"/api/player/' + screen_id + '/playlist")]);return[r.every(function(x){return x.ok}),r.map(function(x){return x.status}).join(",")]},\n'
        js += 'async function(){return[true,(screen.width||innerWidth)+"x"+(screen.height||innerHeight)]},\n'
        js += 'async function(){var r=await fetch(AB+"/api/player/' + screen_id + '/status");var d=await r.json();return[d.status==="online","Status:"+d.status]}\n'
        js += '];\n'
        js += 'for(var i=0;i<names.length;i++){var idx=at(names[i],"r","...");try{var res=await fns[i]();ut(idx,res[0]?"p":"f",res[1])}catch(e){ut(idx,"f",e.message)}}\n'
        js += '}\n'
        js += 'async function phase2(){document.getElementById("stab-sec").style.display="block";var dur=600,el=0,errs=0,fts=0;var si=at("Stability 10min","w","Starting...");var iv=setInterval(async function(){el+=10;fts++;try{await fetch(AB+"/api/player/' + screen_id + '/playlist");ut(si,"w",Math.floor(el/60)+"m"+el%60+"s F:"+fts+" E:"+errs)}catch(e){errs++;ut(si,"w",Math.floor(el/60)+"m"+el%60+"s F:"+fts+" E:"+errs)}if(el>=dur){clearInterval(iv);ut(si,errs===0?"p":"f","Done:"+fts+" fetches,"+errs+" errors")}},10000);await new Promise(function(ok){setTimeout(ok,dur*1000)})}\n'
        js += 'function phase3(){document.getElementById("manual-sec").style.display="block";var checks=[["auto-boot","Auto-Start: Power OFF, wait 10s, power ON. Did MediaView start automatically?"],["home-btn","HOME Button: Press HOME. Does MediaView stay on screen?"],["offline","Offline: Disconnect WiFi. Does cached content keep showing?"],["reconnect","Reconnect: Reconnect WiFi. Does it auto-sync?"],["stability","1-Hour: Leave running 1hr. Any freezes or crashes?"],["remote","Remote Keys: Vol/Ch/Back buttons. Player stays fullscreen?"]];'
        js += 'var h="";checks.forEach(function(c){h+=\'<div class="chk"><input type="checkbox" id="chk-\'+c[0]+\'"><label for="chk-\'+c[0]+\'">\'+c[1]+\'</label></div>\'});'
        js += 'h+=\'<div style="margin-top:14px"><input type="text" id="brand" placeholder="TV Brand" style="background:#1E293B;border:1px solid #312E81;color:#E2E8F0;padding:10px;border-radius:8px;width:46%;margin-right:2%"><input type="text" id="model" placeholder="Model" style="background:#1E293B;border:1px solid #312E81;color:#E2E8F0;padding:10px;border-radius:8px;width:46%"></div>\';'
        js += 'h+=\'<div style="margin-top:12px"><button onclick="submitR()" style="background:#4F46E5;color:#fff;padding:12px 24px;border-radius:8px;border:none;font-size:14px;font-weight:600;cursor:pointer">Submit Results</button></div>\';'
        js += 'document.getElementById("manual").innerHTML=h}\n'
        js += 'async function submitR(){var brand=document.getElementById("brand").value||"Unknown";var model=document.getElementById("model").value||"Unknown";var mc={};document.querySelectorAll("#manual input[type=checkbox]").forEach(function(c){mc[c.id.replace("chk-","")]=c.checked});var mp=Object.values(mc).filter(function(v){return v}).length;var mt=Object.values(mc).length;'
        js += 'try{var r=await fetch(AB+"/api/certification/submit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({device_brand:brand,device_model:model,os_version:navigator.userAgent,screen_resolution:(screen.width||innerWidth)+"x"+(screen.height||innerHeight),user_agent:navigator.userAgent,tests_passed:passed,tests_failed:failed,tests_total:tests.length,test_details:tests.map(function(t){return{name:t.n,status:t.s,detail:t.d}}),stability_minutes:10,manual_checks:mc})});'
        js += 'var d=await r.json();var ok=failed===0&&mp===mt;document.getElementById("result").innerHTML=\'<div class="sum \'+(ok?"ok":"no")+\'"><h3>\'+(ok?"CERTIFIED":"NEEDS REVIEW")+\'</h3><p>Auto:\'+passed+"/"+tests.length+" Manual:"+mp+"/"+mt+\'</p><p style="font-size:11px">\'+brand+" "+model+" | Saved to server</p></div>"}catch(e){document.getElementById("result").innerHTML=\'<div class="sum no"><h3>Error</h3><p>\'+e.message+"</p></div>"}}\n'
        js += 'async function run(){await phase1();await phase2();phase3()}\nrun();\n'
        js += '</script></body></html>'
        html += js
        return HTMLResponse(content=html)

    return router
