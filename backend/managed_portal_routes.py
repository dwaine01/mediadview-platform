"""
managed_portal_routes.py — Fase 4: MediaView Managed Portal
===========================================================

Routes for MANAGED_VIEWER role (view-only client portal) and
admin management of managed accounts.

Collections used:
  - client_requests: change/update requests from managed clients
  - audit_logs:      append-only platform action log
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from rbac import Role, get_effective_role

# ── Request Types / Statuses ─────────────────────────────────────────────────
REQUEST_TYPES = [
    "CONTENT_UPDATE",
    "SCHEDULE_CHANGE",
    "TECHNICAL_ISSUE",
    "ADD_SCREEN",
    "REMOVE_SCREEN",
    "OTHER",
]
REQUEST_STATUSES = ["PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
REQUEST_PRIORITIES = ["LOW", "NORMAL", "HIGH", "URGENT"]


def _gen_id() -> str:
    return str(uuid.uuid4())


# ── Pydantic Models ──────────────────────────────────────────────────────────

class ClientRequestCreate(BaseModel):
    title: str
    request_type: str = "OTHER"
    description: str
    priority: str = "NORMAL"


class ClientRequestStatusUpdate(BaseModel):
    status: str
    admin_notes: Optional[str] = None


# ── Audit Log Helper (exported for use in server.py) ─────────────────────────

async def create_audit_log(
    db,
    action: str,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    org_id: Optional[str] = None,
) -> None:
    """Append-only audit trail. Never throws — errors are silently swallowed."""
    try:
        doc = {
            "id": _gen_id(),
            "action": action,
            "user_id": user_id,
            "user_email": user_email,
            "org_id": org_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details or {},
            "created_at": datetime.utcnow(),
        }
        await db.audit_logs.insert_one(doc)
    except Exception:
        pass  # Audit logging must never break the main flow


# ── Serialiser (avoids circular import with server.py's serialize_doc) ────────

def _serialize(doc):
    if doc is None:
        return None
    if isinstance(doc, list):
        return [_serialize(d) for d in doc]
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == "_id":
                continue
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = _serialize(value)
            elif isinstance(value, list):
                result[key] = _serialize(value)
            else:
                result[key] = value
        return result
    return doc


# ── Route Factory ────────────────────────────────────────────────────────────

def create_managed_portal_routes(db, get_current_user, require_admin):
    """
    Returns a FastAPI router with all Fase 4 routes.

    Routes:
      GET/POST /api/managed/*        — MANAGED_VIEWER role only
      GET/PATCH /api/admin/managed/* — Admin only
      GET       /api/admin/audit-logs — Admin only
    """
    router = APIRouter()

    # ── Role Guard ────────────────────────────────────────────────────────────

    async def _require_managed_viewer(current_user: dict = Depends(get_current_user)):
        role = get_effective_role(current_user)
        if role != Role.MANAGED_VIEWER:
            raise HTTPException(403, "This endpoint is restricted to Managed Viewer accounts")
        return current_user

    # ──────────────────────────────────────────────────────────────────────────
    #  MANAGED VIEWER: Dashboard
    # ──────────────────────────────────────────────────────────────────────────

    @router.get("/api/managed/dashboard")
    async def managed_dashboard(current_user: dict = Depends(_require_managed_viewer)):
        """View-only KPIs for a Managed Viewer client."""
        org_id = current_user.get("organization_id")
        if not org_id:
            return {
                "total_screens": 0,
                "online_screens": 0,
                "offline_screens": 0,
                "total_locations": 0,
                "active_content": 0,
                "pending_requests": 0,
                "screens_status": [],
            }

        screens = await db.screens.find({"organization_id": org_id}).to_list(500)
        screen_ids = [s["id"] for s in screens]

        # Determine online status by heartbeat (last 5 min)
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        online_devices = await db.devices.find(
            {"screen_id": {"$in": screen_ids}, "last_heartbeat": {"$gte": cutoff}}
        ).to_list(500) if screen_ids else []
        online_screen_ids = {d["screen_id"] for d in online_devices}

        online_count = len(online_screen_ids)

        locations = len(set(
            (s.get("location") or {}).get("city", "Unknown") for s in screens
        ))

        active_content = 0
        if screen_ids:
            active_content = await db.playlists.count_documents({
                "screen_ids": {"$in": screen_ids}, "status": "published"
            })

        pending_requests = await db.client_requests.count_documents({
            "org_id": org_id, "status": "PENDING"
        })

        screens_status = []
        for s in screens:
            sid = s.get("id")
            device = await db.devices.find_one(
                {"screen_id": sid},
                {"_id": 0, "last_heartbeat": 1, "status": 1},
            )
            is_online = sid in online_screen_ids
            lh = None
            if device and device.get("last_heartbeat"):
                lh = device["last_heartbeat"].isoformat() \
                    if isinstance(device["last_heartbeat"], datetime) \
                    else str(device["last_heartbeat"])
            screens_status.append({
                "id": sid,
                "name": s.get("name"),
                "location": s.get("location"),
                "status": "online" if is_online else "offline",
                "last_heartbeat": lh,
                "paired": bool(s.get("paired_device_id")),
                "operation_type": s.get("operation_type"),
            })

        return {
            "total_screens": len(screens),
            "online_screens": online_count,
            "offline_screens": len(screens) - online_count,
            "total_locations": locations,
            "active_content": active_content,
            "pending_requests": pending_requests,
            "screens_status": screens_status,
        }

    # ──────────────────────────────────────────────────────────────────────────
    #  MANAGED VIEWER: Screens (read-only)
    # ──────────────────────────────────────────────────────────────────────────

    @router.get("/api/managed/screens")
    async def managed_screens(current_user: dict = Depends(_require_managed_viewer)):
        """List screens that belong to the viewer's organization."""
        org_id = current_user.get("organization_id")
        if not org_id:
            return []

        screens = await db.screens.find({"organization_id": org_id}).to_list(500)
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        result = []
        for s in screens:
            sid = s.get("id")
            device = await db.devices.find_one(
                {"screen_id": sid},
                {"_id": 0, "last_heartbeat": 1, "status": 1, "device_info": 1},
            )
            is_online = (
                device
                and device.get("last_heartbeat")
                and isinstance(device["last_heartbeat"], datetime)
                and device["last_heartbeat"] >= cutoff
            )
            # Count active playlists for this screen
            pl_count = await db.playlists.count_documents({
                "screen_ids": sid, "status": "published"
            })
            doc = _serialize(s)
            doc["device_status"] = (
                "online" if is_online
                else ("offline" if s.get("paired_device_id") else "unpaired")
            )
            lh = None
            if device and device.get("last_heartbeat"):
                lh = device["last_heartbeat"].isoformat() \
                    if isinstance(device["last_heartbeat"], datetime) \
                    else str(device["last_heartbeat"])
            doc["last_heartbeat"] = lh
            doc["active_playlists"] = pl_count
            result.append(doc)
        return result

    # ──────────────────────────────────────────────────────────────────────────
    #  MANAGED VIEWER: Create Change Request
    # ──────────────────────────────────────────────────────────────────────────

    @router.post("/api/managed/requests")
    async def create_managed_request(
        data: ClientRequestCreate,
        current_user: dict = Depends(_require_managed_viewer),
    ):
        """MANAGED_VIEWER submits a change request to their MediaView account manager."""
        if data.request_type not in REQUEST_TYPES:
            raise HTTPException(400, f"request_type must be one of: {REQUEST_TYPES}")
        if data.priority not in REQUEST_PRIORITIES:
            raise HTTPException(400, f"priority must be one of: {REQUEST_PRIORITIES}")
        if not data.title.strip():
            raise HTTPException(400, "title is required")
        if not data.description.strip():
            raise HTTPException(400, "description is required")

        now = datetime.utcnow()
        doc = {
            "id": _gen_id(),
            "org_id": current_user.get("organization_id"),
            "created_by": current_user["id"],
            "created_by_name": current_user.get("name", ""),
            "created_by_email": current_user.get("email", ""),
            "title": data.title.strip()[:200],
            "request_type": data.request_type,
            "description": data.description.strip()[:2000],
            "priority": data.priority,
            "status": "PENDING",
            "admin_notes": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.client_requests.insert_one(doc)
        await create_audit_log(
            db,
            action="request.created",
            user_id=current_user["id"],
            user_email=current_user.get("email"),
            resource_type="client_request",
            resource_id=doc["id"],
            org_id=current_user.get("organization_id"),
            details={"title": doc["title"], "type": doc["request_type"], "priority": doc["priority"]},
        )
        return _serialize(doc)

    # ──────────────────────────────────────────────────────────────────────────
    #  MANAGED VIEWER: List Own Requests
    # ──────────────────────────────────────────────────────────────────────────

    @router.get("/api/managed/requests")
    async def list_managed_requests(current_user: dict = Depends(_require_managed_viewer)):
        """Returns the change requests submitted by the viewer's organization."""
        org_id = current_user.get("organization_id")
        query = (
            {"org_id": org_id} if org_id
            else {"created_by": current_user["id"]}
        )
        reqs = await db.client_requests.find(query).sort("created_at", -1).to_list(200)
        return _serialize(reqs)

    # ──────────────────────────────────────────────────────────────────────────
    #  ADMIN: List All Client Requests
    # ──────────────────────────────────────────────────────────────────────────

    @router.get("/api/admin/managed/requests")
    async def admin_list_requests(
        status: Optional[str] = None,
        org_id: Optional[str] = None,
        limit: int = 200,
        admin: dict = Depends(require_admin),
    ):
        """Admin: browse all managed-client change requests, filterable by status / org."""
        query: dict = {}
        if status:
            query["status"] = status
        if org_id:
            query["org_id"] = org_id
        limit = max(1, min(limit, 500))
        reqs = await db.client_requests.find(query).sort("created_at", -1).limit(limit).to_list(limit)
        return _serialize(reqs)

    # ──────────────────────────────────────────────────────────────────────────
    #  ADMIN: Update Request Status
    # ──────────────────────────────────────────────────────────────────────────

    @router.patch("/api/admin/managed/requests/{req_id}")
    async def admin_update_request(
        req_id: str,
        data: ClientRequestStatusUpdate,
        admin: dict = Depends(require_admin),
    ):
        """Admin: transition a request to IN_PROGRESS, COMPLETED or CANCELLED."""
        if data.status not in REQUEST_STATUSES:
            raise HTTPException(400, f"status must be one of: {REQUEST_STATUSES}")
        req = await db.client_requests.find_one({"id": req_id})
        if not req:
            raise HTTPException(404, "Request not found")
        update: dict = {
            "status": data.status,
            "updated_at": datetime.utcnow(),
        }
        if data.admin_notes is not None:
            update["admin_notes"] = data.admin_notes.strip()[:1000]
        await db.client_requests.update_one({"id": req_id}, {"$set": update})
        await create_audit_log(
            db,
            action="request.status_updated",
            user_id=admin["id"],
            user_email=admin.get("email"),
            resource_type="client_request",
            resource_id=req_id,
            org_id=req.get("org_id"),
            details={"new_status": data.status, "prev_status": req.get("status")},
        )
        updated = await db.client_requests.find_one({"id": req_id})
        return _serialize(updated)

    # ──────────────────────────────────────────────────────────────────────────
    #  ADMIN: Audit Logs
    # ──────────────────────────────────────────────────────────────────────────

    @router.get("/api/admin/audit-logs")
    async def admin_audit_logs(
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        org_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
        admin: dict = Depends(require_admin),
    ):
        """Admin: paginated audit trail, filterable by action, resource_type, org or user."""
        query: dict = {}
        if action:
            query["action"] = action
        if resource_type:
            query["resource_type"] = resource_type
        if org_id:
            query["org_id"] = org_id
        if user_id:
            query["user_id"] = user_id
        limit = max(1, min(limit, 500))
        logs = await db.audit_logs.find(query).sort("created_at", -1).limit(limit).to_list(limit)
        return _serialize(logs)

    # ──────────────────────────────────────────────────────────────────────────
    #  ADMIN: Summary for Managed Clients
    # ──────────────────────────────────────────────────────────────────────────

    @router.get("/api/admin/managed/summary")
    async def admin_managed_summary(admin: dict = Depends(require_admin)):
        """Returns aggregate stats for all managed client orgs."""
        total_requests = await db.client_requests.count_documents({})
        pending = await db.client_requests.count_documents({"status": "PENDING"})
        in_progress = await db.client_requests.count_documents({"status": "IN_PROGRESS"})
        completed = await db.client_requests.count_documents({"status": "COMPLETED"})
        managed_screens = await db.screens.count_documents({"operation_type": "MEDIAVIEW_MANAGED"})
        managed_viewers = await db.users.count_documents({"rbac_role": "MANAGED_VIEWER"})
        return {
            "total_requests": total_requests,
            "pending": pending,
            "in_progress": in_progress,
            "completed": completed,
            "managed_screens": managed_screens,
            "managed_viewers": managed_viewers,
        }

    return router
