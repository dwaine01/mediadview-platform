# =====================================================
# MediaView Digital Signage Platform - Backend API
# =====================================================

from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import Response, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pathlib import Path

# Load .env FIRST (before any module reads env vars) then run fail-fast validator.
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')
from startup_check import validate_environment
validate_environment()
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import re
import uuid
from datetime import datetime, timedelta
import jwt
import bcrypt
import base64
from bson import ObjectId

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ============ CONFIGURATION ============

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'mediaview_db')
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

# ============ DATABASE ============

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ============ APP SETUP ============

app = FastAPI(title="MediaView Digital Signage API", version="1.0.0")
api_router = APIRouter(prefix="/api")
security = HTTPBearer()

# Rate limiter (imported early because @_rl.limit decorators are evaluated
# at module load time). LIMITS provides central rate-limit strings.
from rate_limit import limiter as _rl, LIMITS as _LIMITS  # noqa: E402

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
                result['_id'] = str(value)
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

class ScreenLocation(BaseModel):
    city: str
    address: str
    state: Optional[str] = None
    country: str = "US"
    lat: Optional[float] = None
    lng: Optional[float] = None

class ScreenPricing(BaseModel):
    per_hour: float = 50.0
    per_day: float = 400.0
    per_slot: float = 5.0
    currency: str = "USD"

class ScreenSpecs(BaseModel):
    size: str = "20ft x 10ft"
    type: str = "LED"
    resolution: str = "1920x1080"
    orientation: str = "landscape"

class ScreenCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location: ScreenLocation
    pricing: ScreenPricing = ScreenPricing()
    specs: ScreenSpecs = ScreenSpecs()
    preview_image: Optional[str] = None
    status: str = "active"
    location_code: Optional[str] = None

class ScreenUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[dict] = None
    pricing: Optional[dict] = None
    specs: Optional[dict] = None
    preview_image: Optional[str] = None
    status: Optional[str] = None
    location_code: Optional[str] = None

class CampaignSchedule(BaseModel):
    start_date: str
    end_date: str
    start_time: str = "08:00"
    end_time: str = "22:00"
    slot_duration: int = 15
    frequency: int = 5

class CampaignCreate(BaseModel):
    name: str
    screen_id: str
    schedule: CampaignSchedule
    media_ids: List[str] = []

class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    schedule: Optional[CampaignSchedule] = None
    media_ids: Optional[List[str]] = None

class MediaUpload(BaseModel):
    filename: str
    content_type: str
    data: str

class PaymentCreate(BaseModel):
    campaign_id: str
    method: str = "card"
    card_last4: Optional[str] = None

# Device / Player Models
class DeviceRegister(BaseModel):
    device_name: Optional[str] = None
    device_model: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    resolution: Optional[str] = None
    platform: Optional[str] = None  # android_tv, fire_tv, tizen, webos
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None

class DeviceHeartbeat(BaseModel):
    status: str = "online"
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

class DeviceActivate(BaseModel):
    activation_code: str
    screen_id: str
    device_name: Optional[str] = None
    tier: Optional[str] = None  # "tv_direct" or "player_dedicated"

class DeviceLog(BaseModel):
    level: str = "info"
    message: str
    details: Optional[str] = None

class DeviceProvision(BaseModel):
    """Pre-provision a device before shipping (MediaView Player Dedicated)"""
    device_name: str
    screen_id: str
    server_url: str
    tier: str = "player_dedicated"
    reboot_time: str = "03:00"  # Nightly reboot time (HH:MM)
    notes: Optional[str] = None

import random
import string

def gen_activation_code():
    """Generate 6-char easy-to-read activation code (no ambiguous chars)"""
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return ''.join(random.choices(chars, k=6))

