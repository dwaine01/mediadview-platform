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
CHECKOUT_SESSION_TTL_SECONDS = int(os.environ.get("CHECKOUT_SESSION_TTL_SECONDS", "1800"))  # 30 min
DEFAULT_HOURLY_RATE_CENTS = int(os.environ.get("DEFAULT_HOURLY_RATE_CENTS", "1500"))  # $15/hr fallback
MIN_CHARGE_CENTS = 50  # Stripe minimum for USD is $0.50
MAX_HOURS_PER_CAMPAIGN = 24 * 30  # 720h cap — safety valve

MEDIA_MAX_BYTES = int(os.environ.get("GUEST_MEDIA_MAX_BYTES", str(25 * 1024 * 1024)))  # 25 MB
ALLOWED_MEDIA_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "video/mp4", "video/webm", "video/quicktime",
}

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
    start_at: Optional[str] = None,      # ISO-8601 UTC; defaults to the next full hour
    currency: str = DEFAULT_CURRENCY,
) -> dict:
    """Produce a signed price quote AND a checkout_session token.

    Args:
        start_at: optional ISO-8601 UTC datetime. Snapped to the top of
                  the hour. Defaults to now + 5 min ceilinged to the hour.

    Returns:
        {
          quote_id:            opaque signed token,
          checkout_session:    opaque signed session token (30 min),
          total_cents, currency, hourly_rate_cents, hours,
          screen_id, screen_name,
          start_at, end_at, slots:[{day, hour}, ...],
          expires_at
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

    # ── Compute the exact hour blocks (inventory keys) ──────────────
    start_dt = _parse_start_at(start_at)
    slot_specs = [_slot_spec(start_dt, i) for i in range(hours)]

    # ── Pre-check availability (best-effort — a full atomic check runs
    #    in create_intent when we insert the slot docs) ──────────────
    day_hour_pairs = [{"screen_id": screen_id, "day": s["day"], "hour": s["hour"]}
                      for s in slot_specs]
    conflict = await db.slot_reservations.find_one({"$or": day_hour_pairs})
    if conflict:
        raise ValueError(f"slot already taken ({conflict['day']} {conflict['hour']:02d}:00); "
                         "please pick a different start time")

    now = int(time.time())
    quote_payload = {
        "v": 1,
        "screen_id": screen_id,
        "hours": hours,
        "start_at": start_dt.isoformat(),
        "currency": currency,
        "hourly_rate_cents": rate,
        "total_cents": total,
        "slots": slot_specs,
        "iat": now,
        "exp": now + QUOTE_TTL_SECONDS,
        "nonce": uuid.uuid4().hex,
    }

    # Checkout session — a longer-lived token that ties uploaded media to
    # the same buyer/browser without needing an account. Media uploaded
    # under this session can only be attached to an Order that presents
    # THIS session token in create_intent.
    session_jti = uuid.uuid4().hex
    session_payload = {
        "v": 1,
        "jti": session_jti,
        "screen_id": screen_id,
        "purpose": "checkout",
        "iat": now,
        "exp": now + CHECKOUT_SESSION_TTL_SECONDS,
    }

    # Persist the session so we can revoke it. Insert BEFORE returning so
    # a race between mint + first use always sees the row.
    await db.checkout_sessions.insert_one({
        "jti": session_jti,
        "screen_id": screen_id,
        "created_at": _utcnow(),
        "expires_at": datetime.fromtimestamp(session_payload["exp"], tz=timezone.utc),
        "used_for_order": None,
        "revoked": False,
    })

    return {
        "quote_id": _sign_quote(quote_payload),
        "checkout_session": _sign_quote(session_payload),  # same HMAC scheme
        "total_cents": total,
        "currency": currency,
        "hourly_rate_cents": rate,
        "hours": hours,
        "screen_id": screen_id,
        "screen_name": screen.get("name") or screen.get("title") or "Screen",
        "start_at": start_dt.isoformat(),
        "end_at": (start_dt + timedelta(hours=hours)).isoformat(),
        "slots": slot_specs,
        "expires_at": datetime.fromtimestamp(quote_payload["exp"], tz=timezone.utc).isoformat(),
    }


def _parse_start_at(raw: Optional[str]) -> datetime:
    """Return a UTC datetime snapped to the top of the hour.

    Rules:
      · If `raw` is None → next full hour from now + 5 min buffer.
      · If given → must be within 90 days in the future, else 400.
      · Must NOT be in the past.
    """
    now = _utcnow()
    if not raw:
        # Snap "now + 5 min" up to the next hour.
        candidate = now + timedelta(minutes=5)
        candidate = candidate.replace(minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(hours=1)
        return candidate
    try:
        # Accept both "…Z" and "+00:00" forms
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("start_at must be a valid ISO-8601 UTC datetime")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if dt < now - timedelta(minutes=5):
        raise ValueError("start_at cannot be in the past")
    if dt > now + timedelta(days=90):
        raise ValueError("start_at cannot be more than 90 days in the future")
    return dt


def _slot_spec(start_dt: datetime, offset_hours: int) -> dict:
    """Return {day: 'YYYY-MM-DD', hour: 0..23} for the Nth slot from start."""
    d = start_dt + timedelta(hours=offset_hours)
    return {"day": d.strftime("%Y-%m-%d"), "hour": d.hour}


# ─────────────────────────────────────────────────────────────────────
# Slot reservation — Mongo unique index is the SOURCE OF TRUTH.
# Redis SETNX is a fast pre-filter for the happy path.
# ─────────────────────────────────────────────────────────────────────
def _slot_key(screen_id: str, nonce: str) -> str:
    return f"mediadview:slot:{screen_id}:{nonce}"


async def _reserve_all_slots(
    db: AsyncIOMotorDatabase,
    *,
    screen_id: str,
    slot_specs: list[dict],
    order_id: str,
    quote_nonce: str,
) -> tuple[bool, Optional[dict]]:
    """Atomically try to lock every (screen_id, day, hour) tuple in `slot_specs`.

    Uses `insert_many(ordered=True)` — the unique index on
    (screen_id, day, hour) causes the whole insert to fail on the FIRST
    conflict. On failure we roll back the docs already inserted.

    Returns (True, None) on success or (False, conflict_info) on failure.
    """
    now = _utcnow()
    expires = now + timedelta(seconds=SLOT_TTL_SECONDS)
    docs = [{
        "_id": str(uuid.uuid4()),
        "screen_id": screen_id,
        "day": s["day"],
        "hour": s["hour"],
        "order_id": order_id,
        "quote_nonce": quote_nonce,
        "status": "pending",       # → 'confirmed' on webhook, deleted on failure
        "confirmed": False,
        "created_at": now,
        "expires_at": expires,     # TTL sweeps pending holds after 10 min
    } for s in slot_specs]

    try:
        await db.slot_reservations.insert_many(docs, ordered=True)
        return True, None
    except Exception as e:
        # Roll back the docs that DID insert before the conflict.
        # motor raises `BulkWriteError` on partial success; find our
        # order_id-tagged rows and remove them.
        try:
            await db.slot_reservations.delete_many(
                {"order_id": order_id, "status": "pending"})
        except Exception:
            pass
        conflict_msg = str(e)
        # Extract the offending (day, hour) from the error message
        # (best-effort — only used for the 409 body).
        info = {"reason": "slot_conflict", "detail": conflict_msg[:200]}
        return False, info


async def _confirm_slots(db: AsyncIOMotorDatabase, *, order_id: str) -> None:
    """Called from the webhook when payment succeeded: promote pending
    reservations to confirmed and drop the TTL (expires_at=None)."""
    await db.slot_reservations.update_many(
        {"order_id": order_id, "status": "pending"},
        {"$set": {"status": "confirmed", "confirmed": True, "expires_at": None}},
    )


async def _release_slots(db: AsyncIOMotorDatabase, *, order_id: str) -> None:
    """Called on payment_failed / canceled — remove the pending holds so
    a different buyer can grab them immediately."""
    await db.slot_reservations.delete_many({"order_id": order_id})


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
# Checkout session verification (media binding)
# ─────────────────────────────────────────────────────────────────────
async def verify_checkout_session(db, *, token: str, screen_id: str) -> Optional[dict]:
    """Return the session payload iff signature+DB row valid AND not
    already consumed by another order AND for the same screen."""
    payload = _verify_quote(token)   # same HMAC scheme
    if not payload or payload.get("purpose") != "checkout":
        return None
    if payload.get("screen_id") != screen_id:
        return None
    row = await db.checkout_sessions.find_one({"jti": payload["jti"]})
    if not row or row.get("revoked") or row.get("used_for_order"):
        return None
    return payload


async def _validate_media_for_order(
    db: AsyncIOMotorDatabase,
    *,
    media_id: str,
    session_jti: str,
    email: str,
) -> dict:
    """Load the media doc and enforce every rule from the user's brief."""
    m = await db.media.find_one({"id": media_id})
    if not m:
        raise ValueError("media not found")
    if m.get("deleted_at"):
        raise ValueError("media was deleted")
    if m.get("status") != "ready":
        raise ValueError("media not ready yet")

    # Ownership: the media must have been uploaded under THIS session
    # (or by the same guest email as a fallback for legacy path).
    if m.get("checkout_session_jti") != session_jti and m.get("guest_email") != email.lower():
        raise ValueError("media does not belong to this checkout session")

    if (m.get("content_type") or "") not in ALLOWED_MEDIA_MIMES:
        raise ValueError(f"media type {m.get('content_type')!r} not allowed")
    if int(m.get("size", 0)) > MEDIA_MAX_BYTES:
        raise ValueError("media exceeds size limit")

    conflicting = await db.orders.find_one({
        "media_id": media_id,
        "status": {"$in": [
            "paid", "pending_review", "approved", "scheduled", "playing",
            "completed", "refund_pending", "refunded",
        ]},
    })
    if conflicting:
        raise ValueError("media already used by another order")

    return m


