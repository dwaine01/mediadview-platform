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

import stripe   # only for the type of exception in webhook parse
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr, Field

DEFAULT_CURRENCY = "usd"

from checkout_service import (
    build_quote,
    create_intent,
    mint_order_token,
    verify_order_token,
    stripe_configured_check,
)
from financial_audit import audit
from payments import (
    get_provider, ProviderError, CardError, SignatureVerificationError,
)
from stripe_events import process_event

log = logging.getLogger("stripe_routes")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Request/Response models ────────────────────────────────────────────
class QuoteRequest(BaseModel):
    screen_id: str
    hours: int = Field(ge=1, le=720)
    start_at: Optional[str] = None    # ISO-8601; default = next full hour UTC
    currency: str = DEFAULT_CURRENCY


class GuestMediaUpload(BaseModel):
    checkout_session: str
    filename: str
    content_type: str
    data: str                          # base64
    screen_id: str                     # must match session's screen


class CreateIntentRequest(BaseModel):
    quote_id: str
    checkout_session: str
    media_id: str                      # REQUIRED — user brief §1
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None


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
        try:
            p = get_provider()
            return {
                "enabled": True,
                "provider": p.name,
                "mode": p.mode,
                "publishable_key": p.publishable_key or "",
                "currency": DEFAULT_CURRENCY,
                "payment_methods": ["card"],
                "supports_webhooks": p.supports_webhooks,
                "supports_3ds": p.supports_3ds,
            }
        except Exception:
            return {
                "enabled": False, "provider": "none", "mode": "disabled",
                "publishable_key": "", "currency": DEFAULT_CURRENCY,
                "payment_methods": ["card"],
                "supports_webhooks": False, "supports_3ds": False,
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
                start_at=body.start_at,
                currency=body.currency,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        await audit(db, action="checkout.quote",
                    actor_kind="guest", actor_ip=_client_ip(request),
                    request_id=_request_id(request),
                    entity_type="screen", entity_id=body.screen_id,
                    amount_cents=quote["total_cents"], currency=quote["currency"],
                    metadata={"hours": body.hours, "start_at": quote["start_at"]})
        return quote

    # ══════════════════════════════════════════════════════════════════
    # POST /api/checkout/media  (guest upload, session-bound)
    # ══════════════════════════════════════════════════════════════════
    @router.post("/checkout/media")
    async def checkout_media(body: GuestMediaUpload, request: Request):
        """Upload a creative under an active checkout session.

        Auth: presented `checkout_session` token instead of user auth.
        The token binds the media to the ONE order that will eventually
        consume this session — attempts to reuse the media across sessions
        are rejected in `create-intent`.
        """
        from checkout_service import (
            verify_checkout_session, ALLOWED_MEDIA_MIMES, MEDIA_MAX_BYTES,
        )
        session = await verify_checkout_session(
            db, token=body.checkout_session, screen_id=body.screen_id)
        if not session:
            raise HTTPException(401, "checkout session invalid or expired")

        # Type + size guardrails BEFORE decoding base64 (which allocates).
        if body.content_type not in ALLOWED_MEDIA_MIMES:
            raise HTTPException(400, f"media type {body.content_type!r} not allowed")
        # base64 → 4/3 * n bytes; cheap upper bound.
        est_bytes = int(len(body.data) * 3 / 4)
        if est_bytes > MEDIA_MAX_BYTES:
            raise HTTPException(413, "media exceeds size limit")

        import base64 as _b64, uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz
        try:
            payload = _b64.b64decode(body.data, validate=True)
        except Exception:
            raise HTTPException(400, "invalid base64 payload")
        if len(payload) > MEDIA_MAX_BYTES:
            raise HTTPException(413, "media exceeds size limit")

        # Write to R2 if enabled, otherwise legacy disk. Import from
        # storage.py directly (server.py just re-exports these names).
        from storage import R2_ENABLED, _ext_of, build_key, r2_put_bytes, public_url_for_key
        import os
        MEDIA_DIR = os.environ.get("MEDIA_DIR", "/app/backend/media")
        media_id = _uuid.uuid4().hex
        ext = _ext_of(body.filename, body.content_type)
        kind = "image" if body.content_type.startswith("image/") else "video"

        media_doc = {
            "id": media_id,
            "filename": body.filename,
            "content_type": body.content_type,
            "size": len(payload),
            "type": kind,
            "created_at": _dt.now(_tz.utc),
            "checkout_session_jti": session["jti"],
            "guest_email": None,       # populated at create-intent time
            "status": "ready",
        }
        if R2_ENABLED:
            key = build_key(tenant_id="guest", client_id=session["jti"],
                            campaign_id="guest-checkout", ext=ext)
            try:
                info = await r2_put_bytes(key, payload, body.content_type)
            except Exception:
                raise HTTPException(502, "media storage temporarily unavailable")
            media_doc.update({
                "storage": "r2", "r2_key": key,
                "r2_etag": info.get("etag"),
                "public_url": public_url_for_key(key),
            })
        else:
            os.makedirs(MEDIA_DIR, exist_ok=True)
            stored_name = f"{media_id}{ext or '.bin'}"
            with open(os.path.join(MEDIA_DIR, stored_name), "wb") as fh:
                fh.write(payload)
            media_doc.update({
                "storage": "legacy",
                "stored_filename": stored_name,
                "data": body.data if kind == "image" else None,
            })

        await db.media.insert_one(media_doc)
        await audit(db, action="checkout.media.upload",
                    actor_kind="guest", actor_ip=_client_ip(request),
                    request_id=_request_id(request),
                    entity_type="media", entity_id=media_id,
                    metadata={"size": len(payload),
                              "content_type": body.content_type,
                              "session_jti": session["jti"]})
        return {"media_id": media_id, "filename": body.filename,
                "size": len(payload), "type": kind,
                "storage": media_doc["storage"]}

    # ══════════════════════════════════════════════════════════════════
    # POST /api/checkout/create-intent
    # ══════════════════════════════════════════════════════════════════
    @router.post("/checkout/create-intent")
    async def checkout_create_intent(body: CreateIntentRequest, request: Request):
        if not stripe_configured_check():
            raise HTTPException(503, "payments are temporarily unavailable")
        try:
            result = await create_intent(
                db,
                quote_id=body.quote_id,
                checkout_session=body.checkout_session,
                media_id=body.media_id,
                email=body.email,
                name=body.name,
                phone=body.phone,
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

        token = await mint_order_token(db, order_id=result["order_id"])
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
    # Defense-in-depth for webhook (per user requirement, NO IP rate limit —
    # Stripe uses many source IPs and blocking them would drop valid retries):
    #   1. Body size cap (Stripe events are usually < 32 KB; we cap at 256 KB).
    #   2. HMAC-SHA256 signature verification with WEBHOOK_SECRET.
    #   3. Unique index on stripe_events.event_id → dedup.
    #   4. Fast 2xx return; heavy work would move to ARQ in Sprint 2.
    WEBHOOK_MAX_BODY = 256 * 1024   # bytes

    @router.post("/webhooks/stripe")
    async def stripe_webhook(request: Request):
        # 0) Body size cap — reject before parsing anything expensive.
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > WEBHOOK_MAX_BODY:
            log.warning("stripe webhook body too large: %s bytes", cl)
            raise HTTPException(413, "payload too large")

        # 1) Read RAW bytes (Stripe signs raw bytes; parsing first breaks it)
        raw_body = await request.body()
        if len(raw_body) > WEBHOOK_MAX_BODY:
            raise HTTPException(413, "payload too large")

        # 2) Signature verification through the provider abstraction.
        provider = get_provider()
        if not provider.supports_webhooks:
            raise HTTPException(503, "current payment provider does not accept webhooks")

        sig_header = request.headers.get("stripe-signature", "")
        try:
            event = provider.verify_webhook(raw_body=raw_body, signature=sig_header)
        except SignatureVerificationError as e:
            log.warning("webhook signature FAILED (%s)", e)
            await audit(db, action=f"{provider.name}.webhook.bad_signature",
                        actor_kind="webhook", actor_ip=_client_ip(request),
                        reason=str(e)[:200])
            raise HTTPException(400, "invalid signature")
        except ProviderError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            log.warning("webhook parse failed: %s", e)
            raise HTTPException(400, "invalid payload")

        event_id = event.id
        etype = event.type
        raw_event = event.raw

        # 3) Deduplicate: try to insert into stripe_events. If the unique
        #    index rejects us, this is a retry we already processed.
        try:
            await db.stripe_events.insert_one({
                "event_id": event_id,
                "type": etype,
                "received_at": _utcnow(),
                "processed_at": None,
                "result": None,
                "payload": raw_event,
                "provider": provider.name,
            })
        except Exception as e:
            if "duplicate" in str(e).lower() or "E11000" in str(e):
                return Response(status_code=200)
            log.exception("stripe_events insert failed")
            raise HTTPException(500, "storage error")

        # 4) Dispatch. If handler raises, mark the event failed and
        #    return non-2xx so the provider retries.
        try:
            outcome = await process_event(db, raw_event)
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
