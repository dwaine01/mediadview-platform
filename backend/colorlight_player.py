"""
MediAd View — Direct Player Server (replaces ColorlightCloud as device cloud).

Implements Colorlight's "Integrate to Player" protocol from
  https://developer.colorlightcloud.com/cloudServer/dui-jie-she-bei/

Endpoints the A40 device firmware expects to find on the server (URL it points to):
  1. PUT  /wp-json/screen/v1/status          ← device reports status (heartbeat)
  2. GET  /wp-json/wp/v2/comments            ← device polls for commands
  3. POST /wp-json/wp/v2/comments            ← device confirms command execution
  4. GET  /wp-json/wp/v2/programs            ← device gets program list
  5. GET  /wp-json/wp/v2/media               ← device gets material list
  6. GET  /wp-content/upload/<path>          ← device downloads material files

In our setup the A40 URL is set to "https://<our-domain>/api" so all routes are
mounted under /api/...

Authentication: HTTP Basic Auth (username=device_id, password=secret_key) —
records are stored in db.colorlight_terminals (created by colorlight.py provision flow).

MediaView admin uses /api/cls/... endpoints (Colorlight Server admin) to:
  • queue commands
  • publish programs
  • see live device status
"""
import os
import json
import base64
import hashlib
import secrets
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Header, Request, Query, Body
from fastapi.responses import FileResponse, Response, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Directory where material files (images/videos) are stored on the host
MEDIA_DIR = os.path.join(os.path.dirname(__file__), "media", "cls")
os.makedirs(MEDIA_DIR, exist_ok=True)


# ============ HELPERS ============

def _parse_basic_auth(auth_header: Optional[str]) -> Optional[tuple]:
    """Decode 'Basic <b64>' header → (user, pass) or None."""
    if not auth_header or not auth_header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(auth_header.split(None, 1)[1]).decode("utf-8")
        if ":" in decoded:
            u, p = decoded.split(":", 1)
            return (u, p)
    except Exception:
        pass
    return None


