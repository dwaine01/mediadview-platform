"""
workspace_team_routes.py — Team management inside one customer organization.

The org owner creates accounts for their staff with a temporary password.
Members are forced to set their own password the first time they sign in
(`must_change_password`), and every query is scoped to organization_id.

Team roles exposed to the customer (mapped onto the platform RBAC roles):
  admin    → SELF_SERVICE_OWNER    full access, including billing and team
  manager  → SELF_SERVICE_MANAGER  screens, content, menus, schedules
  employee → SELF_SERVICE_STAFF    prices, photos and publishing only
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Literal, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from rbac import Role, get_effective_role

TeamRole = Literal["admin", "manager", "employee"]

ROLE_TO_RBAC: dict[str, str] = {
    "admin": Role.SELF_SERVICE_OWNER,
    "manager": Role.SELF_SERVICE_MANAGER,
    "employee": Role.SELF_SERVICE_STAFF,
}
RBAC_TO_ROLE: dict[str, str] = {
    Role.SELF_SERVICE_OWNER: "admin",
    Role.SELF_SERVICE_MANAGER: "manager",
    Role.SELF_SERVICE_STAFF: "employee",
}


class MemberCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., min_length=3, max_length=320)
    temporary_password: str = Field(..., min_length=8, max_length=128)
    role: TeamRole = "employee"


class MemberUpdate(BaseModel):
    role: Optional[TeamRole] = None
    active: Optional[bool] = None


class PasswordReset(BaseModel):
    temporary_password: str = Field(..., min_length=8, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _verify(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), (hashed or "").encode())
    except ValueError:
        return False


def _public(user: dict, current_user_id: str) -> dict:
    rbac_role = get_effective_role(user)
    created = user.get("created_at")
    return {
        "id": user["id"],
        "name": user.get("name") or "",
        "email": user.get("email") or "",
        "team_role": RBAC_TO_ROLE.get(rbac_role, "employee"),
        "rbac_role": rbac_role,
        "active": bool(user.get("active", True)),
        "must_change_password": bool(user.get("must_change_password")),
        "is_me": user["id"] == current_user_id,
        "created_at": created.isoformat() if isinstance(created, datetime) else created,
    }


def create_workspace_team_routes(db, get_current_user):
    router = APIRouter(prefix="/api/workspace", tags=["Workspace — Team"])

    async def require_team_manager(current_user: dict = Depends(get_current_user)):
        """Only the org owner/admin can manage team members."""
        if get_effective_role(current_user) != Role.SELF_SERVICE_OWNER:
            raise HTTPException(403, "Solo el dueño o un administrador puede gestionar el equipo.")
        if not current_user.get("organization_id"):
            raise HTTPException(403, "Tu cuenta no está asociada a una organización.")
        return current_user

    async def _member_or_404(member_id: str, current_user: dict) -> dict:
        member = await db.users.find_one({
            "id": member_id,
            "organization_id": current_user["organization_id"],
        })
        if not member:
            raise HTTPException(404, "Miembro no encontrado")
        if member["id"] == current_user["id"]:
            raise HTTPException(400, "No puedes modificar tu propia cuenta desde aquí.")
        return member

    @router.get("/team", summary="List team members of my organization")
    async def list_team(current_user: dict = Depends(get_current_user)):
        org_id = current_user.get("organization_id")
        if not org_id:
            raise HTTPException(403, "Tu cuenta no está asociada a una organización.")
        members = await db.users.find(
            {"organization_id": org_id}, {"password_hash": 0, "_id": 0},
        ).sort("created_at", 1).to_list(200)
        return {
            "can_manage": get_effective_role(current_user) == Role.SELF_SERVICE_OWNER,
            "members": [_public(m, current_user["id"]) for m in members],
        }

    @router.post("/team", summary="Create a team member", status_code=201)
    async def create_member(data: MemberCreate, current_user: dict = Depends(require_team_manager)):
        email = data.email.strip().lower()
        if "@" not in email:
            raise HTTPException(400, "Correo electrónico inválido")
        if await db.users.find_one({"email": email}):
            raise HTTPException(409, "Ese correo ya está registrado en MediaView.")

        now = datetime.utcnow()
        member = {
            "id": str(_uuid.uuid4()),
            "email": email,
            "name": data.name.strip(),
            "company_name": current_user.get("company_name"),
            "role": "customer",
            "rbac_role": ROLE_TO_RBAC[data.role],
            "password_hash": _hash(data.temporary_password),
            "organization_id": current_user["organization_id"],
            "active": True,
            "session_epoch": 0,
            "must_change_password": True,
            "created_by_user_id": current_user["id"],
            "created_at": now,
            "updated_at": now,
        }
        await db.users.insert_one(member)
        return _public(member, current_user["id"])

    @router.patch("/team/{member_id}", summary="Change a member role or activate/deactivate")
    async def update_member(member_id: str, data: MemberUpdate,
                            current_user: dict = Depends(require_team_manager)):
        member = await _member_or_404(member_id, current_user)
        update: dict = {"updated_at": datetime.utcnow()}
        if data.role is not None:
            update["rbac_role"] = ROLE_TO_RBAC[data.role]
        if data.active is not None:
            update["active"] = data.active
        if data.role is not None or data.active is False:
            # invalidate existing sessions on role change / deactivation
            update["session_epoch"] = int(member.get("session_epoch") or 0) + 1
        await db.users.update_one({"id": member_id}, {"$set": update})
        return _public({**member, **update}, current_user["id"])

    @router.post("/team/{member_id}/reset-password", summary="Set a new temporary password")
    async def reset_member_password(member_id: str, data: PasswordReset,
                                    current_user: dict = Depends(require_team_manager)):
        member = await _member_or_404(member_id, current_user)
        await db.users.update_one({"id": member_id}, {"$set": {
            "password_hash": _hash(data.temporary_password),
            "must_change_password": True,
            "session_epoch": int(member.get("session_epoch") or 0) + 1,
            "password_reset_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }})
        return {"message": "Contraseña temporal actualizada", "member_id": member_id}

    @router.delete("/team/{member_id}", summary="Deactivate a member (soft delete)")
    async def deactivate_member(member_id: str, current_user: dict = Depends(require_team_manager)):
        member = await _member_or_404(member_id, current_user)
        await db.users.update_one({"id": member_id}, {"$set": {
            "active": False,
            "session_epoch": int(member.get("session_epoch") or 0) + 1,
            "updated_at": datetime.utcnow(),
        }})
        return {"message": "Miembro desactivado", "member_id": member_id}

    @router.post("/change-password", summary="Change my own password (clears the forced flag)")
    async def change_my_password(data: PasswordChange, current_user: dict = Depends(get_current_user)):
        if not _verify(data.current_password, current_user.get("password_hash", "")):
            raise HTTPException(400, "La contraseña actual no es correcta.")
        if data.current_password == data.new_password:
            raise HTTPException(400, "La nueva contraseña debe ser diferente.")
        await db.users.update_one({"id": current_user["id"]}, {"$set": {
            "password_hash": _hash(data.new_password),
            "must_change_password": False,
            "password_changed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }})
        return {"message": "Contraseña actualizada"}

    return router
