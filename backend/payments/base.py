"""
Payment provider — abstract interface + normalised DTOs.

Every method returns a plain, provider-agnostic dataclass. The rest of
the codebase (checkout_service, refund flows, admin panel) sees ONLY
these DTOs — never a `stripe.PaymentIntent` object.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
# DTOs — provider-agnostic, immutable snapshots
# ═══════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class CustomerResult:
    id: str                                 # provider-native ID (e.g. cus_...)
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None


# Canonical PaymentIntent statuses. Providers must MAP their native
# statuses onto these. The state machine only understands this set.
PI_STATUS_REQUIRES_METHOD  = "requires_payment_method"
PI_STATUS_REQUIRES_CONFIRM = "requires_confirmation"
PI_STATUS_REQUIRES_ACTION  = "requires_action"     # e.g. 3D-Secure
PI_STATUS_PROCESSING       = "processing"
PI_STATUS_SUCCEEDED        = "succeeded"
PI_STATUS_FAILED           = "failed"
PI_STATUS_CANCELED         = "canceled"

_ALL_PI_STATUSES = {
    PI_STATUS_REQUIRES_METHOD, PI_STATUS_REQUIRES_CONFIRM,
    PI_STATUS_REQUIRES_ACTION, PI_STATUS_PROCESSING,
    PI_STATUS_SUCCEEDED, PI_STATUS_FAILED, PI_STATUS_CANCELED,
}


@dataclass(frozen=True)
class PaymentIntentResult:
    id: str
    client_secret: str                      # opaque, safe to pass to frontend
    status: str                             # one of PI_STATUS_*
    amount_cents: int
    currency: str
    customer_id: Optional[str]
    metadata: dict = field(default_factory=dict)
    latest_charge_id: Optional[str] = None
    provider: str = ""                      # "stripe" | "dev"

    def __post_init__(self):
        if self.status not in _ALL_PI_STATUSES:
            raise ValueError(f"invalid status {self.status!r}; must be one of {_ALL_PI_STATUSES}")


# Canonical Refund statuses
REFUND_STATUS_PENDING   = "pending"
REFUND_STATUS_SUCCEEDED = "succeeded"
REFUND_STATUS_FAILED    = "failed"
REFUND_STATUS_CANCELED  = "canceled"

_ALL_REFUND_STATUSES = {
    REFUND_STATUS_PENDING, REFUND_STATUS_SUCCEEDED,
    REFUND_STATUS_FAILED, REFUND_STATUS_CANCELED,
}


@dataclass(frozen=True)
class RefundResult:
    id: str
    payment_intent_id: str
    amount_cents: int
    currency: str
    status: str
    reason: Optional[str] = None
    provider: str = ""

    def __post_init__(self):
        if self.status not in _ALL_REFUND_STATUSES:
            raise ValueError(f"invalid refund status {self.status!r}")


@dataclass(frozen=True)
class SubscriptionResult:
    """Sprint 2 placeholder. Signature is stable; providers can raise
    NotImplementedError until Sprint 2 needs them."""
    id: str
    customer_id: str
    status: str
    current_period_end: Optional[str] = None
    provider: str = ""


@dataclass(frozen=True)
class WebhookEvent:
    """Provider-agnostic webhook representation. `type` uses Stripe-style
    names (`payment_intent.succeeded`, `charge.refunded`, …) because they
    are the de-facto standard; non-Stripe providers translate their
    native events to these names."""
    id: str
    type: str
    object: dict                # the primary object (e.g. the PaymentIntent)
    raw: dict                   # full event payload (audited)
    provider: str = ""


# ═══════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════
class ProviderError(Exception):
    """Base class for provider-side errors. Business logic catches this,
    never provider-specific exceptions (stripe.error.CardError etc)."""

    def __init__(self, message: str, *,
                 user_message: Optional[str] = None,
                 code: Optional[str] = None,
                 retriable: bool = False):
        super().__init__(message)
        self.user_message = user_message or message
        self.code = code
        self.retriable = retriable


class ProviderNotConfigured(ProviderError):
    """Missing credentials or misconfiguration."""


class CardError(ProviderError):
    """Card was declined / bad CVC / etc — user-actionable."""


class SignatureVerificationError(ProviderError):
    """Webhook signature failed."""


# ═══════════════════════════════════════════════════════════════════
# The interface
# ═══════════════════════════════════════════════════════════════════
class PaymentProvider(ABC):
    """Abstract interface for any payment service provider."""

    # ── Identity ────────────────────────────────────────────────
    @property
    @abstractmethod
    def name(self) -> str:
        """Machine identifier: 'stripe', 'dev', 'paypal', …"""

    @property
    @abstractmethod
    def mode(self) -> str:
        """'test' | 'live' | 'dev'."""

    @property
    def publishable_key(self) -> Optional[str]:
        """Frontend-safe key. Some providers don't have one (e.g. ACH)."""
        return None

    @property
    def supports_webhooks(self) -> bool:
        """Whether this provider delivers webhook events. Dev providers
        typically don't and rely on admin-driven synthetic events."""
        return False

    @property
    def supports_3ds(self) -> bool:
        return False

    # ── Customers ───────────────────────────────────────────────
    @abstractmethod
    async def create_customer(
        self, *,
        email: str,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> CustomerResult: ...

    # ── Payments ────────────────────────────────────────────────
    @abstractmethod
    async def create_payment_intent(
        self, *,
        amount_cents: int,
        currency: str,
        customer_id: str,
        metadata: dict,
        idempotency_key: str,
        description: Optional[str] = None,
        receipt_email: Optional[str] = None,
        payment_method_types: Optional[list[str]] = None,
    ) -> PaymentIntentResult: ...

    @abstractmethod
    async def confirm_payment(
        self, *,
        payment_intent_id: str,
        payment_method_token: Optional[str] = None,
    ) -> PaymentIntentResult:
        """Server-side confirm. Optional — providers where the client
        library confirms may raise NotImplementedError."""

    @abstractmethod
    async def get_payment(self, payment_intent_id: str) -> PaymentIntentResult: ...

    # ── Refunds ─────────────────────────────────────────────────
    @abstractmethod
    async def refund_payment(
        self, *,
        payment_intent_id: str,
        amount_cents: Optional[int] = None,      # None = full refund
        reason: Optional[str] = None,
        idempotency_key: str,
    ) -> RefundResult: ...

    # ── Subscriptions (Sprint 2) ────────────────────────────────
    async def create_subscription(
        self, *,
        customer_id: str,
        price_id: str,
        metadata: Optional[dict] = None,
    ) -> SubscriptionResult:
        raise NotImplementedError(
            f"{self.name} does not support subscriptions in Sprint 1")

    # ── Webhooks ────────────────────────────────────────────────
    @abstractmethod
    def verify_webhook(self, *, raw_body: bytes, signature: str) -> WebhookEvent:
        """Verify signature and return a normalised WebhookEvent.
        Raises SignatureVerificationError on tamper/mismatch."""

    # ── Debug / dev helpers ─────────────────────────────────────
    async def simulate_event(self, *, event_type: str, payment_intent_id: str, **kwargs) -> WebhookEvent:
        """Only implemented by dev providers. Real providers must raise
        NotImplementedError to prevent operators from bypassing the real
        webhook flow in production by mistake."""
        raise NotImplementedError(
            f"{self.name} does not allow synthetic events. "
            f"Use the real webhook flow.")
