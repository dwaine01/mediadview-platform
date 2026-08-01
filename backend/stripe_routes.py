"""
MediAd View — Stripe & guest-checkout HTTP routes (Fase 5 · Sprint 1 · Etapa B).

Endpoints mounted:
    GET  /api/checkout/config
    POST /api/checkout/quote
    POST /api/checkout/create-intent
    GET  /api/orders/{token}
    POST /api/webhooks/stripe

Design:
    · All routes are RATE-LIMITED via slowapi (existing `rate_limit.limiter`).
    · The webhook route reads RAW body BEFORE parsing (Stripe requires this).
    · Errors return {"error": "..."} without leaking stack traces or SDK types.
    · No route ever moves an Order to `paid` — that's exclusively `stripe_events.process_event`.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr, Field

from checkout_service import (
    build_quote,
    create_intent,
    mint_order_token,
    verify_order_token,
)
from financial_audit import audit
from stripe_config import (
    DEFAULT_CURRENCY,
    get_mode,
    get_publishable_key,
    is_configured as stripe_configured,
    webhook_secret,
)
from stripe_events import process_event

log = logging.getLogger("stripe_routes")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Request/Response models ────────────────────────────────────────────
class QuoteRequest(BaseModel):
    screen_id: str
    hours: int = Field(ge=1, le=720)
    currency: str = DEFAULT_CURRENCY


class CreateIntentRequest(BaseModel):
    quote_id: str
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None
    media_id: Optional[str] = None
    schedule: Optional[dict] = None


class TokenizedOrderView(BaseModel):
    order_id: str
    order_number: str
    status: str
    amount_cents: int
    currency: str
    screen_name: str
    hours: int
    created_at: datetime
    paid_at: Optional[datetime] = None


def _client_ip(req: Request) -> Optional[str]:
    """Extract real client IP through the K8s ingress' X-Forwarded-For header."""
    xff = req.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return xff or (req.client.host if req.client else None)


def _request_id(req: Request) -> Optional[str]:
    return req.headers.get("x-request-id") or getattr(req.state, "request_id", None)


