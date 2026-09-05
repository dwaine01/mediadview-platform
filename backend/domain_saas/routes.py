"""
domain_saas/routes.py — Phase 2C-1A Admin CRM Routes
=====================================================
Additive admin-side endpoints for the SaaS domain foundation.

All routes are under /api/admin/crm/
All routes require at minimum require_admin (SUPER_ADMIN, MEDIAVIEW_ADMIN, SUPPORT).

STRICT CONSTRAINTS:
- NO modifications to existing collections (screens, campaigns, playlists, menus, ad_campaigns).
- NO production data migration.
- NO legacy record reclassification.
- NO Stripe integration.
- NO public signup automation.
- NO automatic user/screen provisioning.

Collections used (all additive):
  leads               — new
  customers           — new
  subscriptions       — additive (Phase 2C documents carry customer_id + schema_version=2)
  pricing_agreements  — new
  organizations       — additive only: new orgs linked to customer_id via CRM path
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from domain_saas.models import (
    CustomerCreate,
    CustomerUpdate,
    LeadCreate,
    LeadStatus,
    LeadUpdate,
    OrgForCustomerCreate,
    PricingAgreementCreate,
    SubscriptionCreate,
    SubscriptionStatus,
    SubscriptionStatusUpdate,
    normalize_plan_id,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _gen_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


def _ser(doc: dict | None) -> dict | None:
    """Minimal serializer: remove _id, stringify ObjectId, isoformat datetime."""
    if doc is None:
        return None
    result = {}
    for key, value in doc.items():
        if key == "_id":
            continue
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, dict):
            result[key] = _ser(value)
        elif isinstance(value, list):
            result[key] = [_ser(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value
    return result


def _slugify(name: str) -> str:
    """Generate a URL-safe slug from a name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:60] or "org"


# ── router factory ────────────────────────────────────────────────────────────

