# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
# =====================================================
# MediaView Digital Signage Platform - Backend API
# =====================================================

from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

# Load .env FIRST (before any module reads env vars) then run fail-fast validator.
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')
from startup_check import validate_environment

validate_environment()
import asyncio
import base64
import hashlib
import html as html_lib
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

import bcrypt
import jwt
from bson import ObjectId
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from playlist_domain import (
    PLAYLIST_MODES,
    normalize_playlist_items,
    normalize_schedule,
    scheduled_playlist_key,
    select_winning_playlist,
)
from rbac import (
    OperationType, Role, ALL_OPERATION_TYPES,
    get_effective_role, has_permission,
    assert_permission, assert_tenant,
    assert_can_manage_screen, effective_operation_type,
)

# Fase 4: Audit log helper (imported early, used in screen/device/playlist handlers)
from managed_portal_routes import create_audit_log as _audit

# ============ CONFIGURATION ============

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')
IS_PROD = ENVIRONMENT == 'production'

JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    if IS_PROD:
        raise RuntimeError("JWT_SECRET must be set in production")
    JWT_SECRET = 'mediaview-dev-only-secret-do-not-deploy'
    logging.getLogger("server").warning("Using dev JWT_SECRET fallback — NOT for production")
JWT_ALGORITHM = "HS256"
# Legacy tokens still accepted for a short grace period after deploy.
JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_LEGACY_EXPIRATION_HOURS', '48'))

MEDIA_DIR = os.environ.get('MEDIA_DIR', str(ROOT_DIR / 'media'))

Path(MEDIA_DIR).mkdir(parents=True, exist_ok=True)

# ── Canonical plan IDs (Phase 1 normalization) ──────────────────────────────
# Canonical set: free | starter | pro | enterprise
# Compatibility alias: 'standard' → 'starter' (legacy label; retained for any
# existing references in HTML/config that have not yet been updated).
# Runtime consumer: deferred to the future authorized acquisition/subscription
# implementation.  These constants are preserved here so Phase 2B can reference
# them without re-introducing normalisation logic.
VALID_PLANS: frozenset = frozenset({"free", "starter", "pro", "enterprise"})
LEGACY_PLAN_MAP: dict = {"standard": "starter"}

# ============ DATABASE ============

# Owned by database.py (Fase 2A) — single Mongo client/handle for the whole app.
from database import DB_NAME, MONGO_URL, client, db

# ============ APP SETUP ============

app = FastAPI(title="MediaView Digital Signage API", version="1.0.0")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

# Rate limiter (imported early because @_rl.limit decorators are evaluated
# at module load time). LIMITS provides central rate-limit strings.
from rate_limit import LIMITS as _LIMITS
from rate_limit import limiter as _rl  # noqa: E402

# ============ HELPERS ============

def serialize_doc(doc):
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == '_id':
                continue
            elif isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = serialize_doc(value)
            elif isinstance(value, list):
                result[key] = serialize_doc(value)
            else:
                result[key] = value
        return result
    return doc

def gen_id():
    return str(uuid.uuid4())

def gen_invoice():
    return f"INV-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

# ============ PYDANTIC MODELS ============

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






class CampaignSchedule(BaseModel):
    # start_date / end_date now optional. `null` (or missing) means
    # "no bound on that side" (always valid from the beginning /
    # never expires). Empty strings are also accepted and normalised
    # to null so old clients keep working.
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    start_time: str = "00:00"
    end_time: str = "23:59"
    slot_duration: int = 15
    frequency: int = 5



# MediaUpload moved to media_utils.py (Fase 2B-2) -- shared with server.py's
# public_playlist_media, which still needs it at module scope here.
from media_utils import MediaUpload





class PaymentCreate(BaseModel):
    campaign_id: str
    method: str = "card"
    card_last4: Optional[str] = None

# Device / Player Models







import random
import string


def gen_activation_code():
    """Generate 6-char easy-to-read activation code (no ambiguous chars)"""
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return ''.join(random.choices(chars, k=6))


# Movido a media_utils.py (Fase 2A)
from media_utils import media_orientation

def screen_orientation(screen: Optional[dict]) -> str:
    """Single source of truth for a screen's orientation.

    Admin screens keep it in `specs.orientation`; screens created through the
    workspace used to store it at the top level, so both are accepted.
    """
    screen = screen or {}
    specs = screen.get("specs") or {}
    return specs.get("orientation") or screen.get("orientation") or "landscape"


# ============================================================
# CAMPAIGN STATE MODEL (single source of truth)
# ============================================================
#   draft     - being edited by the customer
#   pending   - submitted for admin approval
#   approved  - admin approved, ready to play
#   active    - currently running (alias of approved, historical)
#   paused    - temporarily suspended by admin/customer
#   expired   - end_date has passed
#   archived  - removed from view but kept for history
# PLAYABLE_STATUSES moved to media_utils.py (Fase 2B-2) -- shared with
# several not-yet-extracted server.py routes that still need it here.
from media_utils import PLAYABLE_STATUSES
NON_PLAYABLE_STATUSES = {"draft", "pending", "paused", "expired", "archived", "rejected"}


from media_utils import _norm_date


from media_utils import normalise_schedule


def is_campaign_playable(campaign: dict, now: Optional[datetime] = None) -> tuple:
    """Single source of truth for 'is this campaign eligible to play NOW?'.

    Returns (bool, reason_str). reason_str is empty if playable, otherwise
    the human-readable reason why it's not.
    """
    now = now or datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    now_hm = now.strftime("%H:%M")

    status = campaign.get("status")
    if status not in PLAYABLE_STATUSES:
        return False, f"status={status!r}"

    sched = campaign.get("schedule") or {}
    sd = _norm_date(sched.get("start_date"))
    ed = _norm_date(sched.get("end_date"))
    # null means "no bound"
    if sd is not None and sd > today:
        return False, f"starts on {sd}"
    if ed is not None and ed < today:
        return False, f"expired on {ed}"

    st = sched.get("start_time") or "00:00"
    et = sched.get("end_time") or "23:59"
    if not (st <= now_hm <= et):
        return False, f"outside time window {st}-{et}"

    if not (campaign.get("media_ids") or []):
        return False, "no media assigned"

    return True, ""


# Playlist builders only need metadata. Media documents stored before object
# storage keep the whole file as base64 in `data`, so fetching a full document
# per playlist item moved megabytes per request (a screen with a handful of
# campaigns took 36 s in production).
MEDIA_METADATA_PROJECTION = {"data": 0, "thumbnail": 0}


# MEDIA_METADATA_PROJECTION moved to media_utils.py (Fase 2B-2) -- shared
# with several not-yet-extracted server.py routes that still need it here.
from media_utils import MEDIA_METADATA_PROJECTION

def _legacy_media_sha256(media: dict) -> Optional[str]:
    """Return a verifiable SHA-256 for legacy disk media when available."""
    existing = str(media.get("sha256") or "").lower()
    if re.fullmatch(r"[0-9a-f]{64}", existing):
        return existing
    stored = media.get("stored_filename")
    if not stored:
        return None
    path = os.path.join(MEDIA_DIR, stored)
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()




# Movido a media_utils.py (Fase 2A)
from media_utils import _media_has_inline_bytes

async def _build_owned_playlist_items(screen_id: str) -> list:
    now = datetime.utcnow()
    playlists = await db.playlists.find(
        {
            "screen_ids": screen_id,
            "status": "published",
            # Instant promos carry an expiry; once it passes they stop playing.
            "$or": [{"expires_at": None}, {"expires_at": {"$exists": False}}, {"expires_at": {"$gt": now}}],
        },
        {"_id": 0},
    ).to_list(200)
    winner = select_winning_playlist(playlists)
    if not winner:
        return []
    rendered = []
    for item in sorted(winner.get("items") or [], key=lambda value: value.get("order", 0)):
        item_type = item.get("type")
        ref_id = item.get("ref_id")
        base = {
            "campaign_id": f"playlist:{winner['id']}",
            "playlist_id": winner["id"],
            "playlist_name": winner.get("name"),
            "duration": item.get("duration", 15),
            "rotation": 0,
            "animation": item.get("transition", "fade"),
            "display_mode": item.get("display_mode", "cover"),
            "size": 0,
            "checksum": None,
        }
        if item_type == "menu":
            # H3: Only include published/active menus in player playlists.
            # Draft menus are excluded so the render endpoint stays properly gated.
            menu = await db.menus.find_one(
                {"id": ref_id, "status": {"$in": ["published", "active"]}},
                {"_id": 0, "name": 1}
            )
            if not menu:
                continue
            url = f"/api/menus/{ref_id}/render"
            rendered.append({
                **base, "media_id": f"menu:{ref_id}", "filename": menu.get("name", "Menu"),
                "content_type": "widget", "media_url": url, "download_url": url,
            })
        elif item_type == "webpage":
            rendered.append({
                **base, "media_id": item["id"], "filename": item.get("title", "Web page"),
                "content_type": "widget", "media_url": ref_id, "download_url": ref_id,
            })
        elif item_type == "media":
            media = await db.media.find_one({"id": ref_id, "status": {"$ne": "pending"}},
                                            MEDIA_METADATA_PROJECTION)
            if not media:
                continue
            if media.get("storage", "legacy") == "legacy":
                stored = media.get("stored_filename")
                on_disk = bool(stored) and os.path.isfile(os.path.join(MEDIA_DIR, stored))
                if not on_disk and not await _media_has_inline_bytes(ref_id):
                    continue
            checksum = await run_in_threadpool(_legacy_media_sha256, media)
            url = f"/api/player/media/{ref_id}"
            rendered.append({
                **base, "media_id": ref_id, "filename": media.get("filename"),
                "content_type": media.get("content_type"), "size": media.get("size", 0),
                "checksum": checksum, "media_url": url, "download_url": url,
            })
    return rendered


