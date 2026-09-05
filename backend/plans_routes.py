"""
plans_routes.py — Admin-manageable canonical plan configurations.
Phase 2C P1: Replaces the hardcoded PLANS dict for public-facing pricing.

Plan IDs (canonical, immutable): free | starter | pro | enterprise
Admin can update: price, features, screens_included, trial_days, visibility.
Pricing config is stored in the 'plans' MongoDB collection and seeded on startup.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field


# ── Default seed values (admin can override any field except plan_id) ──────────
DEFAULT_PLANS = [
    {
        "plan_id": "free",
        "display_name": "Free",
        "monthly_price": 0.0,
        "annual_price": 0.0,
        "screens_included": 1,
        "screens_limit": 1,
        "price_per_extra_screen": 0.0,
        "features": [
            "1 screen",
            "Basic scheduling",
            "1 GB media storage",
            "Web player",
            "Community support",
        ],
        "trial_days": 0,
        "is_active": True,
        "is_public": True,
        "display_order": 1,
        "highlight": False,
        "highlight_text": "",
    },
    {
        "plan_id": "starter",
        "display_name": "Starter",
        "monthly_price": 49.0,
        "annual_price": 470.0,
        "screens_included": 3,
        "screens_limit": 3,
        "price_per_extra_screen": 15.0,
        "features": [
            "3 screens",
            "Playlists & scheduling",
            "10 GB media storage",
            "Web & Android player",
            "Team members (up to 2)",
            "Email support",
        ],
        "trial_days": 14,
        "is_active": True,
        "is_public": True,
        "display_order": 2,
        "highlight": False,
        "highlight_text": "",
    },
    {
        "plan_id": "pro",
        "display_name": "Pro",
        "monthly_price": 149.0,
        "annual_price": 1430.0,
        "screens_included": 10,
        "screens_limit": 10,
        "price_per_extra_screen": 12.0,
        "features": [
            "10 screens",
            "Playlists & scheduling",
            "50 GB media storage",
            "All players supported",
            "Widgets & integrations",
            "Team members (up to 10)",
            "Analytics dashboard",
            "Priority support",
        ],
        "trial_days": 14,
        "is_active": True,
        "is_public": True,
        "display_order": 3,
        "highlight": True,
        "highlight_text": "Most Popular",
    },
    {
        "plan_id": "enterprise",
        "display_name": "Enterprise",
        "monthly_price": 499.0,
        "annual_price": 4790.0,
        "screens_included": 50,
        "screens_limit": None,
        "price_per_extra_screen": 9.0,
        "features": [
            "50+ screens (unlimited add-ons)",
            "Unlimited playlists & scheduling",
            "500 GB media storage",
            "All players + API access",
            "Custom branding",
            "Unlimited team members",
            "Advanced analytics",
            "Dedicated account manager",
            "SLA guarantee",
        ],
        "trial_days": 30,
        "is_active": True,
        "is_public": True,
        "display_order": 4,
        "highlight": False,
        "highlight_text": "",
    },
]


def _ser_plan(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in doc.items() if k != "_id"}


async def seed_default_plans(db) -> None:
    """Idempotent: insert defaults only if a plan_id does not exist yet."""
    for plan in DEFAULT_PLANS:
        existing = await db.plans.find_one({"plan_id": plan["plan_id"]})
        if not existing:
            doc = {
                **plan,
                "id": str(uuid.uuid4()),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            await db.plans.insert_one(doc)


# ── Pydantic model ──────────────────────────────────────────────────────────────
class PlanUpdate(BaseModel):
    display_name: Optional[str] = None
    monthly_price: Optional[float] = Field(None, ge=0)
    annual_price: Optional[float] = Field(None, ge=0)
    screens_included: Optional[int] = Field(None, ge=0)
    screens_limit: Optional[int] = Field(None, ge=0)
    price_per_extra_screen: Optional[float] = Field(None, ge=0)
    features: Optional[List[str]] = None
    trial_days: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None
    display_order: Optional[int] = None
    highlight: Optional[bool] = None
    highlight_text: Optional[str] = None


# ── Router factory ──────────────────────────────────────────────────────────────
def create_plans_routes(db, get_current_user, require_admin):
    router = APIRouter(tags=["Plans — Phase 2C"])

    @router.get("/api/plans", summary="List active public plans (no auth required)")
    async def list_public_plans():
        """Public endpoint: returns only active, public plans in display order."""
        docs = await db.plans.find(
            {"is_active": True, "is_public": True}
        ).sort("display_order", 1).to_list(20)
        return [_ser_plan(d) for d in docs]

    @router.get("/api/admin/plans", summary="List all plans (admin)")
    async def list_all_plans(admin=Depends(require_admin)):
        docs = await db.plans.find({}).sort("display_order", 1).to_list(20)
        return [_ser_plan(d) for d in docs]

    @router.get("/api/admin/plans/{plan_id}", summary="Get a single plan by plan_id (admin)")
    async def get_plan(plan_id: str, admin=Depends(require_admin)):
        doc = await db.plans.find_one({"plan_id": plan_id})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found")
        return _ser_plan(doc)

    @router.post("/api/admin/plans", summary="Create a new plan (admin)", status_code=201)
    async def create_plan(data: dict, admin=Depends(require_admin)):
        """Create a custom/additional plan. plan_id must be unique and lowercase."""
        plan_id = str(data.get("plan_id") or "").strip().lower().replace(" ", "_")
        if not plan_id:
            raise HTTPException(status_code=400, detail="plan_id is required")
        existing = await db.plans.find_one({"plan_id": plan_id})
        if existing:
            raise HTTPException(status_code=409, detail=f"Plan '{plan_id}' already exists")
        now = datetime.utcnow()
        doc = {
            "id": str(uuid.uuid4()),
            "plan_id": plan_id,
            "display_name": data.get("display_name", plan_id.title()),
            "monthly_price": float(data.get("monthly_price", 0)),
            "annual_price": float(data.get("annual_price", 0)),
            "screens_included": int(data.get("screens_included", 1)),
            "screens_limit": data.get("screens_limit"),
            "price_per_extra_screen": float(data.get("price_per_extra_screen", 0)),
            "features": data.get("features", []),
            "trial_days": int(data.get("trial_days", 14)),
            "is_active": bool(data.get("is_active", True)),
            "is_public": bool(data.get("is_public", True)),
            "display_order": int(data.get("display_order", 99)),
            "highlight": bool(data.get("highlight", False)),
            "highlight_text": data.get("highlight_text", ""),
            "created_at": now,
            "updated_at": now,
        }
        await db.plans.insert_one(doc)
        return _ser_plan(doc)

    @router.put("/api/admin/plans/{plan_id}", summary="Update plan commercial config (admin)")
    async def update_plan(plan_id: str, data: PlanUpdate, admin=Depends(require_admin)):
        """Update a plan's commercial terms. plan_id (canonical key) cannot be changed."""
        doc = await db.plans.find_one({"plan_id": plan_id})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found")
        updates = data.dict(exclude_unset=True)
        if not updates:
            return _ser_plan(doc)
        updates["updated_at"] = datetime.utcnow()
        await db.plans.update_one({"plan_id": plan_id}, {"$set": updates})
        return _ser_plan(await db.plans.find_one({"plan_id": plan_id}))

    return router
