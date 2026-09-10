"""superadmin_routes.py -- Super Admin account management (create/list/
toggle/delete admins + platform overview), RBAC endpoints (effective-role
info, operation-type migration, screens-by-type summary, dev-only
seed-test-users), and the admin customer-orders view (list/detail/status).

Fase 2B-6c of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md,
docs/FASE2B6_MAPA_RUTAS_ADMIN.md and docs/AGENT_COORDINATION.md). LAST PR of
Fase 2B-6. Pure relocation of the 14 handlers below out of server.py:
identical paths, methods, decorators and logic, registered on a router with
prefix="/api" so the final routes match api_router exactly as before. No
behavior change.

Deliberately NOT moved (out of scope, stay in server.py): serve_admin_orders_page,
serve_admin_clients_page, serve_admin_reports_page (/admin/orders-view,
/admin/clients-view, /admin/reports-view). These are plain FileResponse(WEB_DIR,
...) page servers with zero domain logic -- grep-verified they already sit in
the same static-page block as every other page route (advertise.html,
download.html, /player-activate, landing.html, etc.), which was never split
out in any prior phase. Splitting them here would only thread WEB_DIR into
one more module for no benefit.

Dependency notes:
  - gen_id and serialize_doc are threaded in, same pattern as every prior
    phase.
  - gen_pairing_code, gen_pairing_secret and get_unique_location_code are
    threaded in too: they're defined in server.py and used by
    seed_rbac_test_users here, but they also stay in server.py (used
    directly by other, not-yet-moved code) and are already threaded the
    same way into screens_routes.py's create_screens_routes(...) factory --
    same precedent, not re-invented here.
  - db (database.py) and require_admin / require_superadmin (deps.py) are
    imported directly.
  - OperationType, Role, get_effective_role, assert_permission and
    effective_operation_type (rbac.py) are imported directly, exactly as
    server.py already does.
  - hash_password is used by create_admin and seed_rbac_test_users but stays
    defined in server.py (many other non-moving routes use it too: signup,
    demo-seed data). Rather than threading it or duplicating its body, both
    functions do a local `from server import hash_password` inside the
    function -- the exact same cross-module-reuse pattern finance.py already
    uses for the same name ("Import hash_password from server module
    (already registered at boot)"), not a new pattern invented for this PR.
  - rbac_info keeps its existing local `from rbac import PERMISSIONS` inside
    the function body untouched -- that was already how the original code
    did it, preserved byte-for-byte.
  - IS_PROD is recomputed locally (`ENVIRONMENT = os.environ.get(...)`;
    `IS_PROD = ENVIRONMENT == "production"`) instead of imported from
    server.py: importing it would risk a circular import (server.py imports
    this module at module load time), and auth_v2.py already establishes the
    precedent of recomputing this exact one-line formula locally instead of
    cross-importing it.
  - CustomerOrderStatusUpdate and CreateAdminRequest move here as plain
    Pydantic models: grep-verified across every file in backend/ that
    admin_customer_order_status and create_admin are their only respective
    call sites anywhere in the codebase.

Known cosmetic leftovers (same accepted precedent as every prior phase --
comments themselves are never touched, to keep this script a pure
relocation): the "# ============ ROUTES: SUPER ADMIN ============" section
header and the "# ============ FASE 1: RBAC INFO + MIGRATION ENDPOINTS
============" section header both become orphaned in server.py (everything
they introduced moves here), left in place untouched.
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from deps import require_admin, require_superadmin
from rbac import (
    OperationType,
    Role,
    assert_permission,
    effective_operation_type,
    get_effective_role,
)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
IS_PROD = ENVIRONMENT == "production"


class CustomerOrderStatusUpdate(BaseModel):
    status: str  # 'paid' | 'approved' | 'live' | 'rejected' | 'cancelled'
    admin_note: Optional[str] = None

class CreateAdminRequest(BaseModel):
    name: str
    email: str
    password: str
    company_name: Optional[str] = None


def create_superadmin_routes(gen_id, serialize_doc, gen_pairing_code, gen_pairing_secret, get_unique_location_code):
    router = APIRouter(prefix="/api", tags=["Super Admin"])

    @router.get("/admin/customer-orders")
    async def admin_customer_orders(status: Optional[str] = None, admin=Depends(require_admin)):
        q = {"status": status} if status else {}
        cur = db.customer_orders.find(q).sort("created_at", -1)
        docs = await cur.to_list(500)
        for d in docs:
            d.pop("_id", None)
            # Keep media_data_url — admin needs to preview it. If too heavy,
            # frontend can request the detail endpoint per row instead.
        return docs

    @router.get("/admin/customer-orders/{oid}")
    async def admin_customer_order_detail(oid: str, admin=Depends(require_admin)):
        d = await db.customer_orders.find_one({"id": oid})
        if not d:
            raise HTTPException(status_code=404, detail="Order not found")
        d.pop("_id", None)
        return d

    @router.put("/admin/customer-orders/{oid}/status")
    async def admin_customer_order_status(oid: str, payload: CustomerOrderStatusUpdate, admin=Depends(require_admin)):
        allowed = {"pending_payment", "paid", "approved", "live", "rejected", "cancelled"}
        if payload.status not in allowed:
            raise HTTPException(status_code=400, detail=f"status must be one of {sorted(allowed)}")
        update = {"status": payload.status, "updated_at": datetime.utcnow()}
        if payload.admin_note is not None:
            update["admin_note"] = payload.admin_note
        r = await db.customer_orders.update_one({"id": oid}, {"$set": update})
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Order not found")
        return {"id": oid, "status": payload.status}

    @router.post("/superadmin/create-admin")
    async def create_admin(data: CreateAdminRequest, sa: dict = Depends(require_superadmin)):
        """Super Admin creates a new Admin account."""
        existing = await db.users.find_one({"email": data.email.lower()})
        # Import hash_password from server module (already registered at boot)
        from server import hash_password

        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        admin = {
            "id": gen_id(), "name": data.name, "email": data.email.lower(),
            "password_hash": hash_password(data.password), "role": "admin",
            "company_name": data.company_name, "phone": None,
            "language": "en", "active": True,
            "created_by": sa["id"],
            "created_at": datetime.utcnow()
        }
        await db.users.insert_one(admin)
        return {"message": "Admin created", "admin_id": admin["id"], "email": admin["email"]}

    @router.get("/superadmin/admins")
    async def list_admins(sa: dict = Depends(require_superadmin)):
        """List all admin accounts."""
        admins = await db.users.find({"role": "admin"}, {"password_hash": 0}).sort("created_at", -1).to_list(100)
        enriched = []
        for a in admins:
            customers = await db.users.count_documents({"role": "customer"})
            campaigns = await db.campaigns.count_documents({})
            a["total_customers"] = customers
            a["total_campaigns"] = campaigns
            enriched.append(a)
        return serialize_doc(enriched)

    @router.put("/superadmin/admins/{admin_id}/toggle")
    async def toggle_admin(admin_id: str, sa: dict = Depends(require_superadmin)):
        """Enable/disable an admin account."""
        admin = await db.users.find_one({"id": admin_id, "role": "admin"})
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        new_status = not admin.get("active", True)
        await db.users.update_one({"id": admin_id}, {"$set": {"active": new_status}})
        return {"message": f"Admin {'enabled' if new_status else 'disabled'}", "active": new_status}

    @router.delete("/superadmin/admins/{admin_id}")
    async def delete_admin(admin_id: str, sa: dict = Depends(require_superadmin)):
        """Remove an admin account."""
        admin = await db.users.find_one({"id": admin_id, "role": "admin"})
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        await db.users.delete_one({"id": admin_id})
        return {"message": "Admin removed"}

    @router.get("/superadmin/overview")
    async def superadmin_overview(sa: dict = Depends(require_superadmin)):
        """Platform-wide overview for Super Admin."""
        total_admins = await db.users.count_documents({"role": "admin"})
        total_customers = await db.users.count_documents({"role": "customer"})
        total_screens = await db.screens.count_documents({})
        total_campaigns = await db.campaigns.count_documents({})
        total_devices = await db.devices.count_documents({})
        payments = await db.payments.find({"status": "completed"}).to_list(10000)
        total_revenue = sum(p.get("amount", 0) for p in payments)
        return {
            "total_admins": total_admins, "total_customers": total_customers,
            "total_screens": total_screens, "total_campaigns": total_campaigns,
            "total_devices": total_devices, "total_revenue": round(total_revenue, 2),
        }

    @router.get("/admin/users")
    async def admin_list_users(admin: dict = Depends(require_admin)):
        users = await db.users.find({}, {"password_hash": 0}).sort("created_at", -1).to_list(500)
        return serialize_doc(users)

    @router.put("/admin/users/{user_id}")
    async def admin_update_user(user_id: str, active: bool, admin: dict = Depends(require_admin)):
        result = await db.users.update_one({"id": user_id}, {"$set": {"active": active}})
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": "User updated"}

    @router.get("/admin/rbac/info")
    async def rbac_info(admin: dict = Depends(require_admin)):
        """Return the current user's effective RBAC role and all permissions they hold."""
        from rbac import PERMISSIONS
        role = get_effective_role(admin)
        granted = [p for p, roles in PERMISSIONS.items() if role in roles]
        return {
            "legacy_role": admin.get("role"),
            "rbac_role": role,
            "permissions": sorted(granted),
        }

    @router.post("/admin/migrate-operation-types")
    async def migrate_operation_types(admin: dict = Depends(require_admin)):
        """
    One-time migration: set operation_type on screens that don't have it yet.
    Migration rules:
      - advertising.is_public == True  → PUBLIC_ADVERTISING
      - everything else                → SELF_SERVICE  (safe default)
    Super Admin can change individual screens afterward via PUT /admin/screens/{id}.
    """
        assert_permission(admin, "admin.all_screens")
        screens = await db.screens.find({"operation_type": {"$exists": False}}).to_list(10000)
        updated = 0
        for s in screens:
            is_pub = s.get("advertising", {}).get("is_public", False)
            op_type = OperationType.PUBLIC_ADVERTISING if is_pub else OperationType.SELF_SERVICE
            await db.screens.update_one(
                {"id": s["id"]},
                {"$set": {"operation_type": op_type, "updated_at": datetime.utcnow()}}
            )
            updated += 1
        return {
            "migrated": updated,
            "message": f"Set operation_type on {updated} screens. Review SELF_SERVICE screens that may actually be MEDIAVIEW_MANAGED."
        }

    @router.get("/admin/rbac/screens-by-type")
    async def screens_by_operation_type(admin: dict = Depends(require_admin)):
        """Summary of screens grouped by operation_type (with effective type inference)."""
        assert_permission(admin, "admin.all_screens")
        screens = await db.screens.find({}, {"id": 1, "name": 1, "operation_type": 1, "advertising": 1, "status": 1}).to_list(10000)
        groups: dict = {t: [] for t in [OperationType.SELF_SERVICE, OperationType.PUBLIC_ADVERTISING, OperationType.MEDIAVIEW_MANAGED]}
        for s in screens:
            t = effective_operation_type(s)
            groups[t].append({"id": s.get("id"), "name": s.get("name"), "status": s.get("status"), "has_operation_type_field": bool(s.get("operation_type"))})
        return {t: {"count": len(v), "screens": v} for t, v in groups.items()}

    @router.post("/admin/rbac/seed-test-users")
    async def seed_rbac_test_users(sa: dict = Depends(require_superadmin)):
        """Dev-only: seed one user per RBAC role (plus two SELF_SERVICE_OWNER users in
    different organisations) and a matching test screen per org.
    Idempotent — existing accounts are skipped.
    Returns all created / existing credentials so the test suite can log in."""
        if IS_PROD:
            raise HTTPException(status_code=403, detail="Endpoint not available in production")

        ORG_A = "org_rbac_test_a"
        ORG_B = "org_rbac_test_b"
        TEST_PW = "RbacTest#2026"

        # Import hash_password from server module (already registered at boot)
        from server import hash_password

        test_users = [
            {
                "email": "rbac.mwadmin@test.com",
                "name": "RBAC MediaView Admin",
                "role": "admin",
                "rbac_role": Role.MEDIAVIEW_ADMIN,
                "organization_id": None,
            },
            {
                "email": "rbac.ssowner.orga@test.com",
                "name": "RBAC Self-Service Owner Org A",
                "role": "customer",
                "rbac_role": Role.SELF_SERVICE_OWNER,
                "organization_id": ORG_A,
            },
            {
                "email": "rbac.ssowner.orgb@test.com",
                "name": "RBAC Self-Service Owner Org B",
                "role": "customer",
                "rbac_role": Role.SELF_SERVICE_OWNER,
                "organization_id": ORG_B,
            },
            {
                "email": "rbac.advertiser@test.com",
                "name": "RBAC Advertiser",
                "role": "advertiser",
                "rbac_role": Role.ADVERTISER,
                "organization_id": None,
            },
            {
                "email": "rbac.viewer@test.com",
                "name": "RBAC Managed Viewer",
                "role": "viewer",
                "rbac_role": Role.MANAGED_VIEWER,
                # ── Fase 4: assign to the demo managed org so GET /managed/* works ─
                "organization_id": "org_managed_demo_v4",
            },
        ]

        created_users: list[str] = []
        user_ids: dict[str, str] = {}

        for u in test_users:
            existing = await db.users.find_one({"email": u["email"]})
            if existing:
                user_ids[u["email"]] = existing["id"]
            else:
                uid = gen_id()
                doc = {
                    "id": uid, "name": u["name"], "email": u["email"],
                    "password_hash": hash_password(TEST_PW),
                    "role": u["role"], "rbac_role": u["rbac_role"],
                    "organization_id": u.get("organization_id"),
                    "company_name": f"Test — {u['rbac_role']}",
                    "phone": None, "language": "en",
                    "active": True, "session_epoch": 0,
                    "created_at": datetime.utcnow(),
                }
                await db.users.insert_one(doc)
                user_ids[u["email"]] = uid
                created_users.append(u["email"])

        # ── Create test screens (one per org, one PUBLIC, one MANAGED) ──────────
        created_screens: dict[str, str] = {}

        async def _ensure_screen(key: str, name: str, op_type: str, org: Optional[str]) -> str:
            existing = await db.screens.find_one({"name": name})
            if existing:
                return existing["id"]
            code = gen_pairing_code()
            while await db.screens.find_one({"pairing_code": code}):
                code = gen_pairing_code()
            loc_code = await get_unique_location_code()
            screen = {
                "id": gen_id(), "name": name,
                "description": f"Auto-created test screen for RBAC Acceptance Tests — {op_type}",
                "location": {"city": "Test City", "address": "123 Test St", "state": "TC", "country": "US", "lat": 0.0, "lng": 0.0},
                "pricing": {"per_hour": 10.0, "per_day": 80.0, "per_slot": 1.0, "currency": "USD"},
                "specs": {"size": "32in", "type": "LCD", "resolution": "1920x1080", "orientation": "landscape"},
                "preview_image": None, "status": "active", "location_code": loc_code,
                "pairing_code": code, "pairing_secret": gen_pairing_secret(),
                "paired_device_id": None, "paired_at": None, "active": True,
                "operation_type": op_type,
                "organization_id": org,
                "created_by": sa.get("id"),
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
            }
            await db.screens.insert_one(screen)
            created_screens[key] = screen["id"]
            return screen["id"]

        screen_org_a = await _ensure_screen("screen_org_a", "RBAC Test Screen — Org A (SELF_SERVICE)", OperationType.SELF_SERVICE, ORG_A)
        screen_org_b = await _ensure_screen("screen_org_b", "RBAC Test Screen — Org B (SELF_SERVICE)", OperationType.SELF_SERVICE, ORG_B)
        screen_public = await _ensure_screen("screen_public", "RBAC Test Screen — PUBLIC_ADVERTISING", OperationType.PUBLIC_ADVERTISING, None)
        screen_managed = await _ensure_screen("screen_managed", "RBAC Test Screen — MEDIAVIEW_MANAGED", OperationType.MEDIAVIEW_MANAGED, None)

        # ── Ensure test organizations exist in db.organizations ──────────────
        # IMPORTANT: must run BEFORE the return so create_organization's
        # owner_user_id check finds the org doc and returns 409 (not 200).
        created_orgs: list[str] = []
        for org_id, org_name, owner_email in [
            (ORG_A, "Test Org A", "rbac.ssowner.orga@test.com"),
            (ORG_B, "Test Org B", "rbac.ssowner.orgb@test.com"),
        ]:
            owner_uid = user_ids.get(owner_email)
            if owner_uid and not await db.organizations.find_one({"id": org_id}):
                await db.organizations.insert_one({
                    "id": org_id,
                    "name": org_name,
                    "slug": org_id.replace("_", "-"),
                    "owner_user_id": owner_uid,
                    "plan": "free",
                    "status": "active",
                    "billing_email": owner_email,
                    "settings": {},
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                })
                created_orgs.append(org_id)
            elif owner_uid:
                # Idempotent: ensure owner_user_id is correct on existing org
                await db.organizations.update_one(
                    {"id": org_id},
                    {"$set": {"owner_user_id": owner_uid}},
                )

        return {
            "created_users": created_users,
            "created_orgs": created_orgs,
            "created_screens": created_screens,
            "password": TEST_PW,
            "credentials": {
                "super_admin":              {"email": "superadmin@mediadview.com",  "password": "SuperAdmin#2026",  "rbac_role": "SUPER_ADMIN"},
                "mediaview_admin":          {"email": "rbac.mwadmin@test.com",      "password": TEST_PW,            "rbac_role": "MEDIAVIEW_ADMIN"},
                "self_service_owner_org_a": {"email": "rbac.ssowner.orga@test.com", "password": TEST_PW,            "rbac_role": "SELF_SERVICE_OWNER", "org": ORG_A},
                "self_service_owner_org_b": {"email": "rbac.ssowner.orgb@test.com", "password": TEST_PW,            "rbac_role": "SELF_SERVICE_OWNER", "org": ORG_B},
                "advertiser":               {"email": "rbac.advertiser@test.com",   "password": TEST_PW,            "rbac_role": "ADVERTISER"},
                "managed_viewer":           {"email": "rbac.viewer@test.com",       "password": TEST_PW,            "rbac_role": "MANAGED_VIEWER"},
            },
            "test_screens": {
                "screen_org_a":   {"id": screen_org_a,  "org": ORG_A, "type": "SELF_SERVICE"},
                "screen_org_b":   {"id": screen_org_b,  "org": ORG_B, "type": "SELF_SERVICE"},
                "screen_public":  {"id": screen_public, "org": None,  "type": "PUBLIC_ADVERTISING"},
                "screen_managed": {"id": screen_managed,"org": None,  "type": "MEDIAVIEW_MANAGED"},
            },
        }

    return router
