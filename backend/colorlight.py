"""
MediAd View — ColorlightCloud Integration (us33.colorlightcloud.com)
SAFE MODE: read-only by default. Publishing requires explicit user confirmation.
"""
import os
import logging
from typing import Optional, Dict, List, Any
import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("colorlight")


def _fernet():
    """Reuse the same Fernet key as finance_email for password encryption."""
    from finance_email import _get_fernet
    return _get_fernet()


def encrypt(plain: str) -> str:
    if not plain: return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    if not token: return ""
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
        """Try several common WordPress / ColorlightCloud login endpoints."""
        candidates = [
            ("/wp-json/jwt-auth/v1/token", "json"),    # JWT (most modern)
            ("/wp-json/wp/v2/users/me",    "basic"),    # HTTP basic
            ("/wp-login.php",              "form"),     # classic WP form
        ]
        last_err = ""
        for path, mode in candidates:
            try:
                url = self.server + path
                if mode == "json":
                    r = self.s.post(url, json={"username": self.username, "password": self.password}, timeout=15)
                    if r.status_code == 200:
                        data = r.json()
                        token = data.get("token") or data.get("access_token")
                        if token:
                            self.s.headers["Authorization"] = f"Bearer {token}"
                            logger.info(f"[colorlight] JWT login OK via {path}")
                            return {"ok": True, "method": "jwt", "token": "*****"}
                elif mode == "basic":
                    r = self.s.get(url, auth=(self.username, self.password), timeout=15)
                    if r.status_code == 200:
                        # Persist basic auth on session
                        self.s.auth = (self.username, self.password)
                        logger.info(f"[colorlight] Basic auth OK via {path}")
                        return {"ok": True, "method": "basic"}
                elif mode == "form":
                    r = self.s.post(url, data={"log": self.username, "pwd": self.password, "wp-submit": "Log In"},
                                    timeout=15, allow_redirects=True)
                    if "wordpress_logged_in" in self.s.cookies.get_dict().__str__() or r.status_code == 200:
                        logger.info(f"[colorlight] Form login OK via {path}")
                        return {"ok": True, "method": "form"}
                last_err = f"{path} → HTTP {r.status_code}"
            except Exception as e:
                last_err = f"{path} → {e}"
        raise RuntimeError(f"Could not authenticate against ColorlightCloud. Last error: {last_err}")

    # ============ READ-ONLY METHODS (safe to call against production) ============
    def get_terminal_groups(self) -> List[Dict[str, Any]]:
        r = self.s.get(self.server + "/wp-json/wp/v2/terminalgroup",
                       params={"schedule": "true"}, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"GET terminalgroup → HTTP {r.status_code}: {r.text[:200]}")
        return r.json() if isinstance(r.json(), list) else r.json().get("groups", [])

    def get_terminals_flat(self) -> List[Dict[str, Any]]:
        """Flatten groups + terminals into a single list for dropdowns."""
        groups = self.get_terminal_groups()
        flat = []
        for g in groups:
            gid = g.get("id")
            gname = g.get("name") or g.get("title", {}).get("rendered", "")
            terminals = g.get("terminals") or g.get("children") or []
            for t in terminals:
                flat.append({
                    "group_id": gid,
                    "group_name": gname,
                    "terminal_id": t.get("id"),
                    "terminal_name": t.get("name") or t.get("title", "Terminal"),
                    "online": t.get("online", False),
                    "model": t.get("model", ""),
                })
        return flat


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
        if not cfg: return {"configured": False}
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
        # Build a clean response for the dropdown
        clean_groups = []
        for g in raw_groups:
            terms = g.get("terminals") or g.get("children") or []
            clean_groups.append({
                "group_id": g.get("id"),
                "group_name": g.get("name") or g.get("title", {}).get("rendered", "(unnamed)"),
                "terminals": [{
                    "id": t.get("id"),
                    "name": t.get("name") or f"Terminal {t.get('id')}",
                    "online": bool(t.get("online", False)),
                    "model": t.get("model", ""),
                } for t in terms],
                "terminal_count": len(terms),
            })
        return {"groups": clean_groups, "total_groups": len(clean_groups),
                "total_terminals": sum(g["terminal_count"] for g in clean_groups)}

    @router.get("/terminals/flat")
    async def list_terminals_flat(_admin=Depends(require_admin)):
        sess = await get_session()
        return {"items": sess.get_terminals_flat()}

    return router