def create_saas_crm_routes(db, get_current_user, require_admin, require_superadmin):
    """
    Returns a FastAPI APIRouter with all Phase 2C-1A admin CRM endpoints.
    db              — AsyncIOMotorDatabase instance (injected from server.py)
    require_admin   — dependency for SUPER_ADMIN | MEDIAVIEW_ADMIN | SUPPORT
    require_superadmin — dependency for SUPER_ADMIN only (create/delete ops)
    """
    router = APIRouter(prefix="/api/admin/crm", tags=["CRM — Phase 2C-1A"])

    # ══════════════════════════════════════════════════════════════════════════
    # LEADS
    # ══════════════════════════════════════════════════════════════════════════

    @router.get("/leads", summary="List all leads")
    async def list_leads(
        status: Optional[str] = None,
        admin=Depends(require_admin),
    ):
        """Return all leads, optionally filtered by status."""
        query: dict = {}
        if status:
            valid_statuses = [s.value for s in LeadStatus]
            if status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status {status!r}. Valid: {valid_statuses}",
                )
            query["status"] = status
        docs = await db.leads.find(query).sort("created_at", -1).to_list(1000)
        return [_ser(d) for d in docs]

    @router.post("/leads", summary="Create a new Lead", status_code=201)
    async def create_lead(
        data: LeadCreate,
        admin=Depends(require_admin),
    ):
        """
        Create a lead record. A Lead represents an interested business
        before conversion — no users, orgs, or subscriptions are created.
        """
        now = _now()
        doc = {
            "id": _gen_id(),
            "name": data.name,
            "business_name": data.business_name,
            "email": data.email.lower().strip(),
            "phone": data.phone,
            "business_type": data.business_type,
            "estimated_screens": data.estimated_screens,
            "desired_plan": data.desired_plan,
            "source": data.source,
            "status": LeadStatus.new.value,
            "signup_date": data.signup_date,
            "notes": data.notes,
            "created_at": now,
            "updated_at": now,
        }
        await db.leads.insert_one(doc)
        return _ser(doc)

    @router.get("/leads/{lead_id}", summary="Get a Lead by ID")
    async def get_lead(lead_id: str, admin=Depends(require_admin)):
        doc = await db.leads.find_one({"id": lead_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Lead not found")
        return _ser(doc)

    @router.patch("/leads/{lead_id}", summary="Update Lead status or details")
    async def update_lead(
        lead_id: str,
        data: LeadUpdate,
        admin=Depends(require_admin),
    ):
        """Partial update — only provided fields are changed."""
        doc = await db.leads.find_one({"id": lead_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Lead not found")

        updates: dict = {}
        for field, value in data.dict(exclude_unset=True).items():
            if value is not None or field in ("notes", "phone"):
                if field == "status" and value is not None:
                    updates["status"] = value.value if hasattr(value, "value") else value
                else:
                    updates[field] = value

        if not updates:
            return _ser(doc)  # no-op

        updates["updated_at"] = _now()
        await db.leads.update_one({"id": lead_id}, {"$set": updates})
        return _ser(await db.leads.find_one({"id": lead_id}))

    # ══════════════════════════════════════════════════════════════════════════
    # CUSTOMERS
    # ══════════════════════════════════════════════════════════════════════════

    @router.get("/customers", summary="List all Customers")
    async def list_customers(
        status: Optional[str] = None,
        admin=Depends(require_admin),
    ):
        query: dict = {}
        if status:
            query["status"] = status
        docs = await db.customers.find(query).sort("created_at", -1).to_list(1000)
        return [_ser(d) for d in docs]

    @router.post("/customers", summary="Create a new Customer", status_code=201)
    async def create_customer(
        data: CustomerCreate,
        admin=Depends(require_admin),
    ):
        """
        Create a Customer (CRM/commercial entity).
        Customer is NOT the technical tenant boundary — Organization is.
        Does NOT automatically create an Organization or Subscription.
        """
        now = _now()
        doc = {
            "id": _gen_id(),
            "legal_name": data.legal_name,
            "display_name": data.display_name,
            "primary_contact_name": data.primary_contact_name,
            "primary_contact_email": (
                data.primary_contact_email.lower().strip()
                if data.primary_contact_email else None
            ),
            "primary_contact_phone": data.primary_contact_phone,
            "billing_contact_name": data.billing_contact_name,
            "billing_contact_email": (
                data.billing_contact_email.lower().strip()
                if data.billing_contact_email else None
            ),
            "billing_contact_phone": data.billing_contact_phone,
            "status": data.status.value,
            "notes": data.notes,
            "created_at": now,
            "updated_at": now,
        }
        await db.customers.insert_one(doc)
        return _ser(doc)

    @router.get("/customers/{customer_id}", summary="Get a Customer by ID")
    async def get_customer(customer_id: str, admin=Depends(require_admin)):
        doc = await db.customers.find_one({"id": customer_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Customer not found")
        # Attach linked organizations (read-only enrichment — no mutation)
        orgs = await db.organizations.find(
            {"customer_id": customer_id}, {"_id": 0}
        ).to_list(100)
        result = _ser(doc)
        result["organizations"] = [_ser(o) for o in orgs]
        return result

    @router.patch("/customers/{customer_id}", summary="Update Customer details")
    async def update_customer(
        customer_id: str,
        data: CustomerUpdate,
        admin=Depends(require_admin),
    ):
        doc = await db.customers.find_one({"id": customer_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Customer not found")

        updates: dict = {}
        for field, value in data.dict(exclude_unset=True).items():
            if field == "status" and value is not None:
                updates["status"] = value.value if hasattr(value, "value") else value
            elif value is not None:
                updates[field] = value

        if not updates:
            return _ser(doc)

        updates["updated_at"] = _now()
        await db.customers.update_one({"id": customer_id}, {"$set": updates})
        return _ser(await db.customers.find_one({"id": customer_id}))

    # ══════════════════════════════════════════════════════════════════════════
    # ORGANIZATIONS — CRM-LINKED CREATION
    # (Organization remains the technical SaaS tenant boundary.
    #  This endpoint creates an org linked to a Customer via customer_id.
    #  Preserves organization_id terminology. Compatible with future 1:N.)
    # ══════════════════════════════════════════════════════════════════════════

    @router.post(
        "/customers/{customer_id}/organizations",
        summary="Create an Organization linked to a Customer",
        status_code=201,
    )
    async def create_org_for_customer(
        customer_id: str,
        data: OrgForCustomerCreate,
        admin=Depends(require_admin),
    ):
        """
        Create a new Organization linked to the given Customer.
        Phase 2C-1A cardinality: Customer 1:1 Organization.
        Schema is forward-compatible with future Customer 1:N Organizations.
        Does NOT provision screens, invite users, or create subscriptions.
        """
        # Verify customer exists
        customer = await db.customers.find_one({"id": customer_id})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Enforce Phase 2C-1A cardinality: 1:1
        existing_org = await db.organizations.find_one({"customer_id": customer_id})
        if existing_org:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Customer '{customer_id}' already has an Organization "
                    f"(id={existing_org['id']!r}). "
                    "Phase 2C-1A enforces Customer 1:1 Organization. "
                    "This constraint may be relaxed in a future phase."
                ),
            )

        # Generate slug
        base_slug = data.slug or _slugify(data.name)
        slug = base_slug
        suffix = 1
        while await db.organizations.find_one({"slug": slug}):
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        now = _now()
        org = {
            "id": _gen_id(),
            "name": data.name,
            "slug": slug,
            "plan": data.plan,   # already normalized by model validator
            "status": "active",
            # ── Phase 2C-1A additive fields ──
            "customer_id": customer_id,
            "schema_source": "crm_2c",   # distinguishes CRM-created from self-service orgs
            # ── Standard fields expected by existing self_service_routes reads ──
            "owner_user_id": None,       # no owner user — managed by MediaView admin
            "notes": data.notes,
            "created_at": now,
            "updated_at": now,
        }
        await db.organizations.insert_one(org)
        return _ser(org)

    @router.get(
        "/customers/{customer_id}/organizations",
        summary="List Organizations linked to a Customer",
    )
    async def list_orgs_for_customer(
        customer_id: str,
        admin=Depends(require_admin),
    ):
        customer = await db.customers.find_one({"id": customer_id})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        orgs = await db.organizations.find(
            {"customer_id": customer_id}, {"_id": 0}
        ).to_list(100)
        return [_ser(o) for o in orgs]

    # ══════════════════════════════════════════════════════════════════════════
    # SUBSCRIPTIONS
    # ══════════════════════════════════════════════════════════════════════════

    @router.post("/subscriptions", summary="Create a Subscription", status_code=201)
    async def create_subscription(
        data: SubscriptionCreate,
        admin=Depends(require_admin),
    ):
        """
        Create a Subscription for an Organization/Customer pair.
        Subscription represents lifecycle and access state only.
        Pricing terms belong to PricingAgreement — not stored here.
        Production has zero subscriptions; this creates the first Phase 2C records.
        """
        # Verify org exists
        org = await db.organizations.find_one({"id": data.org_id})
        if not org:
            raise HTTPException(status_code=404, detail=f"Organization '{data.org_id}' not found")

        # Verify customer exists
        customer = await db.customers.find_one({"id": data.customer_id})
        if not customer:
            raise HTTPException(status_code=404, detail=f"Customer '{data.customer_id}' not found")

        # Guard: org must be linked to this customer (CRM integrity)
        if org.get("customer_id") and org["customer_id"] != data.customer_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Organization '{data.org_id}' is linked to customer "
                    f"'{org['customer_id']}', not '{data.customer_id}'."
                ),
            )

        # Guard: prevent duplicate active subscriptions per org
        existing = await db.subscriptions.find_one(
            {
                "org_id": data.org_id,
                "schema_version": 2,
                "status": {"$in": ["trial", "active", "suspended", "past_due"]},
            }
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Organization '{data.org_id}' already has an active Phase 2C "
                    f"subscription (id={existing['id']!r}, status={existing['status']!r})."
                ),
            )

        now = _now()
        doc = {
            "id": _gen_id(),
            "schema_version": 2,        # distinguishes Phase 2C subscriptions from legacy
            "org_id": data.org_id,
            "customer_id": data.customer_id,
            "status": data.status.value,
            "current_pricing_agreement_id": None,
            "billing_provider": data.billing_provider,
            "billing_customer_ref": data.billing_customer_ref,
            "billing_subscription_ref": data.billing_subscription_ref,
            "billing_status": data.billing_status,
            "trial_started_at": data.trial_started_at,
            "trial_ends_at": data.trial_ends_at,
            "activated_at": now if data.status == SubscriptionStatus.active else None,
            "suspended_at": None,
            "cancelled_at": None,
            "reactivated_at": None,
            "current_period_start": None,
            "current_period_end": None,
            "last_synced_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.subscriptions.insert_one(doc)
        return _ser(doc)

    @router.get("/subscriptions/{sub_id}", summary="Get a Subscription by ID")
    async def get_subscription(sub_id: str, admin=Depends(require_admin)):
        doc = await db.subscriptions.find_one({"id": sub_id, "schema_version": 2})
        if not doc:
            raise HTTPException(status_code=404, detail="Phase 2C Subscription not found")
        return _ser(doc)

    @router.patch(
        "/subscriptions/{sub_id}/status",
        summary="Update Subscription lifecycle status",
    )
    async def update_subscription_status(
        sub_id: str,
        data: SubscriptionStatusUpdate,
        admin=Depends(require_admin),
    ):
        doc = await db.subscriptions.find_one({"id": sub_id, "schema_version": 2})
        if not doc:
            raise HTTPException(status_code=404, detail="Phase 2C Subscription not found")

        now = _now()
        updates: dict = {
            "status": data.status.value,
            "updated_at": now,
            "last_synced_at": now,
        }
        # Record lifecycle timestamps
        if data.status == SubscriptionStatus.active and not doc.get("activated_at"):
            updates["activated_at"] = now
        elif data.status == SubscriptionStatus.suspended:
            updates["suspended_at"] = now
        elif data.status == SubscriptionStatus.cancelled:
            updates["cancelled_at"] = now
        elif data.status == SubscriptionStatus.active and doc.get("status") == "suspended":
            updates["reactivated_at"] = now

        await db.subscriptions.update_one({"id": sub_id}, {"$set": updates})
        return _ser(await db.subscriptions.find_one({"id": sub_id}))

    @router.get(
        "/organizations/{org_id}/subscription",
        summary="Get the active Phase 2C Subscription for an Organization",
    )
    async def get_org_subscription(org_id: str, admin=Depends(require_admin)):
        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        doc = await db.subscriptions.find_one(
            {"org_id": org_id, "schema_version": 2},
            sort=[("created_at", -1)],
        )
        if not doc:
            raise HTTPException(
                status_code=404,
                detail=f"No Phase 2C Subscription found for organization '{org_id}'",
            )
        return _ser(doc)

    # ══════════════════════════════════════════════════════════════════════════
    # PRICING AGREEMENTS
    # ══════════════════════════════════════════════════════════════════════════

    @router.post(
        "/pricing-agreements",
        summary="Create a PricingAgreement for a Subscription",
        status_code=201,
    )
    async def create_pricing_agreement(
        data: PricingAgreementCreate,
        admin=Depends(require_admin),
    ):
        """
        Create a versioned PricingAgreement (commercial contract/terms layer).
        PricingAgreement is effectively immutable after activation.
        To change terms, create a new version with an updated effective_from date.
        agreed_monthly_price is the authoritative MRR source — never stored on Subscription.
        """
        # Verify subscription exists
        sub = await db.subscriptions.find_one(
            {"id": data.subscription_id, "schema_version": 2}
        )
        if not sub:
            raise HTTPException(
                status_code=404,
                detail=f"Phase 2C Subscription '{data.subscription_id}' not found",
            )

        # Auto-increment version for this subscription
        existing_count = await db.pricing_agreements.count_documents(
            {"subscription_id": data.subscription_id}
        )
        version = existing_count + 1

        now = _now()
        doc = {
            "id": _gen_id(),
            "subscription_id": data.subscription_id,
            "version": version,
            "plan_id": data.plan_id,          # already normalized by model validator
            "pricing_model": data.pricing_model.value,
            "screens_included": data.screens_included,
            "screens_limit": data.screens_limit,
            "overage_price_per_screen": data.overage_price_per_screen,
            "agreed_monthly_price": data.agreed_monthly_price,
            "currency": data.currency.upper(),
            "billing_cycle": data.billing_cycle.value,
            "discount_percent": data.discount_percent,
            "credit_balance": data.credit_balance,
            "effective_from": data.effective_from,
            "effective_to": data.effective_to,
            "created_by": admin.get("id") or admin.get("email", "unknown"),
            "notes": data.notes,
            "created_at": now,
        }
        await db.pricing_agreements.insert_one(doc)

        # Update the subscription's current_pricing_agreement_id pointer
        await db.subscriptions.update_one(
            {"id": data.subscription_id},
            {"$set": {
                "current_pricing_agreement_id": doc["id"],
                "updated_at": now,
            }},
        )

        return _ser(doc)

    @router.get(
        "/subscriptions/{sub_id}/pricing-agreements",
        summary="List all PricingAgreements for a Subscription (version history)",
    )
    async def list_pricing_agreements(sub_id: str, admin=Depends(require_admin)):
        sub = await db.subscriptions.find_one({"id": sub_id, "schema_version": 2})
        if not sub:
            raise HTTPException(status_code=404, detail="Phase 2C Subscription not found")
        docs = await db.pricing_agreements.find(
            {"subscription_id": sub_id}
        ).sort("version", 1).to_list(100)
        return [_ser(d) for d in docs]

    @router.get(
        "/pricing-agreements/{pa_id}",
        summary="Get a PricingAgreement by ID",
    )
    async def get_pricing_agreement(pa_id: str, admin=Depends(require_admin)):
        doc = await db.pricing_agreements.find_one({"id": pa_id})
        if not doc:
            raise HTTPException(status_code=404, detail="PricingAgreement not found")
        return _ser(doc)

    # ══════════════════════════════════════════════════════════════════════════
    # RELATIONSHIP VIEW — Customer CRM summary
    # ══════════════════════════════════════════════════════════════════════════

    @router.get(
        "/customers/{customer_id}/summary",
        summary="Full CRM relationship summary for a Customer",
    )
    async def customer_summary(customer_id: str, admin=Depends(require_admin)):
        """
        Returns: Customer → Organizations → Subscriptions → latest PricingAgreement.
        Read-only enrichment — no mutations.
        """
        customer = await db.customers.find_one({"id": customer_id})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        orgs = await db.organizations.find(
            {"customer_id": customer_id}, {"_id": 0}
        ).to_list(100)

        org_summaries = []
        for org in orgs:
            sub = await db.subscriptions.find_one(
                {"org_id": org["id"], "schema_version": 2},
                sort=[("created_at", -1)],
            )
            sub_data = _ser(sub)
            pricing = None
            if sub and sub.get("current_pricing_agreement_id"):
                pa = await db.pricing_agreements.find_one(
                    {"id": sub["current_pricing_agreement_id"]}
                )
                pricing = _ser(pa)
            org_summaries.append({
                "organization": _ser(org),
                "subscription": sub_data,
                "current_pricing_agreement": pricing,
            })

        return {
            "customer": _ser(customer),
            "organizations": org_summaries,
        }

    return router
