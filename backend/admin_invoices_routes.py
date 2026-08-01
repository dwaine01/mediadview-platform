"""Sprint 1 · Etapa C2 — Invoice HTTP endpoints (admin)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from permissions import require_permission
from invoices_service import issue_invoice_for_order, regenerate_invoice_pdf


def build_admin_invoices_router(db: AsyncIOMotorDatabase) -> APIRouter:
    router = APIRouter(prefix="/api/admin/invoices", tags=["admin_invoices"])
    read_dep    = require_permission("invoices:read")
    reissue_dep = require_permission("invoices:reissue_pdf")

    @router.get("")
    async def list_invoices(
        status: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        _user=Depends(read_dep),
    ):
        q: dict = {}
        if status: q["status"] = status
        if year:   q["_id"] = {"$regex": f"^INV-{year}-"}
        total = await db.fin_invoices.count_documents(q)
        cursor = db.fin_invoices.find(q).sort("issued_at", -1).skip(offset).limit(limit)
        items = []
        async for i in cursor:
            items.append({
                "number": i["_id"],
                "status": i["status"],
                "order_id": i.get("order_id"),
                "order_number": i.get("order_number"),
                "customer_email": (i.get("customer") or {}).get("email"),
                "customer_name":  (i.get("customer") or {}).get("name"),
                "total_cents": i.get("total_cents"),
                "currency": i.get("currency"),
                "issued_at": i.get("issued_at"),
                "paid_at": i.get("paid_at"),
                "pdf_generated_at": i.get("pdf_generated_at"),
            })
        counts_by_status: dict = {}
        async for r in db.fin_invoices.aggregate([{"$group":{"_id":"$status","n":{"$sum":1}}}]):
            counts_by_status[r["_id"]] = r["n"]
        return {"items": items, "total": total,
                "counts_by_status": counts_by_status,
                "limit": limit, "offset": offset}

    @router.get("/{invoice_id}")
    async def get_invoice(invoice_id: str, _user=Depends(read_dep)):
        i = await db.fin_invoices.find_one({"_id": invoice_id})
        if not i:
            raise HTTPException(404, "invoice not found")
        i["_id"] = str(i["_id"])
        return i

    @router.get("/{invoice_id}/pdf")
    async def download_invoice_pdf(invoice_id: str, _user=Depends(read_dep)):
        i = await db.fin_invoices.find_one({"_id": invoice_id})
        if not i:
            raise HTTPException(404, "invoice not found")
        from invoices_service import _render_pdf
        pdf = _render_pdf(i)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition":
                                 f'inline; filename="{invoice_id}.pdf"'})

    @router.post("/{invoice_id}/reissue-pdf")
    async def reissue_pdf(invoice_id: str, user=Depends(reissue_dep)):
        try:
            pdf = await regenerate_invoice_pdf(
                db, invoice_id=invoice_id,
                actor_email=user.get("email", "unknown"))
        except ValueError as e:
            raise HTTPException(404, str(e))
        return {"ok": True, "size": len(pdf), "invoice_id": invoice_id}

    return router