async def build_screen_playlist_items(screen_id: str, include_widgets: bool = False) -> list:
    """Canonical playlist builder shared by screen and device contracts.

    Null schedule bounds are intentionally supported through
    ``is_campaign_playable``. Missing/corrupt legacy files are excluded so a
    player receives either playable content or a controlled empty state.

    ── FASE 3: También incluye campañas publicitarias (ad_campaigns) ACTIVE/APPROVED
       que apuntan a esta pantalla.
    """
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")

    campaigns = await db.campaigns.find({
        "screen_id": screen_id,
        "status": {"$in": list(PLAYABLE_STATUSES)},
    }).to_list(500)
    items = await _build_owned_playlist_items(screen_id)
    for campaign in campaigns:
        playable, reason = is_campaign_playable(campaign, now)
        if not playable:
            logger.debug("Campaign %s excluded from playlist: %s", campaign.get("id"), reason)
            continue
        schedule = campaign.get("schedule") or {}
        for media_id in campaign.get("media_ids") or []:
            media = await db.media.find_one({"id": media_id, "status": {"$ne": "pending"}},
                                            MEDIA_METADATA_PROJECTION)
            if not media:
                logger.warning("Playlist skipped missing media document %s", media_id)
                continue
            if media.get("storage", "legacy") == "legacy":
                stored = media.get("stored_filename")
                on_disk = bool(stored) and os.path.isfile(os.path.join(MEDIA_DIR, stored))
                if not on_disk and not await _media_has_inline_bytes(media_id):
                    logger.error("Playlist skipped media %s: no disk file and no inline bytes", media_id)
                    continue
            checksum = await run_in_threadpool(_legacy_media_sha256, media)
            if checksum and media.get("sha256") != checksum:
                await db.media.update_one({"id": media_id}, {"$set": {"sha256": checksum}})
            media_url = f"/api/player/media/{media_id}"
            items.append({
                "campaign_id": campaign["id"],
                "media_id": media_id,
                "filename": media.get("filename"),
                "content_type": media.get("content_type"),
                "size": media.get("size", 0),
                "duration": schedule.get("slot_duration", 15),
                "rotation": media.get("rotation", 0),
                "animation": media.get("animation", "fade"),
                "display_mode": media.get("display_mode", "cover"),
                "media_url": media_url,
                "download_url": media_url,
                "checksum": checksum,
            })

    # ── FASE 3: Inject ACTIVE ad campaigns into the playlist ──────────────────
    try:
        today = now.strftime("%Y-%m-%d")
        ad_campaigns = await db.ad_campaigns.find({
            "selected_screens": screen_id,
            "status": "ACTIVE",   # Only ACTIVE — scheduler manages all transitions
        }).to_list(100)
        for ad in ad_campaigns:
            creative_url = ad.get("creative_url")
            if not creative_url:
                continue

            # Inferir content_type por extensión de URL
            url_lower = creative_url.lower().split("?")[0]
            if any(url_lower.endswith(ext) for ext in [".mp4", ".mov", ".avi", ".webm", ".mkv"]):
                content_type = "video/mp4"
            elif any(url_lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                content_type = "image/jpeg"
            else:
                content_type = "video/mp4"  # suposición conservadora

            items.append({
                "campaign_id": f"ad:{ad['id']}",
                "media_id": f"ad-creative:{ad['id']}",
                "filename": ad.get("name", "Ad Campaign"),
                "content_type": content_type,
                "size": 0,
                "duration": ad.get("slot_duration_seconds", 30),
                "rotation": 0,
                "animation": "fade",
                "display_mode": "cover",
                "media_url": creative_url,
                "download_url": creative_url,
                "checksum": None,
                "is_ad": True,
                "advertiser_name": ad.get("advertiser_name"),
            })
    except Exception as e:
        logger.warning("Fase 3 ad_campaigns playlist injection failed for %s: %s", screen_id, e)

    if include_widgets:
        widgets = await db.widgets.find({"screen_id": screen_id, "enabled": True}).to_list(50)
        for widget in widgets:
            items.append({
                "campaign_id": "widget",
                "media_id": widget["id"],
                "filename": widget.get("name", "Widget"),
                "content_type": "widget",
                "size": 0,
                "duration": widget.get("duration", 30),
                "rotation": 0,
                "animation": "fade",
                "display_mode": "stretch",
                "media_url": f"/api/widgets/{widget['id']}/render",
                "download_url": f"/api/widgets/{widget['id']}/render",
                "checksum": None,
            })
    return items


# Movido a media_utils.py (Fase 2A)
from media_utils import bump_playlist_version


# ============ AUTH HELPERS ============

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str, role: str, ver: int = 0) -> str:
    """Legacy v1 token. Includes 'ver' so SEC-002 session_epoch check works for existing users."""
    payload = {
        "sub":  user_id,
        "role": role,
        "ver":  ver,   # must equal user.session_epoch at login time
        "exp":  datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

# Movidos a deps.py (Fase 2A)
from deps import get_current_user, require_admin, require_superadmin

# ============ PRICING CALCULATOR ============

def calculate_campaign_price(screen_pricing: dict, schedule: dict) -> dict:
    try:
        start = datetime.strptime(schedule["start_date"], "%Y-%m-%d")
        end = datetime.strptime(schedule["end_date"], "%Y-%m-%d")
        num_days = max((end - start).days + 1, 1)
        start_h = int(schedule.get("start_time", "08:00").split(":")[0])
        end_h = int(schedule.get("end_time", "22:00").split(":")[0])
        hours_per_day = max(end_h - start_h, 1)
        total_hours = hours_per_day * num_days
        per_hour = screen_pricing.get("per_hour", 50.0)
        subtotal = round(total_hours * per_hour, 2)
        tax = round(subtotal * 0.075, 2)
        total = round(subtotal + tax, 2)
        return {
            "num_days": num_days, "hours_per_day": hours_per_day,
            "total_hours": total_hours, "per_hour": per_hour,
            "subtotal": subtotal, "tax": tax, "total": total,
            "currency": screen_pricing.get("currency", "USD")
        }
    except Exception as e:
        logging.error(f"Price calc error: {e}")
        return {"num_days": 0, "hours_per_day": 0, "total_hours": 0,
                "per_hour": 0, "subtotal": 0, "tax": 0, "total": 0, "currency": "USD"}

# ============ ROUTES: HEALTH ============

@api_router.get("/")
async def root():
    return {"message": "MediaView Digital Signage API", "version": "1.0.0"}

@api_router.get("/health")
async def health():
    # NOTE: This route is superseded by health.py build_health_router() which provides
    # the full liveness + readiness implementation. This simple route is kept as a fallback
    # for code paths that register api_router before health.py is loaded.
    # The full response (with ok, uptime, etc.) is served by /api/livez.
    return {"status": "healthy", "service": "MediaView API", "ok": True}

# ============ ROUTES: AUTH ============

@api_router.post("/auth/register")
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

@api_router.post("/auth/login")
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

@api_router.get("/auth/me")
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

@api_router.put("/auth/profile")
async def update_profile(data: ProfileUpdate, current_user: dict = Depends(get_current_user)):
    update = {k: v for k, v in data.dict().items() if v is not None}
    if update:
        await db.users.update_one({"id": current_user["id"]}, {"$set": update})
    return {"message": "Profile updated"}

# ============ ROUTES: SCREENS (PUBLIC) ============





# ============ PUBLIC / TRANSIENT CUSTOMER FLOW ============
# Discount scale for month-based advertising commitments (public buyers).
# Applied on top of (num_ads × months × price_per_ad_per_month).
PUBLIC_DISCOUNT_SCALE = {1: 0.00, 3: 0.10, 6: 0.20, 12: 0.30}

def _public_screen_view(screen: dict) -> dict:
    """Strip sensitive fields — safe for unauthenticated visitors.
    Includes photo (so the catalog is visual) but hides price and internals."""
    adv = screen.get("advertising") or {}
    return {
        "id": screen.get("id"),
        "name": screen.get("name"),
        "description": screen.get("description"),
        "location": screen.get("location"),
        "pairing_code": screen.get("pairing_code"),
        "photo_base64": adv.get("photo_base64"),
        "is_public": adv.get("is_public", True),
        "status": screen.get("status", "active"),
    }

def _customer_screen_view(screen: dict) -> dict:
    """Same as public but includes price_per_ad_per_month for authenticated customers."""
    view = _public_screen_view(screen)
    adv = screen.get("advertising") or {}
    view["price_per_ad_per_month"] = adv.get("price_per_ad_per_month")
    return view

def _apply_discount(months: int) -> float:
    """Return discount FRACTION (0.10 = 10% off) for a given commitment length.
    Non-listed lengths are interpolated to the nearest lower tier."""
    tiers = sorted(PUBLIC_DISCOUNT_SCALE.keys())
    disc = 0.0
    for t in tiers:
        if months >= t:
            disc = PUBLIC_DISCOUNT_SCALE[t]
    return disc

@api_router.get("/public/screens")
async def public_screens(city: Optional[str] = None):
    """Public screen catalog for the transient QR-scanning customer.
    No auth, no prices, only marketing-safe fields."""
    query: dict = {"status": "active", "advertising.is_public": {"$ne": False}}
    if city:
        query["location.city"] = {"$regex": city, "$options": "i"}
    screens = await db.screens.find(query).to_list(200)
    return [_public_screen_view(s) for s in screens]

@api_router.get("/public/screens/by-code/{code}")
async def public_screen_by_code(code: str):
    """Look up a screen by its short pairing code (printed under the QR).
    Case-insensitive so 'mv-kd6k-twtu' == 'MV-KD6K-TWTU'."""
    screen = await db.screens.find_one({"pairing_code": {"$regex": f"^{code}$", "$options": "i"}})
    if not screen:
        raise HTTPException(status_code=404, detail="Screen code not found")
    if (screen.get("advertising") or {}).get("is_public") is False:
        raise HTTPException(status_code=404, detail="Screen not available for public advertising")
    return _public_screen_view(screen)

@api_router.get("/public/screens/{screen_id}")
async def public_screen_detail(screen_id: str):
    """Single-screen public detail (used by the QR landing to resolve a scan by ID)."""
    screen = await db.screens.find_one({"id": screen_id})
    if not screen:
        raise HTTPException(status_code=404, detail="Screen not found")
    if (screen.get("advertising") or {}).get("is_public") is False:
        raise HTTPException(status_code=404, detail="Screen not available for public advertising")
    return _public_screen_view(screen)

@api_router.get("/customer/screens")
async def customer_screens(city: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Screen catalog visible AFTER signup — includes pricing."""
    query: dict = {"status": "active", "advertising.is_public": {"$ne": False}}
    if city:
        query["location.city"] = {"$regex": city, "$options": "i"}
    screens = await db.screens.find(query).to_list(200)
    return [_customer_screen_view(s) for s in screens]

@api_router.get("/customer/screens/{screen_id}")
async def customer_screen_detail(screen_id: str, current_user: dict = Depends(get_current_user)):
    screen = await db.screens.find_one({"id": screen_id})
    if not screen:
        raise HTTPException(status_code=404, detail="Screen not found")
    return _customer_screen_view(screen)

@api_router.get("/customer/discount-scale")
async def customer_discount_scale(current_user: dict = Depends(get_current_user)):
    """Publishes the discount tiers so the frontend cart can render them."""
    return {"scale": PUBLIC_DISCOUNT_SCALE, "unit_days": 30}

class QuoteItem(BaseModel):
    screen_id: str
    num_ads: int = 1     # how many ad slots on this screen
    months: int = 1      # commitment length in 30-day units

class QuoteRequest(BaseModel):
    items: List[QuoteItem]

@api_router.post("/customer/quote")
async def customer_quote(payload: QuoteRequest, current_user: dict = Depends(get_current_user)):
    """Calculate total for a cart of (screen × num_ads × months).
    Returns per-line detail + grand total after applying the month-based
    scale discount separately to each line (each line can have its own term)."""
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    lines = []
    grand_total = 0.0
    for it in payload.items:
        if it.num_ads < 1 or it.months < 1:
            raise HTTPException(status_code=400, detail="num_ads and months must be >= 1")
        screen = await db.screens.find_one({"id": it.screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail=f"Screen {it.screen_id} not found")
        adv = screen.get("advertising") or {}
        price = adv.get("price_per_ad_per_month")
        if not price or price <= 0:
            raise HTTPException(status_code=400, detail=f"Screen {screen.get('name')} has no advertising price set")
        subtotal = it.num_ads * it.months * float(price)
        discount_pct = _apply_discount(it.months)
        line_total = round(subtotal * (1 - discount_pct), 2)
        grand_total += line_total
        lines.append({
            "screen_id": it.screen_id,
            "screen_name": screen.get("name"),
            "num_ads": it.num_ads,
            "months": it.months,
            "price_per_ad_per_month": price,
            "subtotal": round(subtotal, 2),
            "discount_pct": round(discount_pct * 100),
            "line_total": line_total,
        })
    return {"lines": lines, "grand_total": round(grand_total, 2), "currency": "USD"}



# ============ CUSTOMER ORDER SUBMISSION (Phase C.6) ============
# The transient customer signs up, browses the catalog, builds a cart,
# uploads a creative, and submits an order. Until Stripe LIVE is enabled
# (currently ENVIRONMENT=staging), payment is coordinated manually by the
# admin who is notified through the new customer-orders panel.

class CartItem(BaseModel):
    screen_id: str
    num_ads: int = 1
    months: int = 1

class CustomerOrderSubmit(BaseModel):
    items: List[CartItem]
    media_data_url: Optional[str] = None   # data:image/... or data:video/...
    media_kind: Optional[str] = None       # 'image' | 'video'
    notes: Optional[str] = None

@api_router.post("/customer/orders/from-cart")
async def customer_order_from_cart(payload: CustomerOrderSubmit,
                                   current_user: dict = Depends(get_current_user)):
    """Customer submits their cart + creative. We revalidate the quote server-side
    (never trust client totals), persist the order, and return a reference."""
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Recompute the quote from scratch — same rules as /customer/quote
    lines = []
    grand_total = 0.0
    for it in payload.items:
        if it.num_ads < 1 or it.months < 1:
            raise HTTPException(status_code=400, detail="num_ads and months must be >= 1")
        screen = await db.screens.find_one({"id": it.screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail=f"Screen {it.screen_id} not found")
        adv = screen.get("advertising") or {}
        price = adv.get("price_per_ad_per_month")
        if not price or price <= 0:
            raise HTTPException(status_code=400, detail=f"Screen {screen.get('name')} has no advertising price set")
        subtotal = it.num_ads * it.months * float(price)
        discount = _apply_discount(it.months)
        line_total = round(subtotal * (1 - discount), 2)
        grand_total += line_total
        lines.append({
            "screen_id": it.screen_id,
            "screen_name": screen.get("name"),
            "screen_location": screen.get("location"),
            "num_ads": it.num_ads,
            "months": it.months,
            "price_per_ad_per_month": price,
            "subtotal": round(subtotal, 2),
            "discount_pct": round(discount * 100),
            "line_total": line_total,
        })

    # Human-readable ref like CUST-YYMMDD-HHMMSS-XXXX
    now = datetime.utcnow()
    short = uuid.uuid4().hex[:4].upper()
    order_ref = f"CUST-{now.strftime('%y%m%d-%H%M%S')}-{short}"

    doc = {
        "id": gen_id(),
        "ref": order_ref,
        "customer_id": current_user.get("id"),
        "customer_email": current_user.get("email"),
        "customer_name": current_user.get("name"),
        "customer_phone": current_user.get("phone"),
        "lines": lines,
        "grand_total": round(grand_total, 2),
        "currency": "USD",
        "status": "pending_payment",   # pending_payment -> paid -> approved -> live
        "media_data_url": payload.media_data_url,
        "media_kind": payload.media_kind,
        "notes": (payload.notes or "").strip() or None,
        "created_at": now,
        "updated_at": now,
    }
    await db.customer_orders.insert_one(doc)
    return {
        "id": doc["id"],
        "ref": order_ref,
        "grand_total": doc["grand_total"],
        "currency": doc["currency"],
        "status": doc["status"],
        "message": "Order received. Our team will contact you shortly to arrange payment and activation.",
    }

@api_router.get("/customer/orders/mine")
async def customer_my_orders(current_user: dict = Depends(get_current_user)):
    cur = db.customer_orders.find({"customer_id": current_user.get("id")}).sort("created_at", -1)
    docs = await cur.to_list(100)
    out = []
    for d in docs:
        d.pop("_id", None)
        d.pop("media_data_url", None)  # drop the heavy field from list view
        out.append(d)
    return out





# ============ ROUTES: CAMPAIGNS ============












# ============ ROUTES: MEDIA ============
# Fase 4 (Cloudflare R2):
#   - New uploads → R2 when configured, legacy base64+disk otherwise.
#   - Reads       → open_media_for_response() picks r2 URL / bytes automatically.
#   - Big files   → POST /media/presign + PUT to R2 + POST /media/finalize.









class ClientErrorReport(BaseModel):
    stage: str
    message: str
    context: Optional[dict] = None


@api_router.post("/client-errors")
async def report_client_error(data: ClientErrorReport, request: Request):
    """Collect browser-side failures so uploads can be diagnosed with facts.

    The marketplace runs on the customer's phone, where a failed upload only
    shows a generic browser message ("Load failed" on Safari). Reporting the
    real stage plus the file details is the only way to see what happened.
    """
    await db.client_errors.insert_one({
        "id": str(uuid.uuid4()),
        "stage": data.stage[:80],
        "message": (data.message or "")[:500],
        "context": data.context or {},
        "user_agent": request.headers.get("user-agent", "")[:300],
        "ip": request.client.host if request.client else None,
        "created_at": datetime.utcnow(),
    })
    return {"logged": True}



























# ============ ROUTES: PAYMENTS (MOCKED - Stripe-ready) ============

@api_router.post("/payments")
@_rl.limit(_LIMITS.payment_create)
async def create_payment(request: Request, response: Response, data: PaymentCreate, current_user: dict = Depends(get_current_user)):
    campaign = await db.campaigns.find_one({"id": data.campaign_id, "user_id": current_user["id"]})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    existing = await db.payments.find_one({"campaign_id": data.campaign_id, "status": "completed"})
    if existing:
        raise HTTPException(status_code=400, detail="Payment already exists")
    pricing = campaign.get("pricing", {})
    payment = {
        "id": gen_id(), "user_id": current_user["id"],
        "campaign_id": data.campaign_id,
        "amount": pricing.get("total", 0),
        "subtotal": pricing.get("subtotal", 0),
        "tax": pricing.get("tax", 0),
        "currency": pricing.get("currency", "USD"),
        "status": "completed",
        "method": data.method,
        "card_last4": data.card_last4 or "4242",
        "stripe_payment_id": f"mock_pi_{uuid.uuid4().hex[:16]}",
        "invoice_number": gen_invoice(),
        "created_at": datetime.utcnow()
    }
    await db.payments.insert_one(payment)
    await db.campaigns.update_one(
        {"id": data.campaign_id},
        {"$set": {"payment_id": payment["id"], "status": "pending", "updated_at": datetime.utcnow()}}
    )
    return serialize_doc(payment)

@api_router.get("/payments")
async def list_payments(current_user: dict = Depends(get_current_user)):
    payments = await db.payments.find({"user_id": current_user["id"]}).sort("created_at", -1).to_list(100)
    enriched = []
    for p in payments:
        campaign = await db.campaigns.find_one({"id": p.get("campaign_id")})
        if campaign:
            screen = await db.screens.find_one({"id": campaign.get("screen_id")})
            p["campaign_name"] = campaign.get("name", "")
            p["screen_name"] = screen.get("name", "") if screen else ""
        enriched.append(p)
    return serialize_doc(enriched)

@api_router.get("/payments/{payment_id}")
async def get_payment(payment_id: str, current_user: dict = Depends(get_current_user)):
    payment = await db.payments.find_one({"id": payment_id, "user_id": current_user["id"]})
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return serialize_doc(payment)

# ============ ROUTES: SUPER ADMIN ============







# ============ ROUTES: ADMIN ============






def gen_location_code():
    """Generate permanent location code: MV-XXXX (letters + numbers)"""
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "MV-" + ''.join(random.choices(chars, k=4))

async def get_unique_location_code():
    """Generate a unique location code that doesn't exist yet"""
    for _ in range(100):
        code = gen_location_code()
        exists = await db.screens.find_one({"location_code": code})
        if not exists:
            return code
    return "MV-" + uuid.uuid4().hex[:4].upper()

def gen_pairing_code() -> str:
    """Short, human-friendly Device ID (e.g. MV-A4F2-B83K). Easy to type on a TV remote."""
    import secrets
    alphabet = string.ascii_uppercase + string.digits
    # remove confusing chars
    alphabet = alphabet.replace('O','').replace('0','').replace('I','').replace('1','')
    part1 = ''.join(secrets.choice(alphabet) for _ in range(4))
    part2 = ''.join(secrets.choice(alphabet) for _ in range(4))
    return f"MV-{part1}-{part2}"

def gen_pairing_secret() -> str:
    """Random secret key for device pairing (24 chars URL-safe)."""
    import secrets
    return secrets.token_urlsafe(18)

def _gen_public_screen_code() -> str:
    """Genera un código para pantallas PUBLIC_ADVERTISING: MV-ADV-XXXXXX"""
    import secrets as _s
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    part = ''.join(_s.choice(chars) for _ in range(6))
    return f"MV-ADV-{part}"

async def _get_unique_public_screen_code() -> str:
    """Genera un public_screen_code único."""
    for _ in range(100):
        code = _gen_public_screen_code()
        if not await db.screens.find_one({"public_screen_code": code}):
            return code
    return f"MV-ADV-{uuid.uuid4().hex[:6].upper()}"


# ============ DEVICE PAIRING (ColorlightCloud-style flow) ============






@api_router.get("/s/{pairing_code}", response_class=HTMLResponse)
async def screen_by_pairing_code(pairing_code: str):
    """Chat #2 style: public entrypoint to view a screen via its short pairing_code."""
    screen = await db.screens.find_one({"pairing_code": pairing_code.upper()})
    if not screen:
        raise HTTPException(404, "Screen not found")
    # Redirect to the existing public screen page
    return HTMLResponse(
        f'<script>location.replace("/api/screen?id={screen["id"]}")</script>'
        f'<a href="/api/screen?id={screen["id"]}">Ver pantalla</a>',
        status_code=200,
    )




# ============ FASE 1: RBAC INFO + MIGRATION ENDPOINTS ============







# ── FASE 1: Self-Service customer can create their own screens ─────────────


# ── FASE 1: Self-Service customer can update their own org's screens ─────────



# ── FASE 1: Self-Service customer can list their own org's screens ────────────


# ============ ROUTES: PLAYER API ============










# ============ WEB PLAYER ENGINE (Production-Grade HTML5 Digital Signage) ============


# ============ A35 BRIDGE: Export endpoint for Colorlight A35 integration ============



# ============ ROUTES: DEVICE MANAGEMENT (Player App) ============










# --- Screen Power Schedule ---







# Admin: Device Management






# ============ PROOF OF PLAY ============

@api_router.post("/playlog")
async def log_play(media_id: str, device_id: str, screen_id: str, duration: int = 0):
    """Player reports each media play event."""
    log = {
        "id": gen_id(),
        "media_id": media_id,
        "device_id": device_id,
        "screen_id": screen_id,
        "duration": duration,
        "played_at": datetime.utcnow()
    }
    await db.play_logs.insert_one(log)
    return {"status": "logged"}


# ============ REMOTE COMMANDS ============


# ============ APP VERSION / AUTO-UPDATE ============

APP_VERSION = "1.1.0"

# ============ WIDGETS / INTEGRATIONS ============







# ══════════════════════════════════════════════════════════════════════════════
# SEC-001 / SEC-003 — HTML / URL / CSS / JS rendering safety helpers
# These functions MUST be used everywhere user-controlled data is interpolated
# into HTML, CSS, JS-string or URL attribute contexts.
# ══════════════════════════════════════════════════════════════════════════════

def _esc(v) -> str:
    """HTML-escape user text for text-node and HTML attribute context."""
    return html_lib.escape(str(v or ""), quote=True)

# _safe_src moved to menus_routes.py (Fase 2B-1) -- its only caller (render_menu)
# moved there too. Re-imported here so `from server import _safe_src` keeps
# working for tests/test_workspace_iter31_extra.py.
from menus_routes import _safe_src

def _safe_iframe(v: str) -> str:
    """Only https:// or http:// allowed for iframe src — never javascript:, data:."""
    s = str(v or "").strip()
    if s.lower().startswith("https://") or s.lower().startswith("http://"):
        return html_lib.escape(s, quote=True)
    return "about:blank"

def _safe_css_color(v: str, default: str = "#000000") -> str:
    """Accept only CSS hex colours (#RGB, #RRGGBB, #RRGGBBAA). Rejects anything else."""
    s = str(v or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3}(?:[0-9a-fA-F]{2})?)?", s):
        return s
    return default

def _safe_js_str(v) -> str:
    """Return a JSON-encoded string literal safe for JS string context (includes quotes).
    Use when the value goes directly into a <script> block as a quoted string."""
    return json.dumps(str(v or ""))

def _safe_yt_id(v: str) -> str:
    """Validate a YouTube video ID (alphanumeric, underscore, hyphen; 1-20 chars)."""
    s = str(v or "")
    return s if re.fullmatch(r"[a-zA-Z0-9_\-]{1,20}", s) else ""

# ── In-memory weather cache (SEC-003: API key never exposed to clients) ───────
_weather_cache: dict = {}   # widget_id -> {"data": {...}, "ts": float}
_WEATHER_CACHE_TTL_S = 600  # 10 minutes


@api_router.get("/widgets/{widget_id}/render", response_class=HTMLResponse)
async def render_widget(widget_id: str):
    """Render widget as full HTML page for player display."""
    w = await db.widgets.find_one({"id": widget_id})
    if not w: raise HTTPException(status_code=404, detail="Widget not found")
    cfg = w.get("config", {})
    wt = w.get("widget_type")

    base_style = "body{margin:0;font-family:'Inter',Arial,sans-serif;background:#000;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;overflow:hidden}"

    if wt == "weather":
        # SEC-003 FIX: city is HTML-escaped; API key NEVER emitted to client.
        # The widget fetches weather from our server-side proxy endpoint.
        city_raw = cfg.get("city", "New York")
        city_escaped = _esc(city_raw)
        proxy_url = f"/api/widgets/{html_lib.escape(widget_id, quote=True)}/weather"
        html = f"""<html><head><style>{base_style}.w{{text-align:center}}.temp{{font-size:120px;font-weight:900}}.city{{font-size:28px;color:#94a3b8}}.desc{{font-size:22px;color:#22d3ee;margin-top:8px}}</style></head><body><div class="w"><div class="city">{city_escaped}</div><div class="temp" id="temp">--°</div><div class="desc" id="desc">Loading...</div></div><script>
        fetch({_safe_js_str(proxy_url)})
        .then(function(r){{return r.json()}})
        .then(function(d){{if(d.temp!==undefined){{document.getElementById('temp').textContent=Math.round(d.temp)+'°F';document.getElementById('desc').textContent=d.desc||''}}else{{document.getElementById('desc').textContent='Unavailable'}}}})
        .catch(function(){{document.getElementById('desc').textContent={_safe_js_str(city_raw)}}});
        </script></body></html>"""

    elif wt == "clock":
        # SEC-003 FIX: fmt allowed only "12h"/"24h"; bg validated as CSS colour.
        fmt_raw = cfg.get("format", "12h")
        fmt = "12h" if fmt_raw not in ("12h", "24h") else fmt_raw
        bg = _safe_css_color(cfg.get("bg_color", "#000000"), default="#000000")
        html = f"""<html><head><style>{base_style}body{{background:{bg}}}.c{{text-align:center}}.time{{font-size:140px;font-weight:900;letter-spacing:-4px}}.date{{font-size:32px;color:#64748b;margin-top:8px}}</style></head><body><div class="c"><div class="time" id="t"></div><div class="date" id="d"></div></div><script>
        function u(){{var n=new Date(),h=n.getHours(),m=String(n.getMinutes()).padStart(2,'0'),ap='';
        if({_safe_js_str(fmt)}==='12h'){{ap=h>=12?' PM':' AM';h=h%12||12}}
        document.getElementById('t').textContent=h+':'+m+ap;
        document.getElementById('d').textContent=n.toLocaleDateString('en-US',{{weekday:'long',month:'long',day:'numeric',year:'numeric'}})}}
        u();setInterval(u,1000);
        </script></body></html>"""

    elif wt == "ticker":
        # SEC-003 FIX: text HTML-escaped; speed coerced to int; bg validated.
        text = _esc(cfg.get("text", "Welcome to MediAd View Digital Signage Platform"))
        try:
            speed = max(10, min(300, int(cfg.get("speed", 80))))
        except (ValueError, TypeError):
            speed = 80
        bg = _safe_css_color(cfg.get("bg_color", "#111827"), default="#111827")
        html = f"""<html><head><style>body{{margin:0;background:{bg};display:flex;align-items:center;height:100vh;overflow:hidden}}.t{{white-space:nowrap;font-size:48px;font-weight:700;color:#22d3ee;font-family:Arial,sans-serif;animation:scroll {speed}s linear infinite}}@keyframes scroll{{0%{{transform:translateX(100vw)}}100%{{transform:translateX(-100%)}}}}</style></head><body><div class="t">{text}</div></body></html>"""

    elif wt == "qrcode":
        # SEC-003 FIX: label HTML-escaped; url JSON-encoded for JS string context.
        url_raw = cfg.get("url", "https://mediadview.com")
        # Only allow https/http for QR code target
        url_safe_js = _safe_js_str(url_raw if url_raw.lower().startswith(("https://", "http://")) else "https://mediadview.com")
        label = _esc(cfg.get("label", "Scan Me"))
        html = f"""<html><head><script src="https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.min.js"></script><style>{base_style}.q{{text-align:center}}.label{{font-size:28px;color:#22d3ee;margin-top:20px}}</style></head><body><div class="q"><div id="qr"></div><div class="label">{label}</div></div><script>
        var q=qrcode(0,'M');q.addData({url_safe_js});q.make();
        document.getElementById('qr').innerHTML=q.createSvgTag(8,0);
        document.querySelector('svg').style.width='300px';document.querySelector('svg').style.height='300px';
        </script></body></html>"""

    elif wt == "countdown":
        # SEC-003 FIX: title HTML-escaped; target date validated + JSON-encoded for JS.
        title = _esc(cfg.get("title", "Coming Soon"))
        target_raw = cfg.get("target_date", "2026-12-31T00:00:00")
        # Validate ISO date format (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?", str(target_raw)):
            target_raw = "2099-12-31T00:00:00"
        target_js = _safe_js_str(target_raw)
        html = f"""<html><head><style>{base_style}.c{{text-align:center}}.title{{font-size:36px;color:#22d3ee;margin-bottom:30px}}.nums{{display:flex;gap:20px;justify-content:center}}.n{{background:#111827;padding:20px 30px;border-radius:16px;border:1px solid #1e293b}}.n .v{{font-size:72px;font-weight:900}}.n .l{{font-size:14px;color:#64748b}}</style></head><body><div class="c"><div class="title">{title}</div><div class="nums"><div class="n"><div class="v" id="d">0</div><div class="l">Days</div></div><div class="n"><div class="v" id="h">0</div><div class="l">Hours</div></div><div class="n"><div class="v" id="m">0</div><div class="l">Minutes</div></div><div class="n"><div class="v" id="s">0</div><div class="l">Seconds</div></div></div></div><script>
        function u(){{var t=new Date({target_js})-new Date();if(t<0)t=0;var d=Math.floor(t/86400000),h=Math.floor(t%86400000/3600000),m=Math.floor(t%3600000/60000),s=Math.floor(t%60000/1000);
        document.getElementById('d').textContent=d;document.getElementById('h').textContent=h;document.getElementById('m').textContent=m;document.getElementById('s').textContent=s}}u();setInterval(u,1000);
        </script></body></html>"""

    elif wt == "slides":
        # SEC-003 FIX: iframe src validated (https/http only).
        url = _safe_iframe(cfg.get("url", ""))
        html = f"""<html><head><style>body{{margin:0}}iframe{{width:100vw;height:100vh;border:none}}</style></head><body><iframe src="{url}" allowfullscreen></iframe></body></html>"""

    elif wt == "youtube":
        # SEC-003 FIX: video_id strictly validated (alphanumeric + _ -).
        video_id = _safe_yt_id(cfg.get("video_id", ""))
        if video_id:
            embed_url = f"https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1&loop=1&playlist={video_id}&controls=0"
            html = f"""<html><head><style>body{{margin:0;background:#000}}iframe{{width:100vw;height:100vh;border:none}}</style></head><body><iframe src="{embed_url}" allowfullscreen allow="autoplay"></iframe></body></html>"""
        else:
            html = "<html><body style='background:#000;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh'>Invalid video ID</body></html>"

    elif wt == "webpage":
        # SEC-003 FIX: iframe src validated (https/http only).
        url = _safe_iframe(cfg.get("url", "https://google.com"))
        html = f"""<html><head><style>body{{margin:0}}iframe{{width:100vw;height:100vh;border:none}}</style></head><body><iframe src="{url}"></iframe></body></html>"""

    elif wt == "menu":
        # SEC-003 FIX: title and item fields HTML-escaped.
        title = _esc(cfg.get("title", "Today's Menu"))
        items = cfg.get("items", [{"name": "Burger", "price": "$12"}, {"name": "Pizza", "price": "$15"}, {"name": "Salad", "price": "$10"}])
        items_html = "".join([
            f'<div class="item"><span>{_esc(i.get("name",""))}</span><span class="dots"></span><span class="p">{_esc(str(i.get("price","")))}</span></div>'
            for i in items
        ])
        html = f"""<html><head><style>{base_style}body{{background:#0a0f1a}}.m{{width:80%;max-width:600px}}.title{{font-size:48px;font-weight:900;color:#22d3ee;text-align:center;margin-bottom:40px}}.item{{display:flex;align-items:baseline;font-size:28px;padding:16px 0;border-bottom:1px solid #1e293b}}.dots{{flex:1;border-bottom:2px dotted #334155;margin:0 12px}}.p{{color:#22d3ee;font-weight:700}}</style></head><body><div class="m"><div class="title">{title}</div>{items_html}</div></body></html>"""

    elif wt == "calendar":
        html = f"""<html><head><style>{base_style}body{{background:#0a0f1a}}.cal{{text-align:center;width:90%}}.month{{font-size:36px;font-weight:700;color:#22d3ee;margin-bottom:20px}}.grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}}.hd{{font-size:14px;color:#64748b;padding:8px}}.day{{font-size:20px;padding:12px;border-radius:8px}}.day.today{{background:#6366f1;color:#fff;font-weight:700}}</style></head><body><div class="cal"><div class="month" id="mon"></div><div class="grid" id="gr"></div></div><script>
        var n=new Date(),y=n.getFullYear(),m=n.getMonth();
        document.getElementById('mon').textContent=n.toLocaleDateString('en-US',{{month:'long',year:'numeric'}});
        var days=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
        var h=days.map(d=>'<div class="hd">'+d+'</div>').join('');
        var first=new Date(y,m,1).getDay(),last=new Date(y,m+1,0).getDate();
        var cells='';for(var i=0;i<first;i++)cells+='<div class="day"></div>';
        for(var d=1;d<=last;d++)cells+='<div class="day'+(d===n.getDate()?' today':'')+'">'+d+'</div>';
        document.getElementById('gr').innerHTML=h+cells;
        </script></body></html>"""

    else:
        # SEC-003 FIX: widget type HTML-escaped in fallback message.
        wt_safe = _esc(wt or "unknown")
        html = f"<html><body style='background:#000;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh'>Unknown widget type: {wt_safe}</body></html>"

    return HTMLResponse(content=html)


@api_router.get("/widgets/{widget_id}/weather")
async def widget_weather_proxy(widget_id: str):
    """SEC-003 — Server-side weather proxy.
    The OpenWeatherMap API key is read from the DB config and NEVER sent to clients.
    Results are cached in-memory for 10 minutes to reduce upstream calls.
    """
    import time
    import httpx as _httpx
    w = await db.widgets.find_one({"id": widget_id, "widget_type": "weather"})
    if not w:
        raise HTTPException(status_code=404, detail="Weather widget not found")

    cfg = w.get("config", {})
    api_key = cfg.get("api_key", "")
    city = str(cfg.get("city", "New York"))

    if not api_key:
        return {"temp": None, "desc": "No API key configured", "city": city}

    # Check cache
    cached = _weather_cache.get(widget_id)
    now_ts = time.time()
    if cached and (now_ts - cached["ts"]) < _WEATHER_CACHE_TTL_S:
        return cached["data"]

    try:
        async with _httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": api_key, "units": "imperial"},
            )
            resp.raise_for_status()
            ow = resp.json()
        result = {
            "city": city,
            "temp": round(ow.get("main", {}).get("temp", 0)),
            "desc": (ow.get("weather") or [{}])[0].get("description", ""),
        }
    except Exception as exc:
        logger.warning("Weather proxy failed for widget %s: %s", widget_id, exc)
        result = {"city": city, "temp": None, "desc": "Unavailable"}

    _weather_cache[widget_id] = {"data": result, "ts": now_ts}
    return result
