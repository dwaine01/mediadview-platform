# ruff: noqa: E501,E701,E702,E731
"""
advertising_routes.py — MediaView Fase 3: Marketplace de Publicidad Pública
────────────────────────────────────────────────────────────────────────────
Endpoints para:
  • Landing pública por código de pantalla (/api/advertise/{screen_code})
  • Marketplace de pantallas PUBLIC_ADVERTISING
  • Ciclo de vida de campañas publicitarias:
      DRAFT → PENDING_REVIEW → APPROVED → ACTIVE → EXPIRED
  • Centro de Aprobación MediaView Admin
  • Proof of Play (registro de reproducción)
  • Lista de espera cuando max_ad_slots está lleno
"""
import secrets
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from rbac import Role, assert_permission, get_effective_role

# ── State Machine ─────────────────────────────────────────────────────────────
AD_STATUS_DRAFT = "DRAFT"
AD_STATUS_PENDING_REVIEW = "PENDING_REVIEW"
AD_STATUS_APPROVED = "APPROVED"
AD_STATUS_ACTIVE = "ACTIVE"
AD_STATUS_REJECTED = "REJECTED"
AD_STATUS_CANCELLED = "CANCELLED"
AD_STATUS_EXPIRED = "EXPIRED"

AD_PLAYABLE_STATUSES = {AD_STATUS_APPROVED, AD_STATUS_ACTIVE}
PERIOD_DAYS = {"weekly": 7, "monthly": 30, "yearly": 365}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _gen_id() -> str:
    return str(uuid.uuid4())

def _ser(doc):
    if isinstance(doc, list):
        return [_ser(d) for d in doc]
    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            if k == "_id":
                continue
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            elif isinstance(v, (dict, list)):
                out[k] = _ser(v)
            else:
                out[k] = v
        return out
    return doc

def _gen_ad_screen_code() -> str:
    """Genera un código único para pantallas PUBLIC_ADVERTISING: MV-ADV-XXXX"""
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    part = ''.join(secrets.choice(chars) for _ in range(6))
    return f"MV-ADV-{part}"

def _calc_end_date(start_date: str, period: str, duration: int) -> str:
    """Calcula la fecha de fin según el período y duración."""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        days = PERIOD_DAYS.get(period, 30) * duration
        end = start + timedelta(days=days - 1)
        return end.strftime("%Y-%m-%d")
    except Exception:
        return start_date

def _get_period_price(screen: dict, period: str) -> Optional[float]:
    """Obtiene el precio de la pantalla para el período dado."""
    ap = screen.get("advertising_pricing") or {}
    if period == "weekly":
        return ap.get("price_per_week")
    elif period == "monthly":
        return ap.get("price_per_month")
    elif period == "yearly":
        return ap.get("price_per_year")
    return None

