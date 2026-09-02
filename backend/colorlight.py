"""
MediAd View — ColorlightCloud Integration (us33.colorlightcloud.com)
SAFE MODE: read-only by default. Publishing requires explicit user confirmation.
"""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("colorlight")


def _fernet():
    """Reuse the same Fernet key as finance_email for password encryption."""
    from finance_email import _get_fernet
    return _get_fernet()


def encrypt(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:
        return ""


class ColorlightSession:
    """Manages auth + read/write requests against a ColorlightCloud tenant."""

    def __init__(self, server: str, username: str, password: str):
        self.server = server.rstrip("/")
        if not self.server.startswith("http"):
            self.server = "https://" + self.server
        self.username = username
        self.password = password
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "MediAdView/1.0 (Integration)",
            "Accept": "application/json",
        })
        self.nonce: Optional[str] = None

    def login(self) -> Dict[str, Any]:
        """ColorlightCloud uses WP-form login (JSESSIONID cookie).
        Try form login FIRST (confirmed method), then JWT / Basic as fallback."""
        last_err = ""

        # 1) ColorlightCloud form login (confirmed method — sets JSESSIONID cookie)
        try:
            url = self.server + "/wp-login.php"
            r = self.s.post(url, data={
                "log": self.username,
                "pwd": self.password,
                "wp-submit": "Log In",
                "redirect_to": self.server + "/wp-admin/",
                "testcookie": "1",
            }, timeout=20, allow_redirects=True)
            cookies = self.s.cookies.get_dict()
            cookie_str = " ".join(cookies.keys()).lower()
            # Success indicators: JSESSIONID cookie OR wordpress_logged_in OR redirect to wp-admin
            authed = (
                "jsessionid" in cookie_str
                or "wordpress_logged_in" in cookie_str
                or "/wp-admin" in r.url
            )
            if authed:
                # Probe a protected endpoint to confirm the session really works
                probe = self.s.get(self.server + "/wp-json/wp/v2/terminalgroup",
                                   params={"per_page": 1}, timeout=15)
                if probe.status_code == 200:
                    logger.info(f"[colorlight] Form login OK (JSESSIONID). Cookies: {list(cookies.keys())}")
                    return {"ok": True, "method": "form", "cookies": list(cookies.keys())}
                last_err = f"form login set cookies but probe → HTTP {probe.status_code}"
            else:
                last_err = f"/wp-login.php → HTTP {r.status_code}, no auth cookies set"
        except Exception as e:
            last_err = f"/wp-login.php → {e}"

        # 2) JWT fallback (some modern WP installs)
        try:
            url = self.server + "/wp-json/jwt-auth/v1/token"
            r = self.s.post(url, json={"username": self.username, "password": self.password}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                token = data.get("token") or data.get("access_token")
                if token:
                    self.s.headers["Authorization"] = f"Bearer {token}"
                    logger.info("[colorlight] JWT login OK")
                    return {"ok": True, "method": "jwt", "token": "*****"}
            last_err = f"jwt → HTTP {r.status_code}"
        except Exception as e:
            last_err = f"jwt → {e}"

        # 3) Basic auth fallback
        try:
            url = self.server + "/wp-json/wp/v2/users/me"
            r = self.s.get(url, auth=(self.username, self.password), timeout=15)
            if r.status_code == 200:
                self.s.auth = (self.username, self.password)
                logger.info("[colorlight] Basic auth OK")
                return {"ok": True, "method": "basic"}
            last_err = f"basic → HTTP {r.status_code}"
        except Exception as e:
            last_err = f"basic → {e}"

        raise RuntimeError(f"Could not authenticate against ColorlightCloud. Last error: {last_err}")

    # ============ READ-ONLY METHODS (safe to call against production) ============
    def get_terminal_groups(self) -> List[Dict[str, Any]]:
        """List all groups (high-level)."""
        r = self.s.get(self.server + "/wp-json/wp/v2/terminalgroup",
                       params={"schedule": "true", "per_page": 100}, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"GET terminalgroup → HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        return data if isinstance(data, list) else data.get("groups", [])

    def get_group_detail(self, group_id: int) -> Dict[str, Any]:
        """Per-group detail — contains the 'leds' (terminals) array."""
        r = self.s.get(self.server + f"/wp-json/wp/v2/terminalgroup/{group_id}", timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"GET terminalgroup/{group_id} → HTTP {r.status_code}")
        return r.json()

    def get_all_terminals(self) -> List[Dict[str, Any]]:
        """Walk all groups and fetch each group's terminals (leds)."""
        groups = self.get_terminal_groups()
        out = []
        for g in groups:
            gid = g.get("id")
            try:
                detail = self.get_group_detail(gid)
            except Exception:
                continue
            for led in (detail.get("leds") or []):
                out.append({
                    "group_id": gid,
                    "group_name": detail.get("name") or g.get("name", "(unnamed)"),
                    "group_description": detail.get("description", ""),
                    "terminal_id": led.get("led_id"),
                    "terminal_name": led.get("led_name") or f"Terminal {led.get('led_id')}",
                    "last_seen": led.get("_led_latest_report_time"),
                    "description": led.get("led_description", ""),
                })
        return out

    def get_terminals_flat(self):
        return self.get_all_terminals()

    # ============ WRITE METHODS (require explicit confirmation in UI) ============
    def upload_media(self, file_bytes: bytes, filename: str, content_type: str = "image/jpeg") -> Dict[str, Any]:
        """POST /wp-json/wp/v2/media (multipart). Returns {fileID, source_url, src}."""
        files = {"file": (filename, file_bytes, content_type)}
        r = self.s.post(self.server + "/wp-json/wp/v2/media", files=files, timeout=120)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"upload_media HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        # Normalize the response — different ColorlightCloud versions use different keys
        return {
            "fileID":     d.get("fileID") or d.get("id"),
            "source_url": d.get("source_url") or d.get("guid", {}).get("rendered") if isinstance(d.get("guid"), dict) else d.get("guid"),
            "src":        (d.get("media_details", {}).get("sizes", {}).get("thumbnail", {}).get("source_url")
                          if isinstance(d.get("media_details"), dict) else None) or d.get("src") or d.get("source_url"),
            "filename":   filename,
            "file_type":  content_type.split("/")[-1] if "/" in content_type else "jpeg",
            "width":      d.get("media_details", {}).get("width", 900) if isinstance(d.get("media_details"), dict) else 900,
            "height":     d.get("media_details", {}).get("height", 1600) if isinstance(d.get("media_details"), dict) else 1600,
            "_raw":       d,
        }

    def create_program(self, name: str, media_items: List[Dict[str, Any]],
                       width: int = 192, height: int = 320,
                       page_duration_ms: int = 3600000,
                       per_item_duration_ms: int = 8000) -> Dict[str, Any]:
        """POST /wp-json/wp/v2/programs. media_items = [{fileID, name, source_url, src, file_type, width, height}, ...]
        Returns program_id."""
        children = []
        for it in media_items:
            children.append({
                "fileID": it["fileID"],
                "name": it.get("filename") or it.get("name") or "media",
                "type": "image" if it.get("file_type", "jpeg") in ("jpeg","jpg","png","gif","webp") else "video",
                "file_type": it.get("file_type", "jpeg"),
                "author": self.username,
                "source_url": it.get("source_url", ""),
                "src": it.get("src") or it.get("source_url", ""),
                "Duration": per_item_duration_ms,
                "IsSchedule": 0,
                "Schedule": {
                    "IsLimitTime": 0,
                    "StartTime": "00:00:00",
                    "EndTime": "23:59:59",
                    "IsLimitDate": 0,
                    "IsLimitWeek": 0,
                    "LimitWeek": [1,1,1,1,1,1,1],
                },
                "Trigger": {"Type": "lightStrip", "Value": "0"},
                "thumbnailSize": {"width": 113, "height": 200},
                "fullSize": {"width": it.get("width", 900), "height": it.get("height", 1600)},
            })

        payload = {
            "title": name,
            "Terminalgroup": [],
            "program_info": {
                "name": name, "displayName": name,
                "isCrop": 0, "id": 10, "type": "contents",
                "version": 4, "selectChild": 0, "addNum": 1, "overStage": False,
                "info": {"Information": {"Width": width, "Height": height, "Scale": 1}, "Pages": []},
                "children": [{
                    "name": "Page1", "id": 11, "index": 1, "type": "page",
                    "selectChild": 0, "addNum": 1,
                    "info": {
                        "AppointDuration": page_duration_ms, "Opacity": 1, "LoopType": 1,
                        "BgColor": "0xFF000000", "Regions": []
                    },
                    "children": [{
                        "name": "File Window", "id": 12, "index": 1, "type": "fileWindow", "vsnType": 3,
                        "Rect": {"X": 0, "Y": 0, "Width": width, "Height": height,
                                  "BorderWidth": 0, "BorderColor": "#ffff00"},
                        "IsScheduleRegion": 0, "selectChild": None,
                        "children": children,
                    }]
                }]
            }
        }
        r = self.s.post(self.server + "/wp-json/wp/v2/programs",
                        json=payload, timeout=30,
                        headers={"Content-Type": "application/json"})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"create_program HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        program_id = d.get("id") or d.get("program_id") or d.get("ID")
        if not program_id:
            raise RuntimeError(f"create_program: no program_id in response: {str(d)[:200]}")
        return {"program_id": program_id, "_raw": d}

    def publish_program(self, program_id: int, group_id: int,
                        terminal_ids: List[int], mode: str = "single") -> Dict[str, Any]:
        """PUT /wp-json/wp/v2/programs/{id}?flag=terminalgroup.
        mode: 'group' = all=true (whole group), 'single' = all=false (specific terminals)."""
        if mode not in ("group", "single"):
            raise ValueError("mode must be 'group' or 'single'")
        if not terminal_ids:
            raise ValueError("terminal_ids cannot be empty")
        payload = {
            "what": "assign_program_to_terminal_group",
            "to": {
                "terminals_groups": [{
                    "all": (mode == "group"),
                    "id": group_id,
                    "terminals": terminal_ids,
                }]
            }
        }
        r = self.s.put(self.server + f"/wp-json/wp/v2/programs/{program_id}",
                       params={"flag": "terminalgroup"},
                       json=payload, timeout=30,
                       headers={"Content-Type": "application/json"})
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(f"publish HTTP {r.status_code}: {r.text[:300]}")
        return {"ok": True, "program_id": program_id, "mode": mode,
                "group_id": group_id, "terminals": terminal_ids,
                "status_code": r.status_code}

    # ---------- TERMINAL PROVISIONING (auto-create A40 in ColorlightCloud) ----------
    @staticmethod
    def _gen_credentials() -> Dict[str, str]:
        """Generate Device ID + Secret Key + dummy email exactly like ColorlightCloud's
        front-end does. Format matches the HAR capture:
          - username (Device ID): 12 chars [A-Za-z0-9]
          - password (Secret Key): 15 chars [A-Za-z0-9]
          - email: 7-digit-number @lednets.com
        """
        import random
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        username = "".join(secrets.choice(alphabet) for _ in range(12))
        password = "".join(secrets.choice(alphabet) for _ in range(15))
        email = f"{random.randint(1000000, 9999999)}@lednets.com"
        return {"username": username, "password": password, "email": email}

    def create_terminal(self, title: str, group_id: int,
                        description: str = "",
                        lat: Optional[float] = None,
                        lng: Optional[float] = None) -> Dict[str, Any]:
        """POST /wp-json/wp/v2/leds/account — exact replica of the ColorlightCloud
        web panel's 'Add Terminal' flow. Generates Device ID + Secret Key client-side
        and returns them so the admin can paste them into the A40's Cloud Account page.

        Returns: {"terminal_id", "device_id", "secret_key", "email", "url"}
        """
        creds = self._gen_credentials()
        payload = {
            "terminalModel": {
                "title": title,
                "excerpt": description or "",
                "status": "publish",
                "terminalgroup": [int(group_id)],
                "lat": lat,
                "lng": lng,
                "roles": ["terminal"],
            },
            "accountModel": {
                "email": creds["email"],
                "password": creds["password"],
                "username": creds["username"],
                "roles": ["terminal"],
            },
        }
        r = self.s.post(self.server + "/wp-json/wp/v2/leds/account",
                        json=payload, timeout=30,
                        headers={"Content-Type": "application/json"})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"create_terminal HTTP {r.status_code}: {r.text[:400]}")
        try:
            data = r.json()
        except Exception:
            data = {}
        terminal_id = data.get("id") or data.get("terminal_id")
        return {
            "ok": True,
            "terminal_id": terminal_id,
            "device_id": creds["username"],
            "secret_key": creds["password"],
            "email": creds["email"],
            "url": f"https://{self.server.replace('https://','').replace('http://','').strip('/')}",
            "title": title,
            "group_id": int(group_id),
            "_raw": data,
        }


def create_colorlight_routes(db, get_current_user):
    router = APIRouter(prefix="/api/colorlight", tags=["colorlight"])

    class Settings(BaseModel):
        server: str = "us33.colorlightcloud.com"
        username: str
        password: str

    async def require_admin(user: dict = Depends(get_current_user)):
        if not user or user.get("role") not in ("superadmin", "admin"):
            raise HTTPException(403, "Admin required")
        return user

    async def get_session() -> ColorlightSession:
        cfg = await db.fin_settings.find_one({"_id": "colorlight"})
        if not cfg:
            raise HTTPException(400, "ColorlightCloud not configured yet. Save credentials first.")
        sess = ColorlightSession(cfg["server"], cfg["username"], decrypt(cfg["password_enc"]))
        sess.login()
        return sess

    @router.post("/settings")
    async def save_settings(s: Settings, _admin=Depends(require_admin)):
        # Test the login BEFORE saving
        test = ColorlightSession(s.server, s.username, s.password)
        try:
            res = test.login()
        except Exception as e:
            raise HTTPException(400, f"Login failed: {e}")
        await db.fin_settings.update_one({"_id": "colorlight"}, {"$set": {
            "_id": "colorlight",
            "server": s.server,
            "username": s.username,
            "password_enc": encrypt(s.password),
            "enabled": True,
            "auth_method": res.get("method"),
        }}, upsert=True)
        return {"ok": True, "method": res.get("method")}

    @router.get("/status")
    async def status(_admin=Depends(require_admin)):
        cfg = await db.fin_settings.find_one({"_id": "colorlight"})
        if not cfg:
            return {"configured": False}
        return {
            "configured": True,
            "server": cfg.get("server"),
            "username": cfg.get("username"),
            "method": cfg.get("auth_method"),
        }

    @router.get("/terminals")
    async def list_terminals(_admin=Depends(require_admin)):
        """READ-ONLY: list groups + terminals so admin can pick where to publish."""
        sess = await get_session()
        try:
            raw_groups = sess.get_terminal_groups()
        except Exception as e:
            raise HTTPException(502, f"ColorlightCloud read error: {e}")
        # Build a clean response for the dropdown — fetch detail per group to get leds
        clean_groups = []
        for g in raw_groups:
            gid = g.get("id")
            group_name = (g.get("name")
                          or (g.get("title", {}).get("rendered") if isinstance(g.get("title"), dict) else None)
                          or g.get("title")
                          or f"Group {gid}")
            terms = []
            try:
                detail = sess.get_group_detail(gid)
                for led in (detail.get("leds") or []):
                    led_id = led.get("led_id") or led.get("id")
                    led_name = led.get("led_name") or led.get("name") or f"Terminal {led_id}"
                    last_seen = led.get("_led_latest_report_time") or led.get("last_report_time")
                    # Online if seen in the last 10 minutes
                    online = False
                    try:
                        if last_seen:
                            from datetime import datetime as _dt
                            ts = last_seen if isinstance(last_seen, (int, float)) else None
                            if ts:
                                # Heuristic: treat ms or s
                                ts_s = ts / 1000 if ts > 10_000_000_000 else ts
                                online = (_dt.utcnow().timestamp() - ts_s) < 600
                    except Exception:
                        online = False
                    terms.append({
                        "id": led_id,
                        "name": led_name,
                        "online": online,
                        "model": led.get("led_model", "") or led.get("model", ""),
                        "last_seen": last_seen,
                    })
            except Exception as e:
                logger.warning(f"[colorlight] could not load detail for group {gid}: {e}")
            clean_groups.append({
                "group_id": gid,
                "group_name": group_name,
                "terminals": terms,
                "terminal_count": len(terms),
            })
        return {"groups": clean_groups, "total_groups": len(clean_groups),
                "total_terminals": sum(g["terminal_count"] for g in clean_groups)}

    @router.get("/terminals/flat")
    async def list_terminals_flat(_admin=Depends(require_admin)):
        sess = await get_session()
        return {"items": sess.get_terminals_flat()}

    # ============ TERMINAL PROVISIONING (auto-create A40 in ColorlightCloud) ============
    class ProvisionReq(BaseModel):
        title: str                                 # display name
        group_id: int                              # ColorlightCloud group id
        description: Optional[str] = ""
        lat: Optional[float] = None
        lng: Optional[float] = None
        link_screen_id: Optional[str] = None       # optional MediaView screen id to link

    @router.post("/provision")
    async def provision_terminal(req: ProvisionReq, _admin=Depends(require_admin)):
        """Create a brand-new terminal in ColorlightCloud and return the Device ID
        + Secret Key so the admin can paste them into the A40's Cloud Account page.
        Optionally links the new terminal to an existing MediAd View screen."""
        sess = await get_session()
        try:
            result = sess.create_terminal(
                title=req.title,
                group_id=req.group_id,
                description=req.description or "",
                lat=req.lat, lng=req.lng,
            )
        except Exception as e:
            raise HTTPException(502, f"ColorlightCloud provision failed: {e}")
        # Persist a record so we never lose the credentials
        await db.colorlight_terminals.insert_one({
            **{k: v for k, v in result.items() if k != "_raw"},
            "created_at": datetime.utcnow().isoformat(),
            "linked_screen_id": req.link_screen_id,
        })
        # If linked to a MediAd View screen, store the cloud info there too
        if req.link_screen_id:
            await db.screens.update_one({"id": req.link_screen_id}, {"$set": {
                "colorlight": {
                    "terminal_id": result["terminal_id"],
                    "group_id": result["group_id"],
                    "device_id": result["device_id"],
                    "secret_key": result["secret_key"],
                    "url": result["url"],
                    "provisioned_at": datetime.utcnow().isoformat(),
                }
            }})
        return result

    # ============ PUSH FLOW (3-step: upload → create → publish) ============
    class PushReq(BaseModel):
        title: str                    # program name
        media_base64: str             # data URL or raw base64
        filename: str = "media.jpg"
        content_type: str = "image/jpeg"
        # Target
        group_id: int
        terminal_ids: List[int]
        mode: str = "single"          # 'single' or 'group'
        # Display
        width: int = 192
        height: int = 320
        duration_ms: int = 8000

    @router.post("/push")
    async def push(req: PushReq, _admin=Depends(require_admin)):
        """⚠️ PRODUCTION ACTION — uploads media to ColorlightCloud, creates a program,
        and publishes to the selected terminal(s)."""
        import base64
        sess = await get_session()
        # Decode media
        b64 = req.media_base64
        if "," in b64 and ";base64," in b64:
            b64 = b64.split(",", 1)[1]
        try:
            file_bytes = base64.b64decode(b64)
        except Exception as e:
            raise HTTPException(400, f"Invalid media_base64: {e}")
        # 1) Upload
        try:
            up = sess.upload_media(file_bytes, req.filename, req.content_type)
        except Exception as e:
            raise HTTPException(502, f"Upload failed: {e}")
        # 2) Create program
        try:
            prog = sess.create_program(
                req.title, [up], width=req.width, height=req.height,
                per_item_duration_ms=req.duration_ms,
            )
        except Exception as e:
            raise HTTPException(502, f"Create program failed (media uploaded as {up.get('fileID')}): {e}")
        # 3) Publish
        try:
            pub = sess.publish_program(
                prog["program_id"], req.group_id, req.terminal_ids, mode=req.mode
            )
        except Exception as e:
            raise HTTPException(502, f"Publish failed (program created as {prog['program_id']}): {e}")
        logger.info(f"✓ Colorlight push: file={up.get('fileID')} program={prog['program_id']} → group={req.group_id} terminals={req.terminal_ids}")
        return {
            "ok": True,
            "file_id": up.get("fileID"),
            "program_id": prog["program_id"],
            "publish": pub,
        }

    return router
