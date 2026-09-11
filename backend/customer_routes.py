"""customer_routes.py -- authenticated /customer/* transient-buyer flow:
catalog browsing (with pricing), discount-scale lookup, cart quoting, order
submission, and order history.

Fase 2B-9 of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md).
Continues the "2B" numbering: the informally-named "Fase 2C-1"
(public_api_routes.py) is being renamed 2B-8 in the same breath as this PR
lands, per the naming-convention fix agreed with duarte -- "Fase 2C" is
reserved exclusively for the later backend/domains/<dominio>/ folder
reorganization, not for further server.py route extractions. Pure
relocation of the 6 handlers below out of server.py: identical paths,
methods, decorators and logic, registered on a router with prefix="/api"
so the final routes match api_router exactly as before. No behavior change
other than two docstrings gaining correctly-indented continuation lines
(see the reindent-defect note below) -- their string VALUE changes (pure
whitespace inside unused docstrings), nothing that executes differently.
With this PR, server.py has zero remaining /customer/* business logic.

Dependency notes:
  - gen_id is threaded in, same pattern as every prior phase: it's used by
    customer_order_from_cart (doc["id"] = gen_id()) but stays defined in
    server.py because it's shared with a large amount of code that is NOT
    moving here (gen_invoice, other order/document creation paths).
  - serialize_doc is NOT threaded here -- grep-verified that none of these
    6 routes call it (customer_order_from_cart and customer_my_orders both
    build/trim their response dicts by hand instead).
  - db (database.py) and get_current_user (deps.py) are imported directly,
    same precedent as every prior phase.
  - _public_screen_view (media_utils.py) is imported directly: it moved
    there in Fase 2B-8 (ex "2C-1") specifically so both /public/* and this
    /customer/* phase could use it without threading -- _customer_screen_view
    below is exactly the kind of not-yet-moved caller that docstring
    anticipated.
  - PUBLIC_DISCOUNT_SCALE, _customer_screen_view and _apply_discount move
    here as plain module-level constant/functions: grep-verified across
    every file in backend/ (not just server.py) that none has any call
    site outside the exact line range being moved.
  - QuoteItem/QuoteRequest and CartItem/CustomerOrderSubmit move here as
    plain module-level pydantic models, same precedent as
    CampaignMediaReplace in campaigns_routes.py: none of them embed a
    threaded/non-moving type, so none need to live inside the factory
    (contrast with CampaignCreate/CampaignUpdate in campaigns_routes.py,
    which DO embed the threaded CampaignSchedule and so ARE defined inside
    create_campaigns_routes(...)).
  - stripe_routes.py separately defines its OWN class QuoteRequest(BaseModel)
    (its /checkout/quote body, unrelated to this cart-quote flow). Confirmed
    via grep: no cross-import between stripe_routes.py and this file/server.py
    for that name in either direction -- two classes with the same name in
    two separate modules' namespaces don't collide. Purely coincidental,
    zero practical impact, no rename needed.
  - Pre-existing reindent-triplet defect found and worked around here (not
    introduced by this PR): the shared reindent()/protected_rows() helpers
    used by every extraction script never reindent a multi-line docstring's
    CONTINUATION lines, only its first line -- already visible, unfixed, in
    trunk's public_api_routes.py (e.g. lines 89-90). customer_quote and
    customer_order_from_cart both have multi-line docstrings, so each gets
    an explicit, count()==1-verified, round-trip-aware manual fix instead
    of carrying the same defect forward. Purely cosmetic (Python does not
    enforce indentation on string continuation lines, so nothing breaks at
    runtime either way) -- flagged separately as a possible tiny follow-up
    for the already-pushed file.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from deps import get_current_user
from media_utils import _public_screen_view

PUBLIC_DISCOUNT_SCALE = {1: 0.00, 3: 0.10, 6: 0.20, 12: 0.30}

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


class QuoteItem(BaseModel):
    screen_id: str
    num_ads: int = 1     # how many ad slots on this screen
    months: int = 1      # commitment length in 30-day units

class QuoteRequest(BaseModel):
    items: List[QuoteItem]


class CartItem(BaseModel):
    screen_id: str
    num_ads: int = 1
    months: int = 1

class CustomerOrderSubmit(BaseModel):
    items: List[CartItem]
    media_data_url: Optional[str] = None   # data:image/... or data:video/...
    media_kind: Optional[str] = None       # 'image' | 'video'
    notes: Optional[str] = None


def create_customer_routes(gen_id):
    router = APIRouter(prefix="/api", tags=["Customer"])

    @router.get("/customer/screens")
    async def customer_screens(city: Optional[str] = None, current_user: dict = Depends(get_current_user)):
        """Screen catalog visible AFTER signup — includes pricing."""
        query: dict = {"status": "active", "advertising.is_public": {"$ne": False}}
        if city:
            query["location.city"] = {"$regex": city, "$options": "i"}
        screens = await db.screens.find(query).to_list(200)
        return [_customer_screen_view(s) for s in screens]

    @router.get("/customer/screens/{screen_id}")
    async def customer_screen_detail(screen_id: str, current_user: dict = Depends(get_current_user)):
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        return _customer_screen_view(screen)

    @router.get("/customer/discount-scale")
    async def customer_discount_scale(current_user: dict = Depends(get_current_user)):
        """Publishes the discount tiers so the frontend cart can render them."""
        return {"scale": PUBLIC_DISCOUNT_SCALE, "unit_days": 30}

    @router.post("/customer/quote")
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

    @router.post("/customer/orders/from-cart")
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

    @router.get("/customer/orders/mine")
    async def customer_my_orders(current_user: dict = Depends(get_current_user)):
        cur = db.customer_orders.find({"customer_id": current_user.get("id")}).sort("created_at", -1)
        docs = await cur.to_list(100)
        out = []
        for d in docs:
            d.pop("_id", None)
            d.pop("media_data_url", None)  # drop the heavy field from list view
            out.append(d)
        return out

    return router
