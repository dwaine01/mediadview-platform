"""
MediAd View — Permissions & RBAC (Sprint 1 · pre-C2).

Design goals:
    · Business logic depends on PERMISSIONS, not on role names.
    · Adding a role means editing ROLE_PERMISSIONS below — no code changes
      in routes.
    · Roles today: superadmin, admin, client. Roles tomorrow (Sprint 2+):
      finance, sales, content_reviewer, operations, read_only.

Usage:
    dep = require_permission("orders:approve")
    @router.post(..., dependencies=[Depends(dep)])

The single-role require_admin() legacy dep is kept for the many pre-Sprint-1
routes that already use it. New routes SHOULD use require_permission().
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

# All known permissions in the system. Keep this list flat and grep-able.
PERMISSIONS = {
    # Orders
    "orders:read",
    "orders:approve",            # approve / reject / request-changes
    "orders:dev_mark_paid",      # dev provider only — see admin_orders_routes

    # Invoices (Sprint 1 C2)
    "invoices:read",
    "invoices:issue",            # trigger a new invoice
    "invoices:reissue_pdf",      # regenerate PDF, same number
    "invoices:void",             # Sprint 2

    # Refunds (Sprint 1 C3)
    "refunds:read",
    "refunds:create",
    "refunds:approve",           # dual-approval second admin
    "refunds:reject",            # reject a pending refund

    # Credit Notes (Sprint 1 C3)
    "credit_notes:read",
    "credit_notes:reissue_pdf",

    # Ledger (Sprint 1 C3)
    "ledger:read",

    # Reports & analytics (Sprint 1 C4)
    "reports:read",
    "reports:export",

    # Finance (CRM)
    "finance:read",
    "finance:write",

    # Screens / Media / Campaigns (existing modules)
    "screens:write",
    "media:write",

    # Global
    "audit:read",
    "settings:write",
}

# Role → permissions grid. "*" = all permissions (superadmin only).
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "superadmin": {"*"},
    "admin": {                                   # today's "admin" = broad
        "orders:read", "orders:approve", "orders:dev_mark_paid",
        "invoices:read", "invoices:issue", "invoices:reissue_pdf",
        "refunds:read", "refunds:create", "refunds:approve", "refunds:reject",
        "credit_notes:read", "credit_notes:reissue_pdf",
        "ledger:read", "reports:read", "reports:export",
        "finance:read", "finance:write",
        "screens:write", "media:write", "audit:read",
    },
    # Sprint 2+ roles — declared now so the DB / seed data can use them
    # without any code change later.
    "finance":          {"invoices:read", "invoices:issue", "invoices:reissue_pdf",
                         "invoices:void", "refunds:read", "refunds:create",
                         "refunds:approve", "refunds:reject",
                         "credit_notes:read", "credit_notes:reissue_pdf",
                         "ledger:read", "reports:read", "reports:export",
                         "finance:read", "finance:write", "audit:read"},
    "sales":            {"orders:read", "reports:read", "finance:read"},
    "content_reviewer": {"orders:read", "orders:approve", "media:write"},
    "operations":       {"orders:read", "screens:write", "media:write", "reports:read"},
    "read_only":        {"orders:read", "invoices:read", "refunds:read",
                         "credit_notes:read", "ledger:read", "reports:read",
                         "finance:read", "audit:read"},
    "client":           set(),                   # public site users
}


def role_has(role: str, perm: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or perm in perms


def user_has(user: dict, perm: str) -> bool:
    return role_has(user.get("role", ""), perm)


def require_permission(perm: str):
    """FastAPI dependency factory. Usage:

        @router.get("/x", dependencies=[Depends(require_permission("orders:read"))])
    """
    if perm not in PERMISSIONS:
        raise ValueError(f"unknown permission {perm!r}")

    # Import here to avoid circular import at module load.
    from server import get_current_user  # type: ignore

    async def _dep(current_user: dict = Depends(get_current_user)) -> dict:
        if not user_has(current_user, perm):
            raise HTTPException(403,
                f"missing permission: {perm} (role={current_user.get('role','?')})")
        return current_user

    return _dep
