"""
MediAd View — Admin Orders (Sprint 1 · Etapa C1).

Endpoints:
    GET  /api/admin/orders                → paginated list with filters
    GET  /api/admin/orders/{id}           → detail (client + screen + media + audit)
    POST /api/admin/orders/{id}/approve   → pending_review → approved
    POST /api/admin/orders/{id}/reject    → pending_review → rejected (with reason)
    POST /api/admin/orders/{id}/request-changes → pending_review → changes_requested
    POST /api/admin/orders/{id}/dev-mark-paid  → DEV-ONLY: simulates Stripe webhook

Design:
    · All routes require admin auth (require_admin dep from server.py).
    · Every action is audited via financial_audit.
    · State transitions go through order_state.assert_transition —
      illegal moves return 409.
    · Notifications: a minimal in-DB record is created in `notifications`
      so a Sprint 2 mail worker can consume it. NO real email is sent yet.
    · dev-mark-paid is REJECTED when provider.name != "dev" — this is a
      hard guarantee that the button cannot bypass Stripe in production.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from financial_audit import audit
from order_state import (
    STATE_PENDING_REVIEW, STATE_APPROVED, STATE_REJECTED,
    STATE_CHANGES_REQUESTED, STATE_SCHEDULED, STATE_PLAYING,
    STATE_COMPLETED, STATE_PAID,
    assert_transition, InvalidTransition,
)
from payments import get_provider

log = logging.getLogger("admin_orders")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ChangesRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


async def _emit_notification(
    db: AsyncIOMotorDatabase, *,
    kind: str, order: dict, extra: Optional[dict] = None
) -> None:
    """Persist a notification. A Sprint 2 worker will dispatch these via
    email/WhatsApp. For now we just record them so nothing is lost."""
    await db.notifications.insert_one({
        "_id": str(uuid.uuid4()),
        "kind": kind,                    # e.g. 'order.approved'
        "order_id": order["_id"],
        "order_number": order.get("order_number"),
        "to_email": order.get("guest_email"),
        "to_name": order.get("guest_name"),
        "created_at": _utcnow(),
        "sent_at": None,
        "attempts": 0,
        "payload": extra or {},
    })


async def _load_order_or_404(db, order_id: str) -> dict:
    o = await db.orders.find_one({"_id": order_id})
    if not o:
        raise HTTPException(404, "order not found")
    return o


async def _transition(
    db, *, order_id: str, to_state: str, actor: str, actor_email: str,
    reason: str, notification_kind: Optional[str] = None,
    extra_set: Optional[dict] = None,
) -> dict:
    order = await _load_order_or_404(db, order_id)
    from_state = order["status"]

    # True no-op guard: if the caller tries to move to the same state,
    # don't audit, don't notify, don't touch history. Return 409 so the
    # admin UI shows a clear "already in this state" message.
    if from_state == to_state:
        raise HTTPException(409,
            f"order is already in state {to_state!r}")

    try:
        assert_transition(from_state=from_state, to_state=to_state, actor=actor)
    except InvalidTransition as e:
        raise HTTPException(409, str(e))

    update_set = {"status": to_state, "updated_at": _utcnow()}
    if extra_set:
        update_set.update(extra_set)
    if to_state == STATE_APPROVED:
        update_set["approved_at"] = _utcnow()
        update_set["approved_by"] = actor_email

    result = await db.orders.update_one(
        {"_id": order_id, "status": from_state},   # optimistic lock
        {"$set": update_set,
         "$push": {"status_history": {
             "from": from_state, "to": to_state,
             "at": _utcnow(), "by": actor,
             "actor_email": actor_email,
             "reason": reason,
         }}}
    )
    if result.modified_count != 1:
        raise HTTPException(409, "order state changed under us — please refresh")

    order = await _load_order_or_404(db, order_id)
    await audit(db, action=f"admin.order.{to_state}",
                actor_kind="admin", actor_id=actor_email,
                entity_type="order", entity_id=order_id,
                state_before=from_state, state_after=to_state,
                amount_cents=order.get("amount_cents"),
                currency=order.get("currency"),
                reason=reason)
    if notification_kind:
        await _emit_notification(db, kind=notification_kind, order=order,
                                 extra={"reason": reason})

    # Real-time broadcast: order.<newstate>
    try:
        from realtime import manager
        await manager.broadcast_dashboard(f"order.{to_state}", {
            "order_id": order_id,
            "order_number": order.get("order_number"),
            "screen_id": order.get("screen_id"),
            "amount_cents": order.get("amount_cents"),
            "currency": order.get("currency"),
            "guest_email": order.get("guest_email"),
            "actor_email": actor_email,
            "from_state": from_state,
            "to_state": to_state,
        })
    except Exception:
        log.exception("dashboard broadcast (order.%s) failed", to_state)

    return order


def build_admin_orders_router(db: AsyncIOMotorDatabase, require_admin) -> APIRouter:
    # NEW: prefer permission-based deps. Keep `require_admin` in the
    # signature for backwards compat with server.py wiring.
    from permissions import require_permission
    read_dep     = require_permission("orders:read")
    approve_dep  = require_permission("orders:approve")
    dev_dep      = require_permission("orders:dev_mark_paid")
    router = APIRouter(prefix="/api/admin/orders", tags=["admin_orders"])

    # ══════════════════════════════════════════════════════════════
    # GET /api/admin/orders — list with filters
    # ══════════════════════════════════════════════════════════════
    @router.get("")
    async def list_orders(
        status: Optional[str] = None,
        screen_id: Optional[str] = None,
        guest_email: Optional[str] = None,
        provider: Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        admin: dict = Depends(read_dep),
    ):
        q: dict = {}
        if status:      q["status"] = status
        if screen_id:   q["screen_id"] = screen_id
        if guest_email: q["guest_email"] = guest_email.lower()
        if provider:    q["payment_provider"] = provider

        total = await db.orders.count_documents(q)
        cursor = db.orders.find(q).sort("created_at", -1).skip(offset).limit(limit)
        items = []
        async for o in cursor:
            items.append({
                "id": o["_id"],
                "order_number": o.get("order_number"),
                "status": o["status"],
                "screen_id": o.get("screen_id"),
                "screen_name": o.get("screen_name"),
                "guest_email": o.get("guest_email"),
                "guest_name": o.get("guest_name"),
                "amount_cents": o.get("amount_cents"),
                "currency": o.get("currency"),
                "hours": o.get("hours"),
                "created_at": o.get("created_at"),
                "paid_at": o.get("paid_at"),
                "approved_at": o.get("approved_at"),
                "payment_provider": o.get("payment_provider"),
                "payment_intent_id": o.get("stripe_payment_intent_id"),
                "media_id": o.get("media_id"),
            })
        # Aggregate counts by status for the UI badges
        counts_pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
        counts = {r["_id"]: r["n"] async for r in db.orders.aggregate(counts_pipeline)}
        return {"items": items, "total": total, "counts_by_status": counts,
                "limit": limit, "offset": offset}

    # ══════════════════════════════════════════════════════════════
    # GET /api/admin/orders/{id} — detail
    # ══════════════════════════════════════════════════════════════
    @router.get("/{order_id}")
    async def get_order(order_id: str, admin: dict = Depends(read_dep)):
        order = await _load_order_or_404(db, order_id)
        media = None
        if order.get("media_id"):
            media = await db.media.find_one({"id": order["media_id"]})
            if media:
                # scrub the raw base64 for the list view — the UI fetches
                # it on-demand via /api/media/<id> if needed.
                media = {
                    "id": media["id"],
                    "filename": media.get("filename"),
                    "content_type": media.get("content_type"),
                    "size": media.get("size"),
                    "type": media.get("type"),
                    "storage": media.get("storage"),
                    "public_url": media.get("public_url"),
                    "has_inline_data": bool(media.get("data")),
                }
        screen = await db.screens.find_one({"id": order["screen_id"]}) if order.get("screen_id") else None
        if screen:
            screen = {"id": screen["id"], "name": screen.get("name"),
                      "location": screen.get("location"),
                      "specs": screen.get("specs"),
                      "hourly_rate": screen.get("hourly_rate")}
        # Last 50 audit rows for this order
        audits = []
        async for a in db.financial_audit.find(
            {"entity_id": order_id}
        ).sort("ts", -1).limit(50):
            a["_id"] = str(a["_id"])
            audits.append(a)
        return {
            "order": {
                "id": order["_id"],
                "order_number": order.get("order_number"),
                "status": order["status"],
                "created_at": order.get("created_at"),
                "paid_at": order.get("paid_at"),
                "approved_at": order.get("approved_at"),
                "completed_at": order.get("completed_at"),
                "amount_cents": order.get("amount_cents"),
                "refunded_cents": int(order.get("refunded_cents") or 0),
                "currency": order.get("currency"),
                "hours": order.get("hours"),
                "hourly_rate_cents": order.get("hourly_rate_cents"),
                "schedule": order.get("schedule"),
                "status_history": order.get("status_history", []),
                "guest_email": order.get("guest_email"),
                "guest_name": order.get("guest_name"),
                "guest_phone": order.get("guest_phone"),
                "payment_provider": order.get("payment_provider"),
                "payment_intent_id": order.get("stripe_payment_intent_id"),
                "charge_id": order.get("stripe_latest_charge_id"),
                "customer_id": order.get("stripe_customer_id"),
                "media_id": order.get("media_id"),
                "media_snapshot": order.get("media_snapshot"),
            },
            "media": media,
            "screen": screen,
            "audit": audits,
        }

    # ── Media preview passthrough (public_url or inline data) ──
    @router.get("/{order_id}/media")
    async def get_order_media(order_id: str, admin: dict = Depends(read_dep)):
        order = await _load_order_or_404(db, order_id)
        if not order.get("media_id"):
            raise HTTPException(404, "no media")
        m = await db.media.find_one({"id": order["media_id"]})
        if not m:
            raise HTTPException(404, "media not found")
        if m.get("public_url"):
            return {"kind": "url", "url": m["public_url"],
                    "content_type": m.get("content_type")}
        if m.get("data"):
            return {"kind": "inline",
                    "content_type": m.get("content_type"),
                    "data": m["data"]}
        return {"kind": "unknown"}

    # ══════════════════════════════════════════════════════════════
    # POST /api/admin/orders/{id}/approve
    # ══════════════════════════════════════════════════════════════
    @router.post("/{order_id}/approve")
    async def approve_order(order_id: str, admin: dict = Depends(approve_dep)):
        order = await _transition(
            db, order_id=order_id, to_state=STATE_APPROVED,
            actor="admin", actor_email=admin.get("email", "unknown"),
            reason="approved by admin",
            notification_kind="order.approved",
        )
        # C2: auto-emit invoice at approval (idempotent — unique index
        # on fin_invoices.order_id makes retries safe).
        try:
            from invoices_service import issue_invoice_for_order
            inv = await issue_invoice_for_order(
                db, order_id=order_id, actor_email=admin.get("email", "unknown"))
            invoice_number = inv["number"]
        except Exception as e:
            log.exception("auto-invoice emission failed for %s", order_id)
            invoice_number = None
        return {"ok": True, "status": order["status"], "order_id": order_id,
                "invoice_number": invoice_number}

    # ══════════════════════════════════════════════════════════════
    # POST /api/admin/orders/{id}/reject
    # ══════════════════════════════════════════════════════════════
    @router.post("/{order_id}/reject")
    async def reject_order(order_id: str, body: RejectRequest,
                            admin: dict = Depends(approve_dep)):
        order = await _transition(
            db, order_id=order_id, to_state=STATE_REJECTED,
            actor="admin", actor_email=admin.get("email", "unknown"),
            reason=body.reason,
            notification_kind="order.rejected",
            extra_set={"rejected_reason": body.reason},
        )
        return {"ok": True, "status": order["status"], "order_id": order_id}

    # ══════════════════════════════════════════════════════════════
    # POST /api/admin/orders/{id}/request-changes
    # ══════════════════════════════════════════════════════════════
    @router.post("/{order_id}/request-changes")
    async def request_changes(order_id: str, body: ChangesRequest,
                               admin: dict = Depends(approve_dep)):
        order = await _transition(
            db, order_id=order_id, to_state=STATE_CHANGES_REQUESTED,
            actor="admin", actor_email=admin.get("email", "unknown"),
            reason=body.reason,
            notification_kind="order.changes_requested",
            extra_set={"changes_requested_reason": body.reason},
        )
        return {"ok": True, "status": order["status"], "order_id": order_id}

    # ══════════════════════════════════════════════════════════════
    # POST /api/admin/orders/{id}/dev-mark-paid — DEV-ONLY
    # ══════════════════════════════════════════════════════════════
    @router.post("/{order_id}/dev-mark-paid")
    async def dev_mark_paid(order_id: str, admin: dict = Depends(dev_dep)):
        """Only usable when the active provider is LocalDevProvider.
        Calls provider.simulate_event('payment_intent.succeeded') which
        internally routes through the SAME `stripe_events.process_event`
        that handles real Stripe webhooks. So the transition logic is
        identical."""
        provider = get_provider()
        if provider.name != "dev":
            raise HTTPException(403,
                "This endpoint only works with the dev payment provider. "
                "In production, payments are confirmed by the real webhook.")

        order = await _load_order_or_404(db, order_id)
        pi_id = order.get("stripe_payment_intent_id")
        if not pi_id:
            raise HTTPException(409, "order has no PaymentIntent")
        if order["status"] != "payment_processing":
            raise HTTPException(409,
                f"order is in state {order['status']!r} — cannot mark paid "
                "(only orders in payment_processing can be simulated)")

        try:
            event = await provider.simulate_event(
                event_type="payment_intent.succeeded",
                payment_intent_id=pi_id,
            )
        except Exception as e:
            log.exception("simulate_event failed")
            raise HTTPException(500, f"simulate_event failed: {e}")

        await audit(db, action="admin.order.dev_mark_paid",
                    actor_kind="admin", actor_id=admin.get("email"),
                    entity_type="order", entity_id=order_id,
                    reason="dev-only: synthetic webhook",
                    metadata={"event_id": event.id})

        updated = await _load_order_or_404(db, order_id)
        return {"ok": True, "status": updated["status"],
                "payment_intent_id": pi_id,
                "synthetic_event_id": event.id}

    return router
