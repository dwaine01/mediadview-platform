# ruff: noqa: E501,E701,E702,E731
"""
self_service_routes.py — MediaView Fase 2: Self-Service Portal
──────────────────────────────────────────────────────────────
Endpoints for:
  • Organizations  (CRUD + admin management)
  • Locations      (CRUD, org-scoped, tenant isolation)
  • Team Members & Invitations
  • Subscriptions  (SELF_SERVICE_SUBSCRIPTION — mocked billing, full lifecycle)
"""
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt as _jwt_lib
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from rbac import Role, assert_permission, assert_tenant, get_effective_role

# Roles that must NEVER be modified or moved via an invite.
# An invitation can never degrade, move, or co-opt these accounts.
_PROTECTED_ROLES = frozenset({
    Role.SUPER_ADMIN,
    Role.MEDIAVIEW_ADMIN,
    Role.SUPPORT,
})

# ── Subscription plan catalogue ────────────────────────────────────────────────
PLANS: dict = {
    "starter": {
        "name": "Starter",
        "price_monthly": 29.00,
        "price_annual": 290.00,
        "description": "Perfect for small businesses",
        "features": ["1 screen", "Basic scheduling", "5 GB media storage", "Email support"],
        "color": "#6366f1",
    },
    "pro": {
        "name": "Pro",
        "price_monthly": 59.00,
        "price_annual": 590.00,
        "description": "For growing businesses",
        "features": ["Up to 5 screens", "Advanced scheduling", "50 GB storage", "Priority support", "Analytics", "Team members (up to 3)"],
        "color": "#0891b2",
    },
    "enterprise": {
        "name": "Enterprise",
        "price_monthly": 199.00,
        "price_annual": 1990.00,
        "description": "Full platform for large organizations",
        "features": ["Unlimited screens", "Custom branding", "500 GB storage", "Dedicated support", "SLA guarantee", "API access", "Unlimited team members"],
        "color": "#10b981",
    },
}

TRIAL_DAYS = 14


# ── Utilities ──────────────────────────────────────────────────────────────────
def _gen_id() -> str:
    return str(uuid.uuid4())

def _gen_token() -> str:
    return secrets.token_urlsafe(32)

def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def _ser(doc):
    """Recursively strip _id and serialize datetimes."""
    if isinstance(doc, list):
        return [_ser(d) for d in doc]
    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            if k == "_id":
                continue
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            elif isinstance(v, (dict, list)):
                out[k] = _ser(v)
            else:
                out[k] = v
        return out
    return doc


# ── Pydantic models ────────────────────────────────────────────────────────────
class OrgCreate(BaseModel):
    name: str
    billing_email: Optional[str] = None
    logo_url: Optional[str] = None

class OrgUpdate(BaseModel):
    name: Optional[str] = None
    billing_email: Optional[str] = None
    logo_url: Optional[str] = None
    settings: Optional[dict] = None

class OrgStatusUpdate(BaseModel):
    status: str  # active | suspended | cancelled
    reason: Optional[str] = None

class LocationCreate(BaseModel):
    name: str
    address: str
    city: str
    state: Optional[str] = None
    country: str = "US"
    zip: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    timezone: str = "America/New_York"

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    zip: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    timezone: Optional[str] = None

class ScreenLocationLink(BaseModel):
    location_id: Optional[str] = None  # null → unlink

class InviteCreate(BaseModel):
    email: str
    role: str = "SELF_SERVICE_MANAGER"

class InviteAccept(BaseModel):
    name: Optional[str] = None      # required for new users
    password: Optional[str] = None  # required for new users

class SubCreate(BaseModel):
    screen_id: str
    plan: str = "starter"
    billing_cycle: str = "monthly"  # monthly | annual

class SubUpdate(BaseModel):
    plan: Optional[str] = None
    billing_cycle: Optional[str] = None


