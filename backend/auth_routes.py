"""auth_routes.py -- the 4 legacy v1 /auth/* routes: register, login,
me, and profile update. New clients should use /api/auth/* v2 (auth_v2.py);
these stay for backward compatibility.

Fase 2B-11 of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md) --
the LAST piece of Fase 2B: once this lands, server.py has no remaining
business-logic route left to extract (only the ~20+2 static/SPA pages
stay, by design -- see docs/AGENT_COORDINATION.md).
Pure relocation: identical paths, methods, decorators and logic, registered
on a router with prefix="/api" so the final routes match api_router exactly
as before. No behavior change.

Dependency notes:
  - gen_id, hash_password, create_token and serialize_doc are threaded in:
    all four stay defined in server.py because they're shared with code
    that is NOT moving here. hash_password in particular stays put by
    design, not merely by omission: finance.py and superadmin_routes.py
    both do a function-local `from server import hash_password` at call
    time, so moving it out of server.py would break those at runtime.
    create_token is also passed directly to
    create_signup_routes(db, create_token) later in server.py's wiring.
  - verify_password moves here fully as a plain module-level function:
    grep-verified across all of backend/ that login() (which moves with
    it) is its only caller anywhere, and nothing does
    `from server import verify_password` -- unlike hash_password, safe
    to relocate.
  - db (database.py) and get_current_user (deps.py) are imported directly,
    same precedent as every prior phase.
  - Role (rbac.py) is imported directly, not threaded: grep-verified it's
    still used elsewhere in server.py (an unrelated rbac_role check), so
    only the import is duplicated here.
  - _rl / _LIMITS (rate_limit.py) are imported directly: register/login
    were their ONLY callers anywhere in server.py, same precedent as
    public_playlist_media (2B-8) and create_payment (2B-10). The now-dead
    _rl/_LIMITS import left behind in server.py is removed as bundled
    cleanup (see below).
  - _audit (managed_portal_routes.create_audit_log) is imported directly,
    the same standard direct-import already used by screens_routes.py,
    player_routes.py, media_routes.py, promo_routes.py, workspace_routes.py
    and others. register() was its only caller in server.py, so that
    now-dead import is removed too (same bundled cleanup).
  - The auth_v2 imports (audit, _ip, is_locked_out, record_attempt) are
    left untouched as function-local imports inside register()/login(),
    exactly as they were.
"""
from datetime import datetime
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from database import db
from deps import get_current_user
from managed_portal_routes import create_audit_log as _audit
from rate_limit import LIMITS as _LIMITS
from rate_limit import limiter as _rl
from rbac import Role


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    company_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = None


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_auth_routes(gen_id, hash_password, create_token, serialize_doc):
    router = APIRouter(prefix="/api", tags=["Auth"])

    @router.post("/auth/register")
    @_rl.limit(_LIMITS.register)
    async def register(request: Request, response: Response, req: RegisterRequest):
        """Legacy v1. New clients should use /api/auth/register (v2)."""
        # Never reveal existence: return generic success either way.
        existing = await db.users.find_one({"email": req.email.lower()})
        if existing:
            from auth_v2 import audit
            try: await audit(db, user_id=None, action="register_duplicate_legacy", request=request, metadata={"email": req.email.lower()})
            except Exception: pass
            raise HTTPException(status_code=400, detail="Registration failed")
        user = {
            "id": gen_id(), "name": req.name, "email": req.email.lower(),
            "password_hash": hash_password(req.password), "role": "customer",
            # ── FASE 1: new RBAC role field ────────────────────────────────────
            "rbac_role": Role.SELF_SERVICE_OWNER,
            "company_name": req.company_name, "phone": None,
            "language": "en", "active": True, "session_epoch": 0,
            "created_at": datetime.utcnow()
        }
        await db.users.insert_one(user)
        # ── Fase 4: Audit log ─────────────────────────────────────────────────────
        await _audit(
            db, action="user.created",
            user_id=user["id"], user_email=user["email"],
            resource_type="user", resource_id=user["id"],
            details={"name": user["name"], "role": user.get("rbac_role", user["role"])},
        )
        token = create_token(user["id"], user["role"])
        return {
            "access_token": token, "token_type": "bearer",
            "user": {"id": user["id"], "name": user["name"], "email": user["email"],
                     "role": user["role"], "company_name": user["company_name"],
                     "language": user["language"]}
        }

    @router.post("/auth/login")
    @_rl.limit(_LIMITS.login)
    async def login(request: Request, response: Response, req: LoginRequest):
        """Legacy v1 login with brute-force protection + audit log added."""
        from auth_v2 import _ip, audit, is_locked_out, record_attempt
        email = req.email.lower().strip()
        ip = _ip(request)

        # Brute-force lockout
        if await is_locked_out(db, email, ip):
            try: await audit(db, user_id=None, action="login_blocked_bruteforce_legacy", request=request, metadata={"email": email})
            except Exception: pass
            raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes.")

        user = await db.users.find_one({"email": email})
        ok = bool(user) and verify_password(req.password, user.get("password_hash", "")) and user.get("active", True)
        if not ok:
            await record_attempt(db, email, ip, success=False)
            try: await audit(db, user_id=(user or {}).get("id"), action="login_failed_legacy", request=request, metadata={"email": email})
            except Exception: pass
            # Generic error — do NOT reveal whether the account exists or is deactivated
            raise HTTPException(status_code=401, detail="Invalid credentials")

        await record_attempt(db, email, ip, success=True)
        try: await audit(db, user_id=user["id"], action="login_success_legacy", request=request)
        except Exception: pass
        token = create_token(user["id"], user["role"], ver=user.get("session_epoch", 0))
        return {
            "access_token": token, "token_type": "bearer",
            "must_change_password": bool(user.get("must_change_password")),
            "user": {"id": user["id"], "name": user["name"], "email": user["email"],
                     "role": user["role"], "rbac_role": user.get("rbac_role"),
                     "must_change_password": bool(user.get("must_change_password")),
                     "organization_id": user.get("organization_id"),
                     "company_name": user.get("company_name"),
                     "language": user.get("language", "en")}
        }

    @router.get("/auth/me")
    async def get_me(current_user: dict = Depends(get_current_user)):
        return {
            "id": current_user["id"], "name": current_user["name"],
            "email": current_user["email"], "role": current_user["role"],
            "rbac_role": current_user.get("rbac_role"),
            "must_change_password": bool(current_user.get("must_change_password")),
            "organization_id": current_user.get("organization_id"),
            "company_name": current_user.get("company_name"),
            "phone": current_user.get("phone"),
            "language": current_user.get("language", "en"),
            "created_at": serialize_doc(current_user.get("created_at"))
        }

    @router.put("/auth/profile")
    async def update_profile(data: ProfileUpdate, current_user: dict = Depends(get_current_user)):
        update = {k: v for k, v in data.dict().items() if v is not None}
        if update:
            await db.users.update_one({"id": current_user["id"]}, {"$set": update})
        return {"message": "Profile updated"}

    return router