def _file_md5(path: str) -> str:
    """Calculate the upper-case MD5 of a file (Colorlight naming convention)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _bytes_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


# ============ ROUTER ============

def create_player_routes(db):
    """Build and return an APIRouter with all the device-facing and internal endpoints.

    `db` is the motor AsyncIO MongoDB database handle.
    """

    router = APIRouter()

    # ============ AUTH DEPENDENCY ============
    async def _authenticate_device(authorization: Optional[str] = Header(None)) -> Dict:
        """Validate Basic Auth against db.colorlight_terminals.
        Returns the matched terminal document or raises 401."""
        creds = _parse_basic_auth(authorization)
        if not creds:
            raise HTTPException(401, "Missing or invalid Basic Auth", headers={"WWW-Authenticate": "Basic"})
        device_id, secret_key = creds
        term = await db.colorlight_terminals.find_one({"device_id": device_id, "secret_key": secret_key})
        if not term:
            logger.warning(f"[cls] Auth failed for device_id={device_id}")
            raise HTTPException(401, "Invalid Device ID or Secret Key", headers={"WWW-Authenticate": "Basic"})
        return term

    # ════════════════════════════════════════════════════════════════════
    # PUBLIC DEVICE-FACING ENDPOINTS (exact paths the A40 firmware expects)
    # ════════════════════════════════════════════════════════════════════

    # ────────── 1. STATUS / HEARTBEAT ──────────
    @router.put("/wp-json/screen/v1/status")
    async def device_report_status(req: Request, term=Depends(_authenticate_device)):
        """A40 reports its full status (terminal info, vsns playing, brightness,
        volume, RTC, network, etc.). Called periodically (default 30s)."""
        try:
            payload = await req.json()
        except Exception:
            payload = {}
        await db.colorlight_terminal_status.update_one(
            {"device_id": term["device_id"]},
            {"$set": {
                "device_id": term["device_id"],
                "terminal_id": term.get("terminal_id"),
                "status": payload,
                "last_seen": _now_iso(),
                "online": True,
            }},
            upsert=True,
        )
        await db.colorlight_terminals.update_one(
            {"device_id": term["device_id"]},
            {"$set": {"last_seen": _now_iso(), "online": True,
                      "firmware": payload.get("info", {}).get("vername"),
                      "serial":   payload.get("info", {}).get("serialno"),
                      "model":    payload.get("info", {}).get("model")}}
        )
        return {"code": 200, "message": "success"}

    # ────────── 2. COMMAND POLLING (HTTP) ──────────
    @router.get("/wp-json/wp/v2/comments")
    async def device_poll_commands(clt_type: str = Query(...), device_num: Optional[str] = Query(None),
                                    term=Depends(_authenticate_device)):
        """A40 polls this every 5 seconds asking 'any commands for me?'.
        Returns array of command objects pending execution."""
        if clt_type != "terminal":
            return []
        # Find unsent commands for this device
        cursor = db.colorlight_commands.find({
            "device_id": term["device_id"],
            "status": "pending",
        }).sort("created_at", 1).limit(20)
        cmds = []
        async for c in cursor:
            cmds.append({
                "id":          c["cmd_id"],
                "post":        term.get("terminal_id") or 0,
                "karma":       c.get("karma", 2),          # 2 = PUT (most common)
                "ContentDTO": {
                    "raw":        c.get("raw") or "{}",
                    "author_url": c["author_url"],
                },
            })
            # mark as dispatched (waiting for device confirmation)
            await db.colorlight_commands.update_one(
                {"_id": c["_id"]},
                {"$set": {"status": "dispatched", "dispatched_at": _now_iso()}}
            )
        return cmds

    # ────────── 3. COMMAND CONFIRMATION (device → server) ──────────
    @router.post("/wp-json/wp/v2/comments")
    async def device_confirm_command(req: Request, term=Depends(_authenticate_device)):
        """A40 calls this after validating each received command."""
        try:
            body = await req.json()
        except Exception:
            body = {}
        cmd_id = body.get("parent")
        content = body.get("content", "")
        if cmd_id is None:
            return Response(status_code=200)
        await db.colorlight_commands.update_one(
            {"cmd_id": int(cmd_id), "device_id": term["device_id"]},
            {"$set": {"status": "confirmed", "confirmed_at": _now_iso(),
                      "device_response": content}}
        )
        return {"code": 200, "id": cmd_id, "content": content}

    # ────────── 4. PROGRAM LIST (the A40 fetches its assigned playlists) ──────────
    @router.get("/wp-json/wp/v2/programs")
    async def device_program_list(clt_type: str = Query(...),
                                   term=Depends(_authenticate_device)):
        if clt_type != "terminal":
            return []
        cursor = db.colorlight_programs.find({
            "device_id": term["device_id"],
            "active": True,
        }).sort("modified", -1)
        out = []
        async for p in cursor:
            out.append({
                "id":            p["program_id"],
                "date":          p.get("created", _now_iso()),
                "date_gmt":      p.get("created", _now_iso()),
                "modified":      p.get("modified", _now_iso()),
                "modified_gmt":  p.get("modified", _now_iso()),
                "type":          "program",
                "title": {"rendered": p["name"]},
                "_links": {
                    "wp:attachment": [{
                        "href": f"/api/wp-json/wp/v2/media?parent={p['program_id']}"
                    }]
                }
            })
        return out

    # ────────── 5. MATERIAL LIST (the A40 fetches files for one program) ──────────
    @router.get("/wp-json/wp/v2/media")
    async def device_media_list(parent: int = Query(...),
                                 term=Depends(_authenticate_device)):
        prog = await db.colorlight_programs.find_one({"program_id": parent,
                                                       "device_id": term["device_id"]})
        if not prog:
            return []
        materials = prog.get("materials", [])
        out = []
        for m in materials:
            out.append({
                "attachment_filesize": m["size"],
                "source_url": m["source_url"],  # F_<MD5>_<SIZE>.<ext>
            })
        return out

    # ────────── 6. MATERIAL FILE DOWNLOAD ──────────
    @router.get("/wp-content/upload/{filename}")
    async def device_download_material(filename: str, term=Depends(_authenticate_device)):
        # File on disk must follow F_<MD5>_<SIZE>.<ext>
        path = os.path.join(MEDIA_DIR, filename)
        if not os.path.exists(path):
            raise HTTPException(404, "Material not found")
        return FileResponse(path)

    # Alternate path some firmware versions use
    @router.get("/cls-media/{filename}")
    async def device_download_material_alt(filename: str, term=Depends(_authenticate_device)):
        path = os.path.join(MEDIA_DIR, filename)
        if not os.path.exists(path):
            raise HTTPException(404, "Material not found")
        return FileResponse(path)

    # ════════════════════════════════════════════════════════════════════
    # INTERNAL API for MediAd View Admin Panel
    # ════════════════════════════════════════════════════════════════════

    class DirectPushReq(BaseModel):
        device_id: str
        media_base64: str            # data URL or raw base64
        filename: str
        content_type: str = "image/jpeg"
        title: str = "MediAd View Push"
        width: int = 192
        height: int = 320
        duration_ms: int = 8000

    class CommandReq(BaseModel):
        device_id: str
        author_url: str              # e.g. "api/brightness", "api/reboot"
        content: Optional[Dict[str, Any]] = None
        karma: int = 2               # 2=PUT (default), 0=GET, 1=POST, 3=DELETE

    @router.get("/cls/devices")
    async def admin_list_direct_devices():
        """List all terminals that have been provisioned (direct mode)."""
        cursor = db.colorlight_terminals.find({}).sort("created_at", -1)
        out = []
        async for t in cursor:
            status_doc = await db.colorlight_terminal_status.find_one({"device_id": t["device_id"]})
            # online if seen in the last 2 minutes
            online = False
            last_seen = t.get("last_seen") or (status_doc or {}).get("last_seen")
            if last_seen:
                try:
                    delta = (datetime.utcnow() - datetime.fromisoformat(last_seen.replace("Z",""))).total_seconds()
                    online = delta < 120
                except Exception:
                    online = False
            out.append({
                "device_id":   t["device_id"],
                "title":       t.get("title"),
                "url":         t.get("url"),
                "terminal_id": t.get("terminal_id"),
                "group_id":    t.get("group_id"),
                "model":       t.get("model"),
                "serial":      t.get("serial"),
                "firmware":    t.get("firmware"),
                "last_seen":   last_seen,
                "online":      online,
                "status":      (status_doc or {}).get("status", {}),
            })
        return {"devices": out, "total": len(out)}

    @router.get("/cls/devices/{device_id}/status")
    async def admin_get_device_status(device_id: str):
        s = await db.colorlight_terminal_status.find_one({"device_id": device_id})
        if not s:
            return {"device_id": device_id, "status": None, "last_seen": None, "online": False}
        s.pop("_id", None)
        return s

    @router.post("/cls/command")
    async def admin_queue_command(req: CommandReq):
        """Queue a command for delivery to a device. The device will pick it up
        in its next poll cycle (within 5 seconds for HTTP, instant for WebSocket)."""
        term = await db.colorlight_terminals.find_one({"device_id": req.device_id})
        if not term:
            raise HTTPException(404, "Device not found")
        # Generate a unique command ID (must be unique among the last 2 consecutive
        # commands sent to the device — using current timestamp ms ensures that)
        cmd_id = int(datetime.utcnow().timestamp() * 1000) % 1_000_000_000
        raw = json.dumps(req.content) if req.content is not None else "{}"
        await db.colorlight_commands.insert_one({
            "cmd_id":      cmd_id,
            "device_id":   req.device_id,
            "author_url":  req.author_url,
            "raw":         raw,
            "karma":       req.karma,
            "status":      "pending",
            "created_at":  _now_iso(),
        })
        return {"ok": True, "cmd_id": cmd_id, "device_id": req.device_id}

    @router.post("/cls/push")
    async def admin_publish_program(req: DirectPushReq):
        """Upload media + create program + tell device to refresh program list.
        Full E2E: bytes → file on disk → program in DB → 'update program' command."""
        term = await db.colorlight_terminals.find_one({"device_id": req.device_id})
        if not term:
            raise HTTPException(404, "Device not found")
        # 1. Decode and save the file
        b64 = req.media_base64
        if "," in b64 and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        try:
            raw_bytes = base64.b64decode(b64)
        except Exception as e:
            raise HTTPException(400, f"Invalid base64: {e}")
        size = len(raw_bytes)
        md5 = _bytes_md5(raw_bytes)
        ext = (req.filename.rsplit(".", 1)[-1] if "." in req.filename else "jpg").lower()
        # Colorlight material file naming: F_<MD5>_<SIZE>.<ext>
        material_name = f"F_{md5}_{size}.{ext}"
        file_path = os.path.join(MEDIA_DIR, material_name)
        with open(file_path, "wb") as f:
            f.write(raw_bytes)

        # 2. Generate program ID and vsn name
        program_id = int(datetime.utcnow().timestamp() * 1000) % 1_000_000_000
        program_name = f"Playlist{program_id}"
        vsn_name = f"{program_name}_{md5.lower()}_{size}.vsn"

        # 3. Insert program record
        now = _now_iso()
        await db.colorlight_programs.insert_one({
            "program_id": program_id,
            "device_id":  req.device_id,
            "name":       req.title or program_name,
            "vsn_name":   vsn_name,
            "active":     True,
            "created":    now,
            "modified":   now,
            "width":      req.width,
            "height":     req.height,
            "duration_ms": req.duration_ms,
            "materials": [{
                "filename":    material_name,
                "source_url":  f"/api/wp-content/upload/{material_name}",
                "md5":         md5,
                "size":        size,
                "content_type": req.content_type,
            }],
        })

        # 4. Queue an "update program" command so the device fetches the new program
        cmd_id = int(datetime.utcnow().timestamp() * 1000) % 1_000_000_000 + 1
        await db.colorlight_commands.insert_one({
            "cmd_id":      cmd_id,
            "device_id":   req.device_id,
            "author_url":  "api/program/update",
            "raw":         "{}",
            "karma":       2,
            "status":      "pending",
            "created_at":  _now_iso(),
        })
        return {
            "ok": True,
            "program_id":  program_id,
            "vsn_name":    vsn_name,
            "material":    material_name,
            "size":        size,
            "md5":         md5,
            "command_id":  cmd_id,
            "note":        "Device will fetch within 5s. Check status afterwards.",
        }

    # ────────── Convenience command shortcuts ──────────
    class BrightnessReq(BaseModel):
        device_id: str
        value: int  # 0-255

    @router.post("/cls/brightness")
    async def admin_set_brightness(req: BrightnessReq):
        if not (0 <= req.value <= 255):
            raise HTTPException(400, "Brightness must be 0-255")
        return await admin_queue_command(CommandReq(
            device_id=req.device_id,
            author_url="api/brightness",
            content={"brightness": req.value},
        ))

    class VolumeReq(BaseModel):
        device_id: str
        value: int  # 0-15

    @router.post("/cls/volume")
    async def admin_set_volume(req: VolumeReq):
        if not (0 <= req.value <= 15):
            raise HTTPException(400, "Volume must be 0-15")
        return await admin_queue_command(CommandReq(
            device_id=req.device_id,
            author_url="api/volume",
            content={"musicvolume": req.value},
        ))

    @router.post("/cls/reboot/{device_id}")
    async def admin_reboot(device_id: str):
        return await admin_queue_command(CommandReq(
            device_id=device_id, author_url="api/reboot", content={},
        ))

    @router.post("/cls/screenshot/{device_id}")
    async def admin_screenshot(device_id: str):
        return await admin_queue_command(CommandReq(
            device_id=device_id, author_url="api/screenshot", content={},
        ))

    @router.post("/cls/clear-program/{device_id}")
    async def admin_clear_programs(device_id: str):
        # Disable all programs in DB then send clear command
        await db.colorlight_programs.update_many(
            {"device_id": device_id, "active": True},
            {"$set": {"active": False}}
        )
        return await admin_queue_command(CommandReq(
            device_id=device_id, author_url="api/program/clear", content={},
        ))

    @router.get("/cls/commands/{device_id}")
    async def admin_list_recent_commands(device_id: str, limit: int = 30):
        cursor = db.colorlight_commands.find({"device_id": device_id}).sort("created_at", -1).limit(limit)
        out = []
        async for c in cursor:
            c.pop("_id", None)
            out.append(c)
        return {"commands": out, "device_id": device_id}

    return router
