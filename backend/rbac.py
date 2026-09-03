"""
rbac.py — MediaView Role-Based Access Control
==============================================

Single source of truth for roles, permissions, and tenant isolation.

BACKWARD COMPATIBILITY:
  Old role strings (superadmin, admin, customer, corporate) are automatically
  mapped to new RBAC roles via ROLE_MIGRATION_MAP. Existing JWTs keep working
  because the dependency reads the user from DB and resolves the effective role.

USAGE:
  from rbac import require_permission, get_effective_role, OperationType

  # In a FastAPI route:
  @router.post("/screens")
  async def create(
      user: dict = Depends(require_permission("screen.create.self_service"))
  ):
      ...
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from functools import lru_cache
from typing import Optional

# ── Operation Types ────────────────────────────────────────────────────────
class OperationType:
    SELF_SERVICE        = "SELF_SERVICE"
    PUBLIC_ADVERTISING  = "PUBLIC_ADVERTISING"
    MEDIAVIEW_MANAGED   = "MEDIAVIEW_MANAGED"

ALL_OPERATION_TYPES = [
    OperationType.SELF_SERVICE,
    OperationType.PUBLIC_ADVERTISING,
    OperationType.MEDIAVIEW_MANAGED,
]

# ── RBAC Roles ─────────────────────────────────────────────────────────────
class Role:
    SUPER_ADMIN           = "SUPER_ADMIN"
    MEDIAVIEW_ADMIN       = "MEDIAVIEW_ADMIN"
    SUPPORT               = "SUPPORT"
    SELF_SERVICE_OWNER    = "SELF_SERVICE_OWNER"
    SELF_SERVICE_MANAGER  = "SELF_SERVICE_MANAGER"
    MANAGED_VIEWER        = "MANAGED_VIEWER"
    ADVERTISER            = "ADVERTISER"

ALL_ROLES = [
    Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN, Role.SUPPORT,
    Role.SELF_SERVICE_OWNER, Role.SELF_SERVICE_MANAGER,
    Role.MANAGED_VIEWER, Role.ADVERTISER,
]

# Backward compat: map old role strings → new RBAC role
ROLE_MIGRATION_MAP: dict[str, str] = {
    "superadmin":  Role.SUPER_ADMIN,
    "admin":       Role.MEDIAVIEW_ADMIN,
    "customer":    Role.SELF_SERVICE_OWNER,
    "corporate":   Role.SELF_SERVICE_OWNER,   # re-classify via admin if needed
    "support":     Role.SUPPORT,
    "advertiser":  Role.ADVERTISER,
    "viewer":      Role.MANAGED_VIEWER,
    # New roles pass through unchanged
    Role.SUPER_ADMIN:          Role.SUPER_ADMIN,
    Role.MEDIAVIEW_ADMIN:      Role.MEDIAVIEW_ADMIN,
    Role.SUPPORT:              Role.SUPPORT,
    Role.SELF_SERVICE_OWNER:   Role.SELF_SERVICE_OWNER,
    Role.SELF_SERVICE_MANAGER: Role.SELF_SERVICE_MANAGER,
    Role.MANAGED_VIEWER:       Role.MANAGED_VIEWER,
    Role.ADVERTISER:           Role.ADVERTISER,
}

# ── Permissions Matrix ─────────────────────────────────────────────────────
# Each permission maps to the set of RBAC roles that have it.
PERMISSIONS: dict[str, list[str]] = {
    # ── Screen creation (which types each role can create) ──
    "screen.create.self_service": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
        Role.SELF_SERVICE_OWNER,                  # only within their own org
    ],
    "screen.create.public": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
    ],
    "screen.create.managed": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
    ],
    # ── Screen lifecycle ──
    "screen.pair": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
        Role.SELF_SERVICE_OWNER, Role.SELF_SERVICE_MANAGER,
    ],
    "screen.delete": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
        Role.SELF_SERVICE_OWNER,
    ],
    "screen.configure": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
        Role.SELF_SERVICE_OWNER, Role.SELF_SERVICE_MANAGER,
    ],
    "screen.view": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN, Role.SUPPORT,
        Role.SELF_SERVICE_OWNER, Role.SELF_SERVICE_MANAGER,
        Role.MANAGED_VIEWER,
    ],
    "screen.view_all": [                          # see ALL screens (any org)
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN, Role.SUPPORT,
    ],
    # ── Content & publishing ──
    "content.upload": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
        Role.SELF_SERVICE_OWNER, Role.SELF_SERVICE_MANAGER,
        Role.ADVERTISER,
    ],
    "content.publish": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
        Role.SELF_SERVICE_OWNER, Role.SELF_SERVICE_MANAGER,
    ],
    # ── Advertising ──
    "advertising.purchase": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
        Role.ADVERTISER, Role.SELF_SERVICE_OWNER,
    ],
    "advertising.approve": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
    ],
    # ── Billing ──
    "billing.view": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
        Role.SELF_SERVICE_OWNER,
    ],
    "billing.manage": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
    ],
    # ── Organization & users ──
    "organization.manage": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
        Role.SELF_SERVICE_OWNER,
    ],
    "admin.users": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN,
    ],
    "admin.all_screens": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN, Role.SUPPORT,
    ],
    # ── Player / diagnostics ──
    "player.diagnostics": [
        Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN, Role.SUPPORT,
    ],
}


def get_effective_role(user: dict) -> str:
    """Resolve the effective RBAC role for a user dict.

    Priority: user.rbac_role (new field) → mapped from user.role (legacy).
    Falls back to SELF_SERVICE_OWNER if role is unrecognised.
    """
    rbac_role = user.get("rbac_role") or ""
    if rbac_role in ALL_ROLES:
        return rbac_role
    legacy_role = user.get("role", "")
    return ROLE_MIGRATION_MAP.get(legacy_role, Role.SELF_SERVICE_OWNER)


def has_permission(user: dict, permission: str) -> bool:
    """Return True if the user's effective RBAC role grants ``permission``."""
    role = get_effective_role(user)
    allowed_roles = PERMISSIONS.get(permission, [])
    return role in allowed_roles


