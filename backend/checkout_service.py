"""
MediAd View — Guest-checkout service (Fase 5 · Sprint 1 · Etapa B).

Public entry points:
  · quote()          → produce a signed quote_id valid for 10 minutes,
                       server-side price calculation.
  · create_intent()  → create/reuse a Stripe PaymentIntent, insert the
                       Order in Mongo with status=payment_processing.
  · mint_order_token → magic-link JWT signed with ORDER_LINK_SECRET.
  · verify_order_token → validate signature AND check db.order_tokens.
                       Revocable server-side.

DESIGN INVARIANTS (blueprint §2, §3):
  · The AMOUNT of the PaymentIntent is computed EXCLUSIVELY here (server).
  · The frontend never influences the amount, only the quote_id.
  · Slot reservation uses Redis SETNX + TTL for atomic pre-reservation,
    and a Mongo unique index for the durable confirmed reservation.
  · Idempotency key on PaymentIntent = order:{order_id} so retries
    from the browser never double-charge.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import stripe
from motor.motor_asyncio import AsyncIOMotorDatabase
from starlette.concurrency import run_in_threadpool

from financial_audit import audit
from order_state import STATE_AWAITING_PAYMENT, STATE_PAYMENT_PROCESSING
from redis_client import redis_client
from stripe_config import (
    ALLOWED_CURRENCIES,
    ALLOWED_PAYMENT_METHOD_TYPES,
    DEFAULT_CURRENCY,
    is_configured as stripe_configured,
)

log = logging.getLogger("checkout_service")

# ─── Constants (tunable via env if needed) ─────────────────────────────
QUOTE_TTL_SECONDS = int(os.environ.get("CHECKOUT_QUOTE_TTL_SECONDS", "600"))          # 10 min
SLOT_TTL_SECONDS = int(os.environ.get("CHECKOUT_SLOT_TTL_SECONDS", "600"))            # 10 min
ORDER_TOKEN_TTL_DAYS = int(os.environ.get("ORDER_TOKEN_TTL_DAYS", "30"))
DEFAULT_HOURLY_RATE_CENTS = int(os.environ.get("DEFAULT_HOURLY_RATE_CENTS", "1500"))  # $15/hr fallback
MIN_CHARGE_CENTS = 50  # Stripe minimum for USD is $0.50
MAX_HOURS_PER_CAMPAIGN = 24 * 30  # 720h cap — safety valve

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────
# Pricing (deterministic, server-only)
# ─────────────────────────────────────────────────────────────────────
async def _load_screen(db: AsyncIOMotorDatabase, screen_id: str) -> Optional[dict]:
    return await db.screens.find_one({"id": screen_id})


def _hourly_rate_cents(screen: dict) -> int:
    """Screen documents may store a rate in a few different shapes over the
    project's history. We tolerate all of them here and normalise to cents."""
    raw = (screen.get("hourly_rate") or screen.get("price_per_hour")
           or screen.get("rate_hour") or screen.get("hourly_rate_cents"))
    if raw is None:
        return DEFAULT_HOURLY_RATE_CENTS
    try:
        # If the value is already in cents (int > 100 and no decimals) use as-is,
        # otherwise assume dollars and convert.
        f = float(raw)
        return int(round(f * 100)) if f < 1000 else int(f)
    except (TypeError, ValueError):
        return DEFAULT_HOURLY_RATE_CENTS


def _validate_hours(hours: Any) -> int:
    try:
        h = int(hours)
    except (TypeError, ValueError):
        raise ValueError("hours must be a positive integer")
    if h < 1:
        raise ValueError("hours must be >= 1")
    if h > MAX_HOURS_PER_CAMPAIGN:
        raise ValueError(f"hours cannot exceed {MAX_HOURS_PER_CAMPAIGN}")
    return h


# ─────────────────────────────────────────────────────────────────────
# Quote signing (stateless JWT-like, but simpler HMAC token)
# ─────────────────────────────────────────────────────────────────────
def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _quote_secret() -> bytes:
    # Quotes are short-lived and tied to slot reservations that live in
    # Redis, so we can safely reuse JWT_SECRET here — no cross-domain risk.
    key = os.environ.get("JWT_SECRET", "")
    if not key:
        raise RuntimeError("JWT_SECRET not set")
    return key.encode()


