# =====================================================
# MediaView Digital Signage Platform - Backend API
# =====================================================

from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
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
JWT_SECRET = os.environ.get('JWT_SECRET', 'mediaview-secure-jwt-secret-2026')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 48
MEDIA_DIR = os.environ.get('MEDIA_DIR', str(ROOT_DIR / 'media'))

Path(MEDIA_DIR).mkdir(parents=True, exist_ok=True)

# ============ DATABASE ============

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ============ APP SETUP ============

app = FastAPI(title="MediaView Digital Signage API", version="1.0.0")
api_router = APIRouter(prefix="/api")
security = HTTPBearer()

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

class ScreenUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[dict] = None
    pricing: Optional[dict] = None
    specs: Optional[dict] = None
    preview_image: Optional[str] = None
    status: Optional[str] = None

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
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
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
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
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
        tax = round(subtotal * 0.08, 2)
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
async def register(req: RegisterRequest):
    existing = await db.users.find_one({"email": req.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = {
        "id": gen_id(), "name": req.name, "email": req.email.lower(),
        "password_hash": hash_password(req.password), "role": "customer",
        "company_name": req.company_name, "phone": None,
        "language": "en", "active": True, "created_at": datetime.utcnow()
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
async def login(req: LoginRequest):
    user = await db.users.find_one({"email": req.email.lower()})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("active", True):
        raise HTTPException(status_code=401, detail="Account deactivated")
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

@api_router.post("/media/upload")
async def upload_media(data: MediaUpload, current_user: dict = Depends(get_current_user)):
    allowed = ["image/jpeg", "image/png", "image/jpg", "video/mp4"]
    if data.content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Allowed: {', '.join(allowed)}")
    try:
        file_bytes = base64.b64decode(data.data)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 data")
    file_ext = data.filename.rsplit(".", 1)[-1] if "." in data.filename else "bin"
    file_id = gen_id()
    stored_name = f"{file_id}.{file_ext}"
    file_path = os.path.join(MEDIA_DIR, stored_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    is_image = data.content_type.startswith("image/")
    media_doc = {
        "id": file_id, "user_id": current_user["id"],
        "filename": data.filename, "stored_filename": stored_name,
        "content_type": data.content_type, "size": len(file_bytes),
        "type": "image" if is_image else "video",
        "data": data.data if is_image else None,
        "created_at": datetime.utcnow()
    }
    await db.media.insert_one(media_doc)
    return {"id": file_id, "filename": data.filename,
            "content_type": data.content_type, "size": len(file_bytes),
            "type": media_doc["type"]}

@api_router.get("/media")
async def list_media(current_user: dict = Depends(get_current_user)):
    media = await db.media.find({"user_id": current_user["id"]}, {"data": 0}).sort("created_at", -1).to_list(100)
    return serialize_doc(media)

@api_router.get("/media/{media_id}")
async def get_media(media_id: str):
    media = await db.media.find_one({"id": media_id})
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return serialize_doc(media)

@api_router.get("/media/{media_id}/file")
async def get_media_file(media_id: str):
    media = await db.media.find_one({"id": media_id})
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    file_path = os.path.join(MEDIA_DIR, media.get("stored_filename", ""))
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    with open(file_path, "rb") as f:
        content = f.read()
    return Response(content=content, media_type=media.get("content_type", "application/octet-stream"))

@api_router.delete("/media/{media_id}")
async def delete_media(media_id: str, current_user: dict = Depends(get_current_user)):
    media = await db.media.find_one({"id": media_id, "user_id": current_user["id"]})
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    file_path = os.path.join(MEDIA_DIR, media.get("stored_filename", ""))
    if os.path.exists(file_path):
        os.remove(file_path)
    await db.media.delete_one({"id": media_id})
    return {"message": "Media deleted"}

# ============ ROUTES: PAYMENTS (MOCKED - Stripe-ready) ============

@api_router.post("/payments")
async def create_payment(data: PaymentCreate, current_user: dict = Depends(get_current_user)):
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

@api_router.post("/admin/screens")
async def admin_create_screen(data: ScreenCreate, admin: dict = Depends(require_admin)):
    screen = {
        "id": gen_id(), "name": data.name, "description": data.description,
        "location": data.location.dict(), "pricing": data.pricing.dict(),
        "specs": data.specs.dict(), "preview_image": data.preview_image,
        "status": data.status, "active": True,
        "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
    }
    await db.screens.insert_one(screen)
    return serialize_doc(screen)

@api_router.put("/admin/screens/{screen_id}")
async def admin_update_screen(screen_id: str, data: ScreenUpdate, admin: dict = Depends(require_admin)):
    screen = await db.screens.find_one({"id": screen_id})
    if not screen:
        raise HTTPException(status_code=404, detail="Screen not found")
    update = {k: v for k, v in data.dict(exclude_none=True).items()}
    update["updated_at"] = datetime.utcnow()
    await db.screens.update_one({"id": screen_id}, {"$set": update})
    updated = await db.screens.find_one({"id": screen_id})
    return serialize_doc(updated)

@api_router.delete("/admin/screens/{screen_id}")
async def admin_delete_screen(screen_id: str, admin: dict = Depends(require_admin)):
    active = await db.campaigns.count_documents(
        {"screen_id": screen_id, "status": {"$in": ["pending", "approved", "active"]}}
    )
    if active > 0:
        raise HTTPException(status_code=400, detail="Cannot delete screen with active campaigns")
    result = await db.screens.delete_one({"id": screen_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Screen not found")
    return {"message": "Screen deleted"}

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
        headers={"Content-Disposition": f"attachment; filename={media.get('filename', 'media')}",
                 "Cache-Control": "public, max-age=86400"}
    )

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
    admin_exists = await db.users.find_one({"email": "admin@mediaviewads.com"})
    if not admin_exists:
        admin = {
            "id": gen_id(), "name": "MediaView Admin",
            "email": "admin@mediaviewads.com",
            "password_hash": hash_password("MediaViewAdmin#2026"),
            "role": "admin", "company_name": "MediaView Inc.",
            "phone": None, "language": "en", "active": True,
            "created_at": datetime.utcnow()
        }
        await db.users.insert_one(admin)
        logger.info("Admin user created: admin@mediaviewads.com")

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

# ============ APP CONFIGURATION ============

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.on_event("shutdown")
async def shutdown():
    client.close()
