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
# ── State Machine ─────────────────────────────────────────────────────────────
AD_STATUS_DRAFT = "DRAFT"
AD_STATUS_PENDING_REVIEW = "PENDING_REVIEW"
AD_STATUS_APPROVED = "APPROVED"
AD_STATUS_SCHEDULED = "SCHEDULED"    # Aprobada, fecha futura — manejada por campaign_scheduler
AD_STATUS_ACTIVE = "ACTIVE"
AD_STATUS_COMPLETED = "COMPLETED"    # End_date superada — manejada por campaign_scheduler
AD_STATUS_REJECTED = "REJECTED"
AD_STATUS_CANCELLED = "CANCELLED"
AD_STATUS_EXPIRED = "EXPIRED"        # Alias legacy → COMPLETED

# Solo ACTIVE aparece en el playlist del player (el scheduler gestiona transiciones)
AD_PLAYABLE_STATUSES = {AD_STATUS_ACTIVE}

# Statuses que "ocupan" un slot (para control de capacidad max_ad_slots)
AD_SLOT_OCCUPYING_STATUSES = {
    AD_STATUS_PENDING_REVIEW, AD_STATUS_APPROVED,
    AD_STATUS_SCHEDULED, AD_STATUS_ACTIVE,
}

PERIOD_DAYS = {"weekly": 7, "monthly": 30, "yearly": 365}


def _audience(adv: dict) -> Optional[dict]:
    """Tráfico estimado del local, listo para mostrar («500–700 personas/día»).

    Es el dato que decide la compra: el anunciante no paga por una pantalla,
    paga por la gente que pasa delante de ella."""
    low, high = adv.get("audience_min"), adv.get("audience_max")
    note = adv.get("audience_note")
    if low is None and high is None:
        return {"label": None, "min": None, "max": None, "note": note} if note else None
    if low is not None and high is not None and high != low:
        label = f"{low:,}–{high:,} personas/día".replace(",", ".")
    else:
        single = low if low is not None else high
        label = f"{single:,} personas/día".replace(",", ".")
    return {"label": label, "min": low, "max": high, "note": note}


def _venue(screen: dict) -> dict:
    """Ficha comercial de la ubicación: qué negocio, dónde y cuánta gente pasa.

    Se arma en un solo lugar porque la ve el anunciante en tres momentos —
    la landing del QR, el listado del marketplace y la ficha detallada — y
    tiene que decir exactamente lo mismo en los tres."""
    adv = screen.get("advertising") or {}
    location = screen.get("location") or {}
    open_from = adv.get("open_from") or DEFAULT_OPEN[0]
    open_to = adv.get("open_to") or DEFAULT_OPEN[1]
    return {
        "establishment_name": adv.get("establishment_name") or screen.get("name"),
        "address": location.get("address"),
        "city": location.get("city"),
        "state": location.get("state"),
        "country": location.get("country"),
        "reference": adv.get("location_reference"),
        "audience": _audience(adv),
        # La foto real de la pantalla instalada, servida como imagen (el base64
        # crudo pesa cientos de KB y el listado muestra varias a la vez).
        "photo_url": (f"/api/screens/{screen['id']}/venue-photo"
                      if adv.get("photo_base64") else None),
        "has_photo": bool(adv.get("photo_base64")),
        # Para el mapa: el anunciante elige por zona, no leyendo direcciones.
        "lat": location.get("lat"),
        "lng": location.get("lng"),
        "open_from": open_from,
        "open_to": open_to,
        "hours_label": f"{open_from} a {open_to}",
        "hours_are_default": not (adv.get("open_from") and adv.get("open_to")),
    }


DEFAULT_OPEN = ("08:00", "20:00")


def _minutes(value: str, fallback: str) -> int:
    try:
        hour, minute = str(value).split(":")
        return max(0, min(24 * 60, int(hour) * 60 + int(minute)))
    except (ValueError, AttributeError):
        hour, minute = fallback.split(":")
        return int(hour) * 60 + int(minute)




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


