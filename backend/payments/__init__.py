"""
MediAd View — Payment providers package.

Design goal:
    Stripe (or any future PSP) is an IMPLEMENTATION DETAIL.
    The business logic in `checkout_service` and `stripe_events` (which
    should be renamed to `payment_events` in Sprint 2) ONLY talks to
    the abstract `PaymentProvider` interface — never to `stripe.*`.

    Adding a new provider (PayPal, Authorize.Net, ACH, Adyen…) means
    dropping one new file under this package and updating the factory.
    The rest of the app doesn't care.

Public API:
    from payments import get_provider          # returns a singleton
    from payments.base import (
        PaymentProvider,
        CustomerResult, PaymentIntentResult, RefundResult, WebhookEvent,
    )

Selection is driven by env `PAYMENT_PROVIDER`:
    · "stripe" (default when STRIPE_SECRET_KEY is set)
    · "dev"    (LocalDevProvider — no external network, admin-driven)
    · empty    (auto-detect: stripe if configured, else dev)
"""
from __future__ import annotations
import logging
import os
from typing import Optional

from .base import (
    PaymentProvider,
    CustomerResult,
    PaymentIntentResult,
    RefundResult,
    WebhookEvent,
    ProviderError,
    ProviderNotConfigured,
    CardError,
    SignatureVerificationError,
    SubscriptionResult,
)

log = logging.getLogger("payments")

_provider: Optional[PaymentProvider] = None


def get_provider() -> PaymentProvider:
    """Return the singleton payment provider.

    Idempotent — safe to call from any request handler.
    """
    global _provider
    if _provider is not None:
        return _provider

    preference = (os.environ.get("PAYMENT_PROVIDER") or "").strip().lower()
    stripe_key = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()

    if preference == "stripe" or (not preference and stripe_key):
        # Explicit stripe OR auto-detect when a key is present.
        from .stripe_provider import StripeProvider
        try:
            _provider = StripeProvider()
            log.info("PaymentProvider = stripe (mode=%s)", _provider.mode)
            return _provider
        except ProviderNotConfigured as e:
            log.warning("Stripe provider not configured (%s) → falling back to dev", e)

    if preference == "dev" or preference == "":
        from .dev_provider import LocalDevProvider
        _provider = LocalDevProvider()
        log.info("PaymentProvider = dev (LocalDevProvider — admin-driven)")
        return _provider

    raise ValueError(f"Unknown PAYMENT_PROVIDER={preference!r}")


def reset_provider_for_tests() -> None:
    """Test hook — DO NOT call in production."""
    global _provider
    _provider = None


__all__ = [
    "PaymentProvider",
    "CustomerResult", "PaymentIntentResult", "RefundResult", "WebhookEvent",
    "SubscriptionResult", "ProviderError", "ProviderNotConfigured",
    "CardError", "SignatureVerificationError",
    "get_provider", "reset_provider_for_tests",
]