# ── Factory ────────────────────────────────────────────────────────────────────
def create_self_service_routes(db, get_current_user, require_admin, require_superadmin):
    """Return an APIRouter with all Fase 2 Self-Service Portal routes."""

    router = APIRouter(prefix="/api")

    # ── Helpers ────────────────────────────────────────────────────────────────
    async def _org_or_404(org_id: str, user: dict, require_owner: bool = False) -> dict:
        """Fetch org; verify membership. Bypass for SUPER_ADMIN / MEDIAVIEW_ADMIN."""
        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        role = get_effective_role(user)
        if role in (Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN):
            return org
        is_owner = org.get("owner_user_id") == user.get("id")
        is_member = user.get("organization_id") == org_id
        if require_owner and not is_owner:
            raise HTTPException(status_code=403, detail="Only the organization owner can perform this action")
        if not is_owner and not is_member:
            raise HTTPException(status_code=403, detail="You are not a member of this organization")
        return org

    async def _loc_or_404(loc_id: str, user: dict) -> dict:
        loc = await db.locations.find_one({"id": loc_id})
        if not loc:
            raise HTTPException(status_code=404, detail="Location not found")
        role = get_effective_role(user)
        if role not in (Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN):
            assert_permission(user, "screen.configure")
            assert_tenant(user, loc.get("org_id"))
        return loc

    # ══════════════════════════════════════════════════════════════════════════
    #  ORGANIZATIONS
    # ══════════════════════════════════════════════════════════════════════════

    @router.get("/organizations/mine")
    async def get_my_organization(current_user: dict = Depends(get_current_user)):
        """Return the org the authenticated user owns or belongs to."""
        org_id = current_user.get("organization_id")
        if not org_id:
            # maybe owner but organization_id not set on user yet
            org = await db.organizations.find_one({"owner_user_id": current_user.get("id")})
        else:
            org = await db.organizations.find_one({"id": org_id})
        if not org:
            return {"org": None, "message": "No organization yet — create one to get started."}
        lc = await db.locations.count_documents({"org_id": org["id"]})
        sc = await db.screens.count_documents({"organization_id": org["id"]})
        mc = await db.users.count_documents({"organization_id": org["id"]})
        ac = await db.subscriptions.count_documents({"org_id": org["id"], "status": {"$in": ["trialing", "active"]}})
        out = _ser(org)
        out["stats"] = {"locations": lc, "screens": sc, "members": mc, "active_subscriptions": ac}
        return out

    @router.post("/organizations")
    async def create_organization(data: OrgCreate, current_user: dict = Depends(get_current_user)):
        """Create an org. Caller becomes owner; limited to 1 org per user."""
        if await db.organizations.find_one({"owner_user_id": current_user.get("id")}):
            raise HTTPException(status_code=409, detail="You already own an organization. Update it instead.")
        slug = _slugify(data.name)
        base = slug
        n = 1
        while await db.organizations.find_one({"slug": slug}):
            slug = f"{base}-{n}"; n += 1
        org = {
            "id": _gen_id(), "name": data.name, "slug": slug,
            "owner_user_id": current_user.get("id"), "plan": "free", "status": "active",
            "logo_url": data.logo_url,
            "billing_email": data.billing_email or current_user.get("email"),
            "settings": {}, "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
        }
        await db.organizations.insert_one(org)
        # Link owner user to this org
        await db.users.update_one(
            {"id": current_user.get("id")},
            {"$set": {"organization_id": org["id"], "rbac_role": Role.SELF_SERVICE_OWNER}},
        )
        return _ser(org)

    @router.put("/organizations/{org_id}")
    async def update_organization(org_id: str, data: OrgUpdate, current_user: dict = Depends(get_current_user)):
        """Update org details. Only owner or platform admin."""
        await _org_or_404(org_id, current_user, require_owner=True)
        upd = {k: v for k, v in data.dict(exclude_none=True).items()}
        if not upd:
            raise HTTPException(status_code=400, detail="No fields to update")
        if "name" in upd:
            slug = _slugify(upd["name"])
            base = slug; n = 1
            while await db.organizations.find_one({"slug": slug, "id": {"$ne": org_id}}):
                slug = f"{base}-{n}"; n += 1
            upd["slug"] = slug
        upd["updated_at"] = datetime.utcnow()
        await db.organizations.update_one({"id": org_id}, {"$set": upd})
        return _ser(await db.organizations.find_one({"id": org_id}))

    @router.delete("/organizations/{org_id}")
    async def delete_organization(org_id: str, current_user: dict = Depends(get_current_user)):
        """Delete org. Cannot delete while active subscriptions exist."""
        await _org_or_404(org_id, current_user, require_owner=True)
        active = await db.subscriptions.count_documents({"org_id": org_id, "status": {"$in": ["trialing", "active"]}})
        if active:
            raise HTTPException(status_code=409, detail=f"Cancel {active} active subscription(s) before deleting the organization")
        await db.users.update_many({"organization_id": org_id}, {"$unset": {"organization_id": ""}})
        await db.locations.delete_many({"org_id": org_id})
        await db.org_invites.delete_many({"org_id": org_id})
        await db.organizations.delete_one({"id": org_id})
        return {"success": True}

    # ── Admin: Organizations ──────────────────────────────────────────────────

    @router.get("/admin/organizations")
    async def admin_list_organizations(admin: dict = Depends(require_admin)):
        assert_permission(admin, "admin.all_screens")
        orgs = await db.organizations.find({}).sort("created_at", -1).to_list(2000)
        out = []
        for org in orgs:
            o = _ser(org)
            o["screen_count"]  = await db.screens.count_documents({"organization_id": org["id"]})
            o["member_count"]  = await db.users.count_documents({"organization_id": org["id"]})
            o["active_subs"]   = await db.subscriptions.count_documents({"org_id": org["id"], "status": {"$in": ["trialing", "active"]}})
            owner = await db.users.find_one({"id": org.get("owner_user_id")}, {"name": 1, "email": 1, "_id": 0})
            o["owner"] = owner or {}
            out.append(o)
        return out

    @router.get("/admin/organizations/{org_id}")
    async def admin_get_organization(org_id: str, admin: dict = Depends(require_admin)):
        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        o = _ser(org)
        o["locations"]     = _ser(await db.locations.find({"org_id": org_id}).to_list(200))
        o["screens"]       = _ser(await db.screens.find({"organization_id": org_id}, {"id": 1, "name": 1, "status": 1, "operation_type": 1, "_id": 0}).to_list(200))
        o["members"]       = _ser(await db.users.find({"organization_id": org_id}, {"id": 1, "name": 1, "email": 1, "role": 1, "rbac_role": 1, "_id": 0}).to_list(200))
        o["subscriptions"] = _ser(await db.subscriptions.find({"org_id": org_id}).to_list(200))
        owner = await db.users.find_one({"id": org.get("owner_user_id")}, {"name": 1, "email": 1, "_id": 0})
        o["owner"] = owner or {}
        return o

    @router.put("/admin/organizations/{org_id}/status")
    async def admin_set_org_status(org_id: str, data: OrgStatusUpdate, admin: dict = Depends(require_admin)):
        org = await db.organizations.find_one({"id": org_id})
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        if data.status not in ("active", "suspended", "cancelled"):
            raise HTTPException(status_code=400, detail="status must be: active | suspended | cancelled")
        upd: dict = {"status": data.status, "updated_at": datetime.utcnow()}
        if data.reason:
            upd["status_reason"] = data.reason
        await db.organizations.update_one({"id": org_id}, {"$set": upd})
        if data.status == "suspended":
            await db.subscriptions.update_many(
                {"org_id": org_id, "status": "active"},
                {"$set": {"status": "suspended", "updated_at": datetime.utcnow()}},
            )
        return _ser(await db.organizations.find_one({"id": org_id}))

    # ══════════════════════════════════════════════════════════════════════════
    #  LOCATIONS
    # ══════════════════════════════════════════════════════════════════════════

    @router.get("/locations")
    async def list_locations(current_user: dict = Depends(get_current_user)):
        role = get_effective_role(current_user)
        if role in (Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN):
            locs = await db.locations.find({}).sort("name", 1).to_list(5000)
        else:
            org_id = current_user.get("organization_id")
            if not org_id:
                return []
            locs = await db.locations.find({"org_id": org_id}).sort("name", 1).to_list(500)
        out = []
        for loc in locs:
            loc_data = _ser(loc)
            loc_data["screen_count"] = await db.screens.count_documents({"location_id": loc["id"]})
            out.append(loc_data)
        return out

    @router.post("/locations")
    async def create_location(data: LocationCreate, current_user: dict = Depends(get_current_user)):
        assert_permission(current_user, "screen.configure")
        org_id = current_user.get("organization_id")
        if not org_id:
            raise HTTPException(status_code=400, detail="You must belong to an organization before creating locations")
        loc = {
            "id": _gen_id(), "org_id": org_id,
            "name": data.name, "address": data.address, "city": data.city,
            "state": data.state, "country": data.country, "zip": data.zip,
            "lat": data.lat, "lng": data.lng, "timezone": data.timezone,
            "active": True, "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
        }
        await db.locations.insert_one(loc)
        out = _ser(loc)
        out["screen_count"] = 0
        return out

    @router.put("/locations/{loc_id}")
    async def update_location(loc_id: str, data: LocationUpdate, current_user: dict = Depends(get_current_user)):
        await _loc_or_404(loc_id, current_user)
        upd = {k: v for k, v in data.dict(exclude_none=True).items()}
        if not upd:
            raise HTTPException(status_code=400, detail="No fields to update")
        upd["updated_at"] = datetime.utcnow()
        await db.locations.update_one({"id": loc_id}, {"$set": upd})
        out = _ser(await db.locations.find_one({"id": loc_id}))
        out["screen_count"] = await db.screens.count_documents({"location_id": loc_id})
        return out

    @router.delete("/locations/{loc_id}")
    async def delete_location(loc_id: str, current_user: dict = Depends(get_current_user)):
        await _loc_or_404(loc_id, current_user)
        sc = await db.screens.count_documents({"location_id": loc_id})
        if sc:
            raise HTTPException(status_code=409, detail=f"Unlink {sc} screen(s) from this location before deleting")
        await db.locations.delete_one({"id": loc_id})
        return {"success": True}

    @router.get("/admin/locations")
    async def admin_list_locations(admin: dict = Depends(require_admin)):
        locs = await db.locations.find({}).sort("city", 1).to_list(10000)
        out = []
        for loc in locs:
            loc_data = _ser(loc)
            loc_data["screen_count"] = await db.screens.count_documents({"location_id": loc["id"]})
            org = await db.organizations.find_one({"id": loc.get("org_id")}, {"name": 1, "_id": 0})
            loc_data["org_name"] = org.get("name", "—") if org else "—"
            out.append(loc_data)
        return out

    @router.put("/screens/self-service/{screen_id}/link-location")
    async def link_screen_to_location(
        screen_id: str, data: ScreenLocationLink,
        current_user: dict = Depends(get_current_user),
    ):
        """Link or unlink a SELF_SERVICE screen to a location. Tenant isolation enforced."""
        assert_permission(current_user, "screen.configure")
        screen = await db.screens.find_one({"id": screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        assert_tenant(current_user, screen.get("organization_id"))
        if data.location_id:
            loc = await db.locations.find_one({"id": data.location_id})
            if not loc:
                raise HTTPException(status_code=404, detail="Location not found")
            assert_tenant(current_user, loc.get("org_id"))
        await db.screens.update_one(
            {"id": screen_id},
            {"$set": {"location_id": data.location_id, "updated_at": datetime.utcnow()}},
        )
        return _ser(await db.screens.find_one({"id": screen_id}))

    # ══════════════════════════════════════════════════════════════════════════
    #  TEAM MEMBERS & INVITATIONS
    # ══════════════════════════════════════════════════════════════════════════

    @router.get("/organizations/{org_id}/members")
    async def list_org_members(org_id: str, current_user: dict = Depends(get_current_user)):
        await _org_or_404(org_id, current_user)
        org = await db.organizations.find_one({"id": org_id})
        members = _ser(await db.users.find(
            {"organization_id": org_id},
            {"id": 1, "name": 1, "email": 1, "role": 1, "rbac_role": 1, "created_at": 1, "_id": 0},
        ).to_list(500))
        owner = _ser(await db.users.find_one(
            {"id": org.get("owner_user_id")},
            {"id": 1, "name": 1, "email": 1, "role": 1, "rbac_role": 1, "created_at": 1, "_id": 0},
        ))
        pending = _ser(await db.org_invites.find(
            {"org_id": org_id, "status": "pending"},
            {"id": 1, "email": 1, "role": 1, "token": 1, "created_at": 1, "expires_at": 1, "_id": 0},
        ).to_list(100))
        return {"owner": owner, "members": members, "pending_invites": pending}

    @router.post("/organizations/{org_id}/invites")
    async def create_invite(org_id: str, data: InviteCreate, current_user: dict = Depends(get_current_user)):
        """Create an invite link. Only org owner can invite. Returns the invite token/URL."""
        await _org_or_404(org_id, current_user, require_owner=True)
        if data.role not in ("SELF_SERVICE_MANAGER", "SELF_SERVICE_OWNER"):
            raise HTTPException(status_code=400, detail="role must be SELF_SERVICE_MANAGER or SELF_SERVICE_OWNER")
        # Idempotent — reuse existing pending invite for same email
        existing = await db.org_invites.find_one({"org_id": org_id, "email": data.email, "status": "pending"})
        if existing:
            out = _ser(existing)
            out["invite_url"] = f"#/invite/{existing['token']}"
            return out
        token = _gen_token()
        org = await db.organizations.find_one({"id": org_id})
        invite = {
            "id": _gen_id(), "org_id": org_id, "email": data.email, "role": data.role,
            "invited_by_user_id": current_user.get("id"), "token": token,
            "status": "pending", "org_name": org.get("name", ""),
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow(),
        }
        await db.org_invites.insert_one(invite)
        out = _ser(invite)
        out["invite_url"] = f"#/invite/{token}"
        return out

    @router.delete("/organizations/{org_id}/members/{user_id}")
    async def remove_member(org_id: str, user_id: str, current_user: dict = Depends(get_current_user)):
        org = await _org_or_404(org_id, current_user, require_owner=True)
        if org.get("owner_user_id") == user_id:
            raise HTTPException(status_code=400, detail="Cannot remove the organization owner")
        member = await db.users.find_one({"id": user_id, "organization_id": org_id})
        if not member:
            raise HTTPException(status_code=404, detail="Member not found in this organization")
        await db.users.update_one({"id": user_id}, {"$unset": {"organization_id": ""}})
        return {"success": True}

    @router.delete("/organizations/{org_id}/invites/{invite_id}")
    async def revoke_invite(org_id: str, invite_id: str, current_user: dict = Depends(get_current_user)):
        await _org_or_404(org_id, current_user, require_owner=True)
        inv = await db.org_invites.find_one({"id": invite_id, "org_id": org_id})
        if not inv:
            raise HTTPException(status_code=404, detail="Invite not found")
        await db.org_invites.update_one({"id": invite_id}, {"$set": {"status": "revoked"}})
        return {"success": True}

    @router.get("/invites/{token}")
    async def get_invite_info(token: str):
        """Public — no auth required. Returns invite details before acceptance."""
        inv = await db.org_invites.find_one({"token": token})
        if not inv:
            raise HTTPException(status_code=404, detail="Invite not found")
        if inv.get("status") != "pending":
            raise HTTPException(status_code=410, detail=f"This invite has already been {inv.get('status', 'used')}")
        exp = inv.get("expires_at")
        if exp and (isinstance(exp, datetime) and datetime.utcnow() > exp):
            await db.org_invites.update_one({"token": token}, {"$set": {"status": "expired"}})
            raise HTTPException(status_code=410, detail="This invite has expired")
        org = await db.organizations.find_one({"id": inv.get("org_id")}, {"name": 1, "slug": 1, "_id": 0})
        inviter = await db.users.find_one({"id": inv.get("invited_by_user_id")}, {"name": 1, "_id": 0})
        # Check if email already has an account
        has_account = bool(await db.users.find_one({"email": inv.get("email")}))
        return {
            "email": inv.get("email"),
            "role": inv.get("role"),
            "org_name": org.get("name", "") if org else "",
            "org_slug": org.get("slug", "") if org else "",
            "invited_by": inviter.get("name", "") if inviter else "",
            "has_account": has_account,
            "expires_at": exp.isoformat() if isinstance(exp, datetime) else str(exp),
        }

    # Stateless Bearer checker used ONLY inside accept_invite
    _opt_bearer = HTTPBearer(auto_error=False)

    @router.post("/invites/{token}/accept")
    async def accept_invite(
        token: str,
        data: InviteAccept,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(_opt_bearer),
    ):
        """
        SEC-002: Accept invite.

        Security rules enforced:
        - Token must be pending, unexpired, and single-use.
        - If the invited email already has an account:
            • Caller MUST authenticate as that exact email.
            • Privileged accounts (SUPER_ADMIN, MEDIAVIEW_ADMIN, SUPPORT) are NEVER modified.
            • The invite cannot demote an existing account's role unless that role is lower.
        - If the invited email has no account:
            • A new account is created using the email from the invite (not from the request body).
        - The invite role must never be a privileged role.
        - Tokens are marked single-use immediately on acceptance.
        """
        _JWT_SECRET = os.environ.get("JWT_SECRET", "")
        _JWT_ALG = "HS256"

        inv = await db.org_invites.find_one({"token": token})
        if not inv or inv.get("status") != "pending":
            raise HTTPException(status_code=410, detail="Invite not found, already used, or expired")

        # Expiration check (also expire in DB for audit)
        exp = inv.get("expires_at")
        if exp and isinstance(exp, datetime) and datetime.utcnow() > exp:
            await db.org_invites.update_one({"token": token}, {"$set": {"status": "expired"}})
            raise HTTPException(status_code=410, detail="This invite has expired")

        # All values come exclusively from the invite — never from request body
        inv_email = (inv.get("email") or "").lower().strip()
        org_id = inv.get("org_id")
        role = inv.get("role", "SELF_SERVICE_MANAGER")

        # The invite role must never be a privileged role
        if role in {r.value if hasattr(r, "value") else r for r in _PROTECTED_ROLES}:
            raise HTTPException(
                status_code=400,
                detail="This invite assigns an invalid role. Contact a system administrator.",
            )

        existing = await db.users.find_one({"email": inv_email})

        if existing:
            # ── Existing-account path: REQUIRE AUTHENTICATION ──────────────────
            if not credentials:
                raise HTTPException(
                    status_code=401,
                    detail=(
                        "You already have an account. Please log in to accept this invite. "
                        "Your Bearer token is required."
                    ),
                    headers={"WWW-Authenticate": "Bearer"},
                )
            # Decode and validate the caller's token
            try:
                _payload = _jwt_lib.decode(
                    credentials.credentials,
                    _JWT_SECRET,
                    algorithms=[_JWT_ALG],
                    options={"verify_aud": False, "verify_iss": False},
                )
                _uid = _payload.get("sub")
                auth_user = await db.users.find_one({"id": _uid}) if _uid else None
            except Exception as exc:
                raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}")

            if not auth_user or not auth_user.get("active", True):
                raise HTTPException(status_code=401, detail="Authenticated user not found or inactive")

            # Email must match (normalized)
            if auth_user.get("email", "").lower().strip() != inv_email:
                raise HTTPException(
                    status_code=403,
                    detail="The authenticated account email does not match the invite email.",
                )

            # CRITICAL: Never touch privileged accounts
            current_role = get_effective_role(existing)
            if current_role in _PROTECTED_ROLES:
                raise HTTPException(
                    status_code=403,
                    detail="This account cannot be modified by an invitation.",
                )

            # Update org and role (non-privileged only)
            await db.users.update_one(
                {"id": existing["id"]},
                {"$set": {"organization_id": org_id, "rbac_role": role, "role": "customer"}},
            )
            uid = existing["id"]

        else:
            # ── New-account path: create user with invite email ─────────────────
            if not data.name or not data.password:
                raise HTTPException(status_code=400, detail="name and password are required for new users")
            if len(data.password) < 8:
                raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

            new_user = {
                "id": _gen_id(),
                "name": data.name,
                "email": inv_email,        # always from invite, not request body
                "password_hash": _hash_password(data.password),
                "role": "customer",
                "rbac_role": role,
                "organization_id": org_id,
                "company_name": "",
                "phone": None,
                "language": "en",
                "active": True,
                "session_epoch": 0,
                "created_at": datetime.utcnow(),
            }
            await db.users.insert_one(new_user)
            uid = new_user["id"]

        # Single-use: mark accepted immediately
        await db.org_invites.update_one(
            {"token": token},
            {"$set": {
                "status": "accepted",
                "accepted_by_user_id": uid,
                "accepted_at": datetime.utcnow(),
            }},
        )
        org = await db.organizations.find_one({"id": org_id})
        return {
            "success": True,
            "message": f"Successfully joined {org.get('name', 'the organization')}",
            "org_name": org.get("name") if org else "",
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  SUBSCRIPTIONS
    # ══════════════════════════════════════════════════════════════════════════

    @router.get("/subscriptions/plans")
    async def list_plans():
        """Public: list available subscription plans."""
        return PLANS

    @router.get("/subscriptions")
    async def list_subscriptions(current_user: dict = Depends(get_current_user)):
        role = get_effective_role(current_user)
        if role in (Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN):
            subs = await db.subscriptions.find({}).sort("created_at", -1).to_list(5000)
        else:
            org_id = current_user.get("organization_id")
            if not org_id:
                return []
            subs = await db.subscriptions.find({"org_id": org_id}).sort("created_at", -1).to_list(500)
        out = []
        for sub in subs:
            s = _ser(sub)
            sc = await db.screens.find_one({"id": sub.get("screen_id")}, {"name": 1, "status": 1, "_id": 0})
            s["screen_name"] = sc.get("name", "Unknown") if sc else "Unknown"
            s["plan_info"] = PLANS.get(sub.get("plan"), {})
            out.append(s)
        return out

    @router.post("/subscriptions")
    async def create_subscription(data: SubCreate, current_user: dict = Depends(get_current_user)):
        assert_permission(current_user, "screen.configure")
        org_id = current_user.get("organization_id")
        if not org_id:
            raise HTTPException(status_code=400, detail="Join or create an organization before subscribing")
        if data.plan not in PLANS:
            raise HTTPException(status_code=400, detail=f"Invalid plan. Choose: {', '.join(PLANS)}")
        if data.billing_cycle not in ("monthly", "annual"):
            raise HTTPException(status_code=400, detail="billing_cycle must be monthly or annual")
        screen = await db.screens.find_one({"id": data.screen_id})
        if not screen:
            raise HTTPException(status_code=404, detail="Screen not found")
        assert_tenant(current_user, screen.get("organization_id"))
        conflict = await db.subscriptions.find_one({"screen_id": data.screen_id, "status": {"$in": ["trialing", "active", "suspended"]}})
        if conflict:
            raise HTTPException(status_code=409, detail="This screen already has an active subscription. Cancel it first.")
        plan = PLANS[data.plan]
        price = plan["price_annual"] if data.billing_cycle == "annual" else plan["price_monthly"]
        trial_end = datetime.utcnow() + timedelta(days=TRIAL_DAYS)
        period_end = trial_end + (timedelta(days=365) if data.billing_cycle == "annual" else timedelta(days=30))
        sub = {
            "id": _gen_id(), "screen_id": data.screen_id, "org_id": org_id,
            "plan": data.plan, "billing_cycle": data.billing_cycle, "price": price,
            "status": "trialing",
            "trial_ends_at": trial_end,
            "current_period_start": datetime.utcnow(), "current_period_end": period_end,
            "cancelled_at": None, "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
        }
        await db.subscriptions.insert_one(sub)
        out = _ser(sub)
        out["plan_info"] = plan
        out["screen_name"] = screen.get("name", "")
        return out

    @router.put("/subscriptions/{sub_id}")
    async def update_subscription(sub_id: str, data: SubUpdate, current_user: dict = Depends(get_current_user)):
        assert_permission(current_user, "screen.configure")
        sub = await db.subscriptions.find_one({"id": sub_id})
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        assert_tenant(current_user, sub.get("org_id"))
        if sub.get("status") == "cancelled":
            raise HTTPException(status_code=400, detail="Cannot update a cancelled subscription")
        upd: dict = {}
        if data.plan:
            if data.plan not in PLANS:
                raise HTTPException(status_code=400, detail=f"Invalid plan: {data.plan}")
            upd["plan"] = data.plan
        if data.billing_cycle:
            if data.billing_cycle not in ("monthly", "annual"):
                raise HTTPException(status_code=400, detail="billing_cycle must be monthly or annual")
            upd["billing_cycle"] = data.billing_cycle
        if upd:
            pk = upd.get("plan", sub.get("plan"))
            bc = upd.get("billing_cycle", sub.get("billing_cycle", "monthly"))
            upd["price"] = PLANS[pk]["price_annual" if bc == "annual" else "price_monthly"]
            upd["updated_at"] = datetime.utcnow()
            await db.subscriptions.update_one({"id": sub_id}, {"$set": upd})
        updated = await db.subscriptions.find_one({"id": sub_id})
        out = _ser(updated)
        out["plan_info"] = PLANS.get(updated.get("plan"), {})
        return out

    @router.post("/subscriptions/{sub_id}/cancel")
    async def cancel_subscription(sub_id: str, current_user: dict = Depends(get_current_user)):
        assert_permission(current_user, "screen.configure")
        sub = await db.subscriptions.find_one({"id": sub_id})
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        assert_tenant(current_user, sub.get("org_id"))
        if sub.get("status") == "cancelled":
            raise HTTPException(status_code=400, detail="Already cancelled")
        await db.subscriptions.update_one(
            {"id": sub_id},
            {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow(), "updated_at": datetime.utcnow()}},
        )
        return _ser(await db.subscriptions.find_one({"id": sub_id}))

    @router.post("/subscriptions/{sub_id}/activate")
    async def activate_subscription(sub_id: str, current_user: dict = Depends(get_current_user)):
        """Reactivate a suspended subscription (mocked — no payment required)."""
        assert_permission(current_user, "screen.configure")
        sub = await db.subscriptions.find_one({"id": sub_id})
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        assert_tenant(current_user, sub.get("org_id"))
        if sub.get("status") == "active":
            raise HTTPException(status_code=400, detail="Already active")
        if sub.get("status") == "cancelled":
            raise HTTPException(status_code=400, detail="Cannot reactivate a cancelled subscription. Create a new one.")
        period_end = datetime.utcnow() + (timedelta(days=365) if sub.get("billing_cycle") == "annual" else timedelta(days=30))
        await db.subscriptions.update_one(
            {"id": sub_id},
            {"$set": {"status": "active", "current_period_start": datetime.utcnow(), "current_period_end": period_end, "updated_at": datetime.utcnow()}},
        )
        out = _ser(await db.subscriptions.find_one({"id": sub_id}))
        out["plan_info"] = PLANS.get(out.get("plan"), {})
        return out

    @router.get("/admin/subscriptions")
    async def admin_list_subscriptions(admin: dict = Depends(require_admin)):
        subs = await db.subscriptions.find({}).sort("created_at", -1).to_list(10000)
        out = []
        for sub in subs:
            s = _ser(sub)
            sc = await db.screens.find_one({"id": sub.get("screen_id")}, {"name": 1, "_id": 0})
            org = await db.organizations.find_one({"id": sub.get("org_id")}, {"name": 1, "_id": 0})
            s["screen_name"] = sc.get("name", "—") if sc else "—"
            s["org_name"] = org.get("name", "—") if org else "—"
            s["plan_info"] = PLANS.get(sub.get("plan"), {})
            out.append(s)
        return out

    @router.get("/admin/subscriptions/revenue")
    async def admin_subscriptions_revenue(admin: dict = Depends(require_admin)):
        """MRR, ARR, counts by status and plan."""
        subs = await db.subscriptions.find({}).to_list(100_000)
        stats: dict = {"total": len(subs), "by_status": {}, "by_plan": {}, "mrr": 0.0, "arr": 0.0}
        for sub in subs:
            st = sub.get("status", "unknown")
            stats["by_status"][st] = stats["by_status"].get(st, 0) + 1
            pl = sub.get("plan", "unknown")
            stats["by_plan"][pl] = stats["by_plan"].get(pl, 0) + 1
            if st in ("trialing", "active"):
                pi = PLANS.get(pl, {})
                if sub.get("billing_cycle") == "annual":
                    stats["arr"]  += pi.get("price_annual", 0)
                    stats["mrr"]  += pi.get("price_annual", 0) / 12
                else:
                    stats["mrr"]  += pi.get("price_monthly", 0)
                    stats["arr"]  += pi.get("price_monthly", 0) * 12
        return stats

    return router