class ReachEstimate(BaseModel):
    """Lo que el anunciante elige para saber a cuánta gente va a llegar."""
    start_time: str = "08:00"
    end_time: str = "20:00"
    days_per_week: int = 7
    weeks: int = 4
    slot_seconds: int = 30

class ProofOfPlayCreate(BaseModel):
    screen_id: str
    campaign_id: str
    played_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    creative_url: Optional[str] = None


# ── Factory ────────────────────────────────────────────────────────────────────

def create_advertising_routes(db, get_current_user, require_admin):
    router = APIRouter(prefix="/api")

    async def _commercial_view(screen: dict) -> dict:
        """Lo que el anunciante ve de una pantalla: ubicación, gente y precios.

        Nunca datos técnicos internos ni el costo de MediaView."""
        occupied = await db.ad_campaigns.count_documents({
            "selected_screens": screen["id"],
            "status": {"$in": list(AD_SLOT_OCCUPYING_STATUSES)},
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
            # El código corto que el cliente ve en el resumen de su compra y la
            # tarifa diaria con la que la tienda pública arma los planes.
            "location_code": screen.get("location_code"),
            # Algunas pantallas viejas tienen per_day en 0 pero sí tarifa
            # mensual: mostrar «$0/día» en la tienda haría perder la venta.
            "daily_price": ((screen.get("pricing") or {}).get("per_day")
                            or (round(ap.get("price_per_month") / 30, 2)
                                if ap.get("price_per_month") else None)),
            "venue": _venue(screen),
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
        return await _commercial_view(screen)

    # ── Marketplace (requiere auth) ───────────────────────────────────────────

    @router.get("/marketplace/screens")
    async def list_marketplace_screens(
        city: Optional[str] = None,
        here: Optional[str] = None,
        current_user: dict = Depends(get_current_user),
    ):
        """Lista todas las pantallas PUBLIC_ADVERTISING disponibles con capacidad y precios.

        `here` es el código de la pantalla cuyo QR escaneó el anunciante: esa
        pantalla se marca (`is_here`) y va primera en la lista, porque es la
        que tiene delante y la razón por la que entró."""
        query = {"operation_type": "PUBLIC_ADVERTISING", "status": "active",
                 # El interruptor «mostrar en el catálogo público» del panel:
                 # una pantalla alquilada por contrato no se ofrece de nuevo.
                 "advertising.is_public": {"$ne": False}}
        if city:
            query["location.city"] = {"$regex": city, "$options": "i"}
        screens = await db.screens.find(query).to_list(200)
        code = (here or "").strip().upper()
        result = []
        for s in screens:
            row = await _commercial_view(s)
            row["is_here"] = bool(code) and str(s.get("public_screen_code") or "").upper() == code
            result.append(row)
        result.sort(key=lambda row: (not row["is_here"], row["is_full"],
                                     (row["venue"]["establishment_name"] or "").lower()))
        return result

    @router.get("/marketplace/screens/{screen_id}")
    async def marketplace_screen_detail(
        screen_id: str,
        here: Optional[str] = None,
        current_user: dict = Depends(get_current_user),
    ):
        """Ficha detallada de la ubicación, ANTES de cualquier pago.

        El anunciante tiene que poder evaluar dónde va a aparecer su publicidad
        —qué negocio, en qué calle, cómo se llega, cuánta gente pasa y cómo se
        ve la pantalla instalada— antes de poner un peso."""
        screen = await db.screens.find_one({
            "id": screen_id,
            "operation_type": "PUBLIC_ADVERTISING",
            "status": "active",
        })
        if not screen:
            raise HTTPException(404, "Pantalla no encontrada o no disponible para publicidad")
        detail = await _commercial_view(screen)
        code = (here or "").strip().upper()
        detail["is_here"] = bool(code) and str(screen.get("public_screen_code") or "").upper() == code
        return detail


    @router.get("/marketplace/cities")
    async def marketplace_cities(current_user: dict = Depends(get_current_user)):
        """Lista de ciudades con pantallas PUBLIC_ADVERTISING activas."""
        cities = await db.screens.distinct(
            "location.city",
            {"operation_type": "PUBLIC_ADVERTISING", "status": "active",
             "advertising.is_public": {"$ne": False}},
        )
        return sorted(cities)

    @router.post("/marketplace/screens/{screen_id}/reach")
    async def estimate_reach(
        screen_id: str,
        payload: ReachEstimate,
        current_user: dict = Depends(get_current_user),
    ):
        """A cuánta gente le va a llegar el anuncio con los días y el horario elegidos.

        La cuenta es deliberadamente simple y explicable, porque el anunciante
        tiene que poder rehacerla de cabeza: el tráfico diario del local se
        reparte por sus horas de atención, se toma la parte que cae dentro de
        la franja elegida y se multiplica por los días de campaña. Es una
        estimación, no una promesa, y así se rotula."""
        screen = await db.screens.find_one({
            "id": screen_id, "operation_type": "PUBLIC_ADVERTISING", "status": "active",
        })
        if not screen:
            raise HTTPException(404, "Pantalla no encontrada o no disponible para publicidad")

        adv = screen.get("advertising") or {}
        audience = _audience(adv)
        if not audience or audience.get("min") is None and audience.get("max") is None:
            raise HTTPException(400, "Esta pantalla todavía no tiene tráfico estimado cargado")
        low = audience.get("min")
        high = audience.get("max")
        people_day = round(((low or high) + (high or low)) / 2)

        days_per_week = max(1, min(7, int(payload.days_per_week)))
        weeks = max(1, min(104, int(payload.weeks)))
        slot_seconds = max(5, min(120, int(payload.slot_seconds)))

        open_from = _minutes(adv.get("open_from") or DEFAULT_OPEN[0], DEFAULT_OPEN[0])
        open_to = _minutes(adv.get("open_to") or DEFAULT_OPEN[1], DEFAULT_OPEN[1])
        if open_to <= open_from:
            open_to = open_from + 60
        window_from = max(open_from, _minutes(payload.start_time, DEFAULT_OPEN[0]))
        window_to = min(open_to, _minutes(payload.end_time, DEFAULT_OPEN[1]))
        window_minutes = max(0, window_to - window_from)
        open_minutes = open_to - open_from
        share = window_minutes / open_minutes if open_minutes else 0

        reach_day = round(people_day * share)
        days_total = days_per_week * weeks
        reach_total = reach_day * days_total

        # Cuántas veces sale el anuncio: el bucle lo comparten los anunciantes
        # que ya están al aire más el que entra.
        occupied = await db.ad_campaigns.count_documents({
            "selected_screens": screen_id,
            "status": {"$in": list(AD_SLOT_OCCUPYING_STATUSES)},
        })
        ads_in_loop = max(1, occupied + 1)
        loop_seconds = ads_in_loop * slot_seconds
        plays_hour = max(1, round(3600 / loop_seconds))
        plays_day = round(plays_hour * window_minutes / 60)

        return {
            "people_per_day_venue": people_day,
            "hours_open": round(open_minutes / 60, 1),
            "hours_selected": round(window_minutes / 60, 1),
            "share_of_day": round(share, 3),
            "reach_per_day": reach_day,
            "days_total": days_total,
            "days_per_week": days_per_week,
            "weeks": weeks,
            "reach_total": reach_total,
            "plays_per_hour": plays_hour,
            "plays_per_day": plays_day,
            "plays_total": plays_day * days_total,
            "ads_in_loop": ads_in_loop,
            "slot_seconds": slot_seconds,
            "window": {"from": payload.start_time, "to": payload.end_time,
                       "clipped": window_minutes < (_minutes(payload.end_time, DEFAULT_OPEN[1])
                                                    - _minutes(payload.start_time, DEFAULT_OPEN[0]))},
            "venue_hours": {"from": adv.get("open_from") or DEFAULT_OPEN[0],
                            "to": adv.get("open_to") or DEFAULT_OPEN[1]},
            "note": ("Estimación basada en el tráfico declarado del local repartido en su "
                     "horario de atención. No es una garantía de audiencia."),
        }

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
                "status": {"$in": list(AD_SLOT_OCCUPYING_STATUSES)},
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
                "status": {"$in": list(AD_SLOT_OCCUPYING_STATUSES)},
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