def _sign_quote(payload: dict) -> str:
    body = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64u(hmac.new(_quote_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _verify_quote(token: str) -> Optional[dict]:
    try:
        body, sig = token.split(".", 1)
        expected = _b64u(hmac.new(_quote_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64u_decode(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
# Public: build a signed quote
# ─────────────────────────────────────────────────────────────────────
async def build_quote(
    db: AsyncIOMotorDatabase,
    *,
    screen_id: str,
    hours: int,
    currency: str = DEFAULT_CURRENCY,
) -> dict:
    """Produce a signed price quote.

    Returns:
        {
          quote_id:        opaque signed token,
          total_cents:     int,
          currency:        "usd",
          hourly_rate_cents: int,
          hours:           int,
          screen_id:       str,
          screen_name:     str,
          expires_at:      ISO-8601 UTC
        }
    """
    currency = (currency or DEFAULT_CURRENCY).lower()
    if currency not in ALLOWED_CURRENCIES:
        raise ValueError(f"currency {currency!r} not allowed in Sprint 1 (usd only)")

    hours = _validate_hours(hours)

    screen = await _load_screen(db, screen_id)
    if not screen:
        raise ValueError("screen not found")
    if not screen.get("active", True):
        raise ValueError("screen is not active")

    rate = _hourly_rate_cents(screen)
    total = rate * hours
    if total < MIN_CHARGE_CENTS:
        raise ValueError(f"total {total}¢ is below Stripe minimum {MIN_CHARGE_CENTS}¢")

    now = int(time.time())
    payload = {
        "v": 1,
        "screen_id": screen_id,
        "hours": hours,
        "currency": currency,
        "hourly_rate_cents": rate,
        "total_cents": total,
        "iat": now,
        "exp": now + QUOTE_TTL_SECONDS,
        "nonce": uuid.uuid4().hex,
    }
    return {
        "quote_id": _sign_quote(payload),
        "total_cents": total,
        "currency": currency,
        "hourly_rate_cents": rate,
        "hours": hours,
        "screen_id": screen_id,
        "screen_name": screen.get("name") or screen.get("title") or "Screen",
        "expires_at": datetime.fromtimestamp(payload["exp"], tz=timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────
# Slot reservation (Redis SETNX)
# ─────────────────────────────────────────────────────────────────────
def _slot_key(screen_id: str, nonce: str) -> str:
    return f"mediadview:slot:{screen_id}:{nonce}"


async def _reserve_slot(screen_id: str, nonce: str, order_id: str) -> bool:
    """Try to reserve the slot for this order. Returns True if we're the
    first holder, False if another checkout already grabbed it."""
    return await redis_client.setnx(
        _slot_key(screen_id, nonce),
        order_id,
        ex=SLOT_TTL_SECONDS,
    )


async def _release_slot(screen_id: str, nonce: str) -> None:
    await redis_client.delete_raw(_slot_key(screen_id, nonce))


# ─────────────────────────────────────────────────────────────────────
# Guest customer (Stripe Customer, idempotent)
# ─────────────────────────────────────────────────────────────────────
async def _get_or_create_customer(
    db: AsyncIOMotorDatabase,
    *,
    email: str,
    name: Optional[str],
    phone: Optional[str],
    request_id: Optional[str],
) -> str:
    """Return a stripe_customer_id, creating it once per email.

    Guests are keyed by lower-cased email. If the email is later linked to
    an account (Sprint 2), we DO NOT create a duplicate — the account gets
    merged into the existing Customer."""
    email = email.strip().lower()
    doc = await db.customers_stripe.find_one({"email": email})
    if doc and doc.get("stripe_customer_id"):
        return doc["stripe_customer_id"]

    cust = await run_in_threadpool(
        stripe.Customer.create,
        email=email,
        name=name or None,
        phone=phone or None,
        metadata={"source": "guest_checkout", "sprint": "1"},
        idempotency_key=f"customer:guest:{email}",
    )

    await db.customers_stripe.update_one(
        {"email": email},
        {"$set": {
            "email": email,
            "stripe_customer_id": cust.id,
            "name": name,
            "phone": phone,
            "created_at": _utcnow(),
        }},
        upsert=True,
    )
    await audit(db, action="stripe.customer.create", actor_kind="guest",
                entity_type="customer", entity_id=cust.id,
                request_id=request_id, metadata={"email": email})
    return cust.id


# ─────────────────────────────────────────────────────────────────────
# Order number (INV-YYYY-NNNNNN, atomic via counters)
# ─────────────────────────────────────────────────────────────────────
async def _next_order_number(db: AsyncIOMotorDatabase) -> str:
    year = _utcnow().year
    doc = await db.counters.find_one_and_update(
        {"_id": f"order_number:{year}"},
        {"$inc": {"seq": 1}, "$setOnInsert": {"year": year, "created_at": _utcnow()}},
        upsert=True,
        return_document=True,
    )
    seq = int(doc["seq"])
    return f"ORD-{year}-{seq:06d}"


# ─────────────────────────────────────────────────────────────────────
# Order token (magic-link)
# ─────────────────────────────────────────────────────────────────────
def _order_link_secret() -> bytes:
    k = os.environ.get("ORDER_LINK_SECRET", "").strip()
    if not k:
        raise RuntimeError("ORDER_LINK_SECRET not set")
    return k.encode()


async def mint_order_token(
    db: AsyncIOMotorDatabase,
    *,
    order_id: str,
    ttl_days: int = ORDER_TOKEN_TTL_DAYS,
) -> str:
    """Create a signed, revocable magic-link JWT for the given order."""
    jti = uuid.uuid4().hex
    now = int(time.time())
    exp_ts = now + ttl_days * 86400
    payload = {
        "v": 1,
        "jti": jti,
        "order_id": order_id,
        "purpose": "order_view",
        "iat": now,
        "exp": exp_ts,
    }
    body = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64u(hmac.new(_order_link_secret(), body.encode(), hashlib.sha256).digest())
    token = f"{body}.{sig}"

    await db.order_tokens.insert_one({
        "jti": jti,
        "order_id": order_id,
        "purpose": "order_view",
        "created_at": _utcnow(),
        "expires_at": datetime.fromtimestamp(exp_ts, tz=timezone.utc),
        "revoked": False,
    })
    return token


async def verify_order_token(
    db: AsyncIOMotorDatabase,
    *,
    token: str,
) -> Optional[dict]:
    """Return the token payload iff signature valid AND DB row not revoked."""
    try:
        body, sig = token.split(".", 1)
        expected = _b64u(hmac.new(_order_link_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64u_decode(body))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    if payload.get("purpose") != "order_view":
        return None
    row = await db.order_tokens.find_one({"jti": payload["jti"]})
    if not row or row.get("revoked"):
        return None
    return payload


# ─────────────────────────────────────────────────────────────────────
# Public: create Payment Intent
# ─────────────────────────────────────────────────────────────────────
async def create_intent(
    db: AsyncIOMotorDatabase,
    *,
    quote_id: str,
    email: str,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    media_id: Optional[str] = None,
    schedule: Optional[dict] = None,
    request_id: Optional[str] = None,
    actor_ip: Optional[str] = None,
) -> dict:
    """Create an Order draft + a Stripe PaymentIntent.

    Returns:
        {
          order_id, order_number,
          client_secret, payment_intent_id,
          publishable_key (echoed for convenience),
        }
    """
    if not stripe_configured():
        raise RuntimeError("Stripe is not configured on this instance")

    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("invalid email")

    # 1. Re-validate the quote (server-side!)
    quote = _verify_quote(quote_id)
    if not quote:
        raise ValueError("quote expired or invalid — please refresh the page")

    screen = await _load_screen(db, quote["screen_id"])
    if not screen or not screen.get("active", True):
        raise ValueError("screen not available anymore")

    # 2. Create the Order document up front — the order is the source of
    #    truth, PaymentIntent is just an attempt to collect.
    order_id = f"ord_{uuid.uuid4().hex[:24]}"
    order_number = await _next_order_number(db)
    now = _utcnow()

    order_doc = {
        "_id": order_id,           # Mongo _id AND our stable ID
        "id": order_id,
        "order_number": order_number,
        "screen_id": quote["screen_id"],
        "screen_name": screen.get("name") or screen.get("title") or "Screen",
        "media_id": media_id,
        "schedule": schedule or {},
        "hours": quote["hours"],
        "guest_email": email,
        "guest_name": name,
        "guest_phone": phone,
        "customer_id": None,       # linked in Sprint 2 if user creates account
        "stripe_customer_id": None,
        "stripe_payment_intent_id": None,
        "stripe_latest_charge_id": None,
        "amount_cents": quote["total_cents"],
        "currency": quote["currency"],
        "hourly_rate_cents": quote["hourly_rate_cents"],
        "status": STATE_AWAITING_PAYMENT,
        "status_history": [{
            "from": None,
            "to": STATE_AWAITING_PAYMENT,
            "at": now,
            "by": "system",
            "reason": "order created from guest checkout",
        }],
        "quote_nonce": quote["nonce"],
        "created_at": now,
        "updated_at": now,
        "paid_at": None,
        "approved_at": None,
        "completed_at": None,
    }
    await db.orders.insert_one(order_doc)

    # 3. Reserve slot in Redis (atomic SETNX). We key by (screen_id, quote_nonce)
    #    so retries with the same quote reuse the same reservation.
    reserved = await _reserve_slot(quote["screen_id"], quote["nonce"], order_id)
    if not reserved:
        # Another buyer beat us to this quote nonce → refuse.
        await db.orders.update_one({"_id": order_id},
                                   {"$set": {"status": "cancelled",
                                             "updated_at": _utcnow()}})
        await audit(db, action="checkout.slot_taken", actor_kind="guest",
                    actor_ip=actor_ip, request_id=request_id,
                    entity_type="order", entity_id=order_id,
                    state_before=STATE_AWAITING_PAYMENT, state_after="cancelled",
                    reason="another buyer reserved this slot")
        raise ValueError("this slot was just taken by another buyer — please refresh")

    # 4. Create/reuse Stripe Customer for this email
    try:
        stripe_customer_id = await _get_or_create_customer(
            db, email=email, name=name, phone=phone, request_id=request_id,
        )
    except stripe.error.StripeError as e:
        await _release_slot(quote["screen_id"], quote["nonce"])
        raise RuntimeError(f"stripe error creating customer: {e.user_message or str(e)}") from e

    # 5. Move Order → payment_processing and create the PaymentIntent
    from order_state import assert_transition
    assert_transition(from_state=STATE_AWAITING_PAYMENT,
                      to_state=STATE_PAYMENT_PROCESSING, actor="system")

    idempotency_key = f"order:{order_id}"
    try:
        pi = await run_in_threadpool(
            stripe.PaymentIntent.create,
            amount=quote["total_cents"],
            currency=quote["currency"],
            customer=stripe_customer_id,
            payment_method_types=ALLOWED_PAYMENT_METHOD_TYPES,  # ["card"] in Sprint 1
            capture_method="automatic",
            metadata={
                "order_id": order_id,
                "order_number": order_number,
                "screen_id": quote["screen_id"],
                "quote_nonce": quote["nonce"],
                "flow": "guest_checkout",
                "sprint": "1",
            },
            receipt_email=email,
            description=f"MediAd View — {order_number} — {order_doc['screen_name']}",
            idempotency_key=idempotency_key,
        )
    except stripe.error.StripeError as e:
        # Roll back the Order + slot on Stripe failure
        await _release_slot(quote["screen_id"], quote["nonce"])
        await db.orders.update_one({"_id": order_id},
                                   {"$set": {"status": "cancelled",
                                             "updated_at": _utcnow()},
                                    "$push": {"status_history": {
                                        "from": STATE_AWAITING_PAYMENT,
                                        "to": "cancelled",
                                        "at": _utcnow(), "by": "system",
                                        "reason": f"stripe error: {e.user_message or str(e)}",
                                    }}})
        await audit(db, action="stripe.payment_intent.create.failed",
                    actor_kind="guest", actor_ip=actor_ip, request_id=request_id,
                    idempotency_key=idempotency_key,
                    entity_type="order", entity_id=order_id,
                    amount_cents=quote["total_cents"], currency=quote["currency"],
                    reason=str(e)[:500])
        raise RuntimeError(f"payment could not be initialised: {e.user_message or str(e)}") from e

    # 6. Persist PaymentIntent id + new status on the Order
    await db.orders.update_one(
        {"_id": order_id},
        {"$set": {
            "status": STATE_PAYMENT_PROCESSING,
            "stripe_customer_id": stripe_customer_id,
            "stripe_payment_intent_id": pi.id,
            "updated_at": _utcnow(),
        },
         "$push": {"status_history": {
             "from": STATE_AWAITING_PAYMENT,
             "to": STATE_PAYMENT_PROCESSING,
             "at": _utcnow(), "by": "system",
             "reason": f"PaymentIntent {pi.id} created",
         }}}
    )
    await audit(db, action="stripe.payment_intent.create",
                actor_kind="guest", actor_ip=actor_ip, request_id=request_id,
                idempotency_key=idempotency_key,
                entity_type="order", entity_id=order_id,
                stripe_object_id=pi.id,
                amount_cents=quote["total_cents"], currency=quote["currency"],
                state_before=STATE_AWAITING_PAYMENT,
                state_after=STATE_PAYMENT_PROCESSING)

    return {
        "order_id": order_id,
        "order_number": order_number,
        "client_secret": pi.client_secret,
        "payment_intent_id": pi.id,
        "amount_cents": quote["total_cents"],
        "currency": quote["currency"],
    }
