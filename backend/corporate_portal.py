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
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime


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

    return corporate_router
