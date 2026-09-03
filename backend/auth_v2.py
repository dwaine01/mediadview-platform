# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
MediAd View — Security & Auth v2 (production-grade)

Implements the FASE 2 security requirements:
- Access token (JWT) with 30 min expiration (env-configurable)
- Refresh token (JWT) with 7-30 day expiration + rotation + jti + revocation
- Revocation on logout, password change, user deactivation, role change
- Brute-force protection: 5 attempts / 15 min lockout by email AND by IP
- Rate limiting (slowapi + optional Redis)
- Audit log for every security-relevant event
- CORS restrictive (list from env)
- Generic auth-error responses (no user-existence leakage)

BACKWARDS-COMPATIBLE: existing bcrypt passwords and JWT `create_token(user_id, role)`
continue to work. The v1 endpoints keep responding for a grace period; new clients
should switch to /api/auth/v2/*.
"""
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
import jwt as jose_jwt  # PyJWT (imported as `jwt` in server.py; alias to avoid clash)
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

log = logging.getLogger("auth")
log.setLevel(logging.INFO)

# ─── Config ────────────────────────────────────────────────────────────
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET or JWT_SECRET == "mediaview-secure-jwt-secret-2026":
    if os.environ.get("ENVIRONMENT", "development") == "production":
        raise RuntimeError(
            "FATAL: JWT_SECRET must be set to a strong random value in production."
        )
    log.warning("Using development JWT_SECRET fallback — DO NOT deploy this to production.")
    JWT_SECRET = "dev-only-secret-do-not-use-in-production-" + uuid.uuid4().hex

JWT_ALG            = "HS256"
ACCESS_MIN         = int(os.environ.get("JWT_ACCESS_TOKEN_MINUTES", "30"))
REFRESH_DAYS       = max(7, min(30, int(os.environ.get("JWT_REFRESH_TOKEN_DAYS", "30"))))
JWT_ISSUER         = os.environ.get("JWT_ISSUER", "mediadview-api")
JWT_AUDIENCE       = os.environ.get("JWT_AUDIENCE", "mediadview-frontend")
ENVIRONMENT        = os.environ.get("ENVIRONMENT", "development")
IS_PROD            = ENVIRONMENT == "production"
COOKIE_SAMESITE    = os.environ.get("COOKIE_SAMESITE", "lax" if IS_PROD else "lax")
COOKIE_SECURE      = os.environ.get("COOKIE_SECURE", "true" if IS_PROD else "false").lower() == "true"
COOKIE_DOMAIN      = os.environ.get("COOKIE_DOMAIN") or None

# Brute-force config
LOCKOUT_WINDOW_MIN = int(os.environ.get("LOCKOUT_WINDOW_MIN", "15"))
LOCKOUT_MAX_FAIL   = int(os.environ.get("LOCKOUT_MAX_FAIL", "5"))

# Cookie name (use __Host- prefix in prod to enforce Secure+Path=/+no Domain)
REFRESH_COOKIE_NAME = "__Host-mediadview_refresh" if IS_PROD and not COOKIE_DOMAIN else "mediadview_refresh"

# ─── Helpers ──────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _ip(request: Request) -> str:
    """Best-effort client IP behind Cloudflare / Render / proxies."""
    xff = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return (request.client.host if request.client else "unknown")

def _ua(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:255]

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False

# ─── Token creation & verification ────────────────────────────────────

def _encode(payload: dict) -> str:
    return jose_jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def _decode(token: str, *, typ_expected: str) -> dict:
    try:
        payload = jose_jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALG],
            issuer=JWT_ISSUER, audience=JWT_AUDIENCE,
        )
    except jose_jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jose_jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    if payload.get("typ") != typ_expected:
        raise HTTPException(401, "Invalid token type")
    return payload

def _base_claims(user: dict, sid: str, ver: int, ttl: timedelta, typ: str) -> dict:
    now = _now()
    return {
        "iss": JWT_ISSUER, "aud": JWT_AUDIENCE,
        "sub": user["id"], "email": user.get("email"),
        "role": user.get("role", "customer"),
        "sid": sid, "ver": ver, "typ": typ,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }

def create_access_token(user: dict, sid: str, ver: int) -> str:
    return _encode(_base_claims(user, sid, ver, timedelta(minutes=ACCESS_MIN), "access"))

def create_refresh_token(user: dict, sid: str, ver: int) -> str:
    return _encode(_base_claims(user, sid, ver, timedelta(days=REFRESH_DAYS), "refresh"))

# ─── Audit log ────────────────────────────────────────────────────────

async def audit(db, *, user_id: Optional[str], action: str, request: Request,
                metadata: Optional[dict] = None):
    try:
        await db.audit_log.insert_one({
            "user_id":  user_id,
            "action":   action,
            "ip":       _ip(request),
            "ua":       _ua(request),
            "ts":       _now(),
            "metadata": metadata or {},
        })
    except Exception as e:
        log.warning("audit insert failed: %s", e)

# ─── Brute-force check ────────────────────────────────────────────────

async def record_attempt(db, email: str, ip: str, success: bool):
    await db.login_attempts.insert_one({
        "email":   email.lower().strip() if email else None,
        "ip":      ip,
        "ts":      _now(),
        "success": success,
    })

async def is_locked_out(db, email: str, ip: str) -> bool:
    window_start = _now() - timedelta(minutes=LOCKOUT_WINDOW_MIN)
    email_fail = await db.login_attempts.count_documents({
        "email": email.lower().strip() if email else "",
        "success": False,
        "ts": {"$gte": window_start},
    })
    ip_fail = await db.login_attempts.count_documents({
        "ip": ip,
        "success": False,
        "ts": {"$gte": window_start},
    })
    return email_fail >= LOCKOUT_MAX_FAIL or ip_fail >= LOCKOUT_MAX_FAIL

# ─── DB index setup ───────────────────────────────────────────────────

async def ensure_auth_indexes(db):
    """Called once at app startup. Safe to re-run."""
    try:
        await db.refresh_tokens.create_index("jti", unique=True)
        await db.refresh_tokens.create_index("sid")
        await db.refresh_tokens.create_index("user_id")
        # TTL index: mongo deletes documents automatically after expires_at
        await db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)
        await db.login_attempts.create_index([("email", 1), ("ts", -1)])
        await db.login_attempts.create_index([("ip", 1), ("ts", -1)])
        # login_attempts also gets a 24h retention TTL
        await db.login_attempts.create_index("ts", expireAfterSeconds=86400)
        await db.audit_log.create_index([("ts", -1)])
        await db.audit_log.create_index("user_id")
        log.info("✓ Auth indexes ensured (refresh_tokens TTL, login_attempts, audit_log)")
    except Exception as e:
        log.warning("ensure_auth_indexes: %s", e)

# ─── Refresh-token persistence ────────────────────────────────────────

async def store_refresh(db, *, user_id: str, jti: str, sid: str,
                        parent_jti: Optional[str] = None):
    await db.refresh_tokens.insert_one({
        "jti":        jti,
        "sid":        sid,
        "user_id":    user_id,
        "parent_jti": parent_jti,
        "created_at": _now(),
        "expires_at": _now() + timedelta(days=REFRESH_DAYS),
        "revoked":    False,
        "reason":     None,
    })

async def revoke_family(db, sid: str, reason: str):
    """Revoke every refresh token in the same session (sid)."""
    await db.refresh_tokens.update_many(
        {"sid": sid, "revoked": False},
        {"$set": {"revoked": True, "reason": reason, "revoked_at": _now()}}
    )

async def revoke_all_for_user(db, user_id: str, reason: str):
    await db.refresh_tokens.update_many(
        {"user_id": user_id, "revoked": False},
        {"$set": {"revoked": True, "reason": reason, "revoked_at": _now()}}
    )

async def is_refresh_valid(db, jti: str, sid: str) -> bool:
    doc = await db.refresh_tokens.find_one({"jti": jti})
    if not doc: return False
    if doc.get("revoked"):
        # Reuse attempt — revoke the whole family
        await revoke_family(db, sid, reason="reuse_detected")
        log.warning("Refresh token reuse detected on sid=%s → family revoked", sid)
        return False
    exp = doc.get("expires_at")
    if exp:
        # Mongo may return naive datetimes; normalize to UTC
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < _now():
            return False
    return True

# ─── Cookie helpers ───────────────────────────────────────────────────

def set_refresh_cookie(response: Response, refresh_token: str):
    """Set the refresh token as HttpOnly, Secure, SameSite cookie."""
    kwargs = dict(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_DAYS * 24 * 3600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    # __Host- prefix cookies must NOT have a Domain attribute
    if COOKIE_DOMAIN and not REFRESH_COOKIE_NAME.startswith("__Host-"):
        kwargs["domain"] = COOKIE_DOMAIN
    response.set_cookie(**kwargs)

def clear_refresh_cookie(response: Response):
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/",
                           domain=COOKIE_DOMAIN if COOKIE_DOMAIN and not REFRESH_COOKIE_NAME.startswith("__Host-") else None)

# ─── FastAPI dependencies ─────────────────────────────────────────────

bearer = HTTPBearer(auto_error=False)


def build_deps(db):
    """Factory that returns dependencies bound to the given mongo db instance."""

    async def get_current_user(
        request: Request,
        creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    ) -> dict:
        if not creds or not creds.credentials:
            raise HTTPException(401, "Not authenticated")
        payload = _decode(creds.credentials, typ_expected="access")
        user_id = payload.get("sub")
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(401, "User not found")
        if not user.get("active", True):
            raise HTTPException(401, "Account disabled")
        # Verify session epoch (for global-logout after password change)
        expected_ver = int(user.get("session_epoch", 0))
        if int(payload.get("ver", 0)) != expected_ver:
            raise HTTPException(401, "Session invalidated")
        # Verify the sid still has an active refresh in DB (fast revocation)
        sid = payload.get("sid")
        if sid:
            active = await db.refresh_tokens.find_one(
                {"sid": sid, "revoked": False}, {"_id": 1}
            )
            if not active:
                raise HTTPException(401, "Session revoked")
        # Attach for downstream handlers
        user["_sid"] = sid
        user["_jti"] = payload.get("jti")
        return user

    async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in ("admin", "superadmin"):
            raise HTTPException(403, "Admin access required")
        return current_user

    async def require_superadmin(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") != "superadmin":
            raise HTTPException(403, "Super Admin access required")
        return current_user

    return get_current_user, require_admin, require_superadmin


# ─── Auth Router (new v2 endpoints) ───────────────────────────────────

class LoginReq(BaseModel):
    email: EmailStr
    password: str
    client_type: Optional[str] = "web"  # "web" or "native"

class RegisterReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=120)
    company_name: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = "en"

class ChangePassReq(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict
    refresh_token: Optional[str] = None   # Only present for client_type="native"


def build_auth_router(db, get_current_user_dep):
    """Return the /api/auth/v2 router bound to the given db + auth dep."""
    from rate_limit import LIMITS as _LIMITS
    from rate_limit import limiter as _rl
    router = APIRouter(prefix="/api/auth/v2", tags=["auth-v2"])

    @router.post("/login", response_model=TokenResp, response_model_exclude_none=True)
    @_rl.limit(_LIMITS.login)
    async def login(body: LoginReq, request: Request, response: Response):
        ip = _ip(request)
        email = body.email.lower().strip()

        # 1) Brute-force lockout check
        if await is_locked_out(db, email, ip):
            await audit(db, user_id=None, action="login_blocked_bruteforce",
                        request=request, metadata={"email": email})
            raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")

        # 2) Fetch user
        user = await db.users.find_one({"email": email})
        if not user or not verify_password(body.password, user.get("password_hash", "")):
            await record_attempt(db, email, ip, success=False)
            await audit(db, user_id=(user or {}).get("id"), action="login_failed",
                        request=request, metadata={"email": email})
            # Generic message — do NOT reveal whether the user exists
            raise HTTPException(401, "Invalid credentials")

        if not user.get("active", True):
            await audit(db, user_id=user["id"], action="login_failed_inactive",
                        request=request)
            raise HTTPException(401, "Invalid credentials")

        # 3) Success — create session
        sid = uuid.uuid4().hex
        ver = int(user.get("session_epoch", 0))
        access = create_access_token(user, sid, ver)
        refresh = create_refresh_token(user, sid, ver)

        # Extract jti from the refresh we just issued
        r_payload = jose_jwt.decode(refresh, JWT_SECRET, algorithms=[JWT_ALG],
                                    audience=JWT_AUDIENCE, issuer=JWT_ISSUER)
        await store_refresh(db, user_id=user["id"], jti=r_payload["jti"], sid=sid)
        await record_attempt(db, email, ip, success=True)
        await audit(db, user_id=user["id"], action="login_success", request=request,
                    metadata={"client_type": body.client_type})

        # Track last successful login (Phase D.1.d) — non-critical, best-effort
        try:
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"last_login_at": _now(), "last_login_ip": ip}}
            )
        except Exception:
            pass

        # 4) Return tokens
        if body.client_type == "web":
            set_refresh_cookie(response, refresh)
            payload_out = {}
        else:
            payload_out = {"refresh_token": refresh}

        return {
            "access_token": access,
            "token_type": "bearer",
            "expires_in": ACCESS_MIN * 60,
            "user": {
                "id": user["id"], "email": user["email"], "name": user.get("name"),
                "role": user.get("role"), "company_name": user.get("company_name"),
                "language": user.get("language", "en"),
                "client_id": user.get("client_id"),
                "must_change_password": bool(user.get("must_change_password", False)),
                # ── Fase 4: RBAC + Tenant isolation fields ────────────────────
                "rbac_role": user.get("rbac_role"),
                "organization_id": user.get("organization_id"),
            },
            **payload_out,
        }

    @router.post("/register")
    async def register(body: RegisterReq, request: Request):
        email = body.email.lower().strip()
        existing = await db.users.find_one({"email": email})
        if existing:
            # Generic response — do not reveal existence.
            await audit(db, user_id=None, action="register_duplicate",
                        request=request, metadata={"email": email})
            # We still return 200 with a generic message.
            return {"status": "ok"}
        user = {
            "id":            uuid.uuid4().hex,
            "email":         email,
            "password_hash": hash_password(body.password),
            "name":          body.name,
            "company_name":  body.company_name,
            "phone":         body.phone,
            "language":      body.language or "en",
            "role":          "customer",
            "active":        True,
            "session_epoch": 0,
            "created_at":    _now(),
        }
        await db.users.insert_one(user)
        await audit(db, user_id=user["id"], action="user_registered",
                    request=request, metadata={"email": email})
        return {"status": "ok"}

    @router.post("/refresh", response_model=TokenResp)
    async def refresh(request: Request, response: Response):
        # Read refresh token from cookie (web) OR body (native)
        token = request.cookies.get(REFRESH_COOKIE_NAME)
        if not token:
            try:
                body = await request.json()
                token = (body or {}).get("refresh_token")
            except Exception:
                token = None
        if not token:
            raise HTTPException(401, "Missing refresh token")
        payload = _decode(token, typ_expected="refresh")

        sid, jti = payload.get("sid"), payload.get("jti")
        if not await is_refresh_valid(db, jti, sid):
            clear_refresh_cookie(response)
            raise HTTPException(401, "Refresh token invalid or reused")

        user = await db.users.find_one({"id": payload.get("sub")})
        if not user or not user.get("active", True):
            await revoke_family(db, sid, reason="user_inactive")
            clear_refresh_cookie(response)
            raise HTTPException(401, "Session invalid")

        # Verify session_epoch match
        if int(payload.get("ver", 0)) != int(user.get("session_epoch", 0)):
            await revoke_family(db, sid, reason="session_epoch_mismatch")
            clear_refresh_cookie(response)
            raise HTTPException(401, "Session invalidated")

        # Rotate: revoke old jti, issue new refresh
        await db.refresh_tokens.update_one(
            {"jti": jti},
            {"$set": {"revoked": True, "reason": "rotated", "revoked_at": _now()}}
        )
        new_refresh = create_refresh_token(user, sid, int(user.get("session_epoch", 0)))
        new_payload = jose_jwt.decode(new_refresh, JWT_SECRET, algorithms=[JWT_ALG],
                                       audience=JWT_AUDIENCE, issuer=JWT_ISSUER)
        await store_refresh(db, user_id=user["id"], jti=new_payload["jti"], sid=sid,
                            parent_jti=jti)
        new_access = create_access_token(user, sid, int(user.get("session_epoch", 0)))

        set_refresh_cookie(response, new_refresh)
        await audit(db, user_id=user["id"], action="token_refreshed", request=request)
        return {
            "access_token": new_access,
            "token_type": "bearer",
            "expires_in": ACCESS_MIN * 60,
            "user": {
                "id": user["id"], "email": user["email"], "name": user.get("name"),
                "role": user.get("role"), "language": user.get("language", "en"),
            },
        }

    @router.post("/logout")
    async def logout(request: Request, response: Response,
                     current_user: dict = Depends(get_current_user_dep)):
        sid = current_user.get("_sid")
        if sid:
            await revoke_family(db, sid, reason="user_logout")
        clear_refresh_cookie(response)
        await audit(db, user_id=current_user["id"], action="logout", request=request)
        return {"status": "ok"}

    @router.post("/change-password")
    async def change_password(body: ChangePassReq, request: Request,
                              current_user: dict = Depends(get_current_user_dep)):
        if not verify_password(body.current_password, current_user["password_hash"]):
            await audit(db, user_id=current_user["id"],
                        action="change_password_failed", request=request)
            raise HTTPException(400, "Current password is incorrect")
        if body.current_password == body.new_password:
            raise HTTPException(400, "New password must differ from current")
        new_hash = hash_password(body.new_password)
        # Bump session_epoch → invalidates every token issued before this moment
        new_epoch = int(current_user.get("session_epoch", 0)) + 1
        await db.users.update_one(
            {"id": current_user["id"]},
            {"$set": {"password_hash": new_hash, "session_epoch": new_epoch, "must_change_password": False}}
        )
        await revoke_all_for_user(db, current_user["id"], reason="password_changed")
        await audit(db, user_id=current_user["id"], action="change_password",
                    request=request)
        return {"status": "ok"}

    @router.get("/me")
    async def me(current_user: dict = Depends(get_current_user_dep)):
        return {
            "id":           current_user["id"],
            "email":        current_user["email"],
            "name":         current_user.get("name"),
            "role":         current_user.get("role"),
            "company_name": current_user.get("company_name"),
            "language":     current_user.get("language", "en"),
            "client_id":    current_user.get("client_id"),
            "must_change_password": bool(current_user.get("must_change_password", False)),
            # ── Fase 4: RBAC + Tenant isolation fields ────────────────────────
            "rbac_role":     current_user.get("rbac_role"),
            "organization_id": current_user.get("organization_id"),
        }

    return router