# ============ AUTH HELPERS ============

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Legacy decoder that ALSO accepts Auth v2 tokens (aud/iss/typ) for compat.
    Tries v2 first (with audience/issuer verification), falls back to v1 (no aud/iss)."""
    try:
        token = credentials.credentials
        try:
            # v2 tokens carry aud/iss and must be verified — do that first.
            payload = jwt.decode(
                token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                audience=os.environ.get("JWT_AUDIENCE", "mediadview-frontend"),
                issuer=os.environ.get("JWT_ISSUER", "mediadview-api"),
            )
        except jwt.InvalidTokenError:
            # v1 legacy tokens: no aud/iss claims → decode without verification of those.
            payload = jwt.decode(
                token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                options={"verify_aud": False, "verify_iss": False},
            )
        user_id = payload.get("sub")
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if not user.get("active", True):
            raise HTTPException(status_code=401, detail="Account deactivated")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

async def require_superadmin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    return current_user

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
    return {"status": "healthy", "service": "MediaView API"}

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
        "company_name": req.company_name, "phone": None,
        "language": "en", "active": True, "session_epoch": 0,
        "created_at": datetime.utcnow()
    }
    await db.users.insert_one(user)
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
    from auth_v2 import is_locked_out, record_attempt, audit, _ip
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
    token = create_token(user["id"], user["role"])
    return {
        "access_token": token, "token_type": "bearer",
        "user": {"id": user["id"], "name": user["name"], "email": user["email"],
                 "role": user["role"], "company_name": user.get("company_name"),
                 "language": user.get("language", "en")}
    }

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"], "name": current_user["name"],
        "email": current_user["email"], "role": current_user["role"],
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

@api_router.get("/screens")
async def list_screens(city: Optional[str] = None, status: Optional[str] = "active"):
    query = {}
    if status:
        query["status"] = status
    if city:
        query["location.city"] = {"$regex": city, "$options": "i"}
    screens = await db.screens.find(query).to_list(100)
    return serialize_doc(screens)

@api_router.get("/screens/cities")
async def get_cities():
    cities = await db.screens.distinct("location.city", {"status": "active"})
    return sorted(cities)

@api_router.get("/screens/{screen_id}")
async def get_screen(screen_id: str):
    screen = await db.screens.find_one({"id": screen_id})
    if not screen:
        raise HTTPException(status_code=404, detail="Screen not found")
    active = await db.campaigns.count_documents(
        {"screen_id": screen_id, "status": {"$in": ["approved", "active"]}}
    )
    result = serialize_doc(screen)
    result["active_campaigns"] = active
    return result

@api_router.post("/screens/{screen_id}/calculate-price")
async def calc_price(screen_id: str, schedule: CampaignSchedule):
    screen = await db.screens.find_one({"id": screen_id})
    if not screen:
        raise HTTPException(status_code=404, detail="Screen not found")
    return calculate_campaign_price(screen.get("pricing", {}), schedule.dict())

# ============ ROUTES: CAMPAIGNS ============

@api_router.post("/campaigns")
async def create_campaign(data: CampaignCreate, current_user: dict = Depends(get_current_user)):
    screen = await db.screens.find_one({"id": data.screen_id})
    if not screen:
        raise HTTPException(status_code=404, detail="Screen not found")
    pricing = calculate_campaign_price(screen.get("pricing", {}), data.schedule.dict())
    campaign = {
        "id": gen_id(), "user_id": current_user["id"],
        "screen_id": data.screen_id, "name": data.name,
        "status": "draft", "schedule": data.schedule.dict(),
        "media_ids": data.media_ids, "pricing": pricing,
        "payment_id": None, "admin_notes": None,
        "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
    }
    await db.campaigns.insert_one(campaign)
    return serialize_doc(campaign)

@api_router.get("/campaigns")
async def list_campaigns(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"user_id": current_user["id"]}
    if status:
        query["status"] = status
    campaigns = await db.campaigns.find(query).sort("created_at", -1).to_list(100)
    enriched = []
    for c in campaigns:
        screen = await db.screens.find_one({"id": c.get("screen_id")})
        c["screen"] = serialize_doc(screen) if screen else None
        enriched.append(c)
    return serialize_doc(enriched)

@api_router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, current_user: dict = Depends(get_current_user)):
    campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": current_user["id"]})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    screen = await db.screens.find_one({"id": campaign.get("screen_id")})
    campaign["screen"] = serialize_doc(screen) if screen else None
    media_items = []
    for mid in campaign.get("media_ids", []):
        media = await db.media.find_one({"id": mid})
        if media:
            media_items.append(serialize_doc(media))
    campaign["media"] = media_items
    if campaign.get("payment_id"):
        payment = await db.payments.find_one({"id": campaign["payment_id"]})
        campaign["payment"] = serialize_doc(payment)
    return serialize_doc(campaign)

@api_router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, data: CampaignUpdate, current_user: dict = Depends(get_current_user)):
    campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": current_user["id"]})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign["status"] not in ["draft", "rejected"]:
        raise HTTPException(status_code=400, detail="Can only edit draft or rejected campaigns")
    update = {k: v for k, v in data.dict().items() if v is not None}
    if "schedule" in update and data.schedule:
        update["schedule"] = data.schedule.dict()
        screen = await db.screens.find_one({"id": campaign["screen_id"]})
        if screen:
            update["pricing"] = calculate_campaign_price(screen.get("pricing", {}), update["schedule"])
    update["updated_at"] = datetime.utcnow()
    await db.campaigns.update_one({"id": campaign_id}, {"$set": update})
    return {"message": "Campaign updated"}

@api_router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, current_user: dict = Depends(get_current_user)):
    campaign = await db.campaigns.find_one({"id": campaign_id, "user_id": current_user["id"]})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign["status"] != "draft":
        raise HTTPException(status_code=400, detail="Can only delete draft campaigns")
    await db.campaigns.delete_one({"id": campaign_id})
    return {"message": "Campaign deleted"}

# ============ ROUTES: MEDIA ============
# Fase 4 (Cloudflare R2):
#   - New uploads → R2 when configured, legacy base64+disk otherwise.
#   - Reads       → open_media_for_response() picks r2 URL / bytes automatically.
#   - Big files   → POST /media/presign + PUT to R2 + POST /media/finalize.
from storage import (
    R2_ENABLED, R2_BUCKET, validate_upload, build_key, public_url_for_key,
    r2_put_bytes, r2_presign_put, r2_head, r2_delete,
    open_media_for_response, _ext_of,
)

@api_router.post("/media/upload")
@_rl.limit(_LIMITS.media_upload)
async def upload_media(request: Request, response: Response, data: MediaUpload,
                       current_user: dict = Depends(get_current_user)):
    """Legacy small-file upload. Accepts base64 JSON; stores in R2 if configured,
    otherwise writes to legacy disk + base64 (backwards-compat). Big files should
    use /media/presign instead."""
    try:
        file_bytes = base64.b64decode(data.data)
    except Exception:
        raise HTTPException(400, "Invalid base64 data")
    size = len(file_bytes)

    # Validation — MIME + size + (video duration bypass here since we don't
    # know it in a base64 upload; presign flow enforces it).
    kind = validate_upload(filename=data.filename, mime=data.content_type,
                           size=size, duration_seconds=(1 if data.content_type.startswith("video/") else None))

    file_id = gen_id()
    ext = _ext_of(data.filename, data.content_type)
    tenant_id = current_user.get("company_name") or current_user["id"]
    tenant = re.sub(r"[^a-zA-Z0-9_-]", "_", str(tenant_id))[:40] or "default"

    media_doc: dict = {
        "id": file_id, "user_id": current_user["id"],
        "filename": data.filename, "content_type": data.content_type,
        "size": size, "type": kind,
        "created_at": datetime.utcnow(),
    }

    if R2_ENABLED:
        # ── Modern path: put in R2, keep only metadata in Mongo ──────
        key = build_key(tenant_id=tenant, client_id=current_user["id"],
                        campaign_id="unassigned", ext=ext)
        try:
            info = await r2_put_bytes(key, file_bytes, data.content_type)
        except Exception as e:
            logger.exception("R2 upload failed: %s", e)
            raise HTTPException(502, "Media storage temporarily unavailable")
        media_doc.update({
            "storage":    "r2",
            "r2_key":     key,
            "r2_etag":    info.get("etag"),
            "public_url": public_url_for_key(key),
            "status":     "ready",
        })
    else:
        # ── Legacy path (dev / no R2 configured): disk + base64 mirror ─
        stored_name = f"{file_id}{ext or '.bin'}"
        file_path = os.path.join(MEDIA_DIR, stored_name)
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        media_doc.update({
            "storage":         "legacy",
            "stored_filename": stored_name,
            "data":            data.data if kind == "image" else None,
            "status":          "ready",
        })

    await db.media.insert_one(media_doc)
    return {"id": file_id, "filename": data.filename, "size": size,
            "content_type": data.content_type, "type": kind,
            "storage": media_doc["storage"],
            "public_url": media_doc.get("public_url")}


class MediaPresignRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    duration_seconds: Optional[float] = None
    campaign_id: Optional[str] = None
    screen_id:   Optional[str] = None


@api_router.post("/media/presign")
@_rl.limit(_LIMITS.media_upload)
async def presign_media(request: Request, response: Response, body: MediaPresignRequest,
                        current_user: dict = Depends(get_current_user)):
    """Return a short-lived (10 min) presigned PUT URL. Client uploads directly
    to R2, then calls /media/finalize to attach it to a campaign/screen."""
    if not R2_ENABLED:
        raise HTTPException(503, "Direct uploads not available — use /media/upload")
    kind = validate_upload(filename=body.filename, mime=body.content_type,
                           size=body.size_bytes, duration_seconds=body.duration_seconds)
    ext = _ext_of(body.filename, body.content_type)
    tenant = re.sub(r"[^a-zA-Z0-9_-]", "_",
                    str(current_user.get("company_name") or current_user["id"]))[:40] or "default"
    key = build_key(tenant_id=tenant, client_id=current_user["id"],
                    campaign_id=body.campaign_id or "unassigned",
                    screen_id=body.screen_id, ext=ext)
    upload_id = gen_id()
    await db.media.insert_one({
        "id": upload_id, "user_id": current_user["id"],
        "filename": body.filename, "content_type": body.content_type,
        "size": body.size_bytes, "type": kind,
        "duration_seconds": body.duration_seconds,
        "campaign_id": body.campaign_id, "screen_id": body.screen_id,
        "storage": "pending", "r2_key": key,
        "status": "pending", "created_at": datetime.utcnow(),
    })
    signed = await r2_presign_put(key, body.content_type)
    return {"upload_id": upload_id, "key": key, **signed}


class MediaFinalizeRequest(BaseModel):
    upload_id: str


@api_router.post("/media/finalize")
async def finalize_media(request: Request, body: MediaFinalizeRequest,
                         current_user: dict = Depends(get_current_user)):
    """Verify the object landed in R2, then mark media as ready."""
    doc = await db.media.find_one({"id": body.upload_id, "user_id": current_user["id"]})
    if not doc or doc.get("status") != "pending":
        raise HTTPException(404, "Upload not found or already finalized")
    head = await r2_head(doc["r2_key"])
    if not head:
        raise HTTPException(400, "R2 object not found — did the upload complete?")
    # Server-side verification: MIME + size within declared bounds
    got_size = int(head.get("ContentLength") or 0)
    got_mime = head.get("ContentType") or doc["content_type"]
    if got_size > doc["size"] * 1.05 + 1024:      # allow ~5% slack for streaming
        await r2_delete(doc["r2_key"])
        raise HTTPException(400, "Uploaded size does not match declared")
    if got_mime != doc["content_type"]:
        await r2_delete(doc["r2_key"])
        raise HTTPException(400, "Uploaded MIME does not match declared")
    public_url = public_url_for_key(doc["r2_key"])
    await db.media.update_one({"id": doc["id"]}, {"$set": {
        "storage": "r2", "status": "ready",
        "r2_etag": (head.get("ETag") or "").strip('"'),
        "size":    got_size,
        "public_url": public_url,
    }})
    return {"id": doc["id"], "public_url": public_url, "status": "ready"}


@api_router.get("/media")
async def list_media(current_user: dict = Depends(get_current_user)):
    media = await db.media.find(
        {"user_id": current_user["id"], "status": {"$ne": "pending"}},
        {"data": 0}   # never send base64 in listings
    ).sort("created_at", -1).to_list(100)
    return serialize_doc(media)

@api_router.get("/media/{media_id}")
async def get_media(media_id: str):
    media = await db.media.find_one({"id": media_id})
    if not media:
        raise HTTPException(404, "Media not found")
    # Strip base64 payload from metadata responses
    media.pop("data", None)
    return serialize_doc(media)

@api_router.get("/media/{media_id}/file")
async def get_media_file(media_id: str):
    """Universal read — returns 302 to Cloudflare when in R2, or raw bytes otherwise."""
    media = await db.media.find_one({"id": media_id})
    if not media:
        raise HTTPException(404, "Media not found")
    result = open_media_for_response(media, media_dir=MEDIA_DIR)
    if result["type"] == "url":
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=result["value"], status_code=302)
    return Response(content=result["value"], media_type=result["mime"])

@api_router.delete("/media/{media_id}")
async def delete_media(media_id: str, current_user: dict = Depends(get_current_user)):
    media = await db.media.find_one({"id": media_id, "user_id": current_user["id"]})
    if not media:
        raise HTTPException(404, "Media not found")
    # Remove R2 object if present
    if media.get("r2_key"):
        await r2_delete(media["r2_key"])
    # Remove legacy disk copy if present
    if media.get("stored_filename"):
        file_path = os.path.join(MEDIA_DIR, media["stored_filename"])
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except Exception: pass
    await db.media.delete_one({"id": media_id})
    return {"message": "Media deleted"}

@api_router.put("/media/{media_id}/rotate")
async def rotate_media(media_id: str, rotation: int = 0, current_user: dict = Depends(get_current_user)):
    """Set rotation angle and force refresh on all devices showing this media."""
    if rotation not in [0, 90, 180, 270]:
        raise HTTPException(status_code=400, detail="Rotation must be 0, 90, 180 or 270")
    media = await db.media.find_one({"id": media_id})
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    await db.media.update_one({"id": media_id}, {"$set": {"rotation": rotation}})
    
    # Find all campaigns using this media and force restart their devices
    campaigns = await db.campaigns.find({"media_ids": media_id}).to_list(100)
    restarted = 0
    for camp in campaigns:
        devices = await db.devices.find({"screen_id": camp.get("screen_id"), "status": "active"}).to_list(10)
        for dev in devices:
            await db.devices.update_one({"id": dev["id"]}, {"$set": {"pending_command": "reload"}})
            restarted += 1
    
    return {"message": f"Rotation set to {rotation}. {restarted} device(s) will refresh."}

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

class CreateAdminRequest(BaseModel):
    name: str
    email: str
    password: str
    company_name: Optional[str] = None

@api_router.post("/superadmin/create-admin")
async def create_admin(data: CreateAdminRequest, sa: dict = Depends(require_superadmin)):
    """Super Admin creates a new Admin account."""
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    admin = {
        "id": gen_id(), "name": data.name, "email": data.email.lower(),
        "password_hash": hash_password(data.password), "role": "admin",
        "company_name": data.company_name, "phone": None,
        "language": "en", "active": True,
        "created_by": sa["id"],
        "created_at": datetime.utcnow()
    }
    await db.users.insert_one(admin)
    return {"message": "Admin created", "admin_id": admin["id"], "email": admin["email"]}

@api_router.get("/superadmin/admins")
async def list_admins(sa: dict = Depends(require_superadmin)):
    """List all admin accounts."""
    admins = await db.users.find({"role": "admin"}, {"password_hash": 0}).sort("created_at", -1).to_list(100)
    enriched = []
    for a in admins:
        customers = await db.users.count_documents({"role": "customer"})
        campaigns = await db.campaigns.count_documents({})
        a["total_customers"] = customers
        a["total_campaigns"] = campaigns
        enriched.append(a)
    return serialize_doc(enriched)

@api_router.put("/superadmin/admins/{admin_id}/toggle")
async def toggle_admin(admin_id: str, sa: dict = Depends(require_superadmin)):
    """Enable/disable an admin account."""
    admin = await db.users.find_one({"id": admin_id, "role": "admin"})
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    new_status = not admin.get("active", True)
    await db.users.update_one({"id": admin_id}, {"$set": {"active": new_status}})
    return {"message": f"Admin {'enabled' if new_status else 'disabled'}", "active": new_status}

@api_router.delete("/superadmin/admins/{admin_id}")
async def delete_admin(admin_id: str, sa: dict = Depends(require_superadmin)):
    """Remove an admin account."""
    admin = await db.users.find_one({"id": admin_id, "role": "admin"})
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    await db.users.delete_one({"id": admin_id})
    return {"message": "Admin removed"}

@api_router.get("/superadmin/overview")
async def superadmin_overview(sa: dict = Depends(require_superadmin)):
    """Platform-wide overview for Super Admin."""
    total_admins = await db.users.count_documents({"role": "admin"})
    total_customers = await db.users.count_documents({"role": "customer"})
    total_screens = await db.screens.count_documents({})
    total_campaigns = await db.campaigns.count_documents({})
    total_devices = await db.devices.count_documents({})
    payments = await db.payments.find({"status": "completed"}).to_list(10000)
    total_revenue = sum(p.get("amount", 0) for p in payments)
    return {
        "total_admins": total_admins, "total_customers": total_customers,
        "total_screens": total_screens, "total_campaigns": total_campaigns,
        "total_devices": total_devices, "total_revenue": round(total_revenue, 2),
    }

# ============ ROUTES: ADMIN ============

@api_router.get("/admin/users")
async def admin_list_users(admin: dict = Depends(require_admin)):
    users = await db.users.find({}, {"password_hash": 0}).sort("created_at", -1).to_list(500)
    return serialize_doc(users)

@api_router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, active: bool, admin: dict = Depends(require_admin)):
    result = await db.users.update_one({"id": user_id}, {"$set": {"active": active}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User updated"}

@api_router.get("/admin/campaigns")
async def admin_list_campaigns(status: Optional[str] = None, admin: dict = Depends(require_admin)):
    query = {}
    if status:
        query["status"] = status
    campaigns = await db.campaigns.find(query).sort("created_at", -1).to_list(500)
    enriched = []
    for c in campaigns:
        screen = await db.screens.find_one({"id": c.get("screen_id")})
        user = await db.users.find_one({"id": c.get("user_id")}, {"password_hash": 0})
        c["screen"] = serialize_doc(screen) if screen else None
        c["user"] = serialize_doc(user) if user else None
        enriched.append(c)
    return serialize_doc(enriched)

@api_router.put("/admin/campaigns/{campaign_id}/approve")
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
    return {"message": f"Campaign {new_status}"}

@api_router.put("/admin/campaigns/{campaign_id}/reject")
async def admin_reject(campaign_id: str, notes: Optional[str] = None, admin: dict = Depends(require_admin)):
    campaign = await db.campaigns.find_one({"id": campaign_id})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status": "rejected",
                  "admin_notes": notes or f"Rejected by {admin['name']}",
                  "updated_at": datetime.utcnow()}}
    )
    return {"message": "Campaign rejected"}

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
    import secrets, string
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

@api_router.post("/admin/screens")
async def admin_create_screen(data: ScreenCreate, admin: dict = Depends(require_admin)):
    # Auto-generate permanent location code
    location_code = await get_unique_location_code()
    # Generate the device pairing credentials (ColorlightCloud style)
    pairing_code = gen_pairing_code()
    # Ensure uniqueness
    while await db.screens.find_one({"pairing_code": pairing_code}):
        pairing_code = gen_pairing_code()
    pairing_secret = gen_pairing_secret()
    screen = {
        "id": gen_id(), "name": data.name, "description": data.description,
        "location": data.location.dict(), "pricing": data.pricing.dict(),
        "specs": data.specs.dict(), "preview_image": data.preview_image,
        "status": data.status, "location_code": location_code,
        "pairing_code": pairing_code, "pairing_secret": pairing_secret,
        "paired_device_id": None, "paired_at": None,
        "active": True,
        "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
    }
    await db.screens.insert_one(screen)
    return serialize_doc(screen)

# ============ DEVICE PAIRING (ColorlightCloud-style flow) ============
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

@api_router.post("/devices/pair")
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
    return {
        "ok": True,
        "device_id": device_id,
        "screen_id": screen["id"],
        "screen_name": screen.get("name"),
        "location_code": screen.get("location_code"),
        "player_url": f"/api/player/{screen['id']}/web",
        "message": f"Connected to screen: {screen.get('name')}",
    }

@api_router.post("/admin/screens/{screen_id}/regenerate-pairing")
async def regenerate_pairing(screen_id: str, admin: dict = Depends(require_admin)):
    """Rotate pairing credentials (unpairs any current device)."""
    screen = await db.screens.find_one({"id": screen_id})
    if not screen:
        raise HTTPException(404, "Screen not found")
    new_code = gen_pairing_code()
    while await db.screens.find_one({"pairing_code": new_code}):
        new_code = gen_pairing_code()
    new_secret = gen_pairing_secret()
    await db.screens.update_one({"id": screen_id}, {"$set": {
        "pairing_code": new_code,
        "pairing_secret": new_secret,
        "paired_device_id": None,
        "paired_at": None,
    }})
    return {"pairing_code": new_code, "pairing_secret": new_secret}


@api_router.get("/screens/{screen_id}/qr")
@_rl.limit(_LIMITS.qr_generate)
async def screen_qr_code(request: Request, response: Response, screen_id: str, size: int = 8, kind: str = "public"):
    """Return a PNG QR code for the screen. kind=public → public marketplace URL,
    kind=pair → deep link ready to activate the APK player with the screen id."""
    import io
    import qrcode
    screen = await db.screens.find_one({"id": screen_id})
    if not screen:
        raise HTTPException(404, "Screen not found")
    base = os.getenv("PUBLIC_BASE_URL", "https://mediadview.com").rstrip("/")
    if kind == "pair":
        # Player-facing activation URL
        url = f"{base}/api/player-activate?screen_id={screen_id}"
    else:
        url = f"{base}/api/s/{screen.get('pairing_code') or screen_id}"
    q = qrcode.QRCode(box_size=max(4, min(int(size), 20)), border=2)
    q.add_data(url); q.make(fit=True)
    img = q.make_image(fill_color="#0b1220", back_color="#ffffff")
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


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


@api_router.put("/admin/screens/{screen_id}")
async def admin_update_screen(screen_id: str, data: ScreenUpdate, admin: dict = Depends(require_admin)):
    screen = await db.screens.find_one({"id": screen_id})
    if not screen:
        raise HTTPException(status_code=404, detail="Screen not found")
    update = {k: v for k, v in data.dict(exclude_none=True).items()}
    # location_code is permanent - cannot be changed
    update.pop("location_code", None)
    update["updated_at"] = datetime.utcnow()
    await db.screens.update_one({"id": screen_id}, {"$set": update})
    updated = await db.screens.find_one({"id": screen_id})
    return serialize_doc(updated)

@api_router.delete("/admin/screens/{screen_id}")
async def admin_delete_screen(screen_id: str, cascade: bool = False, admin: dict = Depends(require_admin)):
    active = await db.campaigns.count_documents(
        {"screen_id": screen_id, "status": {"$in": ["pending", "approved", "active"]}}
    )
    if active > 0 and not cascade:
        raise HTTPException(status_code=400, detail=f"Cannot delete screen with {active} active campaign(s). Use cascade=true to force.")
    # Cascade: clean up related data
    if cascade:
        await db.campaigns.delete_many({"screen_id": screen_id})
        await db.devices.update_many({"screen_id": screen_id}, {"$set": {"screen_id": None}})
    result = await db.screens.delete_one({"id": screen_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Screen not found")
    return {"message": "Screen deleted", "cascaded_campaigns": active if cascade else 0}

@api_router.get("/admin/analytics")
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

@api_router.get("/admin/payments")
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

# ============ ROUTES: PLAYER API ============

@api_router.get("/player/{screen_id}/playlist")
async def get_playlist(screen_id: str):
    screen = await db.screens.find_one({"id": screen_id})
    if not screen:
        raise HTTPException(status_code=404, detail="Screen not found")
    now = datetime.utcnow()
    cd = now.strftime("%Y-%m-%d")
    ct = now.strftime("%H:%M")
    campaigns = await db.campaigns.find({
        "screen_id": screen_id, "status": {"$in": ["approved", "active"]},
        "schedule.start_date": {"$lte": cd}, "schedule.end_date": {"$gte": cd}
    }).to_list(100)
    items = []
    for c in campaigns:
        s = c.get("schedule", {})
        if s.get("start_time", "00:00") <= ct <= s.get("end_time", "23:59"):
            for mid in c.get("media_ids", []):
                media = await db.media.find_one({"id": mid})
                if media:
                    items.append({
                        "campaign_id": c["id"], "media_id": media["id"],
                        "filename": media.get("filename"),
                        "content_type": media.get("content_type"),
                        "duration": s.get("slot_duration", 15),
                        "rotation": media.get("rotation", 0),
                        "animation": media.get("animation", "fade"),
                        "media_url": f"/api/player/media/{media['id']}"
                    })
    return {"screen_id": screen_id, "screen_name": screen.get("name"),
            "generated_at": now.isoformat(), "total_items": len(items), "items": items}

@api_router.get("/player/{screen_id}/schedule")
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
            media = await db.media.find_one({"id": mid})
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

@api_router.get("/player/media/{media_id}")
async def player_media(media_id: str):
    media = await db.media.find_one({"id": media_id})
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    fp = os.path.join(MEDIA_DIR, media.get("stored_filename", ""))
    if not os.path.exists(fp):
        raise HTTPException(status_code=404, detail="File not found")
    with open(fp, "rb") as f:
        content = f.read()
    return Response(
        content=content,
        media_type=media.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f"attachment; filename=media",
                 "Cache-Control": "public, max-age=86400"}
    )

# ============ WEB PLAYER ENGINE (Production-Grade HTML5 Digital Signage) ============

@api_router.get("/player/{screen_id}/web", response_class=HTMLResponse)
async def web_player(screen_id: str):
    """Production-grade HTML5 signage player. 24/7 capable with offline cache, video preload, heartbeat, auto-recovery, diagnostics HUD (press 'i')."""
    screen = await db.screens.find_one({"id": screen_id})
    if not screen:
        raise HTTPException(status_code=404, detail="Screen not found")
    sn = screen.get('name', 'Screen')
    res = screen.get('specs', {}).get('resolution', '1920x1080')
    html = '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no"><meta name="mobile-web-app-capable" content="yes"><title>MediaView - ' + sn + '</title>'
    html += '<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:100%;height:100%;overflow:hidden;background:#000;font-family:Segoe UI,Arial,sans-serif;cursor:none}body.sc{cursor:default}#ml{width:100%;height:100%;position:absolute;top:0;left:0;display:flex;align-items:center;justify-content:center}#ml img,#ml video{width:100%;height:100%;object-fit:contain;position:absolute;top:0;left:0}video::-webkit-media-controls{display:none!important}video::-webkit-media-controls-play-button{display:none!important}video::-webkit-media-controls-overlay-play-button{display:none!important}video::-webkit-media-controls-start-playback-button{display:none!important}@keyframes fi{from{opacity:0}to{opacity:1}}.fi{animation:fi .8s ease}@keyframes sl{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}.sl{animation:sl .6s ease}@keyframes zm{from{transform:scale(1.2);opacity:0}to{transform:scale(1);opacity:1}}.zm{animation:zm .8s ease}'
    html += '#fb{position:absolute;top:0;left:0;width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;background:linear-gradient(135deg,#09090F,#1E1B4B)}#fb .lg{width:100px;height:100px;border-radius:24px;background:#4F46E5;display:flex;align-items:center;justify-content:center;margin-bottom:24px;box-shadow:0 0 60px rgba(79,70,229,.3)}#fb .lg span{font-size:36px;font-weight:900;color:#fff}#fb h1{font-size:42px;font-weight:800;color:#E2E8F0}#fb h2{font-size:18px;color:#6366F1;margin-top:4px}#fb .dv{width:80px;height:2px;background:#312E81;margin:28px 0}#fb .st{font-size:15px;color:#64748B}#fb .su{font-size:12px;color:#475569;margin-top:4px}.pu{animation:pu 2s ease-in-out infinite}@keyframes pu{0%,100%{opacity:1}50%{opacity:.5}}'
    html += '#hud{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.9);color:#E2E8F0;font-size:13px;padding:24px 32px;display:none;overflow-y:auto;z-index:1000}#hud.v{display:block}#hud h2{font-size:20px;font-weight:700;color:#A5B4FC;margin-bottom:16px;border-bottom:1px solid #1E293B;padding-bottom:8px}#hud .s{margin-bottom:14px}#hud .s h3{font-size:11px;font-weight:700;color:#6366F1;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:6px}#hud .r{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #111827}#hud .r .l{color:#64748B}#hud .r .vl{color:#E2E8F0;font-weight:600;text-align:right;max-width:60%}.g{color:#10B981!important}.rd{color:#EF4444!important}.y{color:#F59E0B!important}#hud .le{padding:3px 0;border-bottom:1px solid #111827;font-family:monospace;font-size:11px}#hud .le.er{color:#FCA5A5}#hud .ch{position:fixed;bottom:16px;right:24px;font-size:12px;color:#475569}'
    html += '#sb{position:fixed;bottom:0;left:0;right:0;background:rgba(0,0,0,.7);color:#fff;padding:8px 20px;font-size:12px;display:flex;justify-content:space-between;align-items:center;opacity:0;transition:opacity .4s;z-index:500}#sb.v{opacity:1}#sb .br{display:flex;align-items:center;gap:8px}#sb .dt{width:8px;height:8px;border-radius:4px}'
    html += '</style></head><body><div id="player"><div id="ml"></div><div id="fb"><img src="/api/web/logo.png" style="width:200px;margin-bottom:20px" alt="MediAd View"><h1>MediAd View</h1><h2>' + sn + '</h2><div class="dv"></div><p class="st pu" id="fbs">Connecting...</p><p class="su" id="fbu"></p></div></div>'
    html += '<div id="sb"><div class="br"><span class="dt" id="sbd" style="background:#10B981"></span><span>MediAd View</span><span style="color:#6366F1">' + sn + '</span></div><span id="sbi">Loading...</span><span id="sbt"></span></div>'
    html += '<div id="hud"><h2>MediAd View Player - Diagnostics</h2><div id="hc"></div><div class="ch">Press i or click to close</div></div>'
    html += """<script>
