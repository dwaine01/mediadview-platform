# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""screens_routes.py -- screen CRUD (list/get/cities/price calc/QR),
admin screen management, and self-service (customer-owned) screens.

Fase 2B-3 of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md and
docs/AGENT_COORDINATION.md). Pure relocation of the 8 /screens/* + 5
/admin/screens* route handlers out of server.py: identical paths, methods,
decorators and logic, registered on a router with prefix="/api" so the
final routes match api_router exactly as before. No behavior change.

Scope, confirmed with Emergent before writing this: GET /admin/rbac/screens-
by-type stays in server.py (RBAC sub-resource, moves with admin_panel_routes.py
in 2B-6 instead). GET/POST /public/screens*, /customer/screens* (the
read-only public/marketplace views -- not to be confused with the
"self-service" write routes below, which DO move) and
GET /playlists/{playlist_id}/available-screens all stay too -- they belong
to the public/marketplace and playlist domains respectively.

Route-order note (same shadowing concern as 2B-1/2B-2): GET /screens/cities
MUST be registered before GET /screens/{screen_id}, or the parametric route
swallows "cities" as a screen_id. This file preserves the original relative
order of all 13 routes, so registration order at app.include_router() time
is unaffected.

Dependency note: gen_id and serialize_doc are threaded in as
create_screens_routes(...) factory parameters, same pattern as every prior
phase. Eight more names are threaded in for the same reason -- they are
used by code that is NOT moving (campaigns routes, device-pairing routes,
seed-data paths, and other domains entirely), so importing them back from
server.py would be circular:
  - CampaignSchedule (the request-body model calc_price's endpoint takes)
    and calculate_campaign_price (the pricing helper it calls) are also
    used directly by CampaignCreate/CampaignUpdate and by unmoved
    campaign routes.
  - _get_unique_public_screen_code, get_unique_location_code,
    gen_pairing_code and gen_pairing_secret (all used by
    admin_create_screen/regenerate_pairing/customer_create_screen to mint
    marketplace codes and pairing credentials) are also called from
    unmoved device-pairing routes and seed-data code.
  - gen_activation_code (used by admin_delete_screen's cascade path) is
    also called from unmoved device-activation routes.
  - _is_platform_admin (used by customer_list_my_screens) is the same
    widely-shared helper already threaded into create_menus_routes(...)
    in Fase 2B-1 -- same treatment here.
screen_orientation was NOT threaded in, despite Emergent's suggestion to
thread it defensively: grep-verified that none of its 7 call sites fall
inside these 13 routes (they're all in campaigns/marketplace/player code).
Adding it here would be dead weight; it should be threaded when whichever
later phase (campaigns or player) actually calls it needs to.

ScreenLocation, ScreenPricing, ScreenSpecs, ScreenCreate, ScreenUpdate,
ScreenAdvertisingUpdate and SelfServiceScreenUpdate were used ONLY by the
routes moving here (grep-verified against the whole file), so they moved
here verbatim, including the three small nested models ScreenCreate embeds.
"""
import logging
import os
from datetime import datetime
from typing import Optional

from geocoding import address_key, geocode_location
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from database import db
from deps import get_current_user, require_admin
from managed_portal_routes import create_audit_log as _audit
from rate_limit import LIMITS as _LIMITS
from rate_limit import limiter as _rl
from rbac import (
    ALL_OPERATION_TYPES,
    OperationType,
    assert_can_manage_screen,
    assert_permission,
    assert_tenant,
    effective_operation_type,
)

logger = logging.getLogger(__name__)


async def _located(db, location: dict) -> dict:
    """La dirección con su pin. Si no se puede ubicar, la pantalla se guarda igual."""
    if location.get("lat") is not None and location.get("lng") is not None:
        return location
    found = await geocode_location(db, location)
    if found:
        location = {**location, "lat": found["lat"], "lng": found["lng"],
                    "geocoded_from": address_key(location),
                    "geocoded_at": datetime.utcnow()}
    return location


class ScreenLocation(BaseModel):
    city: str
    address: str
    state: Optional[str] = None
    # El código postal es lo que convierte una dirección escrita a mano en un
    # pin exacto en el mapa: con él el buscador no confunde ciudades homónimas.
    postal_code: Optional[str] = None
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
    # ── FASE 1: operation type ────────────────────────────────────────────
    operation_type: Optional[str] = None   # SELF_SERVICE | PUBLIC_ADVERTISING | MEDIAVIEW_MANAGED
    organization_id: Optional[str] = None  # owning org (tenant isolation)
    # ── FASE 3: Public Advertising ────────────────────────────────────────
    max_ad_slots: int = 4                  # cuántos anunciantes simultáneos
    price_per_week: Optional[float] = None
    price_per_month: Optional[float] = None
    price_per_year: Optional[float] = None


class ScreenUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[dict] = None
    pricing: Optional[dict] = None
    specs: Optional[dict] = None
    preview_image: Optional[str] = None
    status: Optional[str] = None
    location_code: Optional[str] = None
    # ── FASE 1: operation type ────────────────────────────────────────────
    operation_type: Optional[str] = None
    organization_id: Optional[str] = None
    # ── FASE 3: Public Advertising ────────────────────────────────────────
    max_ad_slots: Optional[int] = None
    price_per_week: Optional[float] = None
    price_per_month: Optional[float] = None
    price_per_year: Optional[float] = None


class ScreenAdvertisingUpdate(BaseModel):
    price_per_ad_per_month: Optional[float] = None
    is_public: Optional[bool] = None
    photo_base64: Optional[str] = None   # data URL or raw base64
    # ── Ficha comercial que ve el anunciante antes de pagar ───────────────
    # El anunciante necesita saber DÓNDE va a aparecer su publicidad: en qué
    # negocio, cómo se llega y cuánta gente pasa. Sin esto la pantalla es un
    # nombre y un precio, y nadie compra a ciegas.
    establishment_name: Optional[str] = None   # «Supermercado La Colonia»
    location_reference: Optional[str] = None   # «Frente al parque central»
    audience_min: Optional[int] = None         # personas por día (desde)
    audience_max: Optional[int] = None         # personas por día (hasta)
    audience_note: Optional[str] = None        # «Mayor tráfico de 5 a 8 pm»
    # Horario del local: sin esto no se puede estimar cuánta gente ve el
    # anuncio en la franja que el anunciante elige.
    open_from: Optional[str] = None            # "07:00"
    open_to: Optional[str] = None              # "22:00"
    # Coordenadas para el mapa del anunciante (elige por zona, no por lista).
    lat: Optional[float] = None
    lng: Optional[float] = None


class SelfServiceScreenUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    specs: Optional[dict] = None


def create_screens_routes(gen_id, serialize_doc, CampaignSchedule, calculate_campaign_price,
                           _get_unique_public_screen_code, get_unique_location_code,
                           gen_pairing_code, gen_pairing_secret, gen_activation_code,
                           _is_platform_admin):
    router = APIRouter(prefix="/api", tags=["Screens"])

    @router.get("/screens")
    async def list_screens(city: Optional[str] = None, status: Optional[str] = "active"):
        query = {}
        if status:
            query["status"] = status
        if city:
            query["location.city"] = {"$regex": city, "$options": "i"}
        # PERF: the list view never renders advertising.photo_base64 (a ~100 KB
        # base64 blob per screen). Excluding it turns a 600 KB response into ~2 KB.
        # GET /screens/{id} still returns it for the screen editor.
        screens = await db.screens.find(query, {"advertising.photo_base64": 0}).to_list(100)
        return serialize_doc(screens)

    @router.get("/screens/cities")
    async def get_cities():
        cities = await db.screens.distinct("location.city", {"status": "active"})
        return sorted(cities)

    @router.get("/screens/{screen_id}")
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

    @router.post("/screens/{screen_id}/calculate-price")
    async def calc_price(screen_id: str, schedule: CampaignSchedule):
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        return calculate_campaign_price(screen.get("pricing", {}), schedule.dict())

    @router.put("/admin/screens/{screen_id}/advertising")
    async def update_screen_advertising(screen_id: str, payload: ScreenAdvertisingUpdate, admin=Depends(require_admin)):
        """Admin updates the public-advertising settings for a screen:
          - photo shown in the marketplace
          - price per ad per month
          - whether it appears in the public catalog at all"""
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        # ── FASE 1: tenant isolation + permission check ──────────────────────────
        assert_can_manage_screen(admin, screen)
        current = screen.get("advertising") or {}
        if payload.price_per_ad_per_month is not None:
            if payload.price_per_ad_per_month < 0:
                raise HTTPException(status_code=400, detail="Price cannot be negative")
            current["price_per_ad_per_month"] = float(payload.price_per_ad_per_month)
        if payload.is_public is not None:
            current["is_public"] = bool(payload.is_public)
        if payload.photo_base64 is not None:
            # accept both data URLs and raw base64
            current["photo_base64"] = payload.photo_base64
        for field in ("establishment_name", "location_reference", "audience_note"):
            value = getattr(payload, field)
            if value is not None:
                current[field] = str(value).strip()[:160] or None
        for field in ("audience_min", "audience_max"):
            value = getattr(payload, field)
            if value is not None:
                if value < 0:
                    raise HTTPException(400, "La audiencia no puede ser negativa")
                current[field] = int(value)
        low, high = current.get("audience_min"), current.get("audience_max")
        if low is not None and high is not None and low > high:
            raise HTTPException(400, "La audiencia mínima no puede ser mayor que la máxima")
        for field in ("open_from", "open_to"):
            value = getattr(payload, field)
            if value is None:
                continue
            text = str(value).strip()
            parts = text.split(":")
            if (len(parts) != 2 or not all(p.isdigit() for p in parts)
                    or not 0 <= int(parts[0]) <= 23 or not 0 <= int(parts[1]) <= 59):
                raise HTTPException(400, "El horario va en formato HH:MM (ej. 07:00)")
            current[field] = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        update = {"advertising": current, "updated_at": datetime.utcnow()}
        # Las coordenadas son de la ubicación, no de la configuración publicitaria:
        # el mapa del anunciante y el resto del sistema leen `location`.
        if payload.lat is not None:
            if not -90 <= payload.lat <= 90:
                raise HTTPException(400, "Latitud fuera de rango")
            update["location.lat"] = float(payload.lat)
        if payload.lng is not None:
            if not -180 <= payload.lng <= 180:
                raise HTTPException(400, "Longitud fuera de rango")
            update["location.lng"] = float(payload.lng)
        await db.screens.update_one({"id": screen_id}, {"$set": update})
        return {"screen_id": screen_id, "advertising": current}

    @router.post("/admin/screens/geocode-missing")
    async def geocode_missing_screens(limit: int = 25, admin: dict = Depends(require_admin)):
        """Ubica en el mapa las pantallas que ya estaban cargadas sin coordenadas.

        Las pantallas creadas antes de que el sistema buscara el pin solo se
        quedaron fuera del mapa del anunciante. Esto las ubica desde su
        dirección, de a tandas, porque el buscador admite una consulta por
        segundo y una tanda grande dejaría la pantalla del panel colgada."""
        screens = await db.screens.find({
            "status": "active",
            "$or": [{"location.lat": None}, {"location.lat": {"$exists": False}}],
        }).to_list(max(1, min(int(limit), 40)))

        located, failed, no_address = 0, [], 0
        for screen in screens:
            location = screen.get("location") or {}
            if not address_key(location):
                no_address += 1
                continue
            found = await geocode_location(db, location)
            if not found:
                failed.append(screen.get("name"))
                continue
            await db.screens.update_one({"id": screen["id"]}, {"$set": {
                "location.lat": found["lat"], "location.lng": found["lng"],
                "location.geocoded_from": address_key(location),
                "location.geocoded_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }})
            located += 1
        remaining = await db.screens.count_documents({
            "status": "active",
            "$or": [{"location.lat": None}, {"location.lat": {"$exists": False}}],
        })
        return {"reviewed": len(screens), "located": located,
                "without_address": no_address, "not_found": failed[:10],
                "remaining": remaining}

    @router.get("/screens/{screen_id}/venue-photo")
    async def screen_venue_photo(screen_id: str, response: Response):
        """La foto real de la pantalla instalada en el local.

        Se sirve como imagen y no dentro del JSON: el base64 pesa cientos de
        kilobytes y el catálogo muestra varias pantallas a la vez."""
        import base64 as _b64

        screen = await db.screens.find_one({"id": screen_id},
                                           {"_id": 0, "advertising.photo_base64": 1})
        raw = ((screen or {}).get("advertising") or {}).get("photo_base64")
        if not raw:
            raise HTTPException(404, "Esta pantalla todavía no tiene foto")
        media_type = "image/jpeg"
        if raw.startswith("data:"):
            header, _, raw = raw.partition(",")
            media_type = header[5:].split(";")[0] or media_type
        try:
            data = _b64.b64decode(raw + "=" * (-len(raw) % 4))
        except Exception:
            raise HTTPException(404, "La foto de esta pantalla está dañada")
        return Response(content=data, media_type=media_type,
                        headers={"Cache-Control": "public, max-age=3600"})

    @router.post("/admin/screens")
    async def admin_create_screen(data: ScreenCreate, admin: dict = Depends(require_admin)):
        # ── FASE 1: Validate operation_type and permissions ──────────────────
        op_type = (data.operation_type or OperationType.SELF_SERVICE).upper()
        if op_type not in ALL_OPERATION_TYPES:
            raise HTTPException(400, f"Invalid operation_type. Must be one of: {ALL_OPERATION_TYPES}")

        # Enforce permissions: only SUPER_ADMIN/MEDIAVIEW_ADMIN can create PUBLIC or MANAGED
        if op_type == OperationType.PUBLIC_ADVERTISING:
            assert_permission(admin, "screen.create.public")
        elif op_type == OperationType.MEDIAVIEW_MANAGED:
            assert_permission(admin, "screen.create.managed")
        else:
            assert_permission(admin, "screen.create.self_service")

        # Auto-generate permanent location code
        location_code = await get_unique_location_code()
        # Generate the device pairing credentials (ColorlightCloud style)
        pairing_code = gen_pairing_code()
        # Ensure uniqueness
        while await db.screens.find_one({"pairing_code": pairing_code}):
            pairing_code = gen_pairing_code()
        pairing_secret = gen_pairing_secret()

        # ── FASE 3: Public Advertising fields ────────────────────────────────
        public_screen_code = None
        advertising_pricing = {}
        max_ad_slots = data.max_ad_slots or 4

        if op_type == OperationType.PUBLIC_ADVERTISING:
            public_screen_code = await _get_unique_public_screen_code()
            if data.price_per_week is not None:
                advertising_pricing["price_per_week"] = float(data.price_per_week)
            if data.price_per_month is not None:
                advertising_pricing["price_per_month"] = float(data.price_per_month)
            if data.price_per_year is not None:
                advertising_pricing["price_per_year"] = float(data.price_per_year)

        screen = {
            "id": gen_id(), "name": data.name, "description": data.description,
            "location": await _located(db, data.location.dict()), "pricing": data.pricing.dict(),
            "specs": data.specs.dict(), "preview_image": data.preview_image,
            "status": data.status, "location_code": location_code,
            "pairing_code": pairing_code, "pairing_secret": pairing_secret,
            "paired_device_id": None, "paired_at": None,
            "active": True,
            # ── FASE 1 fields ─────────────────────────────────────────────────
            "operation_type": op_type,
            "organization_id": data.organization_id or None,
            "created_by": admin.get("id") or admin.get("_id"),
            # ── FASE 3 fields ─────────────────────────────────────────────────
            "public_screen_code": public_screen_code,
            "max_ad_slots": max_ad_slots,
            "advertising_pricing": advertising_pricing,
            "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
        }
        await db.screens.insert_one(screen)
        # ── Fase 4: Audit log ─────────────────────────────────────────────────────
        await _audit(
            db, action="screen.created",
            user_id=admin.get("id"), user_email=admin.get("email"),
            resource_type="screen", resource_id=screen["id"],
            org_id=screen.get("organization_id"),
            details={"name": screen["name"], "operation_type": op_type},
        )
        return serialize_doc(screen)

    @router.post("/admin/screens/{screen_id}/regenerate-pairing")
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

    @router.get("/screens/{screen_id}/qr")
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

    @router.put("/admin/screens/{screen_id}")
    async def admin_update_screen(screen_id: str, data: ScreenUpdate, admin: dict = Depends(require_admin)):
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        # ── FASE 1: tenant isolation + permission check ──────────────────────
        assert_can_manage_screen(admin, screen)

        update = {k: v for k, v in data.dict(exclude_none=True).items()}
        # location_code is permanent - cannot be changed
        update.pop("location_code", None)
        # Si cambió la dirección, el pin del mapa se vuelve a buscar solo: una
        # pantalla que se mudó y sigue marcada en la esquina vieja es peor que
        # una sin pin.
        if "location" in update:
            new_location = dict(update["location"])
            previous = screen.get("location") or {}
            same_address = address_key(new_location) == address_key(previous)
            manual = (new_location.get("lat") is not None
                      and (new_location.get("lat"), new_location.get("lng"))
                      != (previous.get("lat"), previous.get("lng")))
            if same_address and new_location.get("lat") is None:
                new_location["lat"], new_location["lng"] = previous.get("lat"), previous.get("lng")
            elif not manual:
                new_location.pop("lat", None)
                new_location.pop("lng", None)
                new_location = await _located(db, new_location)
            update["location"] = new_location
        # If operation_type is being changed, validate it
        if "operation_type" in update:
            new_op = update["operation_type"].upper()
            if new_op not in ALL_OPERATION_TYPES:
                raise HTTPException(400, f"Invalid operation_type. Must be one of: {ALL_OPERATION_TYPES}")
            update["operation_type"] = new_op
        update["updated_at"] = datetime.utcnow()
        await db.screens.update_one({"id": screen_id}, {"$set": update})
        updated = await db.screens.find_one({"id": screen_id})
        return serialize_doc(updated)

    @router.delete("/admin/screens/{screen_id}")
    async def admin_delete_screen(screen_id: str, cascade: bool = False, admin: dict = Depends(require_admin)):
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        # ── FASE 1: tenant isolation + permission check ──────────────────────────
        assert_can_manage_screen(admin, screen)
        active = await db.campaigns.count_documents(
            {"screen_id": screen_id, "status": {"$in": ["pending", "approved", "active"]}}
        )
        if active > 0 and not cascade:
            raise HTTPException(status_code=400, detail=f"Cannot delete screen with {active} active campaign(s). Use cascade=true to force.")
        # Cascade: clean up related data
        if cascade:
            await db.campaigns.delete_many({"screen_id": screen_id})

        # Always reset any device pointing to this screen so the player app
        # goes back to the pairing screen (fresh activation_code) instead of
        # being stuck on a black WebView loading a deleted screen.
        orphans = await db.devices.find({"screen_id": screen_id}).to_list(100)
        for d in orphans:
            new_code = gen_activation_code()
            while await db.devices.find_one({"activation_code": new_code, "status": "pending"}):
                new_code = gen_activation_code()
            await db.devices.update_one(
                {"id": d["id"]},
                {"$set": {
                    "screen_id": None,
                    "status": "pending",
                    "activation_code": new_code,
                    "activated_at": None,
                }}
            )
            logger.info(f"Device {d['id']} unpaired (screen {screen_id} deleted). New code: {new_code}")

        result = await db.screens.delete_one({"id": screen_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Screen not found")
        return {"message": "Screen deleted", "cascaded_campaigns": active if cascade else 0, "devices_unpaired": len(orphans)}

    @router.post("/screens/self-service")
    async def customer_create_screen(data: ScreenCreate, current_user: dict = Depends(get_current_user)):
        """
        Allows a SELF_SERVICE_OWNER to add a screen within their own organization.
        Only SELF_SERVICE type is permitted here — no PUBLIC or MANAGED.
        """
        assert_permission(current_user, "screen.create.self_service")
        # Force SELF_SERVICE — customers cannot create PUBLIC or MANAGED
        op_type = OperationType.SELF_SERVICE
        user_org = current_user.get("organization_id")
        pairing_code = gen_pairing_code()
        while await db.screens.find_one({"pairing_code": pairing_code}):
            pairing_code = gen_pairing_code()
        location_code = await get_unique_location_code()
        screen = {
            "id": gen_id(), "name": data.name, "description": data.description,
            "location": await _located(db, data.location.dict()), "pricing": data.pricing.dict(),
            "specs": data.specs.dict(), "preview_image": data.preview_image,
            "status": "active", "location_code": location_code,
            "pairing_code": pairing_code, "pairing_secret": gen_pairing_secret(),
            "paired_device_id": None, "paired_at": None,
            "active": True,
            "operation_type": op_type,
            # ── FASE 1: always use the user's own org — ignore any organization_id
            # that the client may have sent in the request body.
            "organization_id": user_org,
            "created_by": current_user.get("id"),
            "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()
        }
        await db.screens.insert_one(screen)
        return serialize_doc(screen)

    @router.put("/screens/self-service/{screen_id}")
    async def customer_update_screen(
        screen_id: str,
        data: SelfServiceScreenUpdate,
        current_user: dict = Depends(get_current_user),
    ):
        """
        Allows SELF_SERVICE_OWNER / SELF_SERVICE_MANAGER to update a screen
        that belongs to their own organization.

        Tenant isolation is enforced server-side:
          - organization_id is validated against the authenticated user's org.
          - Cross-org modification raises HTTP 403.
          - Only SELF_SERVICE screens can be modified via this endpoint.
        """
        assert_permission(current_user, "screen.configure")
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        # ── Tenant isolation: user can only touch screens in their own org ───────
        assert_tenant(current_user, screen.get("organization_id"))
        # ── Operation-type guard: cannot modify PUBLIC or MANAGED screens here ───
        if effective_operation_type(screen) != OperationType.SELF_SERVICE:
            raise HTTPException(
                status_code=403,
                detail="This screen is managed by MediaView and cannot be modified via self-service."
            )
        update = {k: v for k, v in data.dict(exclude_none=True).items()}
        if not update:
            raise HTTPException(status_code=400, detail="No fields to update")
        update["updated_at"] = datetime.utcnow()
        await db.screens.update_one({"id": screen_id}, {"$set": update})
        updated = await db.screens.find_one({"id": screen_id})
        return serialize_doc(updated)

    @router.get("/screens/self-service/mine")
    async def customer_list_my_screens(current_user: dict = Depends(get_current_user)):
        """
        Returns only the SELF_SERVICE screens that belong to the authenticated user's
        organization. Platform admins see ALL screens.
        """
        if _is_platform_admin(current_user):
            screens = await db.screens.find({"operation_type": OperationType.SELF_SERVICE}).to_list(500)
        else:
            assert_permission(current_user, "screen.view")
            user_org = current_user.get("organization_id")
            query: dict = {"operation_type": OperationType.SELF_SERVICE}
            if user_org:
                query["organization_id"] = user_org
            else:
                # No org assigned yet — return only screens created by this user
                query["created_by"] = current_user.get("id")
            screens = await db.screens.find(query).to_list(500)
        return serialize_doc(screens)

    return router