def _calc_status_from_dates(start_date: Optional[str], end_date: Optional[str]) -> str:
    """Determina si una campaña APPROVED debe pasar a ACTIVE o a EXPIRED."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if end_date and end_date < today:
        return AD_STATUS_EXPIRED
    if start_date and start_date > today:
        return AD_STATUS_APPROVED  # still in the future
    return AD_STATUS_ACTIVE  # starts today or already started


# ── Pydantic Models ────────────────────────────────────────────────────────────

class AdCampaignCreate(BaseModel):
    name: str
    screen_ids: List[str]
    creative_url: str            # URL al material publicitario (video/imagen)
    pricing_period: str          # "weekly" | "monthly" | "yearly"
    duration: int = 1            # número de períodos
    start_date: Optional[str] = None  # YYYY-MM-DD, por defecto hoy
    slot_duration_seconds: int = 30
    notes: Optional[str] = None

class AdCampaignCheckout(BaseModel):
    screen_ids: List[str]
    pricing_period: str
    duration: int = 1
    start_date: Optional[str] = None

class AdCampaignReject(BaseModel):
    reason: str

class WaitlistJoin(BaseModel):
    screen_id: str
    notes: Optional[str] = None

class ProofOfPlayCreate(BaseModel):
    screen_id: str
    campaign_id: str
    played_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    creative_url: Optional[str] = None


# ── Factory ────────────────────────────────────────────────────────────────────

def create_advertising_routes(db, get_current_user, require_admin):
    router = APIRouter(prefix="/api")

    # ── Pantallas Públicas (sin auth) ─────────────────────────────────────────

    @router.get("/advertise/{screen_code}")
    async def public_landing_info(screen_code: str):
        """Información comercial de una pantalla pública para la landing del QR.
        No expone datos técnicos ni precios internos."""
        screen = await db.screens.find_one({
            "public_screen_code": {"$regex": f"^{screen_code}$", "$options": "i"},
            "operation_type": "PUBLIC_ADVERTISING",
            "status": "active",
        })
        if not screen:
            raise HTTPException(status_code=404, detail="Pantalla no encontrada o no disponible para publicidad")

        # Contar slots ocupados actualmente
        occupied = await db.ad_campaigns.count_documents({
            "selected_screens": screen["id"],
            "status": {"$in": [AD_STATUS_PENDING_REVIEW, AD_STATUS_APPROVED, AD_STATUS_ACTIVE]},
        })
        max_slots = screen.get("max_ad_slots", 4)
        ap = screen.get("advertising_pricing") or {}

        return {
            "id": screen["id"],
            "name": screen.get("name"),
            "description": screen.get("description"),
            "location": screen.get("location"),
            "specs": screen.get("specs"),
            "public_screen_code": screen.get("public_screen_code"),
            "max_ad_slots": max_slots,
            "available_slots": max(0, max_slots - occupied),
            "occupied_slots": occupied,
            "is_full": occupied >= max_slots,
            "pricing": {
                "price_per_week": ap.get("price_per_week"),
                "price_per_month": ap.get("price_per_month"),
                "price_per_year": ap.get("price_per_year"),
                "currency": "USD",
            },
        }

    # ── Marketplace (requiere auth) ───────────────────────────────────────────

    @router.get("/marketplace/screens")
    async def list_marketplace_screens(
        city: Optional[str] = None,
        current_user: dict = Depends(get_current_user),
    ):
        """Lista todas las pantallas PUBLIC_ADVERTISING disponibles con capacidad y precios."""
        query = {"operation_type": "PUBLIC_ADVERTISING", "status": "active"}
        if city:
            query["location.city"] = {"$regex": city, "$options": "i"}
        screens = await db.screens.find(query).to_list(200)
        result = []
        for s in screens:
            occupied = await db.ad_campaigns.count_documents({
                "selected_screens": s["id"],
                "status": {"$in": [AD_STATUS_PENDING_REVIEW, AD_STATUS_APPROVED, AD_STATUS_ACTIVE]},
            })
            max_slots = s.get("max_ad_slots", 4)
            ap = s.get("advertising_pricing") or {}
            result.append({
                "id": s["id"],
                "name": s.get("name"),
                "description": s.get("description"),
                "location": s.get("location"),
                "specs": s.get("specs"),
                "public_screen_code": s.get("public_screen_code"),
                "max_ad_slots": max_slots,
                "available_slots": max(0, max_slots - occupied),
                "occupied_slots": occupied,
                "is_full": occupied >= max_slots,
                "pricing": {
                    "price_per_week": ap.get("price_per_week"),
                    "price_per_month": ap.get("price_per_month"),
                    "price_per_year": ap.get("price_per_year"),
                    "currency": "USD",
                },
            })
        return result

    @router.get("/marketplace/cities")
    async def marketplace_cities(current_user: dict = Depends(get_current_user)):
        """Lista de ciudades con pantallas PUBLIC_ADVERTISING activas."""
        cities = await db.screens.distinct(
            "location.city",
            {"operation_type": "PUBLIC_ADVERTISING", "status": "active"},
        )
        return sorted(cities)

    # ── Checkout / Cotización (backend-only pricing) ─────────────────────────

    @router.post("/ad-campaigns/checkout")
    async def checkout_ad_campaign(
        payload: AdCampaignCheckout,
        current_user: dict = Depends(get_current_user),
    ):
        """Calcula el precio total de forma SEGURA en el backend.
        NUNCA confiar en totales del frontend."""
        assert_permission(current_user, "advertising.purchase",
                          "Solo anunciantes y administradores pueden cotizar campañas publicitarias")

        if payload.pricing_period not in PERIOD_DAYS:
            raise HTTPException(400, "pricing_period debe ser: weekly, monthly, yearly")
        if payload.duration < 1 or payload.duration > 24:
            raise HTTPException(400, "duration debe ser entre 1 y 24")
        if not payload.screen_ids:
            raise HTTPException(400, "Debe seleccionar al menos una pantalla")

        start_date = payload.start_date or datetime.utcnow().strftime("%Y-%m-%d")
        end_date = _calc_end_date(start_date, payload.pricing_period, payload.duration)

        lines = []
        grand_total = 0.0

        for sid in payload.screen_ids:
            screen = await db.screens.find_one({"id": sid})
            if not screen:
                raise HTTPException(404, f"Pantalla {sid} no encontrada")
            if screen.get("operation_type") != "PUBLIC_ADVERTISING":
                raise HTTPException(400, f"La pantalla {screen.get('name')} no es de tipo PUBLIC_ADVERTISING")
            if screen.get("status") != "active":
                raise HTTPException(400, f"La pantalla {screen.get('name')} no está activa")

            unit_price = _get_period_price(screen, payload.pricing_period)
            if unit_price is None or unit_price <= 0:
                raise HTTPException(400, f"La pantalla '{screen.get('name')}' no tiene precio configurado para el período '{payload.pricing_period}'")

            line_total = round(unit_price * payload.duration, 2)
            grand_total += line_total

            # Disponibilidad
            occupied = await db.ad_campaigns.count_documents({
                "selected_screens": sid,
                "status": {"$in": [AD_STATUS_PENDING_REVIEW, AD_STATUS_APPROVED, AD_STATUS_ACTIVE]},
            })
            max_slots = screen.get("max_ad_slots", 4)

            lines.append({
                "screen_id": sid,
                "screen_name": screen.get("name"),
                "screen_city": screen.get("location", {}).get("city", ""),
                "unit_price": unit_price,
                "pricing_period": payload.pricing_period,
                "duration": payload.duration,
                "line_total": line_total,
                "available_slots": max(0, max_slots - occupied),
                "is_full": occupied >= max_slots,
            })

        return {
            "lines": lines,
            "grand_total": round(grand_total, 2),
            "currency": "USD",
            "pricing_period": payload.pricing_period,
            "duration": payload.duration,
            "start_date": start_date,
            "end_date": end_date,
        }

    # ── Crear Campaña Publicitaria ────────────────────────────────────────────

    @router.post("/ad-campaigns")
    async def create_ad_campaign(
        data: AdCampaignCreate,
        current_user: dict = Depends(get_current_user),
    ):
        """Crea una nueva campaña publicitaria en estado DRAFT.
        Verifica capacidad y calcula el precio en el backend."""
        assert_permission(current_user, "advertising.purchase",
                          "Solo anunciantes pueden crear campañas publicitarias")

        if data.pricing_period not in PERIOD_DAYS:
            raise HTTPException(400, "pricing_period debe ser: weekly, monthly, yearly")
        if data.duration < 1 or data.duration > 24:
            raise HTTPException(400, "duration debe ser entre 1 y 24")
        if not data.screen_ids:
            raise HTTPException(400, "Debe seleccionar al menos una pantalla")
        if not data.creative_url or not data.creative_url.startswith("http"):
            raise HTTPException(400, "creative_url debe ser una URL válida")

        start_date = data.start_date or datetime.utcnow().strftime("%Y-%m-%d")
        end_date = _calc_end_date(start_date, data.pricing_period, data.duration)

        lines = []
        grand_total = 0.0
        full_screens = []  # pantallas a capacidad máxima

        for sid in data.screen_ids:
            screen = await db.screens.find_one({"id": sid})
            if not screen:
                raise HTTPException(404, f"Pantalla {sid} no encontrada")
            if screen.get("operation_type") != "PUBLIC_ADVERTISING":
                raise HTTPException(400, f"La pantalla '{screen.get('name')}' no es de tipo PUBLIC_ADVERTISING")

            unit_price = _get_period_price(screen, data.pricing_period)
            if unit_price is None or unit_price <= 0:
                raise HTTPException(400, f"La pantalla '{screen.get('name')}' no tiene precio para '{data.pricing_period}'")

            line_total = round(unit_price * data.duration, 2)
            grand_total += line_total

            occupied = await db.ad_campaigns.count_documents({
                "selected_screens": sid,
                "status": {"$in": [AD_STATUS_PENDING_REVIEW, AD_STATUS_APPROVED, AD_STATUS_ACTIVE]},
            })
            max_slots = screen.get("max_ad_slots", 4)
            if occupied >= max_slots:
                full_screens.append(screen.get("name", sid))

            lines.append({
                "screen_id": sid,
                "screen_name": screen.get("name"),
                "screen_city": screen.get("location", {}).get("city", ""),
                "unit_price": unit_price,
                "pricing_period": data.pricing_period,
                "duration": data.duration,
                "line_total": line_total,
            })

        if full_screens:
            raise HTTPException(status_code=409, detail={
                "message": f"Las siguientes pantallas están a capacidad máxima: {', '.join(full_screens)}. Puedes unirte a la lista de espera.",
                "full_screens": full_screens,
                "waitlist_available": True,
            })

        now = datetime.utcnow()
        campaign = {
            "id": _gen_id(),
            "advertiser_id": current_user["id"],
            "advertiser_email": current_user.get("email"),
            "advertiser_name": current_user.get("name"),
            "name": data.name,
            "creative_url": data.creative_url,
            "selected_screens": data.screen_ids,
            "pricing_period": data.pricing_period,
            "duration": data.duration,
            "pricing_lines": lines,
            "total_price": round(grand_total, 2),
            "currency": "USD",
            "status": AD_STATUS_DRAFT,
            "payment_status": "unpaid",
            "payment_ref": None,
            "rejection_reason": None,
            "admin_notes": None,
            "start_date": start_date,
            "end_date": end_date,
            "slot_duration_seconds": data.slot_duration_seconds,
            "notes": data.notes,
            "created_at": now,
            "updated_at": now,
        }
        await db.ad_campaigns.insert_one(campaign)
        return _ser(campaign)

    # ── Listar mis campañas ───────────────────────────────────────────────────

    @router.get("/ad-campaigns")
    async def list_my_ad_campaigns(
        status: Optional[str] = None,
        current_user: dict = Depends(get_current_user),
    ):
        """Lista las campañas publicitarias del usuario autenticado."""
        role = get_effective_role(current_user)
        if role in (Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN, Role.SUPPORT):
            # Admins ven todas las campañas
            q = {}
        else:
            q = {"advertiser_id": current_user["id"]}

        if status:
            q["status"] = status.upper()

        campaigns = await db.ad_campaigns.find(q).sort("created_at", -1).to_list(200)
        # Enriquecer con info básica de pantallas
        enriched = []
        for c in campaigns:
            screens_info = []
            for sid in c.get("selected_screens") or []:
                s = await db.screens.find_one({"id": sid}, {"name": 1, "location": 1, "id": 1})
                if s:
                    screens_info.append({
                        "id": s["id"],
                        "name": s.get("name"),
                        "city": s.get("location", {}).get("city"),
                    })
            c["screens_info"] = screens_info
            enriched.append(_ser(c))
        return enriched

    @router.get("/ad-campaigns/{campaign_id}")
    async def get_ad_campaign(
        campaign_id: str,
        current_user: dict = Depends(get_current_user),
    ):
        """Detalle de una campaña publicitaria."""
        role = get_effective_role(current_user)
        if role in (Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN, Role.SUPPORT):
            q = {"id": campaign_id}
        else:
            q = {"id": campaign_id, "advertiser_id": current_user["id"]}

        campaign = await db.ad_campaigns.find_one(q)
        if not campaign:
            raise HTTPException(404, "Campaña no encontrada")

        screens_info = []
        for sid in campaign.get("selected_screens") or []:
            s = await db.screens.find_one({"id": sid})
            if s:
                screens_info.append(_ser(s))
        campaign["screens_info"] = screens_info
        return _ser(campaign)

    # ── Pagar (mock) → PENDING_REVIEW ────────────────────────────────────────

    @router.post("/ad-campaigns/{campaign_id}/pay")
    async def pay_ad_campaign(
        campaign_id: str,
        current_user: dict = Depends(get_current_user),
    ):
        """Procesa el pago MOCK de una campaña y la envía a revisión admin.
        Transición: DRAFT → PENDING_REVIEW."""
        campaign = await db.ad_campaigns.find_one({"id": campaign_id, "advertiser_id": current_user["id"]})
        if not campaign:
            raise HTTPException(404, "Campaña no encontrada")
        if campaign["status"] != AD_STATUS_DRAFT:
            raise HTTPException(400, f"Solo campañas en DRAFT pueden pagarse. Estado actual: {campaign['status']}")

        now = datetime.utcnow()
        payment_ref = f"MOCK-PAY-{now.strftime('%Y%m%d%H%M%S')}-{campaign_id[:6].upper()}"

        await db.ad_campaigns.update_one(
            {"id": campaign_id},
            {"$set": {
                "status": AD_STATUS_PENDING_REVIEW,
                "payment_status": "mocked_paid",
                "payment_ref": payment_ref,
                "paid_at": now,
                "updated_at": now,
            }}
        )
        return {
            "id": campaign_id,
            "status": AD_STATUS_PENDING_REVIEW,
            "payment_ref": payment_ref,
            "payment_status": "mocked_paid",
            "message": "Pago procesado (MOCK). Tu campaña está en revisión por el equipo MediaView.",
        }

    # ── Lista de espera ───────────────────────────────────────────────────────

    @router.post("/marketplace/screens/{screen_id}/waitlist")
    async def join_waitlist(
        screen_id: str,
        payload: WaitlistJoin,
        current_user: dict = Depends(get_current_user),
    ):
        """Unirse a la lista de espera cuando una pantalla está a capacidad máxima."""
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(404, "Pantalla no encontrada")

        # Verificar si ya está en la lista
        existing = await db.ad_waitlist.find_one({
            "screen_id": screen_id,
            "advertiser_id": current_user["id"],
            "status": "waiting",
        })
        if existing:
            raise HTTPException(409, "Ya estás en la lista de espera para esta pantalla")

        now = datetime.utcnow()
        entry = {
            "id": _gen_id(),
            "screen_id": screen_id,
            "screen_name": screen.get("name"),
            "screen_city": screen.get("location", {}).get("city"),
            "advertiser_id": current_user["id"],
            "advertiser_email": current_user.get("email"),
            "advertiser_name": current_user.get("name"),
            "notes": payload.notes,
            "status": "waiting",
            "created_at": now,
            "updated_at": now,
        }
        await db.ad_waitlist.insert_one(entry)
        return _ser({**entry, "message": "Añadido a la lista de espera. Te notificaremos cuando haya disponibilidad."})

    @router.get("/marketplace/screens/{screen_id}/waitlist")
    async def get_my_waitlist_status(
        screen_id: str,
        current_user: dict = Depends(get_current_user),
    ):
        """Verifica si el usuario está en la lista de espera de una pantalla."""
        entry = await db.ad_waitlist.find_one({
            "screen_id": screen_id,
            "advertiser_id": current_user["id"],
            "status": "waiting",
        })
        return {"on_waitlist": entry is not None, "entry": _ser(entry) if entry else None}

    @router.get("/ad-campaigns/waitlist/mine")
    async def my_waitlist(current_user: dict = Depends(get_current_user)):
        """Lista de espera del anunciante actual."""
        entries = await db.ad_waitlist.find(
            {"advertiser_id": current_user["id"]}
        ).sort("created_at", -1).to_list(50)
        return _ser(entries)

    # ── Admin: Centro de Aprobación ───────────────────────────────────────────

    @router.get("/admin/ad-campaigns")
    async def admin_list_ad_campaigns(
        status: Optional[str] = None,
        admin: dict = Depends(require_admin),
    ):
        """Listar todas las campañas publicitarias (admin)."""
        q = {}
        if status:
            q["status"] = status.upper()
        campaigns = await db.ad_campaigns.find(q).sort("created_at", -1).to_list(500)
        result = []
        for c in campaigns:
            advertiser = await db.users.find_one({"id": c.get("advertiser_id")}, {"password_hash": 0})
            screens_info = []
            for sid in c.get("selected_screens") or []:
                s = await db.screens.find_one({"id": sid}, {"name": 1, "location": 1, "id": 1})
                if s:
                    screens_info.append({"id": s["id"], "name": s.get("name"), "city": s.get("location", {}).get("city")})
            c["advertiser"] = _ser(advertiser) if advertiser else None
            c["screens_info"] = screens_info
            result.append(_ser(c))
        return result

    @router.get("/admin/ad-campaigns/pending")
    async def admin_pending_ad_campaigns(admin: dict = Depends(require_admin)):
        """Cola de campañas en PENDING_REVIEW esperando aprobación."""
        campaigns = await db.ad_campaigns.find(
            {"status": AD_STATUS_PENDING_REVIEW}
        ).sort("created_at", 1).to_list(200)  # FIFO
        result = []
        for c in campaigns:
            advertiser = await db.users.find_one({"id": c.get("advertiser_id")}, {"password_hash": 0})
            screens_info = []
            for sid in c.get("selected_screens") or []:
                s = await db.screens.find_one({"id": sid}, {"name": 1, "location": 1, "id": 1})
                if s:
                    screens_info.append({"id": s["id"], "name": s.get("name"), "city": s.get("location", {}).get("city")})
            c["advertiser"] = _ser(advertiser) if advertiser else None
            c["screens_info"] = screens_info
            result.append(_ser(c))
        return result

    @router.post("/admin/ad-campaigns/{campaign_id}/approve")
    async def admin_approve_ad_campaign(
        campaign_id: str,
        admin: dict = Depends(require_admin),
    ):
        """Aprueba una campaña publicitaria.
        Si la fecha de inicio ya pasó o es hoy → ACTIVE. Si es futura → APPROVED."""
        campaign = await db.ad_campaigns.find_one({"id": campaign_id})
        if not campaign:
            raise HTTPException(404, "Campaña no encontrada")
        if campaign["status"] not in (AD_STATUS_PENDING_REVIEW,):
            raise HTTPException(400, f"Solo campañas PENDING_REVIEW pueden aprobarse. Estado: {campaign['status']}")

        new_status = _calc_status_from_dates(campaign.get("start_date"), campaign.get("end_date"))
        now = datetime.utcnow()

        await db.ad_campaigns.update_one(
            {"id": campaign_id},
            {"$set": {
                "status": new_status,
                "admin_notes": f"Aprobado por {admin.get('name', 'Admin')} el {now.strftime('%Y-%m-%d %H:%M')}",
                "approved_by": admin.get("id"),
                "approved_at": now,
                "updated_at": now,
            }}
        )

        # Bump playlist version for all selected screens
        for sid in campaign.get("selected_screens") or []:
            try:
                # NOTE: The playlist builder in server.py will automatically include
                # APPROVED/ACTIVE ad_campaigns on next playlist request.
                # No explicit bump needed as players poll periodically.
                pass
            except Exception:
                pass

        return {
            "id": campaign_id,
            "status": new_status,
            "message": f"Campaña {new_status}. Se ha añadido a las playlists de las pantallas seleccionadas.",
        }

    @router.post("/admin/ad-campaigns/{campaign_id}/reject")
    async def admin_reject_ad_campaign(
        campaign_id: str,
        payload: AdCampaignReject,
        admin: dict = Depends(require_admin),
    ):
        """Rechaza una campaña con una razón específica.
        La campaña vuelve a DRAFT para que el anunciante pueda editarla."""
        campaign = await db.ad_campaigns.find_one({"id": campaign_id})
        if not campaign:
            raise HTTPException(404, "Campaña no encontrada")
        if campaign["status"] not in (AD_STATUS_PENDING_REVIEW, AD_STATUS_APPROVED, AD_STATUS_ACTIVE):
            raise HTTPException(400, f"No se puede rechazar una campaña en estado {campaign['status']}")

        now = datetime.utcnow()
        await db.ad_campaigns.update_one(
            {"id": campaign_id},
            {"$set": {
                "status": AD_STATUS_DRAFT,
                "rejection_reason": payload.reason,
                "payment_status": "unpaid",
                "payment_ref": None,
                "admin_notes": f"Rechazado por {admin.get('name', 'Admin')}: {payload.reason}",
                "rejected_by": admin.get("id"),
                "rejected_at": now,
                "updated_at": now,
            }}
        )

        # Bump playlist si estaba activa/aprobada
        if campaign["status"] in (AD_STATUS_APPROVED, AD_STATUS_ACTIVE):
            for sid in campaign.get("selected_screens") or []:
                pass  # Playlist builder re-checks status on next poll

        return {
            "id": campaign_id,
            "status": AD_STATUS_DRAFT,
            "rejection_reason": payload.reason,
            "message": "Campaña rechazada. El anunciante podrá editarla y volver a pagar.",
        }

    # ── Admin: Waitlist ───────────────────────────────────────────────────────

    @router.get("/admin/ad-waitlist")
    async def admin_waitlist(
        screen_id: Optional[str] = None,
        admin: dict = Depends(require_admin),
    ):
        """Ver lista de espera de pantallas (admin)."""
        q = {"status": "waiting"}
        if screen_id:
            q["screen_id"] = screen_id
        entries = await db.ad_waitlist.find(q).sort("created_at", 1).to_list(500)
        return _ser(entries)

    # ── QR Code para pantallas PUBLIC_ADVERTISING ─────────────────────────────

    @router.get("/admin/screens/{screen_id}/qr")
    async def get_screen_qr(
        screen_id: str,
        base_url: Optional[str] = None,
        admin: dict = Depends(require_admin),
    ):
        """Retorna la URL del QR y la URL de la landing para una pantalla PUBLIC_ADVERTISING."""
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(404, "Pantalla no encontrada")
        if screen.get("operation_type") != "PUBLIC_ADVERTISING":
            raise HTTPException(400, "Esta pantalla no es de tipo PUBLIC_ADVERTISING")

        code = screen.get("public_screen_code")
        if not code:
            raise HTTPException(400, "Esta pantalla no tiene código de publicidad generado. Contacta al administrador.")

        advertise_url = f"{base_url or ''}/api/adpage/{code}"
        # Fallback for local dev: also include /advertise/{code} as secondary
        qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={advertise_url}&bgcolor=ffffff&color=000000&margin=10"

        return {
            "screen_id": screen_id,
            "screen_name": screen.get("name"),
            "public_screen_code": code,
            "advertise_url": advertise_url,
            "advertise_url_local": f"{base_url or ''}/advertise/{code}",
            "qr_image_url": qr_image_url,
        }

    # ── Proof of Play ─────────────────────────────────────────────────────────

    @router.post("/proof-of-play")
    async def record_proof_of_play(data: ProofOfPlayCreate):
        """Registra un evento de reproducción real. Llamado por el player."""
        now = datetime.utcnow()
        played_at = data.played_at or now.isoformat()

        record = {
            "id": _gen_id(),
            "screen_id": data.screen_id,
            "campaign_id": data.campaign_id,
            "creative_url": data.creative_url,
            "played_at": played_at,
            "duration_seconds": data.duration_seconds,
            "recorded_at": now,
        }
        await db.proof_of_play.insert_one(record)
        return {"id": record["id"], "recorded": True}

    @router.get("/admin/proof-of-play")
    async def admin_proof_of_play(
        screen_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        admin: dict = Depends(require_admin),
    ):
        """Ver registros de Proof of Play (admin)."""
        q = {}
        if screen_id:
            q["screen_id"] = screen_id
        if campaign_id:
            q["campaign_id"] = campaign_id
        records = await db.proof_of_play.find(q).sort("recorded_at", -1).to_list(500)
        return _ser(records)

    # ── Stats del Marketplace (dashboard) ────────────────────────────────────

    @router.get("/admin/ad-campaigns/stats")
    async def admin_ad_stats(admin: dict = Depends(require_admin)):
        """Estadísticas del marketplace de publicidad."""
        total = await db.ad_campaigns.count_documents({})
        pending = await db.ad_campaigns.count_documents({"status": AD_STATUS_PENDING_REVIEW})
        active = await db.ad_campaigns.count_documents({"status": {"$in": [AD_STATUS_APPROVED, AD_STATUS_ACTIVE]}})
        rejected = await db.ad_campaigns.count_documents({"status": AD_STATUS_REJECTED})
        waitlist = await db.ad_waitlist.count_documents({"status": "waiting"})

        # Revenue total de campañas pagadas
        paid_campaigns = await db.ad_campaigns.find(
            {"payment_status": "mocked_paid"},
            {"total_price": 1}
        ).to_list(10000)
        total_revenue = sum(c.get("total_price", 0) for c in paid_campaigns)

        return {
            "total_campaigns": total,
            "pending_review": pending,
            "active": active,
            "rejected": rejected,
            "waitlist_entries": waitlist,
            "total_mock_revenue": round(total_revenue, 2),
            "currency": "USD",
        }

    return router