def assert_permission(user: dict, permission: str, detail: str | None = None) -> None:
    """Raise HTTP 403 if the user does not have ``permission``."""
    if not has_permission(user, permission):
        role = get_effective_role(user)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail or f"Role '{role}' does not have permission '{permission}'.",
        )


def assert_tenant(user: dict, resource_org_id: Optional[str]) -> None:
    """Raise HTTP 403 if the user cannot access a resource owned by resource_org_id.

    Rules:
      - SUPER_ADMIN / MEDIAVIEW_ADMIN / SUPPORT → can access everything.
      - All other roles → can only access resources that either:
          (a) have no organization_id (legacy / platform resources), OR
          (b) share the same organization_id as the user.
    """
    role = get_effective_role(user)
    if role in (Role.SUPER_ADMIN, Role.MEDIAVIEW_ADMIN, Role.SUPPORT):
        return
    user_org = user.get("organization_id")
    if resource_org_id and resource_org_id != user_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to resources in another organization.",
        )


def effective_operation_type(screen: dict) -> str:
    """Return the canonical operation_type for a screen.

    Migration rule:
      1. If screen already has operation_type set → use it.
      2. If advertising.is_public == True → PUBLIC_ADVERTISING (legacy inference).
      3. Default → SELF_SERVICE.
    """
    ot = screen.get("operation_type")
    if ot in ALL_OPERATION_TYPES:
        return ot
    if screen.get("advertising", {}).get("is_public"):
        return OperationType.PUBLIC_ADVERTISING
    return OperationType.SELF_SERVICE


def assert_can_manage_screen(user: dict, screen: dict) -> None:
    """Raise 403 if user cannot create/modify/delete the given screen.

    Checks:
      1. Permission to manage the screen's operation_type.
      2. Tenant isolation (organization_id match).
    """
    op_type = effective_operation_type(screen)
    role = get_effective_role(user)

    # Which permission do we need?
    if op_type == OperationType.PUBLIC_ADVERTISING:
        perm = "screen.create.public"
    elif op_type == OperationType.MEDIAVIEW_MANAGED:
        perm = "screen.create.managed"
    else:
        perm = "screen.create.self_service"

    assert_permission(user, perm)
    assert_tenant(user, screen.get("organization_id"))
