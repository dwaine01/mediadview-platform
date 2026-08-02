"""
MediAd View — Admin Refunds / Credit Notes / Ledger HTTP routes
(Fase 5 · Sprint 1 · Etapa C3).

Endpoints (all require permission-based auth):

  Refunds
    POST   /api/admin/orders/{order_id}/refund
    GET    /api/admin/refunds
    GET    /api/admin/refunds/{refund_id}
    POST   /api/admin/refunds/{refund_id}/approve
    POST   /api/admin/refunds/{refund_id}/reject

  Credit Notes
    GET    /api/admin/credit-notes
    GET    /api/admin/credit-notes/{cn_id}
    GET    /api/admin/credit-notes/{cn_id}/pdf
    POST   /api/admin/credit-notes/{cn_id}/reissue-pdf

  Ledger
    GET    /api/admin/orders/{order_id}/ledger
    GET    /api/admin/ledger                    # global list (filters)
    GET    /api/admin/ledger/verify             # walk chain, returns ok/broken
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from permissions import require_permission
from refunds_service import (
    request_refund, approve_refund, reject_refund,
    RF_PENDING_DUAL, RF_SUCCEEDED, RF_FAILED, RF_REJECTED, RF_EXECUTING,
)
from credit_notes_service import (
    regenerate_credit_note_pdf, render_credit_note_pdf,
)
from financial_ledger import (
    get_ledger_for_order, verify_chain, LEDGER_COLLECTION,
    total_paid_for_order, total_refunded_for_order,
    SUPPORTED_CURRENCIES, BASE_CURRENCY,
)

log = logging.getLogger("admin_refunds_routes")


# ─────────────────────────────────────────────────────────────
# Request bodies
# ─────────────────────────────────────────────────────────────
class RefundRequest(BaseModel):
    amount_cents: Optional[int] = Field(default=None, ge=0)
    currency: Optional[str] = None
    reason: str = Field(min_length=10, max_length=2000)
    refund_type: str = Field(default="partial", pattern="^(full|partial)$")


class RejectRefundRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


def _client_meta(request: Request) -> tuple[Optional[str], Optional[str]]:
    ip = None
    if request.client:
        ip = request.client.host
    # honour proxy header if present (already sanitised by our ingress)
    xff = request.headers.get("x-forwarded-for")
    if xff:
        ip = xff.split(",")[0].strip()
    ua = request.headers.get("user-agent")
    return ip, ua


def build_admin_refunds_router(db: AsyncIOMotorDatabase) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["admin_refunds"])
    create_dep  = require_permission("refunds:create")
    approve_dep = require_permission("refunds:approve")
    reject_dep  = require_permission("refunds:reject")
    read_rf_dep = require_permission("refunds:read")
    read_cn_dep = require_permission("credit_notes:read")
    reissue_dep = require_permission("credit_notes:reissue_pdf")
    ledger_dep  = require_permission("ledger:read")

    # ═══════════════════════════════════════════════════════════════
    # POST /api/admin/orders/{order_id}/refund
    # ═══════════════════════════════════════════════════════════════
    @router.post("/orders/{order_id}/refund")
    async def create_refund(
        order_id: str, body: RefundRequest, request: Request,
        admin: dict = Depends(create_dep),
    ):
        ip, ua = _client_meta(request)
        try:
            rf = await request_refund(
                db,
                order_id=order_id,
                amount_cents=body.amount_cents or 0,
                currency=body.currency,
                reason=body.reason,
                refund_type=body.refund_type,
                actor_user_id=str(admin.get("id") or admin.get("_id") or admin.get("email")),
                actor_email=admin.get("email", "unknown"),
                actor_ip=ip,
                actor_user_agent=ua,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            log.exception("refund request failed")
            raise HTTPException(500, f"refund failed: {e}")
        return {"ok": True,
                "refund_id": rf["_id"],
                "status": rf["status"],
                "requires_dual_approval": rf.get("requires_dual_approval"),
                "credit_note_number": rf.get("credit_note_number"),
                "amount_cents": rf.get("amount_cents"),
                "currency": rf.get("currency"),
                "failure_message": rf.get("failure_message")}

    # ═══════════════════════════════════════════════════════════════
    # GET /api/admin/refunds
    # ═══════════════════════════════════════════════════════════════
    @router.get("/refunds")
    async def list_refunds(
        status: Optional[str] = None,
        order_id: Optional[str] = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        _user=Depends(read_rf_dep),
    ):
        q: dict = {}
        if status:   q["status"] = status
        if order_id: q["order_id"] = order_id
        total = await db.refunds.count_documents(q)
        cursor = db.refunds.find(q).sort("created_at", -1).skip(offset).limit(limit)
        items = []
        async for r in cursor:
            items.append({
                "id": r["_id"], "number": r.get("number"),
                "order_id": r.get("order_id"),
                "order_number": r.get("order_number"),
                "status": r.get("status"),
                "amount_cents": r.get("amount_cents"),
                "currency": r.get("currency"),
                "refund_type": r.get("refund_type"),
                "policy": r.get("policy"),
                "requires_dual_approval": r.get("requires_dual_approval"),
                "requested_by": r.get("requested_by"),
                "requested_at": r.get("requested_at"),
                "approved_by": r.get("approved_by"),
                "approved_at": r.get("approved_at"),
                "executed_at": r.get("executed_at"),
                "credit_note_number": r.get("credit_note_number"),
                "provider": r.get("provider"),
                "provider_ref": r.get("provider_ref"),
                "reason": r.get("reason"),
                "failure_message": r.get("failure_message"),
                "created_at": r.get("created_at"),
            })
        counts_pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
        counts = {r["_id"]: r["n"] async for r in db.refunds.aggregate(counts_pipeline)}
        return {"items": items, "total": total, "counts_by_status": counts,
                "limit": limit, "offset": offset}

    # ═══════════════════════════════════════════════════════════════
    # GET /api/admin/refunds/{refund_id}
    # ═══════════════════════════════════════════════════════════════
    @router.get("/refunds/{refund_id}")
    async def get_refund(refund_id: str, _user=Depends(read_rf_dep)):
        r = await db.refunds.find_one({"_id": refund_id})
        if not r:
            raise HTTPException(404, "refund not found")
        # Attach ledger entries for this refund
        entries = []
        async for e in db[LEDGER_COLLECTION].find({"refund_id": refund_id}).sort("entry_number", 1):
            e["_id"] = str(e["_id"])
            entries.append(e)
        r["ledger_entries"] = entries
        cn = await db["fin_credit_notes"].find_one({"refund_id": refund_id})
        r["credit_note"] = cn
        return r

    # ═══════════════════════════════════════════════════════════════
    # POST /api/admin/refunds/{refund_id}/approve
    # ═══════════════════════════════════════════════════════════════
    @router.post("/refunds/{refund_id}/approve")
    async def approve(refund_id: str, request: Request, admin: dict = Depends(approve_dep)):
        ip, ua = _client_meta(request)
        try:
            rf = await approve_refund(
                db, refund_id=refund_id,
                actor_user_id=str(admin.get("id") or admin.get("_id") or admin.get("email")),
                actor_email=admin.get("email", "unknown"),
                actor_ip=ip, actor_user_agent=ua,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True,
                "refund_id": rf["_id"],
                "status": rf["status"],
                "credit_note_number": rf.get("credit_note_number"),
                "failure_message": rf.get("failure_message")}

    # ═══════════════════════════════════════════════════════════════
    # POST /api/admin/refunds/{refund_id}/reject
    # ═══════════════════════════════════════════════════════════════
    @router.post("/refunds/{refund_id}/reject")
    async def reject(refund_id: str, body: RejectRefundRequest,
                     request: Request, admin: dict = Depends(reject_dep)):
        ip, ua = _client_meta(request)
        try:
            rf = await reject_refund(
                db, refund_id=refund_id, reason=body.reason,
                actor_user_id=str(admin.get("id") or admin.get("_id") or admin.get("email")),
                actor_email=admin.get("email", "unknown"),
                actor_ip=ip, actor_user_agent=ua,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "refund_id": rf["_id"], "status": rf["status"]}

    # ═══════════════════════════════════════════════════════════════
    # Credit Notes
    # ═══════════════════════════════════════════════════════════════
    @router.get("/credit-notes")
    async def list_credit_notes(
        status: Optional[str] = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        _user=Depends(read_cn_dep),
    ):
        q: dict = {}
        if status: q["status"] = status
        total = await db["fin_credit_notes"].count_documents(q)
        cursor = db["fin_credit_notes"].find(q).sort("issued_at", -1).skip(offset).limit(limit)
        items = []
        async for cn in cursor:
            items.append({
                "number": cn["_id"], "status": cn.get("status"),
                "order_id": cn.get("order_id"),
                "order_number": cn.get("order_number"),
                "invoice_number": cn.get("invoice_number"),
                "refund_number": cn.get("refund_number"),
                "total_cents": cn.get("total_cents"),
                "currency": cn.get("currency"),
                "issued_at": cn.get("issued_at"),
                "customer_email": (cn.get("customer") or {}).get("email"),
                "customer_name":  (cn.get("customer") or {}).get("name"),
                "pdf_generated_at": cn.get("pdf_generated_at"),
            })
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @router.get("/credit-notes/{cn_id}")
    async def get_credit_note(cn_id: str, _user=Depends(read_cn_dep)):
        cn = await db["fin_credit_notes"].find_one({"_id": cn_id})
        if not cn:
            raise HTTPException(404, "credit note not found")
        cn["_id"] = str(cn["_id"])
        return cn

    @router.get("/credit-notes/{cn_id}/pdf")
    async def download_credit_note_pdf(cn_id: str, _user=Depends(read_cn_dep)):
        cn = await db["fin_credit_notes"].find_one({"_id": cn_id})
        if not cn:
            raise HTTPException(404, "credit note not found")
        pdf = render_credit_note_pdf(cn)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition":
                                 f'inline; filename="{cn_id}.pdf"'})

    @router.post("/credit-notes/{cn_id}/reissue-pdf")
    async def reissue_credit_note_pdf(cn_id: str, admin: dict = Depends(reissue_dep)):
        try:
            pdf = await regenerate_credit_note_pdf(
                db, cn_id=cn_id, actor_email=admin.get("email", "unknown"))
        except ValueError as e:
            raise HTTPException(404, str(e))
        return {"ok": True, "size": len(pdf), "credit_note_id": cn_id}

    # ═══════════════════════════════════════════════════════════════
    # Ledger
    # ═══════════════════════════════════════════════════════════════
    @router.get("/orders/{order_id}/ledger")
    async def get_order_ledger(order_id: str, _user=Depends(ledger_dep)):
        entries = await get_ledger_for_order(db, order_id=order_id)
        for e in entries:
            e["_id"] = str(e["_id"])
        order = await db.orders.find_one({"_id": order_id})
        currency = (order or {}).get("currency") or BASE_CURRENCY
        return {
            "order_id": order_id,
            "currency": currency,
            "amount_cents": (order or {}).get("amount_cents"),
            "refunded_cents": (order or {}).get("refunded_cents", 0),
            "total_paid_cents": await total_paid_for_order(db, order_id=order_id, currency=currency),
            "total_refunded_cents": await total_refunded_for_order(db, order_id=order_id, currency=currency),
            "entries": entries,
            "count": len(entries),
        }

    @router.get("/ledger")
    async def list_ledger(
        entry_type: Optional[str] = None,
        currency: Optional[str] = None,
        order_id: Optional[str] = None,
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        _user=Depends(ledger_dep),
    ):
        q: dict = {}
        if entry_type: q["entry_type"] = entry_type
        if currency:   q["currency"] = currency.lower()
        if order_id:   q["order_id"] = order_id
        total = await db[LEDGER_COLLECTION].count_documents(q)
        cursor = db[LEDGER_COLLECTION].find(q).sort("entry_number", -1).skip(offset).limit(limit)
        items = []
        async for e in cursor:
            e["_id"] = str(e["_id"])
            items.append(e)
        # Aggregate by entry_type
        agg = {}
        async for r in db[LEDGER_COLLECTION].aggregate([
            {"$group": {"_id": "$entry_type", "n": {"$sum": 1},
                        "sum_cents": {"$sum": "$amount_cents"}}}
        ]):
            agg[r["_id"]] = {"count": r["n"], "sum_cents": r["sum_cents"]}
        return {"items": items, "total": total,
                "totals_by_type": agg,
                "supported_currencies": sorted(SUPPORTED_CURRENCIES),
                "base_currency": BASE_CURRENCY,
                "limit": limit, "offset": offset}

    @router.get("/ledger/verify")
    async def verify_ledger(currency: str = Query(default=BASE_CURRENCY),
                            _user=Depends(ledger_dep)):
        try:
            result = await verify_chain(db, currency=currency)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return result

    return router