async def get_app_version():
    """Check latest app version for auto-update."""
    return {
        "version": APP_VERSION,
        "update_available": True,
        "download_url": "/api/web/mediaview-player-android.zip",
        "release_notes": "Nightly reboot, content pre-caching, proof of play, remote commands"
    }



# ============ ROUTES: USER ANALYTICS ============

@api_router.get("/analytics/dashboard")
async def user_analytics(current_user: dict = Depends(get_current_user)):
    uid = current_user["id"]
    total = await db.campaigns.count_documents({"user_id": uid})
    active = await db.campaigns.count_documents({"user_id": uid, "status": "active"})
    pending = await db.campaigns.count_documents({"user_id": uid, "status": "pending"})
    payments = await db.payments.find({"user_id": uid, "status": "completed"}).to_list(1000)
    spent = sum(p.get("amount", 0) for p in payments)
    recent = await db.campaigns.find({"user_id": uid}).sort("created_at", -1).to_list(5)
    for c in recent:
        screen = await db.screens.find_one({"id": c.get("screen_id")})
        c["screen_name"] = screen.get("name", "") if screen else ""
    return {"total_campaigns": total, "active_campaigns": active,
            "pending_campaigns": pending, "total_spent": round(spent, 2),
            "recent_campaigns": serialize_doc(recent)}

