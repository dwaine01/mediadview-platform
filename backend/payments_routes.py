"""payments_routes.py -- the 3 legacy client-facing /payments* routes
(mocked, Stripe-ready per the original comment header). Create/list/get a
payment against one of the caller's own campaigns.

Fase 2B-10a of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md).
Pure relocation: identical paths, methods, decorators and logic, registered
on a router with prefix="/api" so the final routes match api_router exactly
as before. No behavior change.

Dependency notes:
  - gen_id, gen_invoice and serialize_doc are threaded in: all three stay
    defined in server.py because they're shared with code that is NOT
    moving here (gen_id/serialize_doc are used everywhere; gen_invoice is
    also called directly from the demo-seed-data path).
  - db (database.py) and get_current_user (deps.py) are imported directly,
    same precedent as every prior phase.
  - _rl / _LIMITS (rate_limit.py) are imported directly, same precedent as
    public_api_routes.py's public_playlist_media -- create_payment carries
    the exact same @router.post(...) / @_rl.limit(...) decorator stack.
  - PaymentCreate moves here as a plain module-level pydantic model, same
    precedent as CampaignMediaReplace/QuoteItem: it embeds no threaded
    type and grep confirms no use outside this exact route.
  - Naming note: list_payments/get_payment share their names with an
    unrelated method on finance.py's admin-facing class and with
    payments/*_provider.py's real Stripe/dev provider abstraction
    (get_payment). Grep-verified in both directions: no cross-import for
    either name, different modules' namespaces, zero collision.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from database import db
from deps import get_current_user
from rate_limit import LIMITS as _LIMITS
from rate_limit import limiter as _rl


class PaymentCreate(BaseModel):
    campaign_id: str
    method: str = "card"
    card_last4: Optional[str] = None


def create_payments_routes(gen_id, gen_invoice, serialize_doc):
    router = APIRouter(prefix="/api", tags=["Payments"])

    @router.post("/payments")
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

    @router.get("/payments")
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

    @router.get("/payments/{payment_id}")
    async def get_payment(payment_id: str, current_user: dict = Depends(get_current_user)):
        payment = await db.payments.find_one({"id": payment_id, "user_id": current_user["id"]})
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        return serialize_doc(payment)

    return router
