"""
MediAd View — Corporate Client Portal (Phase D.1)

Provides a portal for corporate/business rental clients (users with
role == "corporate") to view their locations, screens, contracts and
invoices. Reuses the existing Finance CRM data model (fin_clients,
fin_contracts, fin_invoices, fin_deposits, fin_payments) so nothing in
the admin CRM is duplicated or disturbed.

Two responsibilities:
  1. Admin-side endpoint to grant / reset portal access for a client
     (creates a `users` doc linked to the fin_client via `client_id`).
     Actually lives under /api/finance/clients/{id}/... in finance.py.
  2. Portal-side endpoints under /api/corporate/* consumed by the
     corporate-portal.js SPA piece.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

corporate_router = APIRouter(prefix="/api/corporate")


def create_corporate_routes(db, get_current_user):

    async def require_corporate(user: dict = Depends(get_current_user)):
        if user.get("role") != "corporate":
            raise HTTPException(403, "Corporate portal access required")
        if not user.get("client_id"):
            raise HTTPException(400, "This account is not linked to a business profile yet. Contact your MediAd View admin.")
        return user

    def _strip(doc):
        if not doc:
            return doc
        doc.pop("_id", None)
        return doc

    @corporate_router.get("/me")
    async def corporate_me(user: dict = Depends(require_corporate)):
        """Return the corporate client's own business profile, locations,
        screens (grouped), plus quick contract/invoice summary. This powers
        the corporate portal HOME view."""
        client_id = user["client_id"]
        client = await db.fin_clients.find_one({"id": client_id})
        if not client:
            raise HTTPException(404, "Business profile not found — please contact your MediAd View admin.")
        _strip(client)

        # Ensure locations / screens keys exist for the front-end
        if not isinstance(client.get("locations"), list):
            client["locations"] = []

        # Attach counts for the frontend header cards
        contracts_cursor = db.fin_contracts.find({"client_id": client_id}).sort("created_at", -1)
        contracts = [_strip(c) async for c in contracts_cursor]

        invoices_cursor = db.fin_invoices.find({"client_id": client_id}).sort("issue_date", -1)
        invoices = [_strip(i) async for i in invoices_cursor]

        # Summaries
        total_screens = 0
        active_locations = 0
        for loc in client["locations"]:
            if loc.get("status", "active") == "active":
                active_locations += 1
            for sc in loc.get("screens", []):
                total_screens += int(sc.get("units", 1))

        open_invoices = [i for i in invoices if i.get("status") in ("pending", "overdue")]
        balance = sum(float(i.get("total", 0)) - float(i.get("amount_paid", 0)) for i in open_invoices)
        active_contract = next((c for c in contracts if c.get("status") == "active"), None)

        return {
            "user": {
                "id": user["id"],
                "email": user.get("email"),
                "name": user.get("name"),
                "must_change_password": bool(user.get("must_change_password", False)),
            },
            "client": {
                "id": client["id"],
                "business_name": client.get("business_name"),
                "representative": client.get("representative"),
                "email": client.get("email"),
                "phone": client.get("phone"),
                "address_line1": client.get("address_line1"),
                "city": client.get("city"),
                "state": client.get("state"),
                "zip": client.get("zip"),
                "country": client.get("country"),
                "status": client.get("status", "active"),
                "locations": client.get("locations", []),
            },
            "summary": {
                "total_locations": len(client["locations"]),
                "active_locations": active_locations,
                "total_screens": total_screens,
                "total_contracts": len(contracts),
                "active_contract_id": active_contract.get("id") if active_contract else None,
                "monthly_total": (active_contract or {}).get("monthly_total", 0),
                "open_invoice_count": len(open_invoices),
                "balance_due": round(balance, 2),
            },
        }

    @corporate_router.get("/contracts")
    async def corporate_contracts(user: dict = Depends(require_corporate)):
        client_id = user["client_id"]
        cursor = db.fin_contracts.find({"client_id": client_id}).sort("created_at", -1)
        return [_strip(c) async for c in cursor]

    @corporate_router.get("/invoices")
    async def corporate_invoices(user: dict = Depends(require_corporate)):
        client_id = user["client_id"]
        cursor = db.fin_invoices.find({"client_id": client_id}).sort("issue_date", -1)
        return [_strip(i) async for i in cursor]

    @corporate_router.get("/invoices/{invoice_id}")
    async def corporate_invoice_detail(invoice_id: str, user: dict = Depends(require_corporate)):
        inv = await db.fin_invoices.find_one({"id": invoice_id, "client_id": user["client_id"]})
        if not inv:
            raise HTTPException(404, "Invoice not found")
        return _strip(inv)

    # ============ D.1.b — MY CONTENT (media library) ============
    #
    # Media is stored inline as a base64 data URL — matches the existing
    # pattern used by screens.photo_base64 and customer_orders.media_data_url,
    # so we don't need to introduce S3 or Cloudflare R2 for the MVP.
    # A single client_media doc looks like:
    #   { id, client_id, kind: 'image'|'video', name, mime, size_bytes,
    #     data_url, screen_ids: [...], status: 'active'|'paused',
    #     schedule: { enabled, days: [0..6], start_time, end_time, priority },
    #     created_at, updated_at }

    def _all_screen_ids(client: dict) -> List[str]:
        ids = []
        for loc in client.get("locations", []):
            for sc in loc.get("screens", []):
                if sc.get("id"):
                    ids.append(sc["id"])
        return ids

    async def _get_own_client(user: dict) -> dict:
        cl = await db.fin_clients.find_one({"id": user["client_id"]})
        if not cl:
            raise HTTPException(404, "Business profile not found")
        return cl

    @corporate_router.get("/screens")
    async def corporate_screens(user: dict = Depends(require_corporate)):
        """Flat list of the client's screens with their location for use in
        multi-select checkboxes (upload / schedule)."""
        cl = await _get_own_client(user)
        out = []
        for loc in cl.get("locations", []):
            for sc in loc.get("screens", []):
                out.append({
                    "id": sc.get("id"),
                    "model": sc.get("model", "MAV-30540S"),
                    "units": int(sc.get("units", 1)),
                    "location_id": loc.get("id"),
                    "location_name": loc.get("name") or "Location",
                    "status": loc.get("status", "active"),
                })
        return out

    @corporate_router.get("/media")
    async def list_media(user: dict = Depends(require_corporate)):
        cursor = db.client_media.find({"client_id": user["client_id"]}).sort("created_at", -1)
        return [_strip(m) async for m in cursor]

    @corporate_router.post("/media")
    async def create_media(payload: dict = Body(...), user: dict = Depends(require_corporate)):
        # Validate mandatory fields
        data_url = (payload.get("data_url") or "").strip()
        if not data_url.startswith("data:"):
            raise HTTPException(400, "Missing or invalid data_url (must be a data:image/... or data:video/... URL)")

        # Size guard — 8 MB base64 ≈ 6 MB actual media
        if len(data_url) > 12 * 1024 * 1024:  # 12MB base64 buffer
            raise HTTPException(413, "File is too large. Maximum 6 MB per upload.")

        mime = data_url.split(";", 1)[0].removeprefix("data:").strip() or "application/octet-stream"
        if mime.startswith("image/"):
            kind = "image"
        elif mime.startswith("video/"):
            kind = "video"
        else:
            raise HTTPException(400, "Unsupported media type. Only images and videos are allowed.")

        cl = await _get_own_client(user)
        # Validate that any screen_ids belong to this client
        allowed = set(_all_screen_ids(cl))
        screen_ids = [s for s in (payload.get("screen_ids") or []) if s in allowed]

        # Sanitise schedule (all optional)
        sch_in = payload.get("schedule") or {}
        schedule = {
            "enabled": bool(sch_in.get("enabled", True)),
            "days": [int(d) for d in (sch_in.get("days") or [0, 1, 2, 3, 4, 5, 6]) if 0 <= int(d) <= 6],
            "start_time": (sch_in.get("start_time") or "00:00")[:5],
            "end_time": (sch_in.get("end_time") or "23:59")[:5],
            "priority": int(sch_in.get("priority") or 1),
        }

        doc = {
            "id": str(uuid.uuid4()),
            "client_id": user["client_id"],
            "kind": kind,
            "mime": mime,
            "name": (payload.get("name") or "Untitled").strip()[:80],
            "size_bytes": int(len(data_url) * 0.75),  # rough decoded size
            "data_url": data_url,
            "screen_ids": screen_ids,
            "status": "active",
            "schedule": schedule,
            "duration_sec": int(payload.get("duration_sec") or 0),
            "created_by": user.get("email"),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        await db.client_media.insert_one(doc)
        return _strip(doc)

    @corporate_router.put("/media/{media_id}")
    async def update_media(media_id: str, payload: dict = Body(...), user: dict = Depends(require_corporate)):
        m = await db.client_media.find_one({"id": media_id, "client_id": user["client_id"]})
        if not m:
            raise HTTPException(404, "Media not found")
        cl = await _get_own_client(user)
        allowed_screens = set(_all_screen_ids(cl))

        update = {}
        if "name" in payload:
            update["name"] = str(payload["name"] or "Untitled").strip()[:80]
        if "screen_ids" in payload:
            update["screen_ids"] = [s for s in (payload["screen_ids"] or []) if s in allowed_screens]
        if "status" in payload and payload["status"] in ("active", "paused"):
            update["status"] = payload["status"]
        if "schedule" in payload and isinstance(payload["schedule"], dict):
            sch_in = payload["schedule"]
            update["schedule"] = {
                "enabled": bool(sch_in.get("enabled", True)),
                "days": sorted({int(d) for d in (sch_in.get("days") or []) if 0 <= int(d) <= 6}),
                "start_time": (sch_in.get("start_time") or "00:00")[:5],
                "end_time": (sch_in.get("end_time") or "23:59")[:5],
                "priority": int(sch_in.get("priority") or 1),
            }
        if not update:
            return _strip(m)

        update["updated_at"] = datetime.utcnow()
        await db.client_media.update_one({"id": media_id}, {"$set": update})
        m2 = await db.client_media.find_one({"id": media_id})
        return _strip(m2)

    @corporate_router.delete("/media/{media_id}")
    async def delete_media(media_id: str, user: dict = Depends(require_corporate)):
        r = await db.client_media.delete_one({"id": media_id, "client_id": user["client_id"]})
        if r.deleted_count == 0:
            raise HTTPException(404, "Media not found")
        return {"ok": True}

    return corporate_router