(function(){
var SID='""" + screen_id + """',SN='""" + sn + """',RES='""" + res + """',AB=location.origin,PI=60000,HI=30000,V='2.0.0';
var pl=[],ci=-1,ip=false,io=false,ls=null,le=null,st=Date.now(),rc=0,tp=0,lg=[],mc={},pt=null,hv=false;
function log(l,m){lg.unshift({t:new Date().toISOString(),l:l,m:m});if(lg.length>100)lg.pop();console[l==='error'?'error':'log']('[MV]',m)}
async function fp(){try{var r=await fetch(AB+'/api/player/'+SID+'/playlist');if(!r.ok)throw new Error('HTTP '+r.status);var d=await r.json();var it=d.items||[];io=false;ls=new Date();rc=0;le=null;try{localStorage.setItem('mvp_'+SID,JSON.stringify(it))}catch(e){}
var ni=it.map(function(i){return i.media_id}).join(',');var oi=pl.map(function(i){return i.media_id}).join(',');
if(ni!==oi){log('info','Playlist updated: '+it.length+' items');pl=it;ci=-1;it.forEach(function(i){pm(i)})}
if(pl.length>0&&!ip){sf(false);pn();pdc()}else if(pl.length===0){sf(true,'No campaigns scheduled','Waiting for active campaigns...')}
}catch(e){io=true;rc++;le=e.message;log('warn','Fetch failed: '+e.message+' (#'+rc+')');
if(pl.length===0){try{var c=localStorage.getItem('mvp_'+SID);if(c){var it=JSON.parse(c);if(it.length>0){pl=it;log('info','Cache loaded: '+it.length);sf(false);pn()}}}catch(x){}}
if(pl.length===0){sf(true,io?'Offline - Reconnecting...':'No content','Auto-retry active')}}}
function pm(i){if(mc[i.media_id])return;var u=AB+i.media_url;if(i.content_type&&i.content_type.startsWith('image/')){var img=new Image();img.src=u;mc[i.media_id]={t:'image',u:u}}else{mc[i.media_id]={t:'video',u:u}}}
function pn(){if(pl.length===0)return;ci=(ci+1)%pl.length;var it=pl[ci],u=AB+it.media_url,ii=it.content_type&&it.content_type.startsWith('image/');ip=true;tp++;clearTimeout(pt);
var c=document.getElementById('ml');c.innerHTML='';
if(ii){var img=document.createElement('img');img.src=gcu(it);var ac=it.animation==='slide'?'sl':it.animation==='zoom'?'zm':it.animation==='none'?'':'fi';img.className=ac;img.onerror=function(){log('error','Img fail: '+it.filename);pt=setTimeout(pn,2e3)};c.appendChild(img);pt=setTimeout(pn,(it.duration||15)*1e3)}
else{var vid=document.createElement('video');vid.src=u;vid.autoplay=true;vid.muted=true;vid.playsInline=true;vid.setAttribute('playsinline','');vid.setAttribute('webkit-playsinline','');vid.preload='auto';vid.poster='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';var vac=it.animation==='slide'?'sl':it.animation==='zoom'?'zm':it.animation==='none'?'':'fi';vid.className=vac;vid.onended=pn;vid.onerror=function(){log('error','Vid fail: '+it.filename);pt=setTimeout(pn,2e3)};c.appendChild(vid);vid.play().catch(function(){vid.muted=true;vid.play()});pt=setTimeout(pn,Math.max((it.duration||15)*1e3,6e4))}
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
fp();setInterval(fp,PI);setInterval(hb,HI);
})();
</script></body></html>"""
    return HTMLResponse(content=html)

# ============ A35 BRIDGE: Export endpoint for Colorlight A35 integration ============

@api_router.get("/player/{screen_id}/export")
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
            media = await db.media.find_one({"id": mid})
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
        "orientation": screen.get("specs", {}).get("orientation", "landscape"),
        "export_date": td,
        "generated_at": now.isoformat(),
        "total_items": len(export_items),
        "items": export_items
    }

@api_router.get("/player/{screen_id}/status")
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

# ============ ROUTES: DEVICE MANAGEMENT (Player App) ============

@api_router.post("/devices/register")
async def register_device(data: DeviceRegister):
    """Called by the Player App on first launch. Returns device_id + activation_code."""
    code = gen_activation_code()
    # Ensure code is unique
    while await db.devices.find_one({"activation_code": code, "status": "pending"}):
        code = gen_activation_code()

    device = {
        "id": gen_id(),
        "activation_code": code,
        "device_name": data.device_name or "MediaView Player",
        "device_info": {
            "model": data.device_model,
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
    await db.devices.insert_one(device)
    logger.info(f"Device registered: {device['id']} code={code}")
    return {
        "device_id": device["id"],
        "activation_code": code,
        "status": "pending",
        "message": "Device registered. Enter the activation code in the admin panel to link this device to a screen."
    }

@api_router.get("/devices/{device_id}/check")
async def check_device_activation(device_id: str):
    """Polled by Player App to check if device has been activated by admin."""
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

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

@api_router.post("/devices/{device_id}/heartbeat")
async def device_heartbeat(device_id: str, data: DeviceHeartbeat):
    """Called periodically by the Player App to report status and diagnostics."""
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    update = {
        "last_heartbeat": datetime.utcnow(),
        "status": "active" if device.get("screen_id") else "pending",
        "diagnostics": {
            "uptime_seconds": data.uptime_seconds,
            "free_storage_mb": data.free_storage_mb,
            "cached_media_count": data.cached_media_count,
            "cpu_usage": data.cpu_usage,
            "memory_usage": data.memory_usage,
            "ip_address": data.ip_address,
            "app_version": data.app_version,
            "temperature": data.temperature,
            "reported_at": datetime.utcnow(),
        }
    }
    if data.last_error:
        update["last_error"] = data.last_error

    await db.devices.update_one({"id": device_id}, {"$set": update})

    # Return instructions for the player
    response = {
        "status": "ok",
        "server_time": datetime.utcnow().isoformat(),
        "poll_interval_seconds": 60,
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

@api_router.get("/devices/{device_id}/update-check")
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

@api_router.post("/admin/player-release")
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

@api_router.get("/admin/player-release")
async def get_player_release(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("superadmin", "admin"):
        raise HTTPException(403, "Admin required")
    cfg = await db.app_config.find_one({"_id": "player_release"})
    if cfg:
        cfg.pop("_id", None)
    return cfg or {}

@api_router.post("/devices/{device_id}/log")
async def device_log(device_id: str, data: DeviceLog):
    """Player App sends logs (errors, crashes, info) to server."""
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

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

@api_router.get("/admin/devices/{device_id}/logs")
async def admin_device_logs(device_id: str, limit: int = 50, admin: dict = Depends(require_admin)):
    """Get recent logs for a device."""
    logs = await db.device_logs.find({"device_id": device_id}).sort("created_at", -1).to_list(limit)
    return serialize_doc(logs)

@api_router.get("/admin/devices/{device_id}/diagnostics")
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

# --- Screen Power Schedule ---

@api_router.put("/admin/devices/{device_id}/power-schedule")
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

@api_router.get("/admin/devices/{device_id}/power-schedule")
async def get_power_schedule(device_id: str, admin: dict = Depends(require_admin)):
    """Get power schedule for a device."""
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device.get("power_schedule", {"enabled": False, "power_on": "08:00", "power_off": "22:00", "days": ["mon","tue","wed","thu","fri","sat","sun"]})

@api_router.post("/admin/devices/{device_id}/power")
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



@api_router.get("/devices/{device_id}/playlist")
async def device_playlist(device_id: str):
    """Get playlist for an activated device. Used by the Player App."""
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.get("screen_id"):
        return {"device_id": device_id, "status": "not_activated", "items": []}

    screen_id = device["screen_id"]
    screen = await db.screens.find_one({"id": screen_id})

    now = datetime.utcnow()
    cd = now.strftime("%Y-%m-%d")
    ct = now.strftime("%H:%M")

    campaigns = await db.campaigns.find({
        "screen_id": screen_id, "status": {"$in": ["approved", "active"]},
        "schedule.start_date": {"$lte": cd}, "schedule.end_date": {"$gte": cd}
    }).to_list(100)

    items = []
    for c in campaigns:
        s = c.get("schedule", {})
        if s.get("start_time", "00:00") <= ct <= s.get("end_time", "23:59"):
            for mid in c.get("media_ids", []):
                media = await db.media.find_one({"id": mid})
                if media:
                    items.append({
                        "campaign_id": c["id"],
                        "media_id": media["id"],
                        "filename": media.get("filename"),
                        "content_type": media.get("content_type"),
                        "size": media.get("size", 0),
                        "duration": s.get("slot_duration", 15),
                        "rotation": media.get("rotation", 0),
                        "animation": media.get("animation", "fade"),
                        "download_url": f"/api/player/media/{media['id']}",
                        "checksum": media.get("id"),
                    })

    # Update last_sync
    await db.devices.update_one({"id": device_id}, {"$set": {"last_sync": datetime.utcnow()}})

    # Add enabled widgets for this screen
    widgets = await db.widgets.find({"screen_id": screen_id, "enabled": True}).to_list(50)
    for w in widgets:
        items.append({
            "campaign_id": "widget",
            "media_id": w["id"],
            "filename": w.get("name", "Widget"),
            "content_type": "widget",
            "size": 0,
            "duration": w.get("duration", 30),
            "rotation": 0,
            "animation": "fade",
            "download_url": f"/api/widgets/{w['id']}/render",
            "widget_type": w.get("widget_type"),
            "checksum": w["id"],
        })

    return {
        "device_id": device_id,
        "screen_id": screen_id,
        "screen_name": screen.get("name") if screen else "Unknown",
        "resolution": screen.get("specs", {}).get("resolution", "1920x1080") if screen else "1920x1080",
        "generated_at": now.isoformat(),
        "total_items": len(items),
        "items": items,
        "loop": True,
        "poll_interval_seconds": 60,
        "config": {
            "reboot_time": device.get("reboot_time", "03:00"),
            "tier": device.get("tier", "tv_direct"),
        }
    }

# Admin: Device Management
@api_router.get("/admin/devices")
async def admin_list_devices(admin: dict = Depends(require_admin)):
    """List all registered devices."""
    devices = await db.devices.find({}).sort("created_at", -1).to_list(500)
    enriched = []
    for d in devices:
        if d.get("screen_id"):
            screen = await db.screens.find_one({"id": d["screen_id"]})
            d["screen_name"] = screen.get("name") if screen else "Unknown"
        else:
            d["screen_name"] = None
        enriched.append(d)
    return serialize_doc(enriched)

@api_router.post("/admin/devices/activate")
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

@api_router.post("/admin/devices/provision")
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

@api_router.delete("/admin/devices/{device_id}")
async def admin_remove_device(device_id: str, admin: dict = Depends(require_admin)):
    """Remove/deactivate a device."""
    result = await db.devices.delete_one({"id": device_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device removed"}

@api_router.put("/admin/devices/{device_id}/reassign")
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

@api_router.put("/admin/devices/{device_id}/unlink")
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

@api_router.get("/admin/playlogs")
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

# ============ REMOTE COMMANDS ============

@api_router.put("/admin/devices/{device_id}/command")
async def send_device_command(device_id: str, command: str, admin: dict = Depends(require_admin)):
    """Send command to device: restart, reload, update."""
    if command not in ["restart", "reload", "update", "clear_cache"]:
        raise HTTPException(status_code=400, detail="Invalid command")
    device = await db.devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await db.devices.update_one(
        {"id": device_id},
        {"$set": {"pending_command": command, "command_sent_at": datetime.utcnow()}}
    )
    return {"message": f"Command '{command}' sent to device"}

# ============ APP VERSION / AUTO-UPDATE ============

APP_VERSION = "1.1.0"

# ============ WIDGETS / INTEGRATIONS ============

WIDGET_TYPES = ["weather", "clock", "ticker", "qrcode", "countdown", "slides", "youtube", "webpage", "menu", "calendar"]

class WidgetCreate(BaseModel):
    screen_id: str
    widget_type: str
    name: str
    config: dict = {}
    duration: int = 30
    enabled: bool = True

@api_router.post("/admin/widgets")
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

@api_router.get("/admin/widgets")
async def list_widgets(screen_id: Optional[str] = None, admin: dict = Depends(require_admin)):
    query = {"screen_id": screen_id} if screen_id else {}
    widgets = await db.widgets.find(query).sort("created_at", -1).to_list(100)
    return serialize_doc(widgets)

@api_router.delete("/admin/widgets/{widget_id}")
async def delete_widget(widget_id: str, admin: dict = Depends(require_admin)):
    w = await db.widgets.find_one({"id": widget_id})
    await db.widgets.delete_one({"id": widget_id})
    # Force reload on devices showing this widget
    if w and w.get("screen_id"):
        await db.devices.update_many({"screen_id": w["screen_id"], "status": "active"}, {"$set": {"pending_command": "reload"}})
    return {"message": "Widget deleted"}

@api_router.put("/admin/widgets/{widget_id}/toggle")
async def toggle_widget(widget_id: str, admin: dict = Depends(require_admin)):
    w = await db.widgets.find_one({"id": widget_id})
    if not w: raise HTTPException(status_code=404, detail="Widget not found")
    new_state = not w.get("enabled", True)
    await db.widgets.update_one({"id": widget_id}, {"$set": {"enabled": new_state}})
    # Force reload on devices
    if w.get("screen_id"):
        await db.devices.update_many({"screen_id": w["screen_id"], "status": "active"}, {"$set": {"pending_command": "reload"}})
    return {"message": f"Widget {'enabled' if new_state else 'disabled'}"}

@api_router.get("/widgets/{widget_id}/render", response_class=HTMLResponse)
async def render_widget(widget_id: str):
    """Render widget as full HTML page for player display."""
    w = await db.widgets.find_one({"id": widget_id})
    if not w: raise HTTPException(status_code=404, detail="Widget not found")
    cfg = w.get("config", {})
    wt = w.get("widget_type")
    
    base_style = "body{margin:0;font-family:'Inter',Arial,sans-serif;background:#000;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;overflow:hidden}"
    
    if wt == "weather":
        city = cfg.get("city", "New York")
        api_key = cfg.get("api_key", "demo")
        html = f"""<html><head><style>{base_style}.w{{text-align:center}}.temp{{font-size:120px;font-weight:900}}.city{{font-size:28px;color:#94a3b8}}.desc{{font-size:22px;color:#22d3ee;margin-top:8px}}</style></head><body><div class="w"><div class="city">{city}</div><div class="temp" id="temp">--°</div><div class="desc" id="desc">Loading...</div></div><script>
        fetch('https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=imperial')
        .then(r=>r.json()).then(d=>{{document.getElementById('temp').textContent=Math.round(d.main.temp)+'°F';document.getElementById('desc').textContent=d.weather[0].description}})
        .catch(()=>{{document.getElementById('desc').textContent='{city}'}});
        </script></body></html>"""
    
    elif wt == "clock":
        fmt = cfg.get("format", "12h")
        bg = cfg.get("bg_color", "#000000")
        html = f"""<html><head><style>{base_style}body{{background:{bg}}}.c{{text-align:center}}.time{{font-size:140px;font-weight:900;letter-spacing:-4px}}.date{{font-size:32px;color:#64748b;margin-top:8px}}</style></head><body><div class="c"><div class="time" id="t"></div><div class="date" id="d"></div></div><script>
        function u(){{var n=new Date(),h=n.getHours(),m=String(n.getMinutes()).padStart(2,'0'),ap='';
        if('{fmt}'==='12h'){{ap=h>=12?' PM':' AM';h=h%12||12}}
        document.getElementById('t').textContent=h+':'+m+ap;
        document.getElementById('d').textContent=n.toLocaleDateString('en-US',{{weekday:'long',month:'long',day:'numeric',year:'numeric'}})}}
        u();setInterval(u,1000);
        </script></body></html>"""
    
    elif wt == "ticker":
        text = cfg.get("text", "Breaking News: Welcome to MediAd View Digital Signage Platform")
        speed = cfg.get("speed", 80)
        bg = cfg.get("bg_color", "#111827")
        html = f"""<html><head><style>body{{margin:0;background:{bg};display:flex;align-items:center;height:100vh;overflow:hidden}}.t{{white-space:nowrap;font-size:48px;font-weight:700;color:#22d3ee;font-family:Arial,sans-serif;animation:scroll {speed}s linear infinite}}@keyframes scroll{{0%{{transform:translateX(100vw)}}100%{{transform:translateX(-100%)}}}}</style></head><body><div class="t">{text}</div></body></html>"""
    
    elif wt == "qrcode":
        url = cfg.get("url", "https://mediadview.com")
        label = cfg.get("label", "Scan Me")
        html = f"""<html><head><script src="https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.min.js"></script><style>{base_style}.q{{text-align:center}}.label{{font-size:28px;color:#22d3ee;margin-top:20px}}</style></head><body><div class="q"><div id="qr"></div><div class="label">{label}</div></div><script>
        var q=qrcode(0,'M');q.addData('{url}');q.make();
        document.getElementById('qr').innerHTML=q.createSvgTag(8,0);
        document.querySelector('svg').style.width='300px';document.querySelector('svg').style.height='300px';
        </script></body></html>"""
    
    elif wt == "countdown":
        target = cfg.get("target_date", "2026-12-31T00:00:00")
        title = cfg.get("title", "Coming Soon")
        html = f"""<html><head><style>{base_style}.c{{text-align:center}}.title{{font-size:36px;color:#22d3ee;margin-bottom:30px}}.nums{{display:flex;gap:20px;justify-content:center}}.n{{background:#111827;padding:20px 30px;border-radius:16px;border:1px solid #1e293b}}.n .v{{font-size:72px;font-weight:900}}.n .l{{font-size:14px;color:#64748b}}</style></head><body><div class="c"><div class="title">{title}</div><div class="nums"><div class="n"><div class="v" id="d">0</div><div class="l">Days</div></div><div class="n"><div class="v" id="h">0</div><div class="l">Hours</div></div><div class="n"><div class="v" id="m">0</div><div class="l">Minutes</div></div><div class="n"><div class="v" id="s">0</div><div class="l">Seconds</div></div></div></div><script>
        function u(){{var t=new Date('{target}')-new Date();if(t<0)t=0;var d=Math.floor(t/86400000),h=Math.floor(t%86400000/3600000),m=Math.floor(t%3600000/60000),s=Math.floor(t%60000/1000);
        document.getElementById('d').textContent=d;document.getElementById('h').textContent=h;document.getElementById('m').textContent=m;document.getElementById('s').textContent=s}}u();setInterval(u,1000);
        </script></body></html>"""
    
    elif wt == "slides":
        url = cfg.get("url", "")
        html = f"""<html><head><style>body{{margin:0}}iframe{{width:100vw;height:100vh;border:none}}</style></head><body><iframe src="{url}" allowfullscreen></iframe></body></html>"""
    
    elif wt == "youtube":
        video_id = cfg.get("video_id", "")
        html = f"""<html><head><style>body{{margin:0;background:#000}}iframe{{width:100vw;height:100vh;border:none}}</style></head><body><iframe src="https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1&loop=1&playlist={video_id}&controls=0" allowfullscreen allow="autoplay"></iframe></body></html>"""
    
    elif wt == "webpage":
        url = cfg.get("url", "https://google.com")
        html = f"""<html><head><style>body{{margin:0}}iframe{{width:100vw;height:100vh;border:none}}</style></head><body><iframe src="{url}"></iframe></body></html>"""
    
    elif wt == "menu":
        title = cfg.get("title", "Today's Menu")
        items = cfg.get("items", [{"name": "Burger", "price": "$12"}, {"name": "Pizza", "price": "$15"}, {"name": "Salad", "price": "$10"}])
        items_html = "".join([f'<div class="item"><span>{i.get("name","")}</span><span class="dots"></span><span class="p">{i.get("price","")}</span></div>' for i in items])
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
        html = f"<html><body style='background:#000;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh'>Unknown widget type: {wt}</body></html>"
    
    return HTMLResponse(content=html)

@api_router.get("/app/version")
async def get_app_version():
    """Check latest app version for auto-update."""
    return {
        "version": APP_VERSION,
        "update_available": True,
        "download_url": "/api/web/mediaview-player-android.zip",
        "release_notes": "Nightly reboot, content pre-caching, proof of play, remote commands"
    }

@api_router.delete("/admin/campaigns/{campaign_id}/media/{media_id}")
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

@api_router.put("/media/{media_id}/animation")
async def set_media_animation(media_id: str, animation: str = "fade", current_user: dict = Depends(get_current_user)):
    """Set animation type: fade, slide, zoom, none."""
    if animation not in ["fade", "slide", "zoom", "none"]:
        raise HTTPException(status_code=400, detail="Animation must be fade, slide, zoom, or none")
    await db.media.update_one({"id": media_id}, {"$set": {"animation": animation}})
    return {"message": f"Animation set to {animation}"}

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
                "created_at": datetime.utcnow()
            }
            await db.users.insert_one(sa)
            logger.info("Super Admin created: %s", sa_email)

    if await db.screens.count_documents({}) == 0:
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
            }
        ]
        await db.screens.insert_many(screens)
        logger.info(f"Created {len(screens)} sample screens")

    # Demo users
    if await db.users.count_documents({"role": "customer"}) == 0:
        demo_users = [
            {"id": gen_id(), "name": "Sarah Mitchell", "email": "sarah@brightagency.com", "password_hash": hash_password("Demo123!"), "role": "customer", "company_name": "Bright Agency", "phone": "+1 (212) 555-0142", "language": "en", "active": True, "created_at": datetime.utcnow() - timedelta(days=45)},
            {"id": gen_id(), "name": "Carlos Mendez", "email": "carlos@urbanmedia.co", "password_hash": hash_password("Demo123!"), "role": "customer", "company_name": "Urban Media Group", "phone": "+1 (305) 555-0198", "language": "en", "active": True, "created_at": datetime.utcnow() - timedelta(days=30)},
            {"id": gen_id(), "name": "Jessica Park", "email": "jessica@novaretail.com", "password_hash": hash_password("Demo123!"), "role": "customer", "company_name": "Nova Retail Inc.", "phone": "+1 (415) 555-0167", "language": "en", "active": True, "created_at": datetime.utcnow() - timedelta(days=20)},
            {"id": gen_id(), "name": "David Chen", "email": "david@techwave.io", "password_hash": hash_password("Demo123!"), "role": "customer", "company_name": "TechWave Solutions", "phone": "+1 (512) 555-0133", "language": "en", "active": True, "created_at": datetime.utcnow() - timedelta(days=15)},
        ]
        await db.users.insert_many(demo_users)
        logger.info("Created demo users")

        # Demo campaigns
        all_screens = await db.screens.find({}).to_list(10)
        if all_screens:
            demo_campaigns = [
                {"id": gen_id(), "user_id": demo_users[0]["id"], "screen_id": all_screens[0]["id"], "name": "Holiday Season Grand Sale", "status": "active", "schedule": {"start_date": "2026-03-01", "end_date": "2026-03-31", "start_time": "08:00", "end_time": "22:00", "slot_duration": 15, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(all_screens[0].get("pricing", {}), {"start_date": "2026-03-01", "end_date": "2026-03-31", "start_time": "08:00", "end_time": "22:00"}), "payment_id": None, "admin_notes": "Approved by MediaView Admin", "created_at": datetime.utcnow() - timedelta(days=20), "updated_at": datetime.utcnow()},
                {"id": gen_id(), "user_id": demo_users[1]["id"], "screen_id": all_screens[2]["id"], "name": "Summer Collection Launch", "status": "approved", "schedule": {"start_date": "2026-04-01", "end_date": "2026-04-15", "start_time": "10:00", "end_time": "20:00", "slot_duration": 15, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(all_screens[2].get("pricing", {}), {"start_date": "2026-04-01", "end_date": "2026-04-15", "start_time": "10:00", "end_time": "20:00"}), "payment_id": None, "admin_notes": None, "created_at": datetime.utcnow() - timedelta(days=10), "updated_at": datetime.utcnow()},
                {"id": gen_id(), "user_id": demo_users[2]["id"], "screen_id": all_screens[4]["id"], "name": "Tech Expo 2026 Promo", "status": "pending", "schedule": {"start_date": "2026-04-10", "end_date": "2026-04-12", "start_time": "08:00", "end_time": "22:00", "slot_duration": 30, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(all_screens[4].get("pricing", {}), {"start_date": "2026-04-10", "end_date": "2026-04-12", "start_time": "08:00", "end_time": "22:00"}), "payment_id": None, "admin_notes": None, "created_at": datetime.utcnow() - timedelta(days=3), "updated_at": datetime.utcnow()},
                {"id": gen_id(), "user_id": demo_users[3]["id"], "screen_id": all_screens[5]["id"], "name": "Vegas Grand Opening", "status": "active", "schedule": {"start_date": "2026-03-15", "end_date": "2026-04-15", "start_time": "06:00", "end_time": "23:00", "slot_duration": 15, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(all_screens[5].get("pricing", {}), {"start_date": "2026-03-15", "end_date": "2026-04-15", "start_time": "06:00", "end_time": "23:00"}), "payment_id": None, "admin_notes": "Approved by MediaView Admin", "created_at": datetime.utcnow() - timedelta(days=5), "updated_at": datetime.utcnow()},
                {"id": gen_id(), "user_id": demo_users[0]["id"], "screen_id": all_screens[6]["id"], "name": "Spring Fashion Week", "status": "completed", "schedule": {"start_date": "2026-02-15", "end_date": "2026-02-28", "start_time": "10:00", "end_time": "20:00", "slot_duration": 15, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(all_screens[6].get("pricing", {}), {"start_date": "2026-02-15", "end_date": "2026-02-28", "start_time": "10:00", "end_time": "20:00"}), "payment_id": None, "admin_notes": None, "created_at": datetime.utcnow() - timedelta(days=40), "updated_at": datetime.utcnow()},
                {"id": gen_id(), "user_id": demo_users[1]["id"], "screen_id": all_screens[3]["id"], "name": "Miami Music Festival", "status": "active", "schedule": {"start_date": "2026-03-10", "end_date": "2026-03-25", "start_time": "12:00", "end_time": "22:00", "slot_duration": 15, "frequency": 5}, "media_ids": [], "pricing": calculate_campaign_price(all_screens[3].get("pricing", {}), {"start_date": "2026-03-10", "end_date": "2026-03-25", "start_time": "12:00", "end_time": "22:00"}), "payment_id": None, "admin_notes": "Approved", "created_at": datetime.utcnow() - timedelta(days=12), "updated_at": datetime.utcnow()},
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
        all_screens = await db.screens.find({}).to_list(10)
        if len(all_screens) >= 4:
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

@api_router.get("/player/{screen_id}/test", response_class=HTMLResponse)
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

@api_router.get("/menu-templates")
async def get_menu_templates():
    """Get all available menu design templates."""
    return MENU_TEMPLATES

# --- Menu CRUD (Customer-facing) ---

@api_router.post("/menus")
async def create_menu(data: dict, current_user: dict = Depends(get_current_user)):
    """Create a new digital menu with pre-populated professional content."""
    template_id = data.get("template_id", "classic")
    
    # Pre-populated content per template
    TEMPLATE_CONTENT = {
        "classic": [
            {"name": "Starters", "description": "Begin your culinary journey", "items": [
                {"name": "French Onion Soup", "description": "Caramelized onions, gruyère cheese, toasted baguette", "price": 14.00, "featured": True},
                {"name": "Tuna Tartare", "description": "Fresh ahi tuna, avocado, sesame, citrus vinaigrette", "price": 18.00},
                {"name": "Caesar Salad", "description": "Romaine hearts, parmesan, anchovies, house croutons", "price": 13.00},
                {"name": "Shrimp Cocktail", "description": "Jumbo shrimp, classic cocktail sauce, lemon", "price": 16.00},
                {"name": "Bruschetta", "description": "Heirloom tomatoes, basil, balsamic glaze, garlic crostini", "price": 12.00},
            ]},
            {"name": "Main Course", "description": "Signature dishes from our chef", "items": [
                {"name": "Filet Mignon", "description": "8oz center cut, truffle mashed potatoes, asparagus, red wine jus", "price": 48.00, "featured": True},
                {"name": "Pan-Seared Salmon", "description": "Atlantic salmon, lemon butter, seasonal vegetables, rice pilaf", "price": 34.00},
                {"name": "Lobster Tail", "description": "Butter-poached Maine lobster, drawn butter, roasted potatoes", "price": 52.00},
                {"name": "Rack of Lamb", "description": "Herb-crusted lamb, mint pesto, roasted root vegetables", "price": 44.00},
                {"name": "Chicken Cordon Bleu", "description": "Stuffed with ham & swiss, dijon cream sauce, haricots verts", "price": 28.00},
                {"name": "Risotto Primavera", "description": "Arborio rice, seasonal vegetables, parmesan, white truffle oil", "price": 26.00},
            ]},
            {"name": "Desserts", "description": "Sweet endings", "items": [
                {"name": "Crème Brûlée", "description": "Classic vanilla bean custard, caramelized sugar", "price": 12.00, "featured": True},
                {"name": "Chocolate Fondant", "description": "Warm chocolate cake, molten center, vanilla ice cream", "price": 14.00},
                {"name": "Tiramisu", "description": "Mascarpone, espresso-soaked ladyfingers, cocoa", "price": 12.00},
                {"name": "Cheesecake", "description": "New York style, berry compote, whipped cream", "price": 11.00},
            ]},
            {"name": "Beverages", "description": "Curated selection", "items": [
                {"name": "House Wine (Glass)", "description": "Red or White, ask your server for today's selection", "price": 12.00},
                {"name": "Craft Cocktail", "description": "Classic or seasonal, crafted by our mixologist", "price": 16.00},
                {"name": "Sparkling Water", "description": "San Pellegrino 750ml", "price": 6.00},
                {"name": "Espresso", "description": "Double shot, Italian roast", "price": 5.00},
            ]},
        ],
        "modern": [
            {"name": "Brunch", "description": "Available until 3 PM", "items": [
                {"name": "Avocado Toast", "description": "Sourdough, smashed avo, poached egg, microgreens, chili flakes", "price": 14.00, "featured": True},
                {"name": "Acai Bowl", "description": "Organic acai, granola, banana, blueberries, honey drizzle", "price": 13.00},
                {"name": "Eggs Benedict", "description": "Poached eggs, Canadian bacon, hollandaise, English muffin", "price": 16.00},
                {"name": "Pancake Stack", "description": "Fluffy buttermilk pancakes, maple syrup, fresh berries", "price": 12.00},
                {"name": "Smoked Salmon Bagel", "description": "Cream cheese, capers, red onion, fresh dill", "price": 15.00},
            ]},
            {"name": "Sandwiches & Wraps", "description": "Served with side salad or fries", "items": [
                {"name": "Club Sandwich", "description": "Turkey, bacon, lettuce, tomato, mayo, toasted sourdough", "price": 15.00},
                {"name": "Grilled Chicken Wrap", "description": "Grilled chicken, avocado, ranch, mixed greens, tortilla", "price": 14.00},
                {"name": "Caprese Panini", "description": "Fresh mozzarella, tomato, basil, pesto, ciabatta", "price": 13.00, "featured": True},
                {"name": "Tuna Melt", "description": "Albacore tuna salad, cheddar, tomato, grilled rye", "price": 13.00},
            ]},
            {"name": "Coffee & Drinks", "description": "Specialty coffee & fresh juices", "items": [
                {"name": "Flat White", "description": "Double espresso, steamed milk, microfoam", "price": 5.50},
                {"name": "Matcha Latte", "description": "Ceremonial grade matcha, oat milk, honey", "price": 6.00, "featured": True},
                {"name": "Fresh Orange Juice", "description": "Freshly squeezed, no sugar added", "price": 6.00},
                {"name": "Iced Americano", "description": "Double shot espresso over ice", "price": 4.50},
                {"name": "Smoothie", "description": "Mango, banana, spinach, almond milk", "price": 7.00},
            ]},
            {"name": "Pastries", "description": "Baked fresh daily", "items": [
                {"name": "Croissant", "description": "Butter croissant, flaky & golden", "price": 4.00},
                {"name": "Blueberry Muffin", "description": "Jumbo muffin, fresh blueberries, streusel top", "price": 4.50},
                {"name": "Cinnamon Roll", "description": "Warm, cream cheese frosting", "price": 5.00, "featured": True},
            ]},
        ],
        "fastfood": [
            {"name": "Burgers", "description": "100% Angus beef patties", "items": [
                {"name": "Classic Burger", "description": "Beef patty, lettuce, tomato, onion, pickles, special sauce", "price": 9.99, "featured": True, "image": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=300&h=300&fit=crop"},
                {"name": "Double Cheeseburger", "description": "Two patties, American cheese, lettuce, tomato, mayo", "price": 12.99, "image": "https://images.unsplash.com/photo-1553979459-d2229ba7433b?w=300&h=300&fit=crop"},
                {"name": "Bacon BBQ Burger", "description": "Crispy bacon, BBQ sauce, onion rings, cheddar", "price": 13.99, "featured": True, "image": "https://images.unsplash.com/photo-1594212699903-ec8a3eca50f5?w=300&h=300&fit=crop"},
                {"name": "Mushroom Swiss", "description": "Sauteed mushrooms, swiss cheese, garlic aioli", "price": 12.99, "image": "https://images.unsplash.com/photo-1572802419224-296b0aeee0d9?w=300&h=300&fit=crop"},
                {"name": "Veggie Burger", "description": "Plant-based patty, lettuce, tomato, vegan mayo", "price": 11.99, "image": "https://images.unsplash.com/photo-1520072959219-c595dc870360?w=300&h=300&fit=crop"},
            ]},
            {"name": "Chicken", "description": "Crispy & juicy", "items": [
                {"name": "Chicken Tenders (6pc)", "description": "Hand-breaded, served with dipping sauce", "price": 8.99, "image": "https://images.unsplash.com/photo-1562967914-608f82629710?w=300&h=300&fit=crop"},
                {"name": "Spicy Chicken Sandwich", "description": "Crispy chicken, spicy mayo, pickles, brioche bun", "price": 10.99, "featured": True, "image": "https://images.unsplash.com/photo-1606755962773-d324e0a13086?w=300&h=300&fit=crop"},
                {"name": "Chicken Wings (10pc)", "description": "Buffalo, BBQ, or Garlic Parmesan", "price": 12.99, "image": "https://images.unsplash.com/photo-1567620832903-9fc6debc209f?w=300&h=300&fit=crop"},
            ]},
            {"name": "Sides", "description": "Perfect additions", "items": [
                {"name": "French Fries", "description": "Golden crispy, seasoned", "price": 3.99, "image": "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=300&h=300&fit=crop"},
                {"name": "Onion Rings", "description": "Beer-battered, crispy", "price": 4.99, "image": "https://images.unsplash.com/photo-1639024471283-03518883512d?w=300&h=300&fit=crop"},
                {"name": "Mozzarella Sticks", "description": "Breaded mozzarella, marinara sauce", "price": 5.99},
                {"name": "Loaded Nachos", "description": "Tortilla chips, cheese, jalapeños, sour cream, guacamole", "price": 8.99, "image": "https://images.unsplash.com/photo-1513456852971-30c0b8199d4d?w=300&h=300&fit=crop"},
            ]},
            {"name": "Drinks & Shakes", "description": "Ice cold refreshments", "items": [
                {"name": "Soft Drink", "description": "Coca-Cola, Sprite, Fanta - Regular or Large", "price": 2.99},
                {"name": "Milkshake", "description": "Vanilla, Chocolate, or Strawberry", "price": 5.99, "featured": True, "image": "https://images.unsplash.com/photo-1572490122747-3968b75cc699?w=300&h=300&fit=crop"},
                {"name": "Lemonade", "description": "Fresh squeezed, sweetened", "price": 3.49},
            ]},
            {"name": "Combos", "description": "Best value meals", "items": [
                {"name": "Combo #1", "description": "Classic Burger + Fries + Drink", "price": 13.99, "featured": True, "image": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=300&h=300&fit=crop"},
                {"name": "Combo #2", "description": "Double Cheeseburger + Fries + Drink", "price": 16.99},
                {"name": "Combo #3", "description": "Chicken Tenders + Fries + Drink", "price": 12.99},
                {"name": "Family Combo", "description": "4 Burgers + 4 Fries + 4 Drinks", "price": 44.99},
            ]},
        ],
        "mexican": [
            {"name": "Antojitos", "description": "Para empezar", "items": [
                {"name": "Guacamole Fresco", "description": "Aguacate, cilantro, cebolla, jalapeño, limón, totopos", "price": 10.99, "featured": True, "image": "https://images.unsplash.com/photo-1615870216519-2f9fa575fa5c?w=300&h=300&fit=crop"},
                {"name": "Queso Fundido", "description": "Queso Oaxaca derretido, chorizo, tortillas de maíz", "price": 11.99, "image": "https://images.unsplash.com/photo-1618449840665-9ed506d73a34?w=300&h=300&fit=crop"},
                {"name": "Elote Callejero", "description": "Maíz asado, mayonesa, queso cotija, chile, limón", "price": 6.99, "image": "https://images.unsplash.com/photo-1551504734-5ee1c4a1479b?w=300&h=300&fit=crop"},
                {"name": "Nachos Supreme", "description": "Totopos, frijoles, queso, jalapeños, crema, guacamole", "price": 12.99, "image": "https://images.unsplash.com/photo-1513456852971-30c0b8199d4d?w=300&h=300&fit=crop"},
                {"name": "Ceviche de Camarón", "description": "Camarón fresco, limón, tomate, cebolla, aguacate, tostadas", "price": 14.99, "image": "https://images.unsplash.com/photo-1535399831218-d5bd36d1a6b3?w=300&h=300&fit=crop"},
            ]},
            {"name": "Tacos", "description": "Servidos con cebolla, cilantro y salsa", "items": [
                {"name": "Tacos al Pastor (3)", "description": "Cerdo marinado, piña, cebolla, cilantro", "price": 11.99, "featured": True, "image": "https://images.unsplash.com/photo-1551504734-5ee1c4a1479b?w=300&h=300&fit=crop"},
                {"name": "Tacos de Carne Asada (3)", "description": "Res a la parrilla, guacamole, cebolla", "price": 13.99, "image": "https://images.unsplash.com/photo-1599974579688-8dbdd335c77f?w=300&h=300&fit=crop"},
                {"name": "Tacos de Pollo (3)", "description": "Pollo asado, lechuga, crema, queso fresco", "price": 11.99, "image": "https://images.unsplash.com/photo-1624300629298-e9de39c13be5?w=300&h=300&fit=crop"},
                {"name": "Tacos de Camarón (3)", "description": "Camarón empanizado, chipotle mayo, repollo", "price": 14.99, "image": "https://images.unsplash.com/photo-1611250188496-e966043a0629?w=300&h=300&fit=crop"},
                {"name": "Tacos de Birria (3)", "description": "Res estofada, consomé, cebolla, cilantro", "price": 14.99, "featured": True, "image": "https://images.unsplash.com/photo-1640719028782-8230f1bdc755?w=300&h=300&fit=crop"},
            ]},
            {"name": "Platos Fuertes", "description": "Especialidades de la casa", "items": [
                {"name": "Enchiladas Suizas", "description": "Tortillas rellenas de pollo, salsa verde, crema, queso gratinado", "price": 16.99, "image": "https://images.unsplash.com/photo-1534352956036-cd81e27dd615?w=300&h=300&fit=crop"},
                {"name": "Burrito Grande", "description": "Tortilla de harina, arroz, frijoles, carne, queso, crema, guacamole", "price": 14.99, "featured": True, "image": "https://images.unsplash.com/photo-1626700051175-6818013e1d4f?w=300&h=300&fit=crop"},
                {"name": "Chile Relleno", "description": "Chile poblano relleno de queso, salsa de tomate, arroz, frijoles", "price": 15.99},
                {"name": "Fajitas Mixtas", "description": "Res y pollo, pimientos, cebolla, tortillas, arroz, frijoles", "price": 19.99, "image": "https://images.unsplash.com/photo-1625398407796-82650a8c135f?w=300&h=300&fit=crop"},
                {"name": "Mole Poblano", "description": "Pollo en mole tradicional, ajonjolí, arroz, tortillas", "price": 17.99},
            ]},
            {"name": "Bebidas", "description": "Refrescantes", "items": [
                {"name": "Margarita", "description": "Tequila, triple sec, limón fresco - Clásica o de Mango", "price": 10.99, "featured": True},
                {"name": "Agua de Horchata", "description": "Bebida de arroz, canela, vainilla", "price": 3.99},
                {"name": "Jamaica", "description": "Agua de flor de jamaica, endulzada", "price": 3.99},
                {"name": "Michelada", "description": "Cerveza, limón, chamoy, chile, sal", "price": 8.99},
                {"name": "Mexican Coke", "description": "Coca-Cola de vidrio, hecha con azúcar de caña", "price": 3.49},
            ]},
            {"name": "Postres", "description": "Dulce final", "items": [
                {"name": "Churros con Chocolate", "description": "Churros crujientes, azúcar y canela, salsa de chocolate", "price": 7.99, "featured": True},
                {"name": "Flan Napolitano", "description": "Flan de vainilla, caramelo", "price": 6.99},
                {"name": "Tres Leches", "description": "Pastel bañado en tres leches, crema batida, canela", "price": 7.99},
            ]},
        ],
        "sushi": [
            {"name": "Appetizers", "description": "To start your experience", "items": [
                {"name": "Edamame", "description": "Steamed soybeans, sea salt", "price": 6.00},
                {"name": "Miso Soup", "description": "Traditional dashi broth, tofu, wakame, scallions", "price": 5.00},
                {"name": "Gyoza (6pc)", "description": "Pan-fried pork dumplings, ponzu sauce", "price": 9.00},
                {"name": "Tuna Tataki", "description": "Seared ahi tuna, ginger sauce, microgreens", "price": 14.00, "featured": True},
                {"name": "Shrimp Tempura", "description": "Lightly battered shrimp, tempura sauce", "price": 12.00},
            ]},
            {"name": "Signature Rolls", "description": "Chef's special creations", "items": [
                {"name": "Dragon Roll", "description": "Shrimp tempura, avocado on top, eel sauce, sesame", "price": 16.00, "featured": True},
                {"name": "Rainbow Roll", "description": "California roll topped with assorted sashimi", "price": 18.00},
                {"name": "Spicy Tuna Roll", "description": "Fresh tuna, spicy mayo, cucumber, sesame", "price": 14.00},
                {"name": "Philadelphia Roll", "description": "Smoked salmon, cream cheese, cucumber, avocado", "price": 13.00},
                {"name": "Volcano Roll", "description": "Crab, avocado inside, baked seafood on top, spicy mayo", "price": 17.00, "featured": True},
                {"name": "Spider Roll", "description": "Soft shell crab, cucumber, avocado, spicy mayo", "price": 16.00},
            ]},
            {"name": "Sashimi & Nigiri", "description": "Fresh cuts, premium quality", "items": [
                {"name": "Salmon Sashimi (5pc)", "description": "Fresh Atlantic salmon", "price": 14.00},
                {"name": "Tuna Sashimi (5pc)", "description": "Premium bluefin tuna", "price": 16.00, "featured": True},
                {"name": "Mixed Sashimi (12pc)", "description": "Chef's selection of premium fish", "price": 28.00},
                {"name": "Nigiri Set (8pc)", "description": "Assorted nigiri, chef's choice", "price": 22.00},
            ]},
            {"name": "Drinks", "description": "Japanese beverages", "items": [
                {"name": "Hot Sake", "description": "Traditional Japanese rice wine", "price": 8.00},
                {"name": "Sapporo Beer", "description": "Japanese lager, draft", "price": 6.00},
                {"name": "Green Tea", "description": "Hot or iced sencha", "price": 3.00},
                {"name": "Ramune Soda", "description": "Japanese marble soda, assorted flavors", "price": 4.00},
            ]},
        ],
        "pizza": [
            {"name": "Antipasti", "description": "Per iniziare", "items": [
                {"name": "Bruschetta Classica", "description": "Toasted bread, tomatoes, garlic, fresh basil, olive oil", "price": 9.00},
                {"name": "Caprese Salad", "description": "Buffalo mozzarella, heirloom tomatoes, basil, balsamic", "price": 12.00, "featured": True},
                {"name": "Arancini (4pc)", "description": "Fried risotto balls, marinara sauce", "price": 10.00},
                {"name": "Garlic Knots (6pc)", "description": "Fresh dough, garlic butter, parmesan, marinara", "price": 7.00},
            ]},
            {"name": "Pizzas", "description": "Wood-fired, hand-tossed", "items": [
                {"name": "Margherita", "description": "San Marzano tomatoes, fresh mozzarella, basil, olive oil", "price": 14.00, "featured": True},
                {"name": "Pepperoni", "description": "Mozzarella, pepperoni, tomato sauce", "price": 16.00},
                {"name": "Quattro Formaggi", "description": "Mozzarella, gorgonzola, fontina, parmesan", "price": 17.00},
                {"name": "Diavola", "description": "Spicy salami, mozzarella, chili flakes, tomato sauce", "price": 16.00},
                {"name": "Prosciutto e Rucola", "description": "Prosciutto di Parma, arugula, parmesan shavings, truffle oil", "price": 18.00, "featured": True},
                {"name": "Vegetariana", "description": "Grilled vegetables, mozzarella, pesto, cherry tomatoes", "price": 15.00},
                {"name": "Hawaiian", "description": "Ham, pineapple, mozzarella, tomato sauce", "price": 15.00},
            ]},
            {"name": "Pasta", "description": "Fatto in casa", "items": [
                {"name": "Spaghetti Bolognese", "description": "Slow-cooked meat sauce, parmesan", "price": 15.00},
                {"name": "Fettuccine Alfredo", "description": "Cream sauce, parmesan, butter", "price": 14.00},
                {"name": "Penne Arrabbiata", "description": "Spicy tomato sauce, garlic, chili, basil", "price": 13.00},
                {"name": "Lasagna", "description": "Layered pasta, meat sauce, béchamel, mozzarella", "price": 16.00, "featured": True},
            ]},
            {"name": "Dolci & Bevande", "description": "Desserts & Drinks", "items": [
                {"name": "Tiramisu", "description": "Classic Italian dessert, mascarpone, espresso", "price": 9.00, "featured": True},
                {"name": "Panna Cotta", "description": "Vanilla cream, berry coulis", "price": 8.00},
                {"name": "Italian Soda", "description": "Assorted flavors, sparkling water, cream", "price": 4.00},
                {"name": "Espresso", "description": "Double shot, Italian roast", "price": 3.50},
                {"name": "House Wine", "description": "Red: Chianti / White: Pinot Grigio - Glass", "price": 9.00},
            ]},
        ],
        "bar": [
            {"name": "Signature Cocktails", "description": "Crafted by our mixologists", "items": [
                {"name": "Midnight Mule", "description": "Premium vodka, ginger beer, activated charcoal, lime", "price": 14.00, "featured": True},
                {"name": "Smoky Old Fashioned", "description": "Bourbon, smoked maple syrup, aromatic bitters, orange peel", "price": 16.00, "featured": True},
                {"name": "Lavender Martini", "description": "Gin, lavender syrup, lemon, egg white foam", "price": 15.00},
                {"name": "Tropical Sunset", "description": "Rum, passion fruit, mango, coconut cream, pineapple", "price": 14.00},
                {"name": "Espresso Martini", "description": "Vodka, Kahlúa, fresh espresso, vanilla", "price": 15.00},
                {"name": "Mojito Royale", "description": "White rum, mint, lime, sugar cane, soda, prosecco float", "price": 14.00},
            ]},
            {"name": "Classic Cocktails", "description": "Timeless favorites", "items": [
                {"name": "Margarita", "description": "Tequila, Cointreau, fresh lime juice, salt rim", "price": 12.00},
                {"name": "Negroni", "description": "Gin, Campari, sweet vermouth, orange twist", "price": 13.00},
                {"name": "Whiskey Sour", "description": "Bourbon, lemon juice, simple syrup, egg white", "price": 12.00},
                {"name": "Manhattan", "description": "Rye whiskey, sweet vermouth, Angostura bitters, cherry", "price": 14.00},
                {"name": "Piña Colada", "description": "Rum, coconut cream, pineapple juice, blended", "price": 12.00},
            ]},
            {"name": "Bar Bites", "description": "Perfect pairings", "items": [
                {"name": "Truffle Fries", "description": "Crispy fries, truffle oil, parmesan, herbs", "price": 10.00, "featured": True},
                {"name": "Wagyu Sliders (3)", "description": "Mini wagyu burgers, caramelized onion, gruyère", "price": 18.00},
                {"name": "Tuna Poke Nachos", "description": "Wonton chips, ahi tuna, avocado, sriracha mayo", "price": 15.00},
                {"name": "Charcuterie Board", "description": "Cured meats, artisan cheeses, crackers, honeycomb", "price": 22.00},
                {"name": "Wings (10pc)", "description": "Korean BBQ or Buffalo, celery, blue cheese", "price": 14.00},
            ]},
            {"name": "Beer & Wine", "description": "Curated selection", "items": [
                {"name": "Draft Beer", "description": "Ask your server for today's rotating selection", "price": 7.00},
                {"name": "Craft IPA", "description": "Local craft IPA, hoppy & refreshing", "price": 8.00},
                {"name": "Red Wine (Glass)", "description": "Cabernet Sauvignon / Malbec", "price": 12.00},
                {"name": "White Wine (Glass)", "description": "Chardonnay / Sauvignon Blanc", "price": 11.00},
                {"name": "Champagne (Glass)", "description": "French brut, perfect for celebrations", "price": 15.00},
            ]},
        ],
        "healthy": [
            {"name": "Bowls", "description": "Nutritious & delicious", "items": [
                {"name": "Buddha Bowl", "description": "Quinoa, roasted sweet potato, chickpeas, avocado, tahini dressing", "price": 14.00, "featured": True},
                {"name": "Açaí Bowl", "description": "Organic açaí, granola, banana, berries, coconut, honey", "price": 13.00},
                {"name": "Poke Bowl", "description": "Brown rice, fresh salmon, edamame, cucumber, avocado, ponzu", "price": 16.00},
                {"name": "Mediterranean Bowl", "description": "Falafel, hummus, tabbouleh, mixed greens, tzatziki", "price": 14.00, "featured": True},
                {"name": "Protein Power Bowl", "description": "Grilled chicken, brown rice, broccoli, sweet potato, teriyaki", "price": 15.00},
            ]},
            {"name": "Salads", "description": "Fresh & crisp", "items": [
                {"name": "Kale Caesar", "description": "Organic kale, vegan caesar dressing, hemp seeds, croutons", "price": 12.00},
                {"name": "Cobb Salad", "description": "Grilled chicken, avocado, bacon, egg, blue cheese, ranch", "price": 14.00},
                {"name": "Asian Sesame", "description": "Mixed greens, mandarin, almonds, crispy wontons, sesame dressing", "price": 13.00, "featured": True},
                {"name": "Harvest Salad", "description": "Arugula, roasted beets, goat cheese, walnuts, balsamic", "price": 13.00},
            ]},
            {"name": "Smoothies & Juices", "description": "Cold-pressed, fresh daily", "items": [
                {"name": "Green Machine", "description": "Spinach, kale, banana, mango, almond milk", "price": 8.00, "featured": True},
                {"name": "Berry Blast", "description": "Strawberry, blueberry, raspberry, yogurt, honey", "price": 8.00},
                {"name": "Tropical Paradise", "description": "Mango, pineapple, coconut water, turmeric", "price": 8.00},
                {"name": "Detox Juice", "description": "Celery, cucumber, green apple, ginger, lemon", "price": 7.00},
                {"name": "Protein Shake", "description": "Whey protein, banana, peanut butter, oat milk", "price": 9.00},
            ]},
            {"name": "Wraps & Toasts", "description": "Light & satisfying", "items": [
                {"name": "Avocado Toast", "description": "Multigrain bread, smashed avo, cherry tomatoes, microgreens, seeds", "price": 11.00, "featured": True},
                {"name": "Turkey Lettuce Wrap", "description": "Ground turkey, Asian sauce, water chestnuts, butter lettuce", "price": 13.00},
                {"name": "Hummus Veggie Wrap", "description": "Whole wheat wrap, hummus, roasted veggies, feta, spinach", "price": 12.00},
            ]},
        ],
    }
    
    # Build categories with IDs
    # New visual templates reuse fastfood content with photos
    if template_id in ("mcdonalds", "modern_visual", "premium_dark"):
        template_cats = TEMPLATE_CONTENT.get("fastfood", TEMPLATE_CONTENT["classic"])
    else:
        template_cats = TEMPLATE_CONTENT.get(template_id, TEMPLATE_CONTENT["classic"])
    categories = []
    for i, cat_data in enumerate(template_cats):
        items = []
        for j, item_data in enumerate(cat_data.get("items", [])):
            items.append({
                "id": gen_id(),
                "name": item_data["name"],
                "description": item_data.get("description", ""),
                "price": item_data.get("price", 0),
                "image": item_data.get("image", ""),
                "featured": item_data.get("featured", False),
                "available": True,
                "order": j
            })
        categories.append({
            "id": gen_id(),
            "name": cat_data["name"],
            "description": cat_data.get("description", ""),
            "items": items,
            "order": i
        })
    
    menu = {
        "id": gen_id(),
        "user_id": current_user["id"],
        "name": data.get("name", "My Menu"),
        "template_id": template_id,
        "restaurant_name": data.get("restaurant_name", ""),
        "restaurant_logo": data.get("restaurant_logo", ""),
        "subtitle": data.get("subtitle", ""),
        "currency": data.get("currency", "USD"),
        "currency_symbol": data.get("currency_symbol", "$"),
        "categories": categories,
        "status": "draft",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    await db.menus.insert_one(menu)
    return serialize_doc(menu)

@api_router.get("/menus")
async def get_menus(current_user: dict = Depends(get_current_user)):
    """Get all menus for the current user."""
    if current_user.get("role") in ("admin", "superadmin"):
        menus = await db.menus.find().sort("created_at", -1).to_list(200)
    else:
        menus = await db.menus.find({"user_id": current_user["id"]}).sort("created_at", -1).to_list(200)
    return serialize_doc(menus)

@api_router.get("/menus/{menu_id}")
async def get_menu(menu_id: str, current_user: dict = Depends(get_current_user)):
    """Get a specific menu with all its data."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return serialize_doc(menu)

@api_router.put("/menus/{menu_id}")
async def update_menu(menu_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update menu settings."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    update = {"updated_at": datetime.utcnow()}
    for field in ["name", "template_id", "restaurant_name", "restaurant_logo", "subtitle",
                  "currency", "currency_symbol", "status", "categories",
                  "slideshow_enabled", "slideshow_interval",
                  "split_screen_enabled", "split_screen_layout",
                  "split_promo_media", "split_widget_id"]:
        if field in data:
            update[field] = data[field]
    
    await db.menus.update_one({"id": menu_id}, {"$set": update})
    updated = await db.menus.find_one({"id": menu_id})
    try:
        await ws_manager.broadcast_menu(menu_id, "updated")
    except Exception:
        pass
    return serialize_doc(updated)

@api_router.delete("/menus/{menu_id}")
async def delete_menu(menu_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a menu."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    await db.menus.delete_one({"id": menu_id})
    return {"message": "Menu deleted"}

# --- Menu Category Management ---

@api_router.post("/menus/{menu_id}/categories")
async def add_menu_category(menu_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Add a category to a menu."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    category = {
        "id": gen_id(),
        "name": data.get("name", "Category"),
        "description": data.get("description", ""),
        "items": [],
        "order": len(menu.get("categories", [])),
        "active_hours": data.get("active_hours", None),  # {"start":"HH:MM","end":"HH:MM","days":[1,1,1,1,1,1,1]}
    }
    
    await db.menus.update_one({"id": menu_id}, {"$push": {"categories": category}, "$set": {"updated_at": datetime.utcnow()}})
    updated = await db.menus.find_one({"id": menu_id})
    try: await ws_manager.broadcast_menu(menu_id, "updated")
    except Exception: pass
    return serialize_doc(updated)

@api_router.put("/menus/{menu_id}/categories/{category_id}")
async def update_menu_category(menu_id: str, category_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update a category in a menu."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    categories = menu.get("categories", [])
    for cat in categories:
        if cat["id"] == category_id:
            if "name" in data: cat["name"] = data["name"]
            if "description" in data: cat["description"] = data["description"]
            break
    
    await db.menus.update_one({"id": menu_id}, {"$set": {"categories": categories, "updated_at": datetime.utcnow()}})
    try: await ws_manager.broadcast_menu(menu_id, "updated")
    except Exception: pass
    updated = await db.menus.find_one({"id": menu_id})
    return serialize_doc(updated)

@api_router.delete("/menus/{menu_id}/categories/{category_id}")
async def delete_menu_category(menu_id: str, category_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a category from a menu."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    categories = [c for c in menu.get("categories", []) if c["id"] != category_id]
    await db.menus.update_one({"id": menu_id}, {"$set": {"categories": categories, "updated_at": datetime.utcnow()}})
    try: await ws_manager.broadcast_menu(menu_id, "updated")
    except Exception: pass
    return {"message": "Category deleted"}

# --- Menu Item Management ---

@api_router.post("/menus/{menu_id}/categories/{category_id}/items")
async def add_menu_item(menu_id: str, category_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Add an item to a category in a menu."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    item = {
        "id": gen_id(),
        "name": data.get("name", "Item"),
        "description": data.get("description", ""),
        "price": data.get("price", 0),
        "image": data.get("image", ""),
        "featured": data.get("featured", False),
        "available": data.get("available", True),
        "order": 0
    }
    
    categories = menu.get("categories", [])
    for cat in categories:
        if cat["id"] == category_id:
            item["order"] = len(cat.get("items", []))
            cat.setdefault("items", []).append(item)
            break
    
    await db.menus.update_one({"id": menu_id}, {"$set": {"categories": categories, "updated_at": datetime.utcnow()}})
    try: await ws_manager.broadcast_menu(menu_id, "updated")
    except Exception: pass
    updated = await db.menus.find_one({"id": menu_id})
    return serialize_doc(updated)

@api_router.put("/menus/{menu_id}/categories/{category_id}/items/{item_id}")
async def update_menu_item(menu_id: str, category_id: str, item_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Update a menu item."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    categories = menu.get("categories", [])
    for cat in categories:
        if cat["id"] == category_id:
            for it in cat.get("items", []):
                if it["id"] == item_id:
                    for field in ["name", "description", "price", "image", "featured", "available"]:
                        if field in data: it[field] = data[field]
                    break
            break
    
    await db.menus.update_one({"id": menu_id}, {"$set": {"categories": categories, "updated_at": datetime.utcnow()}})
    try: await ws_manager.broadcast_menu(menu_id, "updated")
    except Exception: pass
    updated = await db.menus.find_one({"id": menu_id})
    return serialize_doc(updated)

@api_router.delete("/menus/{menu_id}/categories/{category_id}/items/{item_id}")
async def delete_menu_item(menu_id: str, category_id: str, item_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a menu item."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    categories = menu.get("categories", [])
    for cat in categories:
        if cat["id"] == category_id:
            cat["items"] = [it for it in cat.get("items", []) if it["id"] != item_id]
            break
    
    await db.menus.update_one({"id": menu_id}, {"$set": {"categories": categories, "updated_at": datetime.utcnow()}})
    try: await ws_manager.broadcast_menu(menu_id, "updated")
    except Exception: pass
    return {"message": "Item deleted"}

# --- Menu Render (for player/screen display) ---

# --- Promo Media Management ---

@api_router.post("/menus/{menu_id}/promo-media")
async def add_promo_media(menu_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Add promotional video/image to a menu."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    media_item = {
        "id": gen_id(),
        "type": data.get("type", "image"),  # "image" or "video"
        "url": data.get("url", ""),
        "data": data.get("data", ""),  # base64 for uploads
        "title": data.get("title", ""),
        "order": len(menu.get("promo_media", []))
    }
    
    await db.menus.update_one({"id": menu_id}, {
        "$push": {"promo_media": media_item},
        "$set": {"updated_at": datetime.utcnow()}
    })
    updated = await db.menus.find_one({"id": menu_id})
    return serialize_doc(updated)

@api_router.delete("/menus/{menu_id}/promo-media/{media_id}")
async def delete_promo_media(menu_id: str, media_id: str, current_user: dict = Depends(get_current_user)):
    """Remove promotional media from a menu."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    promo_media = [m for m in menu.get("promo_media", []) if m["id"] != media_id]
    await db.menus.update_one({"id": menu_id}, {
        "$set": {"promo_media": promo_media, "updated_at": datetime.utcnow()}
    })
    return {"message": "Promo media deleted"}



@api_router.get("/menus/{menu_id}/render", response_class=HTMLResponse)
async def render_menu(menu_id: str):
    """Render a menu as a full-screen HTML page optimized for landscape LED displays.
    Features: 3-column max per slide, auto-slideshow, always-visible food images."""
    menu = await db.menus.find_one({"id": menu_id})
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    
    template_id = menu.get("template_id", "classic")
    restaurant = menu.get("restaurant_name", "Restaurant")
    subtitle = menu.get("subtitle", "")
    currency_sym = menu.get("currency_symbol", "$")
    categories = menu.get("categories", [])
    promo_media = menu.get("promo_media", [])
    
    # Food emoji placeholders by keyword
    food_emojis = {
        "soup": "🍲", "salad": "🥗", "tuna": "🐟", "shrimp": "🦐", "bruschetta": "🍞", "bread": "🍞",
        "steak": "🥩", "filet": "🥩", "beef": "🥩", "carne": "🥩", "res": "🥩",
        "salmon": "🐟", "fish": "🐟", "lobster": "🦞", "lamb": "🍖", "rack": "🍖",
        "chicken": "🍗", "pollo": "🍗", "wing": "🍗", "tender": "🍗",
        "risotto": "🍚", "rice": "🍚", "arroz": "🍚",
        "creme": "🍮", "flan": "🍮", "custard": "🍮", "pudding": "🍮",
        "chocolate": "🍫", "cake": "🎂", "pastel": "🎂", "cheesecake": "🍰",
        "tiramisu": "🍰", "dessert": "🍰", "postre": "🍰", "churro": "🍩", "donut": "🍩",
        "wine": "🍷", "cocktail": "🍸", "margarita": "🍹", "beer": "🍺", "cerveza": "🍺",
        "coffee": "☕", "espresso": "☕", "latte": "☕", "cappuccino": "☕", "cafe": "☕",
        "tea": "🍵", "matcha": "🍵",
        "juice": "🧃", "smoothie": "🥤", "lemonade": "🍋", "soda": "🥤", "water": "💧",
        "shake": "🥛", "milk": "🥛", "horchata": "🥛",
        "burger": "🍔", "hamburger": "🍔",
        "pizza": "🍕", "margherita": "🍕",
        "pasta": "🍝", "spaghetti": "🍝", "fettuccine": "🍝", "penne": "🍝", "lasagna": "🍝",
        "taco": "🌮", "burrito": "🌯", "enchilada": "🌯", "quesadilla": "🌯",
        "nacho": "🧀", "queso": "🧀", "cheese": "🧀",
        "guacamole": "🥑", "avocado": "🥑", "aguacate": "🥑",
        "fries": "🍟", "french": "🍟", "onion ring": "🧅",
        "sushi": "🍣", "roll": "🍣", "sashimi": "🍣", "nigiri": "🍣",
        "gyoza": "🥟", "dumpling": "🥟",
        "ramen": "🍜", "noodle": "🍜", "pho": "🍜",
        "egg": "🥚", "pancake": "🥞", "waffle": "🧇", "toast": "🍞",
        "croissant": "🥐", "muffin": "🧁", "cinnamon": "🧁", "pastry": "🧁",
        "sandwich": "🥪", "panini": "🥪", "wrap": "🌯", "bagel": "🥯",
        "ice cream": "🍦", "gelato": "🍦", "panna": "🍦",
        "elote": "🌽", "corn": "🌽", "maiz": "🌽",
        "ceviche": "🐟", "mole": "🫕", "chile": "🌶️", "jalapeno": "🌶️",
        "jamaica": "🌺", "michelada": "🍺",
        "edamame": "🫛", "miso": "🍲", "tempura": "🍤",
        "sake": "🍶", "ramune": "🍾",
        "arancini": "🧆", "garlic": "🧄", "knot": "🥨",
        "caprese": "🍅", "tomato": "🍅",
        "combo": "🍱", "family": "👨‍👩‍👧‍👦", "special": "⭐",
        "bowl": "🥣", "acai": "🫐", "poke": "🍣", "buddha": "🥗",
        "falafel": "🧆", "hummus": "🫘",
        "kale": "🥬", "spinach": "🥬", "lettuce": "🥬",
        "prosciutto": "🥓", "bacon": "🥓", "ham": "🥓",
        "truffle": "🍄", "mushroom": "🍄",
        "nachos": "🧀", "mozzarella": "🧀",
        "default": "🍽️"
    }
    
    def get_food_emoji(name):
        name_lower = name.lower()
        for keyword, emoji in food_emojis.items():
            if keyword in name_lower:
                return emoji
        return food_emojis["default"]
    
    templates = {
        "classic": {"bg": "#1a1a2e", "bg2": "#16213e", "text": "#e2e8f0", "text2": "#94a3b8", "accent": "#d4af37", "cat_bg": "rgba(212,175,55,.08)", "item_bg": "rgba(255,255,255,.03)", "item_border": "rgba(212,175,55,.08)", "font": "'Playfair Display',Georgia,serif", "name_size": "48px", "featured_bg": "rgba(212,175,55,.06)", "img_bg": "rgba(212,175,55,.08)"},
        "modern": {"bg": "#f1f5f9", "bg2": "#e2e8f0", "text": "#1e293b", "text2": "#64748b", "accent": "#2563eb", "cat_bg": "rgba(37,99,235,.06)", "item_bg": "rgba(255,255,255,.9)", "item_border": "rgba(37,99,235,.1)", "font": "'Inter',sans-serif", "name_size": "40px", "featured_bg": "rgba(37,99,235,.05)", "img_bg": "rgba(37,99,235,.06)"},
        "fastfood": {"bg": "#fffbeb", "bg2": "#fef3c7", "text": "#1c1917", "text2": "#78716c", "accent": "#dc2626", "cat_bg": "rgba(220,38,38,.08)", "item_bg": "rgba(255,255,255,.7)", "item_border": "rgba(220,38,38,.1)", "font": "'Inter',sans-serif", "name_size": "44px", "featured_bg": "rgba(220,38,38,.05)", "img_bg": "rgba(220,38,38,.06)"},
        "mexican": {"bg": "#451a03", "bg2": "#3b1503", "text": "#fef3c7", "text2": "#d4a574", "accent": "#f59e0b", "cat_bg": "rgba(245,158,11,.1)", "item_bg": "rgba(255,255,255,.04)", "item_border": "rgba(245,158,11,.12)", "font": "'Inter',sans-serif", "name_size": "44px", "featured_bg": "rgba(245,158,11,.08)", "img_bg": "rgba(245,158,11,.1)"},
        "sushi": {"bg": "#0f172a", "bg2": "#1e293b", "text": "#e2e8f0", "text2": "#94a3b8", "accent": "#f43f5e", "cat_bg": "rgba(244,63,94,.06)", "item_bg": "rgba(255,255,255,.02)", "item_border": "rgba(244,63,94,.08)", "font": "'Inter',sans-serif", "name_size": "42px", "featured_bg": "rgba(244,63,94,.05)", "img_bg": "rgba(244,63,94,.06)"},
        "pizza": {"bg": "#1c1917", "bg2": "#292524", "text": "#fef2f2", "text2": "#a8a29e", "accent": "#dc2626", "cat_bg": "rgba(220,38,38,.08)", "item_bg": "rgba(255,255,255,.03)", "item_border": "rgba(220,38,38,.08)", "font": "'Inter',sans-serif", "name_size": "44px", "featured_bg": "rgba(220,38,38,.05)", "img_bg": "rgba(220,38,38,.06)"},
        "bar": {"bg": "#09090b", "bg2": "#18181b", "text": "#e2e8f0", "text2": "#71717a", "accent": "#a855f7", "cat_bg": "rgba(168,85,247,.07)", "item_bg": "rgba(255,255,255,.02)", "item_border": "rgba(168,85,247,.1)", "font": "'Inter',sans-serif", "name_size": "42px", "featured_bg": "rgba(168,85,247,.06)", "img_bg": "rgba(168,85,247,.08)"},
        "healthy": {"bg": "#f0fdf4", "bg2": "#dcfce7", "text": "#14532d", "text2": "#4ade80", "accent": "#16a34a", "cat_bg": "rgba(22,163,74,.06)", "item_bg": "rgba(255,255,255,.9)", "item_border": "rgba(22,163,74,.1)", "font": "'Inter',sans-serif", "name_size": "40px", "featured_bg": "rgba(22,163,74,.05)", "img_bg": "rgba(22,163,74,.06)"},
        "mcdonalds": {"bg": "#1c1917", "bg2": "#292524", "text": "#fef2f2", "text2": "#a8a29e", "accent": "#dc2626", "cat_bg": "rgba(220,38,38,.08)", "item_bg": "rgba(255,255,255,.03)", "item_border": "rgba(220,38,38,.08)", "font": "'Inter',sans-serif", "name_size": "44px", "featured_bg": "rgba(220,38,38,.05)", "img_bg": "rgba(220,38,38,.06)", "grid": True},
        "modern_visual": {"bg": "#0f172a", "bg2": "#1e293b", "text": "#e2e8f0", "text2": "#94a3b8", "accent": "#f59e0b", "cat_bg": "rgba(245,158,11,.06)", "item_bg": "rgba(255,255,255,.02)", "item_border": "rgba(245,158,11,.08)", "font": "'Inter',sans-serif", "name_size": "42px", "featured_bg": "rgba(245,158,11,.05)", "img_bg": "rgba(245,158,11,.06)", "grid": True},
        "premium_dark": {"bg": "#000000", "bg2": "#0a0a0a", "text": "#e2e8f0", "text2": "#71717a", "accent": "#d4af37", "cat_bg": "rgba(212,175,55,.06)", "item_bg": "rgba(255,255,255,.02)", "item_border": "rgba(212,175,55,.08)", "font": "'Playfair Display',Georgia,serif", "name_size": "44px", "featured_bg": "rgba(212,175,55,.05)", "img_bg": "rgba(212,175,55,.06)", "grid": True}
    }
    
    t = templates.get(template_id, templates["classic"])
    
    is_grid = t.get('grid', False)
    
    # -------- Time-based category filtering (Chat #2 feature) --------
    # Categories can define active_hours: {"start":"HH:MM","end":"HH:MM","days":[1,1,1,1,1,1,1]}
    # Filter out categories that shouldn't be shown at this hour on this weekday.
    try:
        import pytz as _pytz
        _tz = _pytz.timezone(os.getenv("MENU_TZ", "America/New_York"))
        _now = datetime.now(_tz)
        _hm = _now.hour * 60 + _now.minute
        _wd = _now.weekday()  # 0=Mon .. 6=Sun
        _filtered = []
        for _cat in categories:
            _ah = _cat.get("active_hours")
            if not _ah:
                _filtered.append(_cat); continue
            _days = _ah.get("days") or [1]*7
            if len(_days) < 7:
                _days = (_days + [1]*7)[:7]
            if not _days[_wd]:
                continue
            _s = _ah.get("start", "00:00"); _e = _ah.get("end", "23:59")
            try:
                _sh, _sm = map(int, _s.split(":")); _eh, _em = map(int, _e.split(":"))
                _sm_ = _sh*60+_sm; _em_ = _eh*60+_em
                # Overnight support: end < start means it wraps midnight
                if _em_ < _sm_:
                    _ok = (_hm >= _sm_) or (_hm <= _em_)
                else:
                    _ok = _sm_ <= _hm <= _em_
            except Exception:
                _ok = True
            if _ok:
                _filtered.append(_cat)
        # If schedule wipes everything, keep the first category to avoid an empty screen.
        if not _filtered and categories:
            _filtered = [categories[0]]
        categories = _filtered
    except Exception:
        pass
    
    # -------- Slideshow settings (menu-level override) --------
    slideshow_enabled = menu.get("slideshow_enabled", True)
    slideshow_interval = int(menu.get("slideshow_interval") or 12)
    
    # Split categories into slides of 3
    slides = []
    for i in range(0, len(categories), 3):
        slides.append(categories[i:i+3])
    if not slides:
        slides = [[]]
    
    num_slides = len(slides)
    slide_duration = slideshow_interval if slideshow_enabled else 999999
    
    has_promo = len(promo_media) > 0
    menu_height = "75%" if has_promo else "calc(100% - 80px)"
    promo_height = "25%" if has_promo else "0"
    
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Playfair+Display:wght@400;700;900&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;overflow:hidden}}
body{{background:{t['bg']};color:{t['text']};font-family:{t['font']}}}

.menu-container{{width:100%;height:100%;display:flex;flex-direction:column}}

.header{{text-align:center;padding:20px 40px 12px;flex-shrink:0;border-bottom:2px solid {t['accent']}25}}
.restaurant-name{{font-size:{t['name_size']};font-weight:900;color:{t['accent']};letter-spacing:3px;text-transform:uppercase}}
.subtitle{{font-size:15px;color:{t['text2']};margin-top:2px;letter-spacing:1px}}

.slides-wrapper{{flex:1;position:relative;overflow:hidden}}
.slide{{position:absolute;top:0;left:0;width:100%;height:100%;display:flex;gap:20px;padding:16px 28px;opacity:0;transition:opacity 0.8s ease}}
.slide.active{{opacity:1}}

.category{{flex:1;display:flex;flex-direction:column;min-width:0;background:{t['bg2']};border-radius:14px;border:1px solid {t['accent']}12;overflow:hidden}}
.cat-header{{padding:12px 16px;background:{t['cat_bg']};border-bottom:1px solid {t['accent']}15;flex-shrink:0}}
.cat-title{{font-size:18px;font-weight:800;color:{t['accent']};text-transform:uppercase;letter-spacing:3px;text-align:center}}
.cat-desc{{font-size:10px;color:{t['text2']};text-align:center;margin-top:2px}}
.cat-items{{flex:1;overflow-y:auto;padding:6px 8px;scrollbar-width:none}}
.cat-items::-webkit-scrollbar{{display:none}}

.item{{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;margin-bottom:5px;border:1px solid {t['item_border']};background:{t['item_bg']}}}
.item.featured{{background:{t['featured_bg']};border-color:{t['accent']}30}}

.item-img{{width:56px;height:56px;border-radius:10px;object-fit:cover;flex-shrink:0;border:1px solid {t['accent']}20}}
.item-emoji{{width:56px;height:56px;border-radius:10px;background:{t['img_bg']};flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:26px;border:1px solid {t['accent']}15}}

.item-info{{flex:1;min-width:0}}
.item-name{{font-size:13px;font-weight:700;line-height:1.2}}
.item-desc{{font-size:9px;color:{t['text2']};margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.item-price{{font-size:17px;font-weight:900;color:{t['accent']};white-space:nowrap;flex-shrink:0}}
.star{{color:{t['accent']};font-size:8px;margin-left:3px;font-weight:400}}
.unavailable{{opacity:.35}}

.grid-items{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;padding:8px}}
.grid-card{{background:{t['item_bg']};border:1px solid {t['item_border']};border-radius:10px;overflow:hidden;text-align:center}}
.grid-card.featured{{border-color:{t['accent']}30;background:{t['featured_bg']}}}
.grid-card-img{{width:100%;height:100px;object-fit:cover}}
.grid-card-emoji{{width:100%;height:100px;background:{t['img_bg']};display:flex;align-items:center;justify-content:center;font-size:40px}}
.grid-card-info{{padding:8px}}
.grid-card-name{{font-size:12px;font-weight:700;line-height:1.2;margin-bottom:4px}}
.grid-card-price{{font-size:16px;font-weight:900;color:{t['accent']}}}

.promo-strip{{height:160px;flex-shrink:0;display:flex;gap:12px;padding:10px 28px;overflow:hidden;border-top:2px solid {t['accent']}15;background:{t['bg2']}}}
.promo-item{{flex-shrink:0;height:140px;border-radius:12px;overflow:hidden;border:1px solid {t['accent']}15;position:relative}}
.promo-item img{{height:100%;width:auto;max-width:250px;object-fit:cover;display:block}}
.promo-item video{{height:100%;width:auto;max-width:250px;object-fit:cover;display:block}}
.promo-scroll{{display:flex;gap:12px;animation:promoScroll linear infinite}}
@keyframes promoScroll{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}

.footer{{padding:6px 40px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;border-top:1px solid {t['accent']}10}}
.footer-text{{font-size:10px;color:{t['text2']}}}
.dots{{display:flex;gap:6px}}
.dot{{width:8px;height:8px;border-radius:50%;background:{t['text2']}40;transition:all .3s}}
.dot.active{{background:{t['accent']};width:20px;border-radius:4px}}
</style></head><body>
<div class="menu-container">
<div class="header">
<div class="restaurant-name">{restaurant}</div>"""
    
    if subtitle:
        html += f'<div class="subtitle">{subtitle}</div>'
    
    html += '</div><div class="slides-wrapper">'
    
    for si, slide_cats in enumerate(slides):
        active = ' active' if si == 0 else ''
        html += f'<div class="slide{active}" data-slide="{si}">'
        
        for cat in slide_cats:
            items = cat.get("items", [])
            html += '<div class="category"><div class="cat-header">'
            html += f'<div class="cat-title">{cat["name"]}</div>'
            if cat.get("description"):
                html += f'<div class="cat-desc">{cat["description"]}</div>'
            html += '</div><div class="cat-items">' if not is_grid else '</div><div class="grid-items">'
            
            for it in items:
                if is_grid:
                    # GRID CARD LAYOUT (McDonald's style)
                    cls = "grid-card"
                    if it.get("featured"): cls += " featured"
                    html += f'<div class="{cls}">'
                    if it.get("image"):
                        html += f'<img class="grid-card-img" src="{it["image"]}" alt="" loading="lazy">'
                    else:
                        emoji = get_food_emoji(it.get("name", ""))
                        html += f'<div class="grid-card-emoji">{emoji}</div>'
                    html += '<div class="grid-card-info">'
                    html += f'<div class="grid-card-name">{it["name"]}</div>'
                    html += f'<div class="grid-card-price">{currency_sym}{it.get("price", 0):.2f}</div>'
                    html += '</div></div>'
                else:
                    # LIST LAYOUT (original)
                    cls = "item"
                    if it.get("featured"): cls += " featured"
                    if not it.get("available", True): cls += " unavailable"
                    html += f'<div class="{cls}">'
                    if it.get("image"):
                        html += f'<img class="item-img" src="{it["image"]}" alt="" loading="lazy">'
                    else:
                        emoji = get_food_emoji(it.get("name", ""))
                        html += f'<div class="item-emoji">{emoji}</div>'
                    html += '<div class="item-info">'
                    html += f'<div class="item-name">{it["name"]}'
                    if it.get("featured"):
                        html += '<span class="star">★ ESPECIAL</span>'
                    html += '</div>'
                    if it.get("description"):
                        html += f'<div class="item-desc">{it["description"]}</div>'
                    html += f'</div><div class="item-price">{currency_sym}{it.get("price", 0):.2f}</div></div>'
            
            html += '</div></div>'
        
        html += '</div>'
    
    html += '</div>'
    
    # Promo media strip
    if promo_media:
        if len(promo_media) == 1:
            # Single media: show full width, no scroll
            pm = promo_media[0]
            src = pm.get("data") or pm.get("url", "")
            if src:
                html += '<div class="promo-strip" style="justify-content:center;padding:0">'
                if pm.get("type") == "video":
                    html += f'<video src="{src}" muted autoplay loop playsinline style="width:100%;height:100%;object-fit:cover"></video>'
                else:
                    html += f'<img src="{src}" style="width:100%;height:100%;object-fit:cover" alt="">'
                html += '</div>'
        else:
            # Multiple media: scrolling strip
            html += '<div class="promo-strip"><div class="promo-scroll" id="promo-scroll">'
            for _ in range(2):
                for pm in promo_media:
                    src = pm.get("data") or pm.get("url", "")
                    if not src:
                        continue
                    html += '<div class="promo-item">'
                    if pm.get("type") == "video":
                        html += f'<video src="{src}" muted autoplay loop playsinline></video>'
                    else:
                        html += f'<img src="{src}" alt="">'
                    html += '</div>'
            html += '</div></div>'
    
    # Footer
    html += '<div class="footer">'
    html += f'<div class="footer-text">{restaurant}</div>'
    if num_slides > 1:
        html += '<div class="dots">'
        for i in range(num_slides):
            active = ' active' if i == 0 else ''
            html += f'<div class="dot{active}" data-dot="{i}"></div>'
        html += '</div>'
    html += f'<div class="footer-text">MediAd View</div>'
    html += '</div></div>'
    
    # Slideshow JS + Promo scroll
    promo_count = len(promo_media)
    scroll_speed = max(promo_count * 8, 20)  # seconds for full scroll
    
    html += f"""<script>
var current=0,total={num_slides},duration={slide_duration}000;
function showSlide(n){{
  document.querySelectorAll('.slide').forEach(function(s){{s.classList.remove('active')}});
  document.querySelectorAll('.dot').forEach(function(d){{d.classList.remove('active')}});
  var slide=document.querySelector('[data-slide="'+n+'"]');
  var dot=document.querySelector('[data-dot="'+n+'"]');
  if(slide)slide.classList.add('active');
  if(dot)dot.classList.add('active');
}}
if(total>1){{setInterval(function(){{current=(current+1)%total;showSlide(current)}},duration)}}
// Promo scroll animation
var ps=document.getElementById('promo-scroll');
if(ps){{ps.style.animationDuration='{scroll_speed}s'}}
// Fallback: reload every 5 min (in case WebSocket dies). Also re-runs the hour-based filter.
setTimeout(function(){{location.reload()}},300000);
// -------- Live sync via WebSocket (Chat #2 real-time feature) --------
(function(){{
  var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var wsUrl = proto + '//' + location.host + '/api/ws/menu/{menu_id}';
  var ws, retry = 0, keepalive;
  function connect(){{
    try {{ ws = new WebSocket(wsUrl); }} catch(e){{ scheduleReconnect(); return; }}
    ws.onopen = function(){{ retry = 0;
      keepalive = setInterval(function(){{ try{{ ws.send('ping'); }}catch(e){{}} }}, 30000);
    }};
    ws.onmessage = function(ev){{
      try {{ var m = JSON.parse(ev.data); }} catch(e){{ return; }}
      if(m.type === 'menu' && (m.event === 'updated' || m.event === 'reload')){{
        // Immediate reload — instant price/menu change on TV
        location.reload();
      }}
    }};
    ws.onclose = function(){{ clearInterval(keepalive); scheduleReconnect(); }};
    ws.onerror = function(){{ try {{ ws.close(); }} catch(e){{}} }};
  }}
  function scheduleReconnect(){{
    retry = Math.min(retry+1, 6);
    var delay = Math.pow(2, retry) * 1000; // 2s..64s
    setTimeout(connect, delay);
  }}
  connect();
  // Also re-run the hour filter every full minute (client-side hint)
  var lastMin = new Date().getMinutes();
  setInterval(function(){{
    var m = new Date().getMinutes();
    if(m !== lastMin){{ lastMin = m; }}
  }}, 15000);
}})();
</script>"""
    
    html += '</body></html>'
    return HTMLResponse(content=html)



# ============ APP CONFIGURATION ============

# Serve web dashboard
WEB_DIR = str(ROOT_DIR / 'web')

@api_router.get("/dashboard")
async def serve_dashboard():
    return FileResponse(os.path.join(WEB_DIR, 'index.html'), media_type='text/html')

@api_router.get("/download")
async def serve_download():
    return FileResponse(os.path.join(WEB_DIR, 'download.html'), media_type='text/html')

@api_router.get("/player-activate")
async def serve_player_activate():
    return FileResponse(os.path.join(WEB_DIR, 'player-activate.html'), media_type='text/html')

@api_router.get("/screen")
async def serve_screen_public():
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

# Mount static assets under /api/ prefix for K8s ingress compatibility
app.mount("/api/web", StaticFiles(directory=WEB_DIR), name="web-static")

app.include_router(api_router)

# ============ FINANCE & ADMIN MODULE ============
from finance import create_finance_routes
from finance_email import create_finance_extensions
from finance_print import create_finance_print_routes
from finance_scheduler import start_scheduler
from colorlight_scheduler import start_colorlight_scheduler
from colorlight import create_colorlight_routes
from colorlight_player import create_player_routes
from realtime import ws_router, manager as ws_manager
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

# Sprint 1 · Etapa C2 — Admin Invoices (list / detail / PDF / reissue)
from admin_invoices_routes import build_admin_invoices_router
app.include_router(build_admin_invoices_router(db))

# ────────────────────────────────────────────────────────────────────────
# Observability: structured logs, Sentry, request-id middleware
# ────────────────────────────────────────────────────────────────────────
from observability import setup_logging, init_sentry, install_request_id_middleware
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
    build_deps as _build_auth_deps,
    build_auth_router as _build_auth_router,
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup():
    await seed_data()
    logger.info("MediaView Digital Signage API started")
    # SCHEDULER_MODE controls where cron jobs run:
    #   "apscheduler" (default): jobs live inside the web-api process
    #   "arq"                  : jobs live in the ARQ worker; web-api DOES NOT
    #                            schedule (avoids duplicate execution once the
    #                            worker is deployed to Render)
    #   "both"                 : useful only in dev, runs both (jobs are
    #                            idempotent by design)
    scheduler_mode = os.environ.get("SCHEDULER_MODE", "apscheduler").lower()
    run_apscheduler = scheduler_mode in ("apscheduler", "both")

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

@app.on_event("shutdown")
async def shutdown():
    client.close()