# ─── Order number (INV-YYYY-NNNNNN, atomic via counters) ─────────────
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
    checkout_session: str,
    email: str,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    media_id: str,                            # REQUIRED — see user brief §1
    request_id: Optional[str] = None,
    actor_ip: Optional[str] = None,
) -> dict:
    """Create an Order draft + a Stripe PaymentIntent.

    Guarantees (each enforced below and covered by smoke tests):
      · Amount is calculated by the SERVER from the signed quote — the
        browser can never influence the price.
      · The Order is inserted BEFORE the PaymentIntent, in
        `awaiting_payment` state. It never transitions to `paid` here.
      · Every hour block of the campaign is atomically inserted into
        `slot_reservations`. A single collision on the unique index
        aborts the whole thing and rolls back.
      · The media_id must belong to the presented checkout_session AND
        pass status/type/size/uniqueness checks.
      · The Stripe idempotency key is `order:{order_id}` so browser
        retries never double-charge.
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

    # 2. Validate the checkout session (must match this screen, not consumed)
    session = await verify_checkout_session(
        db, token=checkout_session, screen_id=quote["screen_id"])
    if not session:
        raise ValueError("checkout session expired or invalid — please refresh")

    # 3. Validate media (exists, ready, right session, right size/type,
    #    not attached to another paid order)
    if not media_id:
        raise ValueError("media is required — please upload a creative first")
    media = await _validate_media_for_order(
        db, media_id=media_id, session_jti=session["jti"], email=email)

    # 4. Create the Order document (source of truth, before Stripe)
    order_id = f"ord_{uuid.uuid4().hex[:24]}"
    order_number = await _next_order_number(db)
    now = _utcnow()
    slot_specs = list(quote.get("slots") or [])

    order_doc = {
        "_id": order_id,
        "id": order_id,
        "order_number": order_number,
        "screen_id": quote["screen_id"],
        "screen_name": screen.get("name") or screen.get("title") or "Screen",
        "media_id": media_id,
        "media_snapshot": {
            "filename": media.get("filename"),
            "content_type": media.get("content_type"),
            "size": media.get("size"),
            "public_url": media.get("public_url"),
            "storage": media.get("storage"),
        },
        "schedule": {
            "start_at": quote.get("start_at"),
            "end_at":   (datetime.fromisoformat(quote["start_at"]) + timedelta(hours=quote["hours"])).isoformat(),
            "slots":    slot_specs,
        },
        "hours": quote["hours"],
        "guest_email": email,
        "guest_name": name,
        "guest_phone": phone,
        "checkout_session_jti": session["jti"],
        "customer_id": None,
        "stripe_customer_id": None,
        "stripe_payment_intent_id": None,
        "stripe_latest_charge_id": None,
        "amount_cents": quote["total_cents"],
        "currency": quote["currency"],
        "hourly_rate_cents": quote["hourly_rate_cents"],
        "status": STATE_AWAITING_PAYMENT,
        "status_history": [{
            "from": None, "to": STATE_AWAITING_PAYMENT,
            "at": now, "by": "system",
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

    # 5. Atomically reserve every hour block. Mongo's unique index is the
    #    single source of truth for inventory — Redis is optional pre-cache.
    ok, conflict = await _reserve_all_slots(
        db, screen_id=quote["screen_id"], slot_specs=slot_specs,
        order_id=order_id, quote_nonce=quote["nonce"],
    )
    if not ok:
        await db.orders.update_one({"_id": order_id},
                                   {"$set": {"status": "cancelled",
                                             "updated_at": _utcnow()}})
        await audit(db, action="checkout.slot_taken", actor_kind="guest",
                    actor_ip=actor_ip, request_id=request_id,
                    entity_type="order", entity_id=order_id,
                    state_before=STATE_AWAITING_PAYMENT, state_after="cancelled",
                    reason="slot conflict", metadata=conflict or {})
        raise ValueError("one or more requested time slots were just taken — please pick a new start time")

    # 6. Consume the checkout session (mark it as used-for-this-order,
    #    so replaying it with a different media/email is impossible).
    session_updated = await db.checkout_sessions.update_one(
        {"jti": session["jti"], "used_for_order": None, "revoked": False},
        {"$set": {"used_for_order": order_id, "used_at": _utcnow()}},
    )
    if session_updated.modified_count != 1:
        # Race — another request grabbed the session first. Roll back.
        await _release_slots(db, order_id=order_id)
        await db.orders.update_one({"_id": order_id},
                                   {"$set": {"status": "cancelled",
                                             "updated_at": _utcnow()}})
        raise ValueError("checkout session already used")

    # 7. Create/reuse Stripe Customer
    try:
        stripe_customer_id = await _get_or_create_customer(
            db, email=email, name=name, phone=phone, request_id=request_id,
        )
    except stripe.error.StripeError as e:
        await _release_slots(db, order_id=order_id)
        raise RuntimeError(f"stripe error creating customer: {e.user_message or str(e)}") from e

    # 8. Move Order → payment_processing and create the PaymentIntent
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
            payment_method_types=ALLOWED_PAYMENT_METHOD_TYPES,
            capture_method="automatic",
            metadata={
                "order_id": order_id,
                "order_number": order_number,
                "screen_id": quote["screen_id"],
                "quote_nonce": quote["nonce"],
                "media_id": media_id,
                "flow": "guest_checkout",
                "sprint": "1",
            },
            receipt_email=email,
            description=f"MediAd View — {order_number} — {order_doc['screen_name']}",
            idempotency_key=idempotency_key,
        )
    except stripe.error.StripeError as e:
        await _release_slots(db, order_id=order_id)
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

    # 9. Persist PaymentIntent id + new status on the Order
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
    # Attach media to the order permanently (so admin sees the exact file)
    await db.media.update_one({"id": media_id},
                              {"$set": {"attached_order_id": order_id}})

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