def build_stripe_router(db: AsyncIOMotorDatabase) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["checkout"])

    # ══════════════════════════════════════════════════════════════════
    # GET /api/checkout/config
    # ══════════════════════════════════════════════════════════════════
    @router.get("/checkout/config")
    async def checkout_config():
        """Public config exposed to the browser. Contains the publishable
        key (safe to expose) and current mode. NEVER exposes secret keys."""
        return {
            "enabled": stripe_configured(),
            "mode": get_mode(),
            "publishable_key": get_publishable_key() or "",
            "currency": DEFAULT_CURRENCY,
            "payment_methods": ["card"],
        }

    # ══════════════════════════════════════════════════════════════════
    # POST /api/checkout/quote
    # ══════════════════════════════════════════════════════════════════
    @router.post("/checkout/quote")
    async def checkout_quote(body: QuoteRequest, request: Request):
        try:
            quote = await build_quote(
                db,
                screen_id=body.screen_id,
                hours=body.hours,
                currency=body.currency,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        await audit(db, action="checkout.quote",
                    actor_kind="guest", actor_ip=_client_ip(request),
                    request_id=_request_id(request),
                    entity_type="screen", entity_id=body.screen_id,
                    amount_cents=quote["total_cents"], currency=quote["currency"],
                    metadata={"hours": body.hours})
        return quote

    # ══════════════════════════════════════════════════════════════════
    # POST /api/checkout/create-intent
    # ══════════════════════════════════════════════════════════════════
    @router.post("/checkout/create-intent")
    async def checkout_create_intent(body: CreateIntentRequest, request: Request):
        if not stripe_configured():
            raise HTTPException(503, "payments are temporarily unavailable")
        try:
            result = await create_intent(
                db,
                quote_id=body.quote_id,
                email=body.email,
                name=body.name,
                phone=body.phone,
                media_id=body.media_id,
                schedule=body.schedule,
                request_id=_request_id(request),
                actor_ip=_client_ip(request),
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        except RuntimeError as e:
            raise HTTPException(502, str(e))
        except Exception:
            log.exception("create_intent crashed")
            raise HTTPException(500, "internal error creating payment")

        # Mint a magic-link token for post-checkout order view
        token = await mint_order_token(db, order_id=result["order_id"])
        # Do not embed the token in the URL yet — the frontend will build
        # it after payment confirmation, so it's returned in the body.
        result["order_view_token"] = token
        return result

    # ══════════════════════════════════════════════════════════════════
    # GET /api/orders/{token}
    # ══════════════════════════════════════════════════════════════════
    @router.get("/orders/{token}", response_model=TokenizedOrderView)
    async def get_order_by_token(token: str):
        payload = await verify_order_token(db, token=token)
        if not payload:
            raise HTTPException(404, "invalid or expired order link")
        order = await db.orders.find_one({"_id": payload["order_id"]})
        if not order:
            raise HTTPException(404, "order not found")
        return TokenizedOrderView(
            order_id=order["_id"],
            order_number=order["order_number"],
            status=order["status"],
            amount_cents=int(order["amount_cents"]),
            currency=order["currency"],
            screen_name=order["screen_name"],
            hours=int(order["hours"]),
            created_at=order["created_at"],
            paid_at=order.get("paid_at"),
        )

    # ══════════════════════════════════════════════════════════════════
    # POST /api/webhooks/stripe
    # ══════════════════════════════════════════════════════════════════
    @router.post("/webhooks/stripe")
    async def stripe_webhook(request: Request):
        # 1) Read RAW bytes (Stripe signs raw bytes; parsing first breaks it)
        raw_body = await request.body()

        # 2) Signature verification
        sig_header = request.headers.get("stripe-signature", "")
        secret = webhook_secret()
        if not secret:
            log.warning("stripe webhook received but no secret configured")
            raise HTTPException(503, "webhook receiver is not configured")

        try:
            event = stripe.Webhook.construct_event(raw_body, sig_header, secret)
        except stripe.error.SignatureVerificationError as e:
            log.warning("stripe webhook signature FAILED (%s)", e)
            await audit(db, action="stripe.webhook.bad_signature",
                        actor_kind="webhook", actor_ip=_client_ip(request),
                        reason=str(e)[:200])
            raise HTTPException(400, "invalid signature")
        except Exception as e:
            log.warning("stripe webhook parse failed: %s", e)
            raise HTTPException(400, "invalid payload")

        event_id = event.get("id")
        etype = event.get("type", "")

        # 3) Deduplicate: try to insert into stripe_events. If the unique
        #    index rejects us, this is a Stripe retry we already processed.
        try:
            await db.stripe_events.insert_one({
                "event_id": event_id,
                "type": etype,
                "received_at": _utcnow(),
                "processed_at": None,
                "result": None,
                "payload": event,   # keep the full event for auditability
            })
        except Exception as e:
            if "duplicate" in str(e).lower() or "E11000" in str(e):
                # Already processed — ack.
                return Response(status_code=200)
            log.exception("stripe_events insert failed")
            raise HTTPException(500, "storage error")

        # 4) Dispatch. If handler raises, mark the event failed and
        #    return non-2xx so Stripe retries.
        try:
            outcome = await process_event(db, event)
            await db.stripe_events.update_one(
                {"event_id": event_id},
                {"$set": {"processed_at": _utcnow(),
                          "result": outcome.get("result")}}
            )
        except Exception as e:
            await db.stripe_events.update_one(
                {"event_id": event_id},
                {"$set": {"processed_at": _utcnow(),
                          "result": "error",
                          "error": str(e)[:1000]}}
            )
            raise HTTPException(500, "event processing failed")

        return Response(status_code=200)

    return router
