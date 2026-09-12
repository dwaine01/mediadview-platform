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
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

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

# RegisterRequest, LoginRequest, ProfileUpdate moved to
# auth_routes.py (Fase 2B-11).








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





# PaymentCreate moved to payments_routes.py (Fase 2B-10a).

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
    # Try the winner first, then the runners-up. A playlist can win the
    # priority tie-break and still render nothing (a deleted menu, media that
    # vanished), and leaving the screen black in that case is worse than
    # falling through to the next contender.
    remaining = list(playlists)
    while remaining:
        winner = select_winning_playlist(remaining)
        if not winner:
            return []
        rendered = await _render_playlist_items(winner)
        if rendered:
            return rendered
        logger.warning("Playlist %s renders nothing for screen %s, falling through",
                       winner.get("id"), screen_id)
        remaining = [p for p in remaining if p.get("id") != winner.get("id")]
    return []


async def _render_playlist_items(winner: dict) -> list:
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
                {"_id": 0, "name": 1, "updated_at": 1, "canvas.updated_at": 1}
            )
            if not menu:
                continue
            # A menu lives behind a URL, so editing a price changes NOTHING in
            # this JSON — and the player only reloads when the playlist
            # signature (media_id:checksum:duration:rotation:display_mode)
            # changes. Stamping the menu's last edit into `checksum` (a real
            # 64-hex sha256, which is what the player accepts) is what makes
            # «cambié el precio y no aparece en la tele» actually appear. The
            # query param does the same for the WebView's own HTTP cache.
            stamps = [s for s in (menu.get("updated_at"),
                                  (menu.get("canvas") or {}).get("updated_at")) if s]
            edited_at = max(stamps) if stamps else None
            url = f"/api/menus/{ref_id}/render"
            if edited_at:
                url += f"?v={int(edited_at.timestamp() * 1000)}"
            rendered.append({
                **base, "media_id": f"menu:{ref_id}", "filename": menu.get("name", "Menu"),
                "content_type": "widget", "media_url": url, "download_url": url,
                "checksum": hashlib.sha256(
                    f"menu:{ref_id}:{edited_at.isoformat() if edited_at else ''}".encode()
                ).hexdigest(),
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

# verify_password moved to auth_routes.py (Fase 2B-11).

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

# register, login, get_me, update_profile moved to
# auth_routes.py (Fase 2B-11).




# ============ ROUTES: SCREENS (PUBLIC) ============





# ============ PUBLIC / TRANSIENT CUSTOMER FLOW ============
# Discount scale for month-based advertising commitments (public buyers).
# Applied on top of (num_ads × months × price_per_ad_per_month).
# PUBLIC_DISCOUNT_SCALE, _customer_screen_view, _apply_discount,
# QuoteItem/QuoteRequest, CartItem/CustomerOrderSubmit and all 6
# /customer/* routes moved to customer_routes.py (Fase 2B-9).















# ============ CUSTOMER ORDER SUBMISSION (Phase C.6) ============
# The transient customer signs up, browses the catalog, builds a cart,
# uploads a creative, and submits an order. Until Stripe LIVE is enabled
# (currently ENVIRONMENT=staging), payment is coordinated manually by the
# admin who is notified through the new customer-orders panel.









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

# create_payment, list_payments, get_payment moved to
# payments_routes.py (Fase 2B-10a).



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

# _safe_iframe, _safe_css_color, _safe_js_str, _safe_yt_id,
# _weather_cache, _WEATHER_CACHE_TTL_S, render_widget and
# widget_weather_proxy moved to widgets_routes.py (Fase 2B-10b).
# _esc stays here (threaded into create_menus_routes too).








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

# CertificationResult moved to certification_routes.py (Fase 2B-10c).

# submit_certification, get_certification_results moved to
# certification_routes.py (Fase 2B-10c).



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
from menu_canvas_routes import create_menu_canvas_routes
from menus_routes import create_menus_routes
from media_routes import create_media_routes
from screens_routes import create_screens_routes
from playlists_routes import create_playlists_routes
from player_routes import create_player_domain_routes
from admin_devices_routes import create_admin_devices_routes
from admin_campaigns_routes import create_admin_campaigns_routes
from superadmin_routes import create_superadmin_routes
from campaigns_routes import create_campaigns_routes
from public_api_routes import create_public_api_routes
from customer_routes import create_customer_routes
from payments_routes import create_payments_routes
from widgets_routes import create_widgets_routes
from certification_routes import create_certification_routes
from auth_routes import create_auth_routes
from promo_routes import create_promo_routes
from workspace_reports_routes import create_workspace_reports_routes
app.include_router(create_plans_routes(db, get_current_user, require_admin))
app.include_router(create_workspace_team_routes(db, get_current_user))
app.include_router(create_menu_ai_routes(db, get_current_user, bump_playlist_version))
app.include_router(create_menu_canvas_routes(db, get_current_user, bump_playlist_version))
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
# -- Fase 2C-1: /public/* client API -- the 8 unauthenticated routes
# (see docs/REFACTOR_FASE2_PLAN.md and docs/AGENT_COORDINATION.md) left
# pending since Fase 2B-4 --
app.include_router(create_public_api_routes(
    upload_media, serialize_doc, WEB_DIR, _bump_playlist_screens,
))
# -- Fase 2B-9: authenticated /customer/* transient-buyer flow (see
# docs/REFACTOR_FASE2_PLAN.md) --
app.include_router(create_customer_routes(gen_id))
# -- Fase 2B-10: /payments*, /widgets/*/render|weather, /certification/*
# (see docs/REFACTOR_FASE2_PLAN.md) --
app.include_router(create_payments_routes(gen_id, gen_invoice, serialize_doc))
app.include_router(create_widgets_routes(_esc))
app.include_router(create_certification_routes(gen_id, serialize_doc))
# -- Fase 2B-11: legacy v1 /auth/* (see docs/REFACTOR_FASE2_PLAN.md) --
# closes out Fase 2B: no business-logic route left in server.py --
app.include_router(create_auth_routes(gen_id, hash_password, create_token, serialize_doc))
app.include_router(create_promo_routes(db, get_current_user, bump_playlist_version))
app.include_router(create_workspace_reports_routes(db, get_current_user))
app.include_router(create_workspace_routes(db, get_current_user, require_admin, bump_playlist_version,
                                             build_screen_playlist_items, gen_activation_code))
app.include_router(create_signup_routes(db, create_token))

# ── Fase 3: Campaign Scheduler monitoring endpoints ───────────────────────────




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
