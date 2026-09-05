"""
domain_saas/models.py — Phase 2C-1A Domain Models
===================================================
Pydantic request/response bodies for the SaaS CRM domain.

Canonical plan_id namespace : free | starter | pro | enterprise
Legacy compatibility alias  : standard → starter

CONSTRAINTS (enforced in code):
- Lead creation does NOT automatically create users/orgs/subscriptions/billing records.
- Customer is NOT the technical tenant boundary (Organization is).
- MRR is NEVER stored here; it must always be derived from Subscription + PricingAgreement.
- PricingAgreement is effectively immutable after activation.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, validator

# ── Plan normalization ─────────────────────────────────────────────────────
VALID_PLAN_IDS: frozenset[str] = frozenset({"free", "starter", "pro", "enterprise"})
LEGACY_PLAN_ALIASES: dict[str, str] = {"standard": "starter"}


def normalize_plan_id(raw: str) -> str:
    """Normalize plan_id: lowercase, resolve legacy alias, validate membership."""
    if not raw:
        raise ValueError("plan_id cannot be empty")
    lowered = raw.strip().lower()
    resolved = LEGACY_PLAN_ALIASES.get(lowered, lowered)
    if resolved not in VALID_PLAN_IDS:
        raise ValueError(
            f"Invalid plan_id {raw!r}. "
            f"Valid values: {sorted(VALID_PLAN_IDS)}. "
            f"Legacy aliases accepted: {list(LEGACY_PLAN_ALIASES.keys())}"
        )
    return resolved


# ══════════════════════════════════════════════════════════════════
# LEAD
# ══════════════════════════════════════════════════════════════════

class LeadStatus(str, Enum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    trial = "trial"
    converted = "converted"
    lost = "lost"


class LeadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    business_name: str = Field(..., min_length=1, max_length=300)
    email: str = Field(..., min_length=3, max_length=320)
    phone: Optional[str] = Field(None, max_length=50)
    business_type: Optional[str] = Field(None, max_length=100)
    estimated_screens: Optional[int] = Field(None, ge=0)
    desired_plan: Optional[str] = Field(None, max_length=50)
    source: Optional[str] = Field(None, max_length=100)
    signup_date: Optional[str] = Field(None, description="ISO date YYYY-MM-DD")
    notes: Optional[str] = Field(None, max_length=2000)

    @validator("desired_plan", pre=True, always=False)
    def _validate_desired_plan(cls, v):  # noqa: N805
        if v is None:
            return v
        try:
            return normalize_plan_id(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class LeadUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    business_name: Optional[str] = Field(None, min_length=1, max_length=300)
    email: Optional[str] = Field(None, min_length=3, max_length=320)
    phone: Optional[str] = Field(None, max_length=50)
    business_type: Optional[str] = Field(None, max_length=100)
    estimated_screens: Optional[int] = Field(None, ge=0)
    desired_plan: Optional[str] = Field(None, max_length=50)
    source: Optional[str] = Field(None, max_length=100)
    status: Optional[LeadStatus] = None
    signup_date: Optional[str] = Field(None)
    notes: Optional[str] = Field(None, max_length=2000)

    @validator("desired_plan", pre=True, always=False)
    def _validate_desired_plan(cls, v):  # noqa: N805
        if v is None:
            return v
        try:
            return normalize_plan_id(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


# ══════════════════════════════════════════════════════════════════
# CUSTOMER
# ══════════════════════════════════════════════════════════════════

class CustomerStatus(str, Enum):
    prospect = "prospect"
    active = "active"
    suspended = "suspended"
    churned = "churned"


class CustomerCreate(BaseModel):
    legal_name: str = Field(..., min_length=1, max_length=300)
    display_name: str = Field(..., min_length=1, max_length=300)
    primary_contact_name: Optional[str] = Field(None, max_length=200)
    primary_contact_email: Optional[str] = Field(None, max_length=320)
    primary_contact_phone: Optional[str] = Field(None, max_length=50)
    billing_contact_name: Optional[str] = Field(None, max_length=200)
    billing_contact_email: Optional[str] = Field(None, max_length=320)
    billing_contact_phone: Optional[str] = Field(None, max_length=50)
    status: CustomerStatus = CustomerStatus.prospect
    notes: Optional[str] = Field(None, max_length=2000)


class CustomerUpdate(BaseModel):
    legal_name: Optional[str] = Field(None, min_length=1, max_length=300)
    display_name: Optional[str] = Field(None, min_length=1, max_length=300)
    primary_contact_name: Optional[str] = Field(None, max_length=200)
    primary_contact_email: Optional[str] = Field(None, max_length=320)
    primary_contact_phone: Optional[str] = Field(None, max_length=50)
    billing_contact_name: Optional[str] = Field(None, max_length=200)
    billing_contact_email: Optional[str] = Field(None, max_length=320)
    billing_contact_phone: Optional[str] = Field(None, max_length=50)
    status: Optional[CustomerStatus] = None
    notes: Optional[str] = Field(None, max_length=2000)


# ══════════════════════════════════════════════════════════════════
# ORGANIZATION (CRM-linked creation only — additive fields)
# ══════════════════════════════════════════════════════════════════

class OrgForCustomerCreate(BaseModel):
    """Request body to create an Organization linked to a Customer.
    Organization continues to be the technical SaaS tenant boundary.
    customer_id is stored as an additive field; organization_id terminology preserved.
    Designed to allow future Customer 1:N Organizations without schema changes.
    """
    name: str = Field(..., min_length=1, max_length=300)
    slug: Optional[str] = Field(
        None, min_length=2, max_length=60,
        pattern=r"^[a-z0-9-]+$",
        description="URL-safe slug; auto-generated from name if omitted"
    )
    plan: str = Field("starter", description="Canonical plan_id")
    notes: Optional[str] = Field(None, max_length=2000)

    @validator("plan", pre=True, always=True)
    def _validate_plan(cls, v):  # noqa: N805
        return normalize_plan_id(v or "starter")


# ══════════════════════════════════════════════════════════════════
# SUBSCRIPTION
# ══════════════════════════════════════════════════════════════════

class SubscriptionStatus(str, Enum):
    trial = "trial"
    active = "active"
    suspended = "suspended"
    cancelled = "cancelled"
    past_due = "past_due"


class SubscriptionCreate(BaseModel):
    """Create a new Subscription for an org/customer pair.
    Subscription represents lifecycle and access state only.
    Pricing terms belong to PricingAgreement.
    """
    org_id: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)
    status: SubscriptionStatus = SubscriptionStatus.trial
    billing_provider: Optional[str] = Field(
        None, max_length=50,
        description="e.g. 'stripe', 'manual', 'invoice'"
    )
    billing_customer_ref: Optional[str] = Field(None, max_length=200)
    billing_subscription_ref: Optional[str] = Field(None, max_length=200)
    billing_status: Optional[str] = Field(None, max_length=50)
    trial_started_at: Optional[str] = Field(None, description="ISO datetime")
    trial_ends_at: Optional[str] = Field(None, description="ISO datetime")


class SubscriptionStatusUpdate(BaseModel):
    """Update subscription lifecycle state."""
    status: SubscriptionStatus
    note: Optional[str] = Field(None, max_length=500)


# ══════════════════════════════════════════════════════════════════
# PRICING AGREEMENT
# ══════════════════════════════════════════════════════════════════

class PricingModelEnum(str, Enum):
    standard = "standard"
    custom = "custom"


class BillingCycle(str, Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"


class PricingAgreementCreate(BaseModel):
    """Create a versioned PricingAgreement for a Subscription.
    PricingAgreement is the immutable commercial contract/terms layer.
    It should NOT be modified after activation — create a new version instead.
    agreed_monthly_price is the authoritative MRR source; never stored on Subscription.
    """
    subscription_id: str = Field(..., min_length=1)
    plan_id: str = Field(..., description="Canonical plan_id")
    pricing_model: PricingModelEnum = PricingModelEnum.standard
    screens_included: int = Field(1, ge=0)
    screens_limit: Optional[int] = Field(None, ge=0)
    overage_price_per_screen: Optional[float] = Field(None, ge=0.0)
    agreed_monthly_price: float = Field(..., ge=0.0)
    currency: str = Field("USD", max_length=3)
    billing_cycle: BillingCycle = BillingCycle.monthly
    discount_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    credit_balance: Optional[float] = Field(None, ge=0.0)
    effective_from: str = Field(..., description="ISO datetime when this agreement takes effect")
    effective_to: Optional[str] = Field(
        None, description="ISO datetime when agreement expires; None = open-ended"
    )
    notes: Optional[str] = Field(None, max_length=2000)

    @validator("plan_id", pre=True, always=True)
    def _validate_plan_id(cls, v):  # noqa: N805
        try:
            return normalize_plan_id(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
