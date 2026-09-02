"""
Stripe provider — the ONE and ONLY file in the codebase allowed to
import `stripe` (besides the webhook signature verification helper in
stripe_routes). Everything else talks to the abstract `PaymentProvider`.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import stripe
from starlette.concurrency import run_in_threadpool

from .base import (
    PI_STATUS_CANCELED,
    PI_STATUS_FAILED,
    PI_STATUS_PROCESSING,
    PI_STATUS_REQUIRES_ACTION,
    PI_STATUS_REQUIRES_CONFIRM,
    PI_STATUS_REQUIRES_METHOD,
    PI_STATUS_SUCCEEDED,
    REFUND_STATUS_CANCELED,
    REFUND_STATUS_FAILED,
    REFUND_STATUS_PENDING,
    REFUND_STATUS_SUCCEEDED,
    CardError,
    CustomerResult,
    PaymentIntentResult,
    PaymentProvider,
    ProviderError,
    ProviderNotConfigured,
    RefundResult,
    SignatureVerificationError,
    WebhookEvent,
)

log = logging.getLogger("payments.stripe")

# Map Stripe-native statuses to our canonical enum.
_PI_STATUS_MAP = {
    "requires_payment_method": PI_STATUS_REQUIRES_METHOD,
    "requires_confirmation":   PI_STATUS_REQUIRES_CONFIRM,
    "requires_action":         PI_STATUS_REQUIRES_ACTION,
    "processing":              PI_STATUS_PROCESSING,
    "succeeded":               PI_STATUS_SUCCEEDED,
    "canceled":                PI_STATUS_CANCELED,
    # Stripe uses "requires_capture" for manual capture flows; Sprint 1
    # is automatic-capture only so we don't expect it.
}


def _map_pi_status(native: str) -> str:
    mapped = _PI_STATUS_MAP.get(native)
    if mapped is None:
        # Unknown status → treat as failed so we never optimistically
        # mark an order as paid on an unexpected Stripe response.
        log.warning("unknown Stripe PaymentIntent status %r → treating as failed", native)
        return PI_STATUS_FAILED
    return mapped


_REFUND_STATUS_MAP = {
    "pending":   REFUND_STATUS_PENDING,
    "succeeded": REFUND_STATUS_SUCCEEDED,
    "failed":    REFUND_STATUS_FAILED,
    "canceled":  REFUND_STATUS_CANCELED,
    "requires_action": REFUND_STATUS_PENDING,
}


class StripeProvider(PaymentProvider):

    def __init__(self):
        # Delegate all boot-time validation + SDK init to stripe_config
        # (kept for backwards compat with existing tests). This module
        # never reads STRIPE_SECRET_KEY directly.
        from stripe_config import (
            configure_stripe,
            get_mode,
            get_publishable_key,
            is_configured,
            webhook_secret,
        )
        configure_stripe()
        if not is_configured():
            raise ProviderNotConfigured("STRIPE_SECRET_KEY not set")
        self._mode = get_mode()
        self._publishable = get_publishable_key()
        self._webhook_secret = webhook_secret()

    # ── Identity ─────────────────────────────────────────────
    @property
    def name(self) -> str: return "stripe"

    @property
    def mode(self) -> str: return self._mode

    @property
    def publishable_key(self) -> Optional[str]: return self._publishable

    @property
    def supports_webhooks(self) -> bool: return True

    @property
    def supports_3ds(self) -> bool: return True

    # ── Customers ────────────────────────────────────────────
    async def create_customer(self, *, email, name=None, phone=None,
                              metadata=None, idempotency_key=None):
        try:
            cust = await run_in_threadpool(
                stripe.Customer.create,
                email=email, name=name, phone=phone,
                metadata=metadata or {},
                idempotency_key=idempotency_key,
            )
        except stripe.error.StripeError as e:
            raise ProviderError(str(e), user_message=e.user_message or str(e)) from e
        return CustomerResult(id=cust.id, email=email, name=name, phone=phone)

    # ── Payments ─────────────────────────────────────────────
    async def create_payment_intent(self, *, amount_cents, currency, customer_id,
                                    metadata, idempotency_key,
                                    description=None, receipt_email=None,
                                    payment_method_types=None):
        try:
            pi = await run_in_threadpool(
                stripe.PaymentIntent.create,
                amount=amount_cents,
                currency=currency,
                customer=customer_id,
                payment_method_types=payment_method_types or ["card"],
                capture_method="automatic",
                metadata=metadata,
                description=description,
                receipt_email=receipt_email,
                idempotency_key=idempotency_key,
            )
        except stripe.error.CardError as e:
            raise CardError(str(e), user_message=e.user_message or str(e),
                            code=getattr(e, "code", None)) from e
        except stripe.error.StripeError as e:
            raise ProviderError(str(e), user_message=e.user_message or str(e),
                                retriable=getattr(e, "http_status", 500) >= 500) from e
        return PaymentIntentResult(
            id=pi.id,
            client_secret=pi.client_secret,
            status=_map_pi_status(pi.status),
            amount_cents=int(pi.amount),
            currency=pi.currency,
            customer_id=customer_id,
            metadata=dict(pi.metadata or {}),
            latest_charge_id=getattr(pi, "latest_charge", None),
            provider="stripe",
        )

    async def confirm_payment(self, *, payment_intent_id, payment_method_token=None):
        try:
            kwargs = {"return_url": "https://mediadview.com/return"}
            if payment_method_token:
                kwargs["payment_method"] = payment_method_token
            pi = await run_in_threadpool(
                stripe.PaymentIntent.confirm, payment_intent_id, **kwargs)
        except stripe.error.CardError as e:
            raise CardError(str(e), user_message=e.user_message or str(e),
                            code=getattr(e, "code", None)) from e
        except stripe.error.StripeError as e:
            raise ProviderError(str(e), user_message=e.user_message or str(e)) from e
        return PaymentIntentResult(
            id=pi.id, client_secret=pi.client_secret,
            status=_map_pi_status(pi.status),
            amount_cents=int(pi.amount), currency=pi.currency,
            customer_id=getattr(pi, "customer", None),
            metadata=dict(pi.metadata or {}),
            latest_charge_id=getattr(pi, "latest_charge", None),
            provider="stripe",
        )

    async def get_payment(self, payment_intent_id):
        try:
            pi = await run_in_threadpool(
                stripe.PaymentIntent.retrieve, payment_intent_id)
        except stripe.error.StripeError as e:
            raise ProviderError(str(e), user_message=str(e)) from e
        return PaymentIntentResult(
            id=pi.id, client_secret=pi.client_secret,
            status=_map_pi_status(pi.status),
            amount_cents=int(pi.amount), currency=pi.currency,
            customer_id=getattr(pi, "customer", None),
            metadata=dict(pi.metadata or {}),
            latest_charge_id=getattr(pi, "latest_charge", None),
            provider="stripe",
        )

    # ── Refunds ──────────────────────────────────────────────
    async def refund_payment(self, *, payment_intent_id, amount_cents=None,
                             reason=None, idempotency_key):
        try:
            kwargs = {"payment_intent": payment_intent_id,
                      "idempotency_key": idempotency_key}
            if amount_cents is not None:
                kwargs["amount"] = amount_cents
            if reason in ("duplicate", "fraudulent", "requested_by_customer"):
                kwargs["reason"] = reason
            r = await run_in_threadpool(stripe.Refund.create, **kwargs)
        except stripe.error.StripeError as e:
            raise ProviderError(str(e), user_message=e.user_message or str(e)) from e
        return RefundResult(
            id=r.id, payment_intent_id=payment_intent_id,
            amount_cents=int(r.amount), currency=r.currency,
            status=_REFUND_STATUS_MAP.get(r.status, REFUND_STATUS_PENDING),
            reason=r.reason, provider="stripe",
        )

    # ── Webhooks ─────────────────────────────────────────────
    def verify_webhook(self, *, raw_body, signature):
        if not self._webhook_secret:
            raise ProviderNotConfigured("STRIPE_WEBHOOK_SECRET not set")
        try:
            event = stripe.Webhook.construct_event(raw_body, signature,
                                                    self._webhook_secret)
        except stripe.error.SignatureVerificationError as e:
            raise SignatureVerificationError(str(e)) from e
        except Exception as e:
            raise ProviderError(f"webhook parse failed: {e}") from e
        return WebhookEvent(
            id=event["id"], type=event["type"],
            object=event["data"]["object"],
            raw=event.to_dict() if hasattr(event, "to_dict") else dict(event),
            provider="stripe",
        )
