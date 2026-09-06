"""
signup_routes.py — Public customer self-signup flow.
Phase 2C P1: Creates the full SaaS stack in a single atomic* operation:
  Customer → Organization → Subscription(v2) → PricingAgreement → User

Note: Not truly atomic (no MongoDB transactions), but each step is idempotent
enough that partial failures leave no orphaned records visible to users.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from rbac import Role


def _gen_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:60] or "org"


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _ser(doc):
    if isinstance(doc, dict):
        return {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in doc.items()
            if k != "_id"
        }
    if isinstance(doc, list):
        return [_ser(d) for d in doc]
    return doc


class CustomerSignupRequest(BaseModel):
    plan_id: str = Field("starter", description="free | starter | pro | enterprise")
    billing_cycle: str = Field("monthly", description="monthly | annual")
    business_name: str = Field(..., min_length=1, max_length=300)
    contact_name: str = Field(..., min_length=1, max_length=200)
    contact_email: str = Field(..., min_length=3, max_length=320)
    contact_phone: Optional[str] = Field(None, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    org_name: Optional[str] = Field(
        None, max_length=300,
        description="Workspace/org name; defaults to business_name if omitted"
    )


def create_signup_routes(db, create_token_fn):
    router = APIRouter(tags=["Signup — Phase 2C"])

    @router.post("/api/auth/customer-signup", summary="Public customer self-signup", status_code=201)
    async def customer_signup(data: CustomerSignupRequest, request: Request):
        """
        One-shot public signup: creates Customer + Organization + Subscription(v2)
        + PricingAgreement + User, then returns a JWT access token.
        The org is marked schema_source='self_service_signup'.
        """
        email = data.contact_email.strip().lower()
        billing_cycle = data.billing_cycle.strip().lower()
        if billing_cycle not in ("monthly", "annual"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid billing_cycle '{data.billing_cycle}'. Valid: monthly, annual",
            )

        # ── Guard: no duplicate email ──────────────────────────────────────────
        existing = await db.users.find_one({"email": email})
        if existing:
            raise HTTPException(
                status_code=409,
                detail="This email is already registered. Please sign in or reset your password.",
            )

        # ── Validate + resolve plan ────────────────────────────────────────────
        VALID_PLANS = {"free", "starter", "pro", "enterprise"}
        ALIASES = {"standard": "starter"}
        plan_id = ALIASES.get(data.plan_id.strip().lower(), data.plan_id.strip().lower())
        if plan_id not in VALID_PLANS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plan_id '{data.plan_id}'. Valid: {sorted(VALID_PLANS)}",
            )

        plan_config = await db.plans.find_one({"plan_id": plan_id, "is_active": True})
        if not plan_config:
            raise HTTPException(
                status_code=400,
                detail=f"Plan '{plan_id}' is not currently available for signup.",
            )

        now = _now()

        # ── 1. Customer ────────────────────────────────────────────────────────
        customer = {
            "id": _gen_id(),
            "legal_name": data.business_name,
            "display_name": data.business_name,
            "primary_contact_name": data.contact_name,
            "primary_contact_email": email,
            "primary_contact_phone": data.contact_phone,
            "billing_contact_name": data.contact_name,
            "billing_contact_email": email,
            "billing_contact_phone": data.contact_phone,
            "status": "active",
            "source": "self_signup",
            "notes": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.customers.insert_one(customer)

        # ── 2. Organization ────────────────────────────────────────────────────
        org_name = (data.org_name or data.business_name).strip()
        base_slug = _slugify(org_name)
        slug = base_slug
        suffix = 1
        while await db.organizations.find_one({"slug": slug}):
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        org = {
            "id": _gen_id(),
            "name": org_name,
            "slug": slug,
            "plan": plan_id,
            "status": "active",
            "customer_id": customer["id"],
            "schema_source": "self_service_signup",
            "owner_user_id": None,          # updated after user creation
            "notes": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.organizations.insert_one(org)

        # ── 3. Subscription ────────────────────────────────────────────────────
        trial_days = plan_config.get("trial_days", 0) if plan_id != "free" else 0
        trial_end_iso = (
            (now + timedelta(days=trial_days)).isoformat() if trial_days > 0 else None
        )
        sub_status = "trial" if trial_days > 0 else "active"

        subscription = {
            "id": _gen_id(),
            "schema_version": 2,
            "org_id": org["id"],
            "customer_id": customer["id"],
            "status": sub_status,
            "current_pricing_agreement_id": None,   # updated below
            "billing_provider": "manual",
            "billing_customer_ref": None,
            "billing_subscription_ref": None,
            "billing_status": "pending",
            "trial_started_at": now.isoformat() if trial_days > 0 else None,
            "trial_ends_at": trial_end_iso,
            "activated_at": now if sub_status == "active" else None,
            "suspended_at": None,
            "cancelled_at": None,
            "reactivated_at": None,
            "billing_cycle": billing_cycle,
            "current_period_start": now,
            "current_period_end": now + timedelta(days=365 if billing_cycle == "annual" else 30),
            "last_synced_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.subscriptions.insert_one(subscription)

        # ── 4. PricingAgreement ────────────────────────────────────────────────
        pricing_agreement = {
            "id": _gen_id(),
            "subscription_id": subscription["id"],
            "version": 1,
            "plan_id": plan_id,
            "pricing_model": "standard",
            "screens_included": plan_config.get("screens_included", 1),
            "screens_limit": plan_config.get("screens_limit"),
            "overage_price_per_screen": plan_config.get("price_per_extra_screen"),
            "agreed_monthly_price": plan_config.get("monthly_price", 0.0),
            "agreed_annual_price": plan_config.get("annual_price", 0.0),
            "currency": "USD",
            "billing_cycle": billing_cycle,
            "discount_percent": None,
            "credit_balance": None,
            "effective_from": now.isoformat(),
            "effective_to": None,
            "created_by": "self_signup",
            "notes": f"Auto-created on self-signup — plan: {plan_id} ({billing_cycle})",
            "created_at": now,
        }
        await db.pricing_agreements.insert_one(pricing_agreement)

        # Link subscription → pricing agreement
        await db.subscriptions.update_one(
            {"id": subscription["id"]},
            {"$set": {
                "current_pricing_agreement_id": pricing_agreement["id"],
                "updated_at": now,
            }},
        )

        # ── 5. User ────────────────────────────────────────────────────────────
        user_doc = {
            "id": _gen_id(),
            "email": email,
            "name": data.contact_name,
            "company_name": data.business_name,
            "role": "customer",
            "password_hash": _hash_password(data.password),
            "rbac_role": Role.SELF_SERVICE_OWNER,
            "organization_id": org["id"],
            "active": True,
            "session_epoch": 0,
            "created_at": now,
            "updated_at": now,
        }
        await db.users.insert_one(user_doc)

        # Back-fill org owner
        await db.organizations.update_one(
            {"id": org["id"]},
            {"$set": {"owner_user_id": user_doc["id"], "updated_at": now}},
        )

        # ── 6. Access token (legacy v1) ────────────────────────────────────────
        token = create_token_fn(user_doc["id"], user_doc["role"], user_doc.get("session_epoch", 0))

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user_doc["id"],
                "email": user_doc["email"],
                "name": user_doc["name"],
                "role": user_doc["role"],
                "rbac_role": user_doc["rbac_role"],
                "organization_id": user_doc["organization_id"],
                "company_name": user_doc["company_name"],
            },
            "organization": _ser(org),
            "plan": {
                "id": plan_id,
                "display_name": plan_config.get("display_name", plan_id),
                "trial_days": trial_days,
                "monthly_price": plan_config.get("monthly_price", 0),
            },
        }

    return router
