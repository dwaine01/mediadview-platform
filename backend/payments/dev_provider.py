"""
LocalDevProvider — a REAL payment provider that runs in-process for
development and staging environments.

Design principles
-----------------
1. This is NOT mock data. Every customer, PaymentIntent and Refund is
   persisted in Mongo just like a real Stripe object would be — with
   stable IDs (`pi_dev_...`, `cus_dev_...`, `re_dev_...`) that are
   stored on the Order and audited exactly like the Stripe ones.

2. Payments do NOT auto-succeed. A PaymentIntent starts in
   `requires_payment_method`; only an ADMIN action from
   `/admin/orders/{id}/mark-paid` (Etapa C1) can advance it, at which
   point this provider emits a synthetic webhook event and the standard
   `stripe_events.process_event` handles the transition.

3. Signature verification of "webhooks": the LocalDevProvider does not
   expose an HTTP webhook. Synthetic events are triggered internally
   via `simulate_event()` which is called from authenticated admin
   endpoints only.

4. Refunds: same principle — admin creates a refund, the provider
   records it, emits synthetic `charge.refunded`, business logic
   transitions the order.

5. Switching to Stripe later requires ZERO business-logic changes:
   the abstract interface is identical.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient

from .base import (
    PI_STATUS_CANCELED,
    PI_STATUS_FAILED,
    PI_STATUS_REQUIRES_ACTION,
    PI_STATUS_REQUIRES_METHOD,
    PI_STATUS_SUCCEEDED,
    REFUND_STATUS_SUCCEEDED,
    CustomerResult,
    PaymentIntentResult,
    PaymentProvider,
    ProviderError,
    RefundResult,
    WebhookEvent,
)

log = logging.getLogger("payments.dev")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LocalDevProvider(PaymentProvider):

    def __init__(self):
        # Lazy Mongo client — we can't get it from FastAPI DI at import time.
        self._mongo_url = os.environ.get("MONGO_URL")
        self._db_name = os.environ.get("DB_NAME")
        self._client: Optional[AsyncIOMotorClient] = None

    def _db(self):
        if self._client is None:
            self._client = AsyncIOMotorClient(self._mongo_url)
        return self._client[self._db_name]

    # ── Identity ─────────────────────────────────────────────
    @property
    def name(self) -> str: return "dev"

    @property
    def mode(self) -> str: return "dev"

    @property
    def publishable_key(self) -> Optional[str]:
        # A stable, non-secret token used by the frontend to switch to
        # the "dev checkout" UI (no Stripe Elements — a simple
        # "complete payment" button that hits an admin-only route).
        return "pk_dev_localdevprovider"

    @property
    def supports_webhooks(self) -> bool: return False

    @property
    def supports_3ds(self) -> bool: return False

    # ── Customers ────────────────────────────────────────────
    async def create_customer(self, *, email, name=None, phone=None,
                              metadata=None, idempotency_key=None):
        db = self._db()
        # Idempotent by email (same rule as StripeProvider)
        existing = await db.dev_customers.find_one({"email": email.lower()})
        if existing:
            return CustomerResult(id=existing["id"], email=email,
                                  name=existing.get("name"), phone=existing.get("phone"))
        cid = f"cus_dev_{uuid.uuid4().hex[:24]}"
        await db.dev_customers.insert_one({
            "id": cid, "email": email.lower(), "name": name, "phone": phone,
            "metadata": metadata or {}, "created_at": _utcnow(),
            "idempotency_key": idempotency_key,
        })
        return CustomerResult(id=cid, email=email, name=name, phone=phone)

    # ── Payments ─────────────────────────────────────────────
    async def create_payment_intent(self, *, amount_cents, currency, customer_id,
                                    metadata, idempotency_key,
                                    description=None, receipt_email=None,
                                    payment_method_types=None):
        db = self._db()
        # Idempotent by idempotency_key (mirrors Stripe behaviour)
        prior = await db.dev_payment_intents.find_one({"idempotency_key": idempotency_key})
        if prior:
            return PaymentIntentResult(
                id=prior["id"], client_secret=prior["client_secret"],
                status=prior["status"], amount_cents=prior["amount_cents"],
                currency=prior["currency"], customer_id=prior["customer_id"],
                metadata=prior.get("metadata", {}),
                latest_charge_id=prior.get("latest_charge_id"),
                provider="dev",
            )
        pi_id = f"pi_dev_{uuid.uuid4().hex[:24]}"
        client_secret = f"{pi_id}_secret_{uuid.uuid4().hex[:16]}"
        doc = {
            "id": pi_id, "client_secret": client_secret,
            "status": PI_STATUS_REQUIRES_METHOD,
            "amount_cents": int(amount_cents), "currency": currency,
            "customer_id": customer_id, "metadata": metadata or {},
            "description": description, "receipt_email": receipt_email,
            "idempotency_key": idempotency_key,
            "created_at": _utcnow(),
            "latest_charge_id": None,
        }
        await db.dev_payment_intents.insert_one(doc)
        log.info("[dev] created PaymentIntent %s amount=%s", pi_id, amount_cents)
        return PaymentIntentResult(
            id=pi_id, client_secret=client_secret,
            status=PI_STATUS_REQUIRES_METHOD,
            amount_cents=int(amount_cents), currency=currency,
            customer_id=customer_id, metadata=metadata or {},
            provider="dev",
        )

    async def confirm_payment(self, *, payment_intent_id, payment_method_token=None):
        """In dev mode confirm() only moves to `processing` — success/fail
        is decided by the admin via simulate_event()."""
        db = self._db()
        r = await db.dev_payment_intents.update_one(
            {"id": payment_intent_id, "status": PI_STATUS_REQUIRES_METHOD},
            {"$set": {"status": "processing", "confirmed_at": _utcnow()}})
        pi = await db.dev_payment_intents.find_one({"id": payment_intent_id})
        if not pi:
            raise ProviderError("PaymentIntent not found")
        return PaymentIntentResult(
            id=pi["id"], client_secret=pi["client_secret"],
            status="processing",
            amount_cents=pi["amount_cents"], currency=pi["currency"],
            customer_id=pi["customer_id"], metadata=pi.get("metadata", {}),
            latest_charge_id=pi.get("latest_charge_id"),
            provider="dev",
        )

    async def get_payment(self, payment_intent_id):
        db = self._db()
        pi = await db.dev_payment_intents.find_one({"id": payment_intent_id})
        if not pi:
            raise ProviderError("PaymentIntent not found")
        return PaymentIntentResult(
            id=pi["id"], client_secret=pi["client_secret"],
            status=pi["status"],
            amount_cents=pi["amount_cents"], currency=pi["currency"],
            customer_id=pi["customer_id"], metadata=pi.get("metadata", {}),
            latest_charge_id=pi.get("latest_charge_id"),
            provider="dev",
        )

    # ── Refunds ──────────────────────────────────────────────
    async def refund_payment(self, *, payment_intent_id, amount_cents=None,
                             reason=None, idempotency_key):
        db = self._db()
        pi = await db.dev_payment_intents.find_one({"id": payment_intent_id})
        if not pi:
            raise ProviderError("PaymentIntent not found")
        if pi["status"] != PI_STATUS_SUCCEEDED:
            raise ProviderError("cannot refund a non-succeeded payment")

        prior = await db.dev_refunds.find_one({"idempotency_key": idempotency_key})
        if prior:
            return RefundResult(
                id=prior["id"], payment_intent_id=payment_intent_id,
                amount_cents=prior["amount_cents"], currency=prior["currency"],
                status=REFUND_STATUS_SUCCEEDED, reason=prior.get("reason"),
                provider="dev")

        rid = f"re_dev_{uuid.uuid4().hex[:24]}"
        amt = amount_cents if amount_cents is not None else pi["amount_cents"]
        await db.dev_refunds.insert_one({
            "id": rid, "payment_intent_id": payment_intent_id,
            "charge_id": pi.get("latest_charge_id") or f"ch_dev_{uuid.uuid4().hex[:16]}",
            "amount_cents": int(amt), "currency": pi["currency"],
            "status": REFUND_STATUS_SUCCEEDED, "reason": reason,
            "idempotency_key": idempotency_key,
            "created_at": _utcnow(),
        })
        log.info("[dev] created Refund %s pi=%s amt=%s", rid, payment_intent_id, amt)
        return RefundResult(
            id=rid, payment_intent_id=payment_intent_id,
            amount_cents=int(amt), currency=pi["currency"],
            status=REFUND_STATUS_SUCCEEDED, reason=reason, provider="dev",
        )

    # ── Webhooks (not exposed over HTTP; admin-driven only) ─
    def verify_webhook(self, *, raw_body, signature):
        # No HTTP webhook in dev mode. Return a hard failure.
        from .base import SignatureVerificationError
        raise SignatureVerificationError(
            "LocalDevProvider does not expose HTTP webhooks. "
            "Use the /admin/orders/{id}/mark-paid endpoint instead.")

    # ── Dev-only: synthetic events (equivalent to Stripe's webhook) ──
    async def simulate_event(self, *, event_type: str, payment_intent_id: str, **kwargs) -> WebhookEvent:
        """Called from authenticated admin endpoints to advance a
        PaymentIntent's state. Emits a Stripe-shaped event so
        `stripe_events.process_event` handles it without knowing this
        wasn't a real webhook."""
        db = self._db()
        pi = await db.dev_payment_intents.find_one({"id": payment_intent_id})
        if not pi:
            raise ProviderError("PaymentIntent not found")

        if event_type == "payment_intent.succeeded":
            charge_id = f"ch_dev_{uuid.uuid4().hex[:16]}"
            await db.dev_payment_intents.update_one(
                {"id": payment_intent_id},
                {"$set": {"status": PI_STATUS_SUCCEEDED,
                          "latest_charge_id": charge_id,
                          "succeeded_at": _utcnow()}})
            pi["status"] = PI_STATUS_SUCCEEDED
            pi["latest_charge_id"] = charge_id

        elif event_type == "payment_intent.payment_failed":
            await db.dev_payment_intents.update_one(
                {"id": payment_intent_id},
                {"$set": {"status": PI_STATUS_FAILED,
                          "failure_message": kwargs.get("reason", "declined")}})
            pi["status"] = PI_STATUS_FAILED

        elif event_type == "payment_intent.canceled":
            await db.dev_payment_intents.update_one(
                {"id": payment_intent_id},
                {"$set": {"status": PI_STATUS_CANCELED}})
            pi["status"] = PI_STATUS_CANCELED

        elif event_type == "charge.refunded":
            # kwargs must have {refund_id, amount_cents}
            pass

        else:
            raise ProviderError(f"unsupported simulated event: {event_type}")

        event_id = f"evt_dev_{uuid.uuid4().hex[:24]}"

        # Build a Stripe-shaped event object that stripe_events.process_event
        # can consume without modification.
        if event_type.startswith("payment_intent."):
            stripe_object = {
                "id": pi["id"],
                "object": "payment_intent",
                "amount": pi["amount_cents"],
                "currency": pi["currency"],
                "status": pi["status"],
                "latest_charge": pi.get("latest_charge_id"),
                "metadata": pi.get("metadata", {}),
                "last_payment_error": (
                    {"message": kwargs.get("reason", "declined")}
                    if event_type == "payment_intent.payment_failed" else None
                ),
            }
        elif event_type == "charge.refunded":
            refund = await db.dev_refunds.find_one({"id": kwargs["refund_id"]})
            stripe_object = {
                "id": refund["charge_id"],
                "object": "charge",
                "payment_intent": pi["id"],
                "amount_refunded": refund["amount_cents"],
                "currency": refund["currency"],
                "refunds": {"data": [{
                    "id": refund["id"],
                    "amount": refund["amount_cents"],
                    "currency": refund["currency"],
                    "status": refund["status"],
                    "reason": refund.get("reason"),
                    "created": int(time.time()),
                }]},
            }
        else:
            stripe_object = {}

        raw_event = {
            "id": event_id, "object": "event",
            "type": event_type,
            "data": {"object": stripe_object},
            "created": int(time.time()),
            "api_version": "dev",
        }

        # Feed to the same processor that handles real Stripe webhooks.
        # Import here to avoid circular imports at module load.
        from stripe_events import process_event
        # Also insert into stripe_events collection for dedup + audit
        try:
            await db.stripe_events.insert_one({
                "event_id": event_id,
                "type": event_type,
                "received_at": _utcnow(),
                "processed_at": None,
                "result": None,
                "payload": raw_event,
            })
        except Exception:
            pass

        outcome = await process_event(db, raw_event)
        await db.stripe_events.update_one(
            {"event_id": event_id},
            {"$set": {"processed_at": _utcnow(),
                      "result": outcome.get("result")}})

        return WebhookEvent(id=event_id, type=event_type,
                            object=stripe_object, raw=raw_event, provider="dev")