# ============ SEED DATA ============

async def seed_data():
    """Seed initial admin/superadmin/demo accounts.
    
    SECURITY: In production, credentials MUST come from env vars. Seeding is
    skipped entirely when SKIP_SEED=true. Demo customers are ONLY seeded in
    non-production or when SEED_DEMO=true.
    """
    if os.environ.get("SKIP_SEED", "").lower() == "true":
        logger.info("seed_data skipped (SKIP_SEED=true)")
        return

    is_prod = os.environ.get("ENVIRONMENT") == "production"

    admin_email = os.environ.get("SEED_ADMIN_EMAIL", "admin@mediaviewads.com").lower()
    admin_pass  = os.environ.get("SEED_ADMIN_PASSWORD") or ("MediaViewAdmin#2026" if not is_prod else None)
    sa_email    = os.environ.get("SEED_SUPERADMIN_EMAIL", "superadmin@mediadview.com").lower()
    sa_pass     = os.environ.get("SEED_SUPERADMIN_PASSWORD") or ("SuperAdmin#2026" if not is_prod else None)

    if is_prod and (not admin_pass or not sa_pass):
        logger.warning("Production seed skipped: SEED_ADMIN_PASSWORD / SEED_SUPERADMIN_PASSWORD not set")
        return

    if admin_pass:
        admin_exists = await db.users.find_one({"email": admin_email})
        if not admin_exists:
            admin = {
                "id": gen_id(), "name": "MediaView Admin",
                "email": admin_email,
                "password_hash": hash_password(admin_pass),
                "role": "admin", "company_name": "MediaView Inc.",
                "phone": None, "language": "en", "active": True,
                "session_epoch": 0,
                "rbac_role": "MEDIAVIEW_ADMIN",
                "created_at": datetime.utcnow()
            }
            await db.users.insert_one(admin)
            logger.info("Admin user created: %s", admin_email)

    if sa_pass:
        sa_exists = await db.users.find_one({"email": sa_email})
        if not sa_exists:
            sa = {
                "id": gen_id(), "name": "Super Admin",
                "email": sa_email,
                "password_hash": hash_password(sa_pass),
                "role": "superadmin", "company_name": "MediaView Platform",
                "phone": None, "language": "en", "active": True,
                "session_epoch": 0,
                "rbac_role": "SUPER_ADMIN",
                "created_at": datetime.utcnow()
            }
            await db.users.insert_one(sa)
            logger.info("Super Admin created: %s", sa_email)
        else:
            # Migration: ensure existing superadmin has correct rbac_role
            if sa_exists.get("rbac_role") != "SUPER_ADMIN":
                await db.users.update_one(
                    {"email": sa_email},
                    {"$set": {"rbac_role": "SUPER_ADMIN"}}
                )
                logger.info("Migrated superadmin rbac_role to SUPER_ADMIN: %s", sa_email)

    # Migration: ensure existing admin has correct rbac_role
    if admin_pass:
        admin_doc = await db.users.find_one({"email": admin_email})
        if admin_doc and admin_doc.get("rbac_role") not in ("MEDIAVIEW_ADMIN", "SUPER_ADMIN"):
            await db.users.update_one(
                {"email": admin_email},
                {"$set": {"rbac_role": "MEDIAVIEW_ADMIN"}}
            )
            logger.info("Migrated admin rbac_role to MEDIAVIEW_ADMIN: %s", admin_email)

    # ── FASE 3: Seed ADVERTISER test user (DEV/DEMO ONLY — never in production) ─
    adv_email = "advertiser@test.mediaview.com"
    adv_pass = "Advertiser#2026"
    seed_demo = os.environ.get("SEED_DEMO", "").lower() == "true"
    # P0-SEC-001: NEVER create test/demo accounts in production unless explicitly opted in
    if not is_prod or seed_demo:
        if not await db.users.find_one({"email": adv_email}):
            adv = {
                "id": gen_id(), "name": "Test Advertiser",
                "email": adv_email,
                "password_hash": hash_password(adv_pass),
                "role": "advertiser", "company_name": "Test Ads Inc.",
                "phone": None, "language": "es", "active": True,
                "session_epoch": 0,
                "rbac_role": "ADVERTISER",
                "created_at": datetime.utcnow()
            }
            await db.users.insert_one(adv)
            logger.info("Advertiser test user created: %s", adv_email)

    # ── FASE 4: Seed MANAGED_VIEWER demo user + org + managed screens ──────────
    # P0-SEC-001: NEVER create demo accounts in production unless explicitly opted in
    ORG_MANAGED_DEMO = "org_managed_demo_v4"
    mv_email = "managed.viewer@demo.mediaview.com"
    mv_pass = "ManagedView#2026"
    if not is_prod or seed_demo:
        if not await db.users.find_one({"email": mv_email}):
            mv_user = {
                "id": gen_id(), "name": "Managed Client Demo",
                "email": mv_email,
                "password_hash": hash_password(mv_pass),
                "role": "viewer", "company_name": "Demo Managed Corp.",
                "phone": None, "language": "en", "active": True,
                "session_epoch": 0,
                "rbac_role": "MANAGED_VIEWER",
                "organization_id": ORG_MANAGED_DEMO,
                "created_at": datetime.utcnow()
            }
            await db.users.insert_one(mv_user)
            logger.info("Fase 4: Managed Viewer demo user created: %s", mv_email)

        # Also update the RBAC test viewer to have the demo org (idempotent)
        await db.users.update_one(
            {"email": "rbac.viewer@test.com", "organization_id": None},
            {"$set": {"organization_id": ORG_MANAGED_DEMO}},
        )

        # Seed 2 demo MEDIAVIEW_MANAGED screens for that org
        managed_screen_names = [
            "Pantalla Lobby Principal — Demo Corp",
            "Pantalla Cafetería — Demo Corp",
        ]
        for sname in managed_screen_names:
            if not await db.screens.find_one({"name": sname}):
                _code = gen_pairing_code()
                while await db.screens.find_one({"pairing_code": _code}):
                    _code = gen_pairing_code()
                _loc_code = await get_unique_location_code()
                _scr = {
                    "id": gen_id(), "name": sname,
                    "description": "Pantalla gestionada por MediaView para Demo Managed Corp.",
                    "location": {
                        "city": "Miami", "address": "100 Brickell Ave",
                        "state": "FL", "country": "US", "lat": 25.7617, "lng": -80.1918,
                    },
                    "pricing": {"per_hour": 0.0, "per_day": 0.0, "per_slot": 0.0, "currency": "USD"},
                    "specs": {"size": "55in", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                    "preview_image": None, "status": "active", "active": True,
                    "location_code": _loc_code, "pairing_code": _code, "pairing_secret": gen_pairing_secret(),
                    "paired_device_id": None, "paired_at": None,
                    "operation_type": OperationType.MEDIAVIEW_MANAGED,
                    "organization_id": ORG_MANAGED_DEMO,
                    "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
                }
                await db.screens.insert_one(_scr)
                logger.info("Fase 4: Created demo managed screen: %s", sname)
    else:
        logger.info("P0-SEC-001: Demo user seeding skipped (ENVIRONMENT=production, SEED_DEMO not set)")

    # ── FASE 3: Migration — Assign public_screen_code to existing PUBLIC_ADVERTISING screens ──
    existing_pa_screens = await db.screens.find({
        "operation_type": "PUBLIC_ADVERTISING",
        "$or": [{"public_screen_code": None}, {"public_screen_code": {"$exists": False}}],
    }).to_list(100)
    for ps in existing_pa_screens:
        code = await _get_unique_public_screen_code()
        await db.screens.update_one(
            {"id": ps["id"]},
            {"$set": {
                "public_screen_code": code,
                "max_ad_slots": ps.get("max_ad_slots") or 4,
                "advertising_pricing": ps.get("advertising_pricing") or {
                    "price_per_week": 150.0,
                    "price_per_month": 500.0,
                    "price_per_year": 5000.0,
                },
            }}
        )
        logger.info("FASE3 migration: assigned public_screen_code %s to screen %s", code, ps.get("name"))

    # ── FASE 3: Ensure Miami Airport has fixed known code (runs always, idempotent) ─
    _miami_existing = await db.screens.find_one({"name": "Miami Airport Terminal A — Digital Ad"})
    if _miami_existing and _miami_existing.get("public_screen_code") != "MV-ADV-MIAMI1":
        # Only update if the fixed code is not already taken by another screen
        if not await db.screens.find_one(
            {"public_screen_code": "MV-ADV-MIAMI1", "id": {"$ne": _miami_existing["id"]}}
        ):
            await db.screens.update_one(
                {"id": _miami_existing["id"]},
                {"$set": {"public_screen_code": "MV-ADV-MIAMI1"}}
            )
            logger.info("FASE3: Migrated Miami Airport screen code to MV-ADV-MIAMI1")

    # ── FASE 3: Add demo PUBLIC_ADVERTISING screens if none exist ─────────────
    demo_pub_count = await db.screens.count_documents({
        "operation_type": "PUBLIC_ADVERTISING",
        "name": {"$in": ["Miami Airport Terminal A — Digital Ad", "New York Penn Station — Public Screen"]}
    })
    if demo_pub_count < 2:
        demo_pub_screens = []
        _miami_existing2 = await db.screens.find_one({"name": "Miami Airport Terminal A — Digital Ad"})
        if _miami_existing2:
            pass  # already migrated above; skip creation
        else:
            # Use a well-known fixed code so test_fase3_advertising.py can rely on it
            miami_code = "MV-ADV-MIAMI1"
            if await db.screens.find_one({"public_screen_code": miami_code}):
                miami_code = await _get_unique_public_screen_code()  # fallback if already taken
            demo_pub_screens.append({
                "id": gen_id(), "name": "Miami Airport Terminal A — Digital Ad",
                "description": "Alta visibilidad en Terminal A del Aeropuerto Internacional de Miami. Más de 50,000 pasajeros diarios.",
                "location": {"city": "Miami", "address": "2100 NW 42nd Ave, MIA", "state": "FL", "country": "US", "lat": 25.7959, "lng": -80.2870},
                "pricing": {"per_hour": 200.0, "per_day": 1600.0, "per_slot": 20.0, "currency": "USD"},
                "specs": {"size": "20ft x 10ft", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "operation_type": "PUBLIC_ADVERTISING",
                "public_screen_code": miami_code,
                "max_ad_slots": 4,
                "advertising_pricing": {"price_per_week": 200.0, "price_per_month": 700.0, "price_per_year": 7000.0},
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            })
        if not await db.screens.find_one({"name": "New York Penn Station — Public Screen"}):
            penn_code = await _get_unique_public_screen_code()
            demo_pub_screens.append({
                "id": gen_id(), "name": "New York Penn Station — Public Screen",
                "description": "Pantalla en Penn Station, Nueva York. Tráfico diario de más de 600,000 personas.",
                "location": {"city": "New York", "address": "341 W 31st St, Penn Station", "state": "NY", "country": "US", "lat": 40.7506, "lng": -73.9971},
                "pricing": {"per_hour": 600.0, "per_day": 5000.0, "per_slot": 60.0, "currency": "USD"},
                "specs": {"size": "30ft x 15ft", "type": "LED", "resolution": "3840x2160", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "operation_type": "PUBLIC_ADVERTISING",
                "public_screen_code": penn_code,
                "max_ad_slots": 6,
                "advertising_pricing": {"price_per_week": 500.0, "price_per_month": 1800.0, "price_per_year": 18000.0},
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            })
        if demo_pub_screens:
            await db.screens.insert_many(demo_pub_screens)
            logger.info("FASE3: Created %d demo PUBLIC_ADVERTISING screens", len(demo_pub_screens))

    # Only seed regular (untyped) screens if none exist yet.
    # We check specifically for screens WITHOUT an operation_type field, because
    # FASE 3 (PUBLIC_ADVERTISING) and FASE 4 (MEDIAVIEW_MANAGED) run first and
    # insert screens that have operation_type set — those must NOT block this block.
    _regular_screen_count = await db.screens.count_documents(
        {"operation_type": {"$exists": False}}
    )
    if _regular_screen_count == 0:
        screens = [
            {
                "id": gen_id(), "name": "Times Square Center Display",
                "description": "Premium LED display in the heart of Times Square. Maximum visibility with over 300,000 daily pedestrians.",
                "location": {"city": "New York", "address": "1560 Broadway, Times Square", "state": "NY", "country": "US", "lat": 40.7580, "lng": -73.9855},
                "pricing": {"per_hour": 500.0, "per_day": 4000.0, "per_slot": 50.0, "currency": "USD"},
                "specs": {"size": "40ft x 20ft", "type": "LED", "resolution": "3840x2160", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            {
                "id": gen_id(), "name": "Broadway Avenue Digital",
                "description": "Eye-catching digital billboard on Broadway. Perfect for entertainment and retail advertising.",
                "location": {"city": "New York", "address": "1475 Broadway", "state": "NY", "country": "US", "lat": 40.7565, "lng": -73.9860},
                "pricing": {"per_hour": 350.0, "per_day": 2800.0, "per_slot": 35.0, "currency": "USD"},
                "specs": {"size": "30ft x 15ft", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            {
                "id": gen_id(), "name": "Sunset Boulevard LED",
                "description": "Iconic display on the famous Sunset Strip in Los Angeles. Reach millions of drivers and pedestrians.",
                "location": {"city": "Los Angeles", "address": "8555 Sunset Blvd", "state": "CA", "country": "US", "lat": 34.0900, "lng": -118.3696},
                "pricing": {"per_hour": 400.0, "per_day": 3200.0, "per_slot": 40.0, "currency": "USD"},
                "specs": {"size": "35ft x 18ft", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            {
                "id": gen_id(), "name": "Miami Beach Boardwalk",
                "description": "Beachfront LED display reaching tourists and locals along Miami Beach. High foot traffic area.",
                "location": {"city": "Miami", "address": "1001 Ocean Drive", "state": "FL", "country": "US", "lat": 25.7826, "lng": -80.1340},
                "pricing": {"per_hour": 300.0, "per_day": 2400.0, "per_slot": 30.0, "currency": "USD"},
                "specs": {"size": "25ft x 12ft", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            {
                "id": gen_id(), "name": "Chicago Magnificent Mile",
                "description": "Premium digital display on Chicago's premier shopping and tourist destination.",
                "location": {"city": "Chicago", "address": "625 N Michigan Ave", "state": "IL", "country": "US", "lat": 41.8932, "lng": -87.6245},
                "pricing": {"per_hour": 280.0, "per_day": 2200.0, "per_slot": 28.0, "currency": "USD"},
                "specs": {"size": "28ft x 14ft", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            {
                "id": gen_id(), "name": "Las Vegas Strip Mega Display",
                "description": "Giant LED screen on the Las Vegas Strip. Maximum impact with 24/7 visibility to millions of visitors.",
                "location": {"city": "Las Vegas", "address": "3570 Las Vegas Blvd S", "state": "NV", "country": "US", "lat": 36.1162, "lng": -115.1745},
                "pricing": {"per_hour": 450.0, "per_day": 3600.0, "per_slot": 45.0, "currency": "USD"},
                "specs": {"size": "50ft x 25ft", "type": "LED", "resolution": "3840x2160", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            {
                "id": gen_id(), "name": "San Francisco Union Square",
                "description": "Digital billboard in downtown San Francisco's busiest shopping district. Tech-savvy audience.",
                "location": {"city": "San Francisco", "address": "333 Post St", "state": "CA", "country": "US", "lat": 37.7879, "lng": -122.4074},
                "pricing": {"per_hour": 320.0, "per_day": 2560.0, "per_slot": 32.0, "currency": "USD"},
                "specs": {"size": "22ft x 11ft", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            {
                "id": gen_id(), "name": "Houston Galleria Display",
                "description": "High-traffic LED display near Houston's premier shopping center. Ideal for retail advertising.",
                "location": {"city": "Houston", "address": "5085 Westheimer Rd", "state": "TX", "country": "US", "lat": 29.7406, "lng": -95.4621},
                "pricing": {"per_hour": 250.0, "per_day": 2000.0, "per_slot": 25.0, "currency": "USD"},
                "specs": {"size": "20ft x 10ft", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            {
                "id": gen_id(), "name": "Dallas Downtown Tower",
                "description": "Modern LED display in downtown Dallas business district. Excellent for B2B and corporate advertising.",
                "location": {"city": "Dallas", "address": "1530 Main St", "state": "TX", "country": "US", "lat": 32.7815, "lng": -96.7975},
                "pricing": {"per_hour": 220.0, "per_day": 1760.0, "per_slot": 22.0, "currency": "USD"},
                "specs": {"size": "18ft x 10ft", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            {
                "id": gen_id(), "name": "Seattle Pike Place",
                "description": "Digital display near Seattle's famous Pike Place Market. Popular tourist and local destination.",
                "location": {"city": "Seattle", "address": "85 Pike St", "state": "WA", "country": "US", "lat": 47.6097, "lng": -122.3422},
                "pricing": {"per_hour": 260.0, "per_day": 2080.0, "per_slot": 26.0, "currency": "USD"},
                "specs": {"size": "24ft x 12ft", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            # ── FASE 3: Demo PUBLIC_ADVERTISING screen ────────────────────────────
            {
                "id": gen_id(), "name": "Miami Airport Terminal A — Digital Ad",
                "description": "Alta visibilidad en el Terminal A del Aeropuerto Internacional de Miami. Más de 50,000 pasajeros diarios. Ideal para marcas premium y publicidad de destino.",
                "location": {"city": "Miami", "address": "2100 NW 42nd Ave, Miami International Airport", "state": "FL", "country": "US", "lat": 25.7959, "lng": -80.2870},
                "pricing": {"per_hour": 200.0, "per_day": 1600.0, "per_slot": 20.0, "currency": "USD"},
                "specs": {"size": "20ft x 10ft", "type": "LED", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                # FASE 3 fields
                "operation_type": "PUBLIC_ADVERTISING",
                "public_screen_code": "MV-ADV-MIAMI1",
                "max_ad_slots": 4,
                "advertising_pricing": {
                    "price_per_week": 200.0,
                    "price_per_month": 700.0,
                    "price_per_year": 7000.0,
                },
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
            {
                "id": gen_id(), "name": "New York Penn Station — Public Screen",
                "description": "Pantalla en el corazón de Penn Station, Nueva York. Tráfico diario de más de 600,000 personas. El billboard digital más transitado del noreste de EE.UU.",
                "location": {"city": "New York", "address": "341 W 31st St, New York Penn Station", "state": "NY", "country": "US", "lat": 40.7506, "lng": -73.9971},
                "pricing": {"per_hour": 600.0, "per_day": 5000.0, "per_slot": 60.0, "currency": "USD"},
                "specs": {"size": "30ft x 15ft", "type": "LED", "resolution": "3840x2160", "orientation": "landscape"},
                "preview_image": None, "status": "active", "active": True,
                # FASE 3 fields
                "operation_type": "PUBLIC_ADVERTISING",
                "public_screen_code": "MV-ADV-PENN01",
                "max_ad_slots": 6,
                "advertising_pricing": {
                    "price_per_week": 500.0,
                    "price_per_month": 1800.0,
                    "price_per_year": 18000.0,
                },
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
            },
        ]
        await db.screens.insert_many(screens)
        logger.info(f"Created {len(screens)} sample screens (incl. 2 PUBLIC_ADVERTISING demo screens)")

    # Demo users — P0-SEC-001: NEVER create demo accounts in production
    if (not is_prod or seed_demo) and await db.users.count_documents({"role": "customer"}) == 0:
        demo_users = [
            {"id": gen_id(), "name": "Sarah Mitchell", "email": "sarah@brightagency.com", "password_hash": hash_password("Demo123!"), "role": "customer", "company_name": "Bright Agency", "phone": "+1 (212) 555-0142", "language": "en", "active": True, "created_at": datetime.utcnow() - timedelta(days=45)},
            {"id": gen_id(), "name": "Carlos Mendez", "email": "carlos@urbanmedia.co", "password_hash": hash_password("Demo123!"), "role": "customer", "company_name": "Urban Media Group", "phone": "+1 (305) 555-0198", "language": "en", "active": True, "created_at": datetime.utcnow() - timedelta(days=30)},
            {"id": gen_id(), "name": "Jessica Park", "email": "jessica@novaretail.com", "password_hash": hash_password("Demo123!"), "role": "customer", "company_name": "Nova Retail Inc.", "phone": "+1 (415) 555-0167", "language": "en", "active": True, "created_at": datetime.utcnow() - timedelta(days=20)},
            {"id": gen_id(), "name": "David Chen", "email": "david@techwave.io", "password_hash": hash_password("Demo123!"), "role": "customer", "company_name": "TechWave Solutions", "phone": "+1 (512) 555-0133", "language": "en", "active": True, "created_at": datetime.utcnow() - timedelta(days=15)},
        ]
        await db.users.insert_many(demo_users)
        logger.info("Created demo users")

        # Demo campaigns — use only untyped/regular screens (not PA or MANAGED)
        # PA screens are reserved for the advertiser test suite (test_fase3_advertising)
        all_screens = await db.screens.find({}).to_list(1000)
        regular_screens = [s for s in all_screens if not s.get("operation_type")]
        _n = len(regular_screens)
        if _n >= 7:
            demo_campaigns = [
                {"id": gen_id(), "user_id": demo_users[0]["id"], "screen_id": regular_screens[0]["id"], "name": "Holiday Season Grand Sale", "status": "active", "schedule": {"start_date": "2026-03-01", "end_date": "2026-03-31", "start_time": "08:00", "end_time": "22:00", "slot_duration": 15, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(regular_screens[0].get("pricing", {}), {"start_date": "2026-03-01", "end_date": "2026-03-31", "start_time": "08:00", "end_time": "22:00"}), "payment_id": None, "admin_notes": "Approved by MediaView Admin", "created_at": datetime.utcnow() - timedelta(days=20), "updated_at": datetime.utcnow()},
                {"id": gen_id(), "user_id": demo_users[1]["id"], "screen_id": regular_screens[2]["id"], "name": "Summer Collection Launch", "status": "approved", "schedule": {"start_date": "2026-04-01", "end_date": "2026-04-15", "start_time": "10:00", "end_time": "20:00", "slot_duration": 15, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(regular_screens[2].get("pricing", {}), {"start_date": "2026-04-01", "end_date": "2026-04-15", "start_time": "10:00", "end_time": "20:00"}), "payment_id": None, "admin_notes": None, "created_at": datetime.utcnow() - timedelta(days=10), "updated_at": datetime.utcnow()},
                {"id": gen_id(), "user_id": demo_users[2]["id"], "screen_id": regular_screens[4]["id"], "name": "Tech Expo 2026 Promo", "status": "pending", "schedule": {"start_date": "2026-04-10", "end_date": "2026-04-12", "start_time": "08:00", "end_time": "22:00", "slot_duration": 30, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(regular_screens[4].get("pricing", {}), {"start_date": "2026-04-10", "end_date": "2026-04-12", "start_time": "08:00", "end_time": "22:00"}), "payment_id": None, "admin_notes": None, "created_at": datetime.utcnow() - timedelta(days=3), "updated_at": datetime.utcnow()},
                {"id": gen_id(), "user_id": demo_users[3]["id"], "screen_id": regular_screens[5]["id"], "name": "Vegas Grand Opening", "status": "active", "schedule": {"start_date": "2026-03-15", "end_date": "2026-04-15", "start_time": "06:00", "end_time": "23:00", "slot_duration": 15, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(regular_screens[5].get("pricing", {}), {"start_date": "2026-03-15", "end_date": "2026-04-15", "start_time": "06:00", "end_time": "23:00"}), "payment_id": None, "admin_notes": "Approved by MediaView Admin", "created_at": datetime.utcnow() - timedelta(days=5), "updated_at": datetime.utcnow()},
                {"id": gen_id(), "user_id": demo_users[0]["id"], "screen_id": regular_screens[6]["id"], "name": "Spring Fashion Week", "status": "completed", "schedule": {"start_date": "2026-02-15", "end_date": "2026-02-28", "start_time": "10:00", "end_time": "20:00", "slot_duration": 15, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(regular_screens[6].get("pricing", {}), {"start_date": "2026-02-15", "end_date": "2026-02-28", "start_time": "10:00", "end_time": "20:00"}), "payment_id": None, "admin_notes": None, "created_at": datetime.utcnow() - timedelta(days=40), "updated_at": datetime.utcnow()},
                {"id": gen_id(), "user_id": demo_users[1]["id"], "screen_id": regular_screens[3]["id"], "name": "Miami Music Festival", "status": "active", "schedule": {"start_date": "2026-03-10", "end_date": "2026-03-25", "start_time": "12:00", "end_time": "22:00", "slot_duration": 15, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(regular_screens[3].get("pricing", {}), {"start_date": "2026-03-10", "end_date": "2026-03-25", "start_time": "12:00", "end_time": "22:00"}), "payment_id": None, "admin_notes": "Approved", "created_at": datetime.utcnow() - timedelta(days=12), "updated_at": datetime.utcnow()},
            ]
            await db.campaigns.insert_many(demo_campaigns)
            logger.info("Created demo campaigns")

            # Demo payments for active/completed campaigns
            for c in demo_campaigns:
                if c["status"] in ["active", "approved", "completed", "pending"]:
                    payment = {
                        "id": gen_id(), "user_id": c["user_id"], "campaign_id": c["id"],
                        "amount": c["pricing"].get("total", 0), "subtotal": c["pricing"].get("subtotal", 0),
                        "tax": c["pricing"].get("tax", 0), "currency": "USD", "status": "completed",
                        "method": "card", "card_last4": random.choice(["4242", "5555", "8888", "1234"]),
                        "stripe_payment_id": f"pi_{uuid.uuid4().hex[:16]}",
                        "invoice_number": gen_invoice(), "created_at": c["created_at"]
                    }
                    await db.payments.insert_one(payment)
                    await db.campaigns.update_one({"id": c["id"]}, {"$set": {"payment_id": payment["id"]}})
            logger.info("Created demo payments")

    # Demo devices
    if await db.devices.count_documents({}) == 0:
        all_screens = await db.screens.find({}).to_list(1000)
        if len(all_screens) >= 6:  # need indices 0, 2, 5 — so min 6 items required
            demo_devices = [
                {"id": gen_id(), "activation_code": "MV7K2N", "device_name": "Lobby Main Screen", "device_info": {"model": "TCL P755", "os_version": "Google TV 14", "app_version": "1.0.0", "resolution": "3840x2160"}, "screen_id": all_screens[0]["id"], "status": "active", "tier": "tv_direct", "reboot_time": "03:00", "last_heartbeat": datetime.utcnow() - timedelta(minutes=2), "last_sync": datetime.utcnow() - timedelta(minutes=1), "activated_at": datetime.utcnow() - timedelta(days=15), "diagnostics": {"uptime_seconds": 345600, "ip_address": "192.168.1.101", "app_version": "1.0.0"}, "created_at": datetime.utcnow() - timedelta(days=15)},
                {"id": gen_id(), "activation_code": "HX4P9R", "device_name": "Store Window Display", "device_info": {"model": "Philips PUS7608", "os_version": "Google TV 13", "app_version": "1.0.0", "resolution": "1920x1080"}, "screen_id": all_screens[2]["id"], "status": "active", "tier": "tv_direct", "reboot_time": "03:00", "last_heartbeat": datetime.utcnow() - timedelta(minutes=5), "last_sync": datetime.utcnow() - timedelta(minutes=3), "activated_at": datetime.utcnow() - timedelta(days=10), "diagnostics": {"uptime_seconds": 172800, "ip_address": "192.168.1.105", "app_version": "1.0.0"}, "created_at": datetime.utcnow() - timedelta(days=10)},
                {"id": gen_id(), "activation_code": "WB3T6Q", "device_name": "Conference Room LED", "device_info": {"model": "Onn 4K Pro", "os_version": "Google TV 14", "app_version": "1.0.0", "resolution": "3840x2160"}, "screen_id": all_screens[5]["id"], "status": "active", "tier": "player_dedicated", "reboot_time": "04:00", "last_heartbeat": datetime.utcnow() - timedelta(seconds=30), "last_sync": datetime.utcnow() - timedelta(seconds=45), "activated_at": datetime.utcnow() - timedelta(days=5), "diagnostics": {"uptime_seconds": 86400, "ip_address": "10.0.0.42", "app_version": "1.0.0"}, "created_at": datetime.utcnow() - timedelta(days=5)},
                {"id": gen_id(), "activation_code": "YN8M5J", "device_name": "Waiting Area Screen", "device_info": {"model": "TCL C655", "os_version": "Google TV 14", "app_version": "1.0.0", "resolution": "3840x2160"}, "screen_id": None, "status": "pending", "tier": "tv_direct", "reboot_time": "03:00", "last_heartbeat": datetime.utcnow() - timedelta(hours=3), "last_sync": None, "activated_at": None, "diagnostics": {"ip_address": "192.168.1.120"}, "created_at": datetime.utcnow() - timedelta(hours=4)},
            ]
            await db.devices.insert_many(demo_devices)
            logger.info("Created demo devices")

# ============ CERTIFIED DEVICES PROGRAM ============

CERTIFIED_DEVICES = [
    {
        "brand": "TCL",
        "tier": "primary",
        "certification": "confirmed",
        "auto_start_method": "Safety Guard Auto Launch + Home Launcher replacement",
        "tested_by": "User confirmed OptiSigns auto-starts on TCL Google TV",
        "models": [
            {"model": "TCL P755", "sizes": ["43", "50", "55", "65", "75", "85"], "os": "Google TV", "year": 2024, "price_range": "$300-$800", "certification": "confirmed", "notes": "Best value. Safety Guard enables reliable auto-start."},
            {"model": "TCL C755", "sizes": ["55", "65", "75", "85", "98"], "os": "Google TV", "year": 2024, "price_range": "$500-$2000", "certification": "confirmed", "notes": "Premium QLED. Higher brightness for well-lit environments."},
            {"model": "TCL C655", "sizes": ["55", "65", "75", "85"], "os": "Google TV", "year": 2024, "price_range": "$400-$1000", "certification": "confirmed", "notes": "Mid-range QLED. Good balance price/quality."},
            {"model": "TCL S5400A", "sizes": ["32", "40", "43"], "os": "Google TV", "year": 2024, "price_range": "$150-$250", "certification": "confirmed", "notes": "Budget entry. Ideal for small signage."},
            {"model": "TCL QM6K", "sizes": ["55", "65", "75", "85", "98"], "os": "Google TV", "year": 2024, "price_range": "$500-$1800", "certification": "confirmed", "notes": "High brightness Mini-LED. Best for sunlit areas."},
        ],
        "setup_script": "setup-tcl-production.sh",
        "setup_steps": [
            "Enable Developer Mode: Settings > System > About > tap Build 7x",
            "Enable USB Debugging: Settings > System > Developer Options > ON",
            "Connect via ADB: adb connect <IP>:5555",
            "Install APK: adb install mediaview-player.apk",
            "Configure Safety Guard: Settings > Apps > Safety Guard > Permission Shield > Auto Launch > Auto Manager OFF, MediaView Player ON",
            "Set as Home: adb shell cmd package set-home-activity com.mediaview.player/.MainActivity",
            "Disable Google launcher: adb shell pm disable-user --user 0 com.google.android.tvlauncher",
            "Disable screen timeout: adb shell settings put system screen_off_timeout 2147483647",
            "Reboot and verify: adb reboot",
        ],
        "features_verified": {
            "auto_start_on_boot": True, "kiosk_mode": True, "offline_cache": True,
            "crash_recovery": True, "remote_update": True, "diagnostics_hud": True,
        },
        "limitations": [
            "Consumer panel rated ~16hrs/day continuous (not 24/7)",
            "Safety Guard step requires one-time manual config on TV remote",
        ],
    },
    {
        "brand": "Philips",
        "tier": "primary",
        "certification": "confirmed",
        "auto_start_method": "Native auto-start (confirmed with OptiSigns behavior) + Pro/Hotel Mode",
        "tested_by": "User confirmed OptiSigns auto-starts on Philips Google TV",
        "models": [
            {"model": "Philips PUS7608", "sizes": ["43", "50", "55", "65", "75"], "os": "Google TV", "year": 2023, "price_range": "$300-$700", "certification": "confirmed", "notes": "Auto-start confirmed via user test with OptiSigns."},
            {"model": "Philips PUS8108", "sizes": ["43", "50", "55", "65", "70", "75", "85"], "os": "Google TV", "year": 2023, "price_range": "$350-$900", "certification": "expected", "notes": "Ambilight model. Same platform as PUS7608."},
            {"model": "Philips PUS8508", "sizes": ["43", "50", "55", "65"], "os": "Google TV", "year": 2023, "price_range": "$400-$800", "certification": "expected", "notes": "Ambilight + P5 engine."},
            {"model": "Philips PUS7009", "sizes": ["43", "50", "55", "65", "75"], "os": "Google TV", "year": 2024, "price_range": "$280-$650", "certification": "expected", "notes": "2024 budget line."},
            {"model": "Philips PUS8609", "sizes": ["43", "50", "55", "65", "75"], "os": "Google TV", "year": 2024, "price_range": "$400-$900", "certification": "expected", "notes": "2024 mid-range Ambilight."},
        ],
        "setup_steps": [
            "Install from Google Play Store (or sideload via ADB)",
            "Enable Developer Mode: Settings > System > About > Build Number 7x taps",
            "Enable USB Debugging: Settings > System > Developer Options",
            "Connect ADB: adb connect <TV_IP>:5555",
            "Optional Pro Mode: Power on > Display(i+) > Mute > Vol Up > Home",
            "Set as Home: adb shell cmd package set-home-activity com.mediaview.player/.MainActivity",
            "Disable screen timeout: adb shell settings put system screen_off_timeout 2147483647",
            "Reboot and verify: adb reboot",
        ],
        "features_verified": {
            "auto_start_on_boot": True, "kiosk_mode": True, "offline_cache": True,
            "crash_recovery": True, "remote_update": True, "diagnostics_hud": True,
        },
        "limitations": [
            "Exact model verification pending (user to confirm specific model)",
            "Consumer panel rated ~16hrs/day (not 24/7)",
        ],
    },
    {
        "brand": "Onn (Walmart)",
        "tier": "primary",
        "certification": "confirmed",
        "auto_start_method": "Home Launcher replacement + Launch Manager app",
        "tested_by": "User confirmed OptiSigns auto-starts on Onn Google TV",
        "models": [
            {"model": "Onn Google TV 4K Streaming Box", "sizes": ["N/A (HDMI stick)"], "os": "Google TV", "year": 2023, "price_range": "$20", "certification": "confirmed", "notes": "Ultra-budget. $20 HDMI dongle. Plug into any TV. Great for mass deployment."},
            {"model": "Onn Google TV 4K Pro", "sizes": ["N/A (HDMI stick)"], "os": "Google TV", "year": 2024, "price_range": "$50", "certification": "confirmed", "notes": "3GB RAM, 32GB storage, Wi-Fi 6, Ethernet. Best Onn for signage."},
            {"model": "Onn Google TV 4K Plus", "sizes": ["N/A (HDMI stick)"], "os": "Google TV", "year": 2025, "price_range": "$30", "certification": "expected", "notes": "16GB storage, improved over base model."},
            {"model": "Onn Google TV 50in", "sizes": ["50"], "os": "Google TV", "year": 2024, "price_range": "$200", "certification": "confirmed", "notes": "Full TV with Google TV built-in."},
            {"model": "Onn Google TV 55in", "sizes": ["55"], "os": "Google TV", "year": 2024, "price_range": "$250", "certification": "confirmed", "notes": "Full TV with Google TV built-in."},
            {"model": "Onn Google TV 65in", "sizes": ["65"], "os": "Google TV", "year": 2024, "price_range": "$350", "certification": "confirmed", "notes": "Full TV with Google TV built-in."},
            {"model": "Onn Google TV 75in", "sizes": ["75"], "os": "Google TV", "year": 2024, "price_range": "$500", "certification": "expected", "notes": "Largest Onn TV."},
        ],
        "setup_steps": [
            "Install from Google Play Store (or sideload via ADB)",
            "Enable Developer Mode: Settings > System > About > Build Number 7x taps",
            "Enable USB Debugging in Developer Options",
            "Connect ADB: adb connect <IP>:5555",
            "Set as Home Launcher: adb shell cmd package set-home-activity com.mediaview.player/.MainActivity",
            "Disable Google TV launcher: adb shell pm disable-user --user 0 com.google.android.tvlauncher",
            "Disable screen timeout: adb shell settings put system screen_off_timeout 2147483647",
            "Reboot and verify: adb reboot",
        ],
        "features_verified": {
            "auto_start_on_boot": True, "kiosk_mode": True, "offline_cache": True,
            "crash_recovery": True, "remote_update": True, "diagnostics_hud": True,
        },
        "limitations": [
            "Base model ($20): only 8GB storage, 2GB RAM - limit media cache size",
            "Pro model ($50): much better with 32GB + Ethernet - recommended for production",
            "Onn TVs: consumer panel, rated ~16hrs/day",
            "Onn Sticks: run 24/7, plug into any TV/monitor",
        ],
    },
]

# ============ CERTIFICATION TEST SUITE ============

class CertificationResult(BaseModel):
    device_brand: str
    device_model: str
    os_version: str
    screen_resolution: str
    user_agent: str
    tests_passed: int
    tests_failed: int
    tests_total: int
    test_details: list
    stability_minutes: Optional[int] = None
    manual_checks: Optional[dict] = None

@api_router.post("/certification/submit")
async def submit_certification(data: CertificationResult):
    """TV submits certification test results to server."""
    result = {
        "id": gen_id(),
        "device_brand": data.device_brand,
        "device_model": data.device_model,
        "os_version": data.os_version,
        "screen_resolution": data.screen_resolution,
        "user_agent": data.user_agent,
        "tests_passed": data.tests_passed,
        "tests_failed": data.tests_failed,
        "tests_total": data.tests_total,
        "pass_rate": round(data.tests_passed / max(data.tests_total, 1) * 100, 1),
        "test_details": data.test_details,
        "stability_minutes": data.stability_minutes,
        "manual_checks": data.manual_checks,
        "certified": data.tests_failed == 0,
        "created_at": datetime.utcnow()
    }
    await db.certification_results.insert_one(result)
    return serialize_doc(result)

@api_router.get("/certification/results")
async def get_certification_results():
    """Get all certification test results."""
    results = await db.certification_results.find({}).sort("created_at", -1).to_list(100)
    return serialize_doc(results)


@api_router.get("/certified-devices")
async def get_certified_devices():
    """Public endpoint: list of MediaView certified TV models."""
    return {
        "program": "MediaView Certified Devices",
        "version": "1.0",
        "primary_brand": "TCL",
        "total_models": sum(len(b["models"]) for b in CERTIFIED_DEVICES),
        "devices": CERTIFIED_DEVICES,
    }

# ============ DIGITAL MENU SYSTEM ============
# Allows restaurant customers to create and manage digital menus

MENU_TEMPLATES = [
    {
        "id": "classic",
        "name": "Clasico Elegante",
        "description": "Menu clasico con fondo oscuro y texto dorado. Ideal para restaurantes finos.",
        "category": "Fine Dining",
        "preview_color": "#1a1a2e",
        "accent_color": "#d4af37"
    },
    {
        "id": "modern",
        "name": "Moderno Minimalista",
        "description": "Diseno limpio y moderno con fondo blanco. Perfecto para cafes y bistros.",
        "category": "Cafe & Bistro",
        "preview_color": "#ffffff",
        "accent_color": "#2563eb"
    },
    {
        "id": "fastfood",
        "name": "Comida Rapida",
        "description": "Colores vibrantes y texto grande. Ideal para fast food y food trucks.",
        "category": "Fast Food",
        "preview_color": "#dc2626",
        "accent_color": "#fbbf24"
    },
    {
        "id": "mexican",
        "name": "Mexicano Festivo",
        "description": "Colores calidos y festivos. Perfecto para restaurantes mexicanos y latinos.",
        "category": "Mexican & Latin",
        "preview_color": "#92400e",
        "accent_color": "#f59e0b"
    },
    {
        "id": "sushi",
        "name": "Sushi & Asian",
        "description": "Estilo zen minimalista. Ideal para restaurantes japoneses y asiaticos.",
        "category": "Asian",
        "preview_color": "#0f172a",
        "accent_color": "#f43f5e"
    },
    {
        "id": "pizza",
        "name": "Pizzeria Italiana",
        "description": "Estilo italiano clasico. Perfecto para pizzerias y restaurantes italianos.",
        "category": "Italian",
        "preview_color": "#1c1917",
        "accent_color": "#dc2626"
    },
    {
        "id": "bar",
        "name": "Bar & Lounge",
        "description": "Tema oscuro con acentos neon. Ideal para bares, lounges y clubes.",
        "category": "Bar & Nightlife",
        "preview_color": "#0a0a0a",
        "accent_color": "#a855f7"
    },
    {
        "id": "healthy",
        "name": "Saludable & Organico",
        "description": "Tonos verdes naturales. Perfecto para juguerias, ensaladas y comida saludable.",
        "category": "Healthy & Organic",
        "preview_color": "#f0fdf4",
        "accent_color": "#16a34a"
    },
    {
        "id": "mcdonalds",
        "name": "Fast Food Visual",
        "description": "Estilo McDonald's: fotos grandes en grid. Ideal para comida rapida con fotos de productos.",
        "category": "Fast Food Visual",
        "preview_color": "#1c1917",
        "accent_color": "#dc2626"
    },
    {
        "id": "modern_visual",
        "name": "Moderno Visual",
        "description": "Grid moderno con fotos grandes. Para cualquier restaurante que quiera mostrar sus platillos.",
        "category": "Modern Visual",
        "preview_color": "#0f172a",
        "accent_color": "#f59e0b"
    },
    {
        "id": "premium_dark",
        "name": "Premium Dark",
        "description": "Elegante fondo negro con fotos iluminadas. Para restaurantes de alta gama.",
        "category": "Premium",
        "preview_color": "#000000",
        "accent_color": "#d4af37"
    }
]

# ============ OWNED CONTENT PLAYLISTS ============

def _is_platform_admin(user: dict) -> bool:
    """RBAC-aware: true for SUPER_ADMIN, MEDIAVIEW_ADMIN and SUPPORT roles.
    Maps legacy role strings automatically via ROLE_MIGRATION_MAP."""
    return get_effective_role(user) in (Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN, Role.SUPPORT)


def _can_view_playlist(playlist: dict, user: dict) -> bool:
    return _is_platform_admin(user) or user.get("id") in {
        playlist.get("owner_user_id"), playlist.get("client_user_id"), playlist.get("created_by_user_id")
    }












async def _bump_playlist_screens(screen_ids: list[str], reason: str) -> None:
    for screen_id in set(screen_ids or []):
        await bump_playlist_version(screen_id, reason=reason)


# _notify_menu_change moved to menus_routes.py (Fase 2B-1) -- its only callers
# were the menu routes that moved there too.


from media_utils import _public_token_hash


async def _public_playlist(token: str) -> dict:
    playlist = await db.playlists.find_one({"public_access.token_hash": _public_token_hash(token)}, {"_id": 0})
    if not playlist or not playlist.get("public_access", {}).get("enabled"):
        raise HTTPException(404, "Public playlist link not found")
    expires_at = playlist.get("public_access", {}).get("expires_at")
    if expires_at and expires_at < datetime.utcnow():
        raise HTTPException(410, "Public playlist link expired")
    return playlist
























@api_router.get("/public/playlists/{token}")
async def get_public_playlist(token: str):
    playlist = await _public_playlist(token)
    return {"id": playlist["id"], "name": playlist["name"], "description": playlist.get("description"),
            "items": playlist.get("items", []), "pending_count": len(playlist.get("pending_items", [])),
            "access": {key: value for key, value in playlist.get("public_access", {}).items()
                       if key not in ("token_hash", "created_by_user_id")}}


@api_router.get("/public/playlists/{token}/qr")
async def public_playlist_qr(token: str, request: Request):
    await _public_playlist(token)
    import io
    import qrcode
    url = f"{str(request.base_url).rstrip('/')}/api/public/playlist?token={token}"
    image = qrcode.make(url)
    buffer = io.BytesIO(); image.save(buffer, format="PNG")
    return Response(buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@api_router.post("/public/playlists/{token}/media")
@_rl.limit(_LIMITS.media_upload)
async def public_playlist_media(token: str, request: Request, response: Response, data: MediaUpload):
    playlist = await _public_playlist(token)
    access = playlist.get("public_access", {})
    if not access.get("allow_upload"):
        raise HTTPException(403, "Uploads are disabled for this link")
    owner = await db.users.find_one({"id": playlist.get("client_user_id") or playlist.get("owner_user_id")}, {"_id": 0})
    if not owner:
        raise HTTPException(409, "Playlist owner account is unavailable")
    uploaded = await upload_media(request=request, response=response, data=data, current_user=owner)
    item = normalize_playlist_items([{
        "type": "media", "ref_id": uploaded["id"], "title": uploaded["filename"], "duration": 15,
    }])[0]
    if access.get("require_approval", True):
        item.update({"submitted_at": datetime.utcnow(), "submission_status": "pending"})
        await db.playlists.update_one({"id": playlist["id"]}, {"$push": {"pending_items": item}})
        return {"message": "Content submitted for approval", "status": "pending", "item": serialize_doc(item)}
    item["order"] = len(playlist.get("items") or [])
    await db.playlists.update_one({"id": playlist["id"]}, {
        "$push": {"items": item}, "$inc": {"version": 1}, "$set": {"updated_at": datetime.utcnow()},
    })
    await _bump_playlist_screens(playlist.get("screen_ids", []), "public playlist upload")
    return {"message": "Content published", "status": "published", "item": item}


@api_router.delete("/public/playlists/{token}/items/{item_id}")
async def public_remove_playlist_item(token: str, item_id: str):
    playlist = await _public_playlist(token)
    if playlist.get("public_access", {}).get("permission") != "editor":
        raise HTTPException(403, "This link can upload but cannot remove content")
    if not any(item.get("id") == item_id for item in playlist.get("items", [])):
        raise HTTPException(404, "Playlist item not found")
    await db.playlists.update_one({"id": playlist["id"]}, {
        "$pull": {"items": {"id": item_id}}, "$inc": {"version": 1}, "$set": {"updated_at": datetime.utcnow()},
    })
    await _bump_playlist_screens(playlist.get("screen_ids", []), "public playlist item removed")
    return {"message": "Content removed"}






@api_router.get("/menu-templates")
async def get_menu_templates():
    """Get all available menu design templates."""
    return MENU_TEMPLATES

# --- Menu CRUD (Customer-facing) ---






# --- Menu Category Management ---




# --- Menu Item Management ---




# --- Menu Render (for player/screen display) ---

# --- Promo Media Management ---








# ============ APP CONFIGURATION ============

# Serve web dashboard
WEB_DIR = str(ROOT_DIR / 'web')
SAAS_DIR = os.path.join(WEB_DIR, 'saas')  # Pre-built Expo SaaS frontend

from public_pages_routes import create_public_pages_router, customer_spa_build

@app.get("/advertise/{screen_code}", include_in_schema=False)
async def advertise_landing(screen_code: str):
    """URL corta /advertise/{code} — sirve la landing pública del QR (local dev)."""
    return FileResponse(os.path.join(WEB_DIR, 'advertise.html'), media_type='text/html')

@app.get("/api/adpage/{screen_code}", include_in_schema=False)
async def advertise_page_public(screen_code: str):
    """Landing pública QR via /api/adpage/* — accesible a través del ingress Kubernetes.
    ESTE es el URL que se usa en los QR codes de pantallas PUBLIC_ADVERTISING."""
    return FileResponse(os.path.join(WEB_DIR, 'advertise.html'), media_type='text/html')

# ── Fase 2: Self-Service Portal (organizations, locations, team, subscriptions)
from self_service_routes import create_self_service_routes
app.include_router(create_self_service_routes(db, get_current_user, require_admin, require_superadmin))

# ── Fase 3: Public Advertising Marketplace
from advertising_routes import create_advertising_routes
app.include_router(create_advertising_routes(db, get_current_user, require_admin))

# ── Phase 2C P1: Plans, Workspace, and Signup routes
from plans_routes import create_plans_routes, seed_default_plans
from workspace_routes import create_workspace_routes
from signup_routes import create_signup_routes
from workspace_team_routes import create_workspace_team_routes
from menu_ai_routes import create_menu_ai_routes
from menus_routes import create_menus_routes
from media_routes import create_media_routes
from screens_routes import create_screens_routes
from playlists_routes import create_playlists_routes
from player_routes import create_player_domain_routes
from admin_devices_routes import create_admin_devices_routes
from admin_campaigns_routes import create_admin_campaigns_routes
from superadmin_routes import create_superadmin_routes
from campaigns_routes import create_campaigns_routes
from promo_routes import create_promo_routes
from workspace_reports_routes import create_workspace_reports_routes
app.include_router(create_plans_routes(db, get_current_user, require_admin))
app.include_router(create_workspace_team_routes(db, get_current_user))
app.include_router(create_menu_ai_routes(db, get_current_user))
# -- Fase 2B-1: /menus/* (see docs/REFACTOR_FASE2_PLAN.md) --
app.include_router(create_menus_routes(gen_id, serialize_doc, _is_platform_admin,
                                        _can_view_playlist, _bump_playlist_screens, _esc))
# -- Fase 2B-2: /media/* (see docs/REFACTOR_FASE2_PLAN.md) --
# create_media_routes returns (router, upload_media): public_playlist_media
# below still calls upload_media(...) directly as a plain function.
media_router, upload_media = create_media_routes(MEDIA_DIR, gen_id, serialize_doc)
app.include_router(media_router)
# -- Fase 2B-3: /screens/* + /admin/screens* (see docs/REFACTOR_FASE2_PLAN.md) --
app.include_router(create_screens_routes(
    gen_id, serialize_doc, CampaignSchedule, calculate_campaign_price,
    _get_unique_public_screen_code, get_unique_location_code,
    gen_pairing_code, gen_pairing_secret, gen_activation_code, _is_platform_admin,
))
# -- Fase 2B-4: /playlists/* owner+share/moderation (see docs/REFACTOR_FASE2_PLAN.md) --
app.include_router(create_playlists_routes(
    gen_id, serialize_doc, _is_platform_admin, _can_view_playlist,
    _bump_playlist_screens,
))
# -- Fase 2B-5: /player/* + /devices/* (see docs/REFACTOR_FASE2_PLAN.md) --
# La factory se llama create_player_domain_routes, NO create_player_routes: ese
# nombre ya lo ocupa colorlight_player.py (modo Direct Player / A40), que se
# importa mas abajo en este mismo archivo.
app.include_router(create_player_domain_routes(
    gen_id, serialize_doc, MEDIA_DIR, gen_activation_code,
    build_screen_playlist_items, screen_orientation,
))
# -- Fase 2B-6a: /admin/devices/*, /admin/player-release, /admin/playlogs,
# /admin/client-errors, /admin/analytics (see docs/FASE2B6_MAPA_RUTAS_ADMIN.md) --
app.include_router(create_admin_devices_routes(
    gen_id, serialize_doc, gen_activation_code,
))
# -- Fase 2B-6b: /admin/campaigns/*, /admin/widgets/*, /admin/payments,
# /admin/campaign-scheduler/* (see docs/FASE2B6_MAPA_RUTAS_ADMIN.md) --
app.include_router(create_admin_campaigns_routes(
    gen_id, serialize_doc, MEDIA_DIR,
))
# -- Fase 2B-6c: /superadmin/*, /admin/users*, /admin/rbac/*,
# /admin/migrate-operation-types, /admin/customer-orders/*
# (see docs/FASE2B6_MAPA_RUTAS_ADMIN.md) -- last PR of Fase 2B-6 --
app.include_router(create_superadmin_routes(
    gen_id, serialize_doc, gen_pairing_code, gen_pairing_secret, get_unique_location_code,
))
# -- Fase 2B-7: client-facing /campaigns/* CRUD (see
# docs/REFACTOR_FASE2_PLAN.md) -- closes out campaign business logic
# left in server.py after Fase 2B-6 --
app.include_router(create_campaigns_routes(
    gen_id, serialize_doc, CampaignSchedule, calculate_campaign_price, screen_orientation,
))
app.include_router(create_promo_routes(db, get_current_user, bump_playlist_version))
app.include_router(create_workspace_reports_routes(db, get_current_user))
app.include_router(create_workspace_routes(db, get_current_user, require_admin, bump_playlist_version,
                                             build_screen_playlist_items))
app.include_router(create_signup_routes(db, create_token))

# ── Fase 3: Campaign Scheduler monitoring endpoints ───────────────────────────



@api_router.get("/public/playlist")
async def serve_public_playlist_editor():
    return FileResponse(os.path.join(WEB_DIR, 'public-playlist.html'), media_type='text/html')

@api_router.get("/download")
async def serve_download():
    return FileResponse(os.path.join(WEB_DIR, 'download.html'), media_type='text/html')

@api_router.get("/player-activate")
async def serve_player_activate():
    return FileResponse(os.path.join(WEB_DIR, 'player-activate.html'), media_type='text/html')

@api_router.get("/screen")
async def serve_screen_public():
    """QR landing — serves the unified customer SPA. The SPA reads ?id= or
    ?code= to pre-select the scanned screen inside v-marketplace / v-plans."""
    return FileResponse(os.path.join(WEB_DIR, 'customer.html'), media_type='text/html',
                        headers={'Cache-Control': 'no-store, must-revalidate'})

@api_router.get("/marketplace")
async def serve_marketplace():
    """Public /api/marketplace alias (same SPA)."""
    return FileResponse(os.path.join(WEB_DIR, 'customer.html'), media_type='text/html',
                        headers={'Cache-Control': 'no-store, must-revalidate'})


@api_router.get("/app-build")
async def app_build():
    """Current SPA build id — the page reloads itself when it goes stale."""
    return {"build": customer_spa_build(WEB_DIR)}

@api_router.get("/screen/legacy")
async def serve_screen_public_legacy():
    """Legacy hourly checkout flow — kept for reference."""
    return FileResponse(os.path.join(WEB_DIR, 'screen-public.html'), media_type='text/html')

@api_router.get("/o/{token}")
async def serve_order_view(token: str):
    """Guest magic-link landing. The token is validated by the JS side
    against /api/orders/{token}; this endpoint just serves the HTML."""
    return FileResponse(os.path.join(WEB_DIR, 'order-view.html'), media_type='text/html')

@api_router.get("/admin/orders-view")
async def serve_admin_orders_page():
    """Admin approval panel (HTML). Auth is checked by the JS after load
    via the standard /api/auth/v2/me endpoint."""
    return FileResponse(os.path.join(WEB_DIR, 'admin-orders.html'), media_type='text/html')

@api_router.get("/admin/clients-view")
async def serve_admin_clients_page():
    """Admin panel to manage the client logos shown on the marketing pages.
    Auth is checked by the JS after load via /api/auth/v2/me."""
    return FileResponse(os.path.join(WEB_DIR, 'admin-clients.html'), media_type='text/html')

@api_router.get("/admin/reports-view")
async def serve_admin_reports_page():
    """Executive reports dashboard (HTML). Auth is checked by JS via /api/auth/v2/me."""
    return FileResponse(os.path.join(WEB_DIR, 'admin-reports.html'), media_type='text/html')

@api_router.get("/landing")
async def serve_landing():
    return FileResponse(os.path.join(WEB_DIR, 'landing.html'), media_type='text/html')

@api_router.get("/about")
async def serve_about():
    return FileResponse(os.path.join(WEB_DIR, 'about.html'), media_type='text/html')

@api_router.get("/menu-editor")
async def serve_menu_editor():
    return FileResponse(os.path.join(WEB_DIR, 'menu-editor.html'), media_type='text/html')

@api_router.get("/design-studio")
async def serve_design_studio():
    return FileResponse(os.path.join(WEB_DIR, 'design-studio.html'), media_type='text/html')

@api_router.get("/dashboard")
async def serve_dashboard():
    """Dashboard principal del sistema."""
    return FileResponse(os.path.join(WEB_DIR, 'index.html'), media_type='text/html')

# Mount static assets under /api/ prefix for K8s ingress compatibility
app.mount("/api/web", StaticFiles(directory=WEB_DIR), name="web-static")

# Mount Expo SaaS frontend static assets at root-level paths
# (Expo builds use absolute /_expo/ and /assets/ paths)
if os.path.isdir(os.path.join(SAAS_DIR, '_expo')):
    app.mount("/_expo", StaticFiles(directory=os.path.join(SAAS_DIR, '_expo')), name="expo-assets")
if os.path.isdir(os.path.join(SAAS_DIR, 'assets')):
    app.mount("/assets", StaticFiles(directory=os.path.join(SAAS_DIR, 'assets')), name="expo-other-assets")

app.include_router(api_router)


# Root route: host-aware direct serve (no redirect, keeps URL clean).
#   - panel.mediadview.com/           → serves web/index.html (admin panel / login)
#   - mediadview.com/, www.*, else    → serves web/landing.html (corporate/marketing)
#     The customer marketplace SPA (customer.html) lives at /marketplace and is
#     the target of a 'Promociónate aquí' CTA inside landing.html.
app.include_router(create_public_pages_router(WEB_DIR))

# ============ FINANCE & ADMIN MODULE ============
from colorlight import create_colorlight_routes
from colorlight_player import create_player_routes
from colorlight_scheduler import start_colorlight_scheduler
from finance import create_finance_routes
from finance_email import create_finance_extensions
from finance_print import create_finance_print_routes
from finance_scheduler import start_scheduler
from realtime import manager as ws_manager
from realtime import set_screen_version_reader, ws_router


async def _screen_playlist_version(screen_id: str):
    """Reader used by the SSE screen channel (single source: realtime.py)."""
    screen = await db.screens.find_one({"id": screen_id}, {"_id": 0, "playlist_version": 1})
    if not screen:
        return None
    return int(screen.get("playlist_version") or 0)


set_screen_version_reader(_screen_playlist_version)

app.include_router(create_finance_routes(db, get_current_user))
app.include_router(create_finance_extensions(db, get_current_user))
app.include_router(create_finance_print_routes(db, get_current_user))
app.include_router(create_colorlight_routes(db, get_current_user))
# Direct player ('Integrate to Player' mode — A40 talks to MediAd View directly).
# Public device-facing routes are at /api/wp-json/... and /api/wp-content/...
# (mounted under /api because k8s ingress routes only /api/* to backend port 8001).
app.include_router(create_player_routes(db), prefix="/api")
# Real-time WebSocket channels: /api/ws/menu/{id}, /api/ws/screen/{id}, /api/ws/device/{id}
app.include_router(ws_router)

# Fase 5 · Sprint 1 · Etapa B — Stripe guest checkout + webhook
from stripe_routes import build_stripe_router

app.include_router(build_stripe_router(db))

# Sprint 1 · Etapa C1 — Admin Orders (approve / reject / request-changes)
from admin_orders_routes import build_admin_orders_router

app.include_router(build_admin_orders_router(db, require_admin))

# Client logos — admin-managed social proof shown on the public marketing pages
from client_logos_routes import create_client_logos_routes

app.include_router(create_client_logos_routes(db, require_admin))

# Sprint 1 · Etapa C2 — Admin Invoices (list / detail / PDF / reissue)
from admin_invoices_routes import build_admin_invoices_router

app.include_router(build_admin_invoices_router(db))

# Sprint 1 · Etapa C3 — Admin Refunds / Credit Notes / Ledger
from admin_refunds_routes import build_admin_refunds_router

app.include_router(build_admin_refunds_router(db))

# Sprint 1 · Etapa C4 — Reports / Dashboard / Exports / BI
from reports_routes import build_reports_router

app.include_router(build_reports_router(db))

# Phase D.1 — Corporate Portal (business/rental clients dashboard)
from corporate_portal import create_corporate_routes

app.include_router(create_corporate_routes(db, get_current_user))

# Sign Permit Information — public form + admin management
from sign_permits import create_sign_permit_routes

app.include_router(create_sign_permit_routes(db, require_admin))

# ── Fase 3: Public Advertising Marketplace already registered above ──────────
# Note: duplicate route registrations removed here to avoid FastAPI conflicts

# ── Fase 4: MediaView Managed Portal ─────────────────────────────────────────
from managed_portal_routes import create_managed_portal_routes

app.include_router(create_managed_portal_routes(db, get_current_user, require_admin))

# ────────────────────────────────────────────────────────────────────────
# Observability: structured logs, Sentry, request-id middleware
# ────────────────────────────────────────────────────────────────────────
from observability import init_sentry, install_request_id_middleware, setup_logging

setup_logging()
init_sentry()
install_request_id_middleware(app)

# ────────────────────────────────────────────────────────────────────────
# Health + readiness probes (/api/health, /api/ready)
# ────────────────────────────────────────────────────────────────────────
from health import build_health_router

app.include_router(build_health_router(db))

# ────────────────────────────────────────────────────────────────────────
# Auth v2 (refresh tokens, brute-force, audit, cookie flow) — mounted at
# /api/auth/*. The legacy /api/auth/login|register|me routes above still
# work for backwards compat during migration.
# ────────────────────────────────────────────────────────────────────────
from auth_v2 import (
    build_auth_router as _build_auth_router,
)
from auth_v2 import (
    build_deps as _build_auth_deps,
)
from auth_v2 import (
    ensure_auth_indexes as _ensure_auth_indexes,
)
from rate_limit import install_rate_limiter as _install_rl

_v2_get_current_user, _v2_require_admin, _v2_require_superadmin = _build_auth_deps(db)
app.include_router(_build_auth_router(db, _v2_get_current_user))

# Install rate-limiter middleware (must be added AFTER routers exist,
# BEFORE CORS so 429 responses get proper CORS headers).
_install_rl(app)

# ────────────────────────────────────────────────────────────────────────
# CORS — restrictive whitelist from env. Defaults for dev only.
# ────────────────────────────────────────────────────────────────────────
_cors_env = os.environ.get("CORS_ORIGINS", "").strip()
if _cors_env and _cors_env != "*":
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    if IS_PROD:
        raise RuntimeError(
            "CORS_ORIGINS must be an explicit comma-separated list in production. "
            "Example: https://mediadview.com,https://www.mediadview.com,https://panel.mediadview.com"
        )
    # Dev fallback: allow local preview + expo tunnel + wildcard for local emulator.
    _cors_origins = [
        "http://localhost:3000", "http://localhost:8001",
        "http://localhost:8081", "http://127.0.0.1:3000",
    ]
    _tunnel = os.environ.get("EXPO_PACKAGER_PROXY_URL")
    if _tunnel: _cors_origins.append(_tunnel)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With",
                   "X-CSRF-Token", "Accept", "Origin", "Cache-Control"],
    expose_headers=["Content-Disposition", "X-RateLimit-Limit",
                    "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    max_age=3600,
)

# ── P0-A1: HTTP Security Headers (HSTS/CSP/XFO/etc) ─────────────
from security_headers import install as install_security_headers

install_security_headers(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup():
    # ── Fase 5: Ensure all MongoDB indexes exist (idempotent) ────────────────
    from db_indexes import ensure_indexes
    await ensure_indexes(db)

    await seed_data()

    # ── Fase 3 + Fase 5: Campaign Lifecycle Scheduler ─────────────────────────
    # SCHEDULER_MODE controls where cron jobs run:
    #   "apscheduler" (default): jobs live inside the web-api process
    #   "arq"                  : jobs live in the ARQ worker; web-api DOES NOT
    #                            schedule (avoids duplicate execution once the
    #                            worker is deployed to Render)
    #   "both"                 : useful only in dev, runs both (jobs are
    #                            idempotent by design)
    scheduler_mode = os.environ.get("SCHEDULER_MODE", "apscheduler").lower()
    run_apscheduler = scheduler_mode in ("apscheduler", "both")

    # P0-SCHED-001: campaign_scheduler MUST honour SCHEDULER_MODE to prevent
    # dual execution when the ARQ worker is deployed alongside the web-api.
    if run_apscheduler:
        try:
            from campaign_scheduler import start_campaign_scheduler
            start_campaign_scheduler(db)
            logger.info("Campaign scheduler started in-process (SCHEDULER_MODE=%s)", scheduler_mode)
        except Exception as e:
            logger.error("Failed to start campaign_scheduler: %s", e)
    else:
        logger.info("P0-SCHED-001: campaign_scheduler skipped (SCHEDULER_MODE=%s → ARQ worker handles it)", scheduler_mode)

    logger.info("MediaView Digital Signage API started (SCHEDULER_MODE=%s)", scheduler_mode)

    if run_apscheduler:
        try:
            start_scheduler(db)
        except Exception as e:
            logger.exception(f"Failed to start finance scheduler: {e}")
        try:
            start_colorlight_scheduler(db)
        except Exception as e:
            logger.exception(f"Failed to start colorlight scheduler: {e}")
    else:
        logger.info("SCHEDULER_MODE=%s → in-process APScheduler skipped "
                    "(ARQ worker owns cron jobs)", scheduler_mode)

    try:
        from auth_v2 import ensure_auth_indexes
        await ensure_auth_indexes(db)
    except Exception as e:
        logger.exception(f"Failed to ensure auth indexes: {e}")

    # Fase 5 · Sprint 1 · Etapa A — Stripe / Finance indexes
    try:
        from stripe_indexes import ensure_stripe_indexes
        await ensure_stripe_indexes(db)
    except Exception as e:
        logger.exception(f"Failed to ensure Stripe indexes: {e}")

    # Phase 2C P1 — Seed canonical plan configs (idempotent)
    try:
        await seed_default_plans(db)
        logger.info("Phase 2C: canonical plan configs seeded OK")
    except Exception as e:
        logger.exception(f"Failed to seed default plans: {e}")

# ── Phase 2C-1A: SaaS CRM Domain Foundation (additive — no legacy changes) ──
from domain_saas.routes import create_saas_crm_routes

app.include_router(
    create_saas_crm_routes(db, get_current_user, require_admin, require_superadmin)
)


@app.on_event("shutdown")
async def shutdown():
    client.close()
    # ── Fase 3: Stop Campaign Scheduler ──────────────────────────────────────
    try:
        from campaign_scheduler import stop_campaign_scheduler
        stop_campaign_scheduler()
    except Exception:
        pass

# ── Expo SaaS SPA catch-all (must be LAST route) ─────────────────────────────
# Routes any unmatched path to the Expo index.html so client-side routing works.
# e.g. /landing, /pricing, /workspace, /login, /(auth)/signup → all return index.html
# Excludes: /api/*, /player/*, /advertise/*, admin paths (handled above).
_SAAS_EXCLUDED = ('api/', 'player/', 'advertise/', '_expo/', 'assets/')

@app.get("/{full_path:path}", include_in_schema=False)
async def expo_spa_catchall(full_path: str):
    """Serve Expo SPA for all non-API routes (SPA client-side routing support)."""
    if any(full_path.startswith(p) for p in _SAAS_EXCLUDED):
        from fastapi import HTTPException as _HE
        raise _HE(status_code=404, detail="Not found")
    saas_index = os.path.join(SAAS_DIR, 'index.html')
    if os.path.isfile(saas_index):
        return FileResponse(saas_index, media_type='text/html')
    return FileResponse(os.path.join(WEB_DIR, 'landing.html'), media_type='text/html')
