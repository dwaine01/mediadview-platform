"""
MediAd View — Stripe webhook event processor (Fase 5 · Sprint 1 · Etapa B).

This module is the ONLY place in the codebase allowed to move an order
from `payment_processing` to `paid` / `payment_failed`. The route file
(`stripe_routes.py`) is a thin wrapper: signature verification + dedup +
handoff to `process_event()` here.

Idempotency
-----------
The webhook endpoint dedups by `stripe_events.event_id UNIQUE` BEFORE
calling this function. If the collection insert succeeds, we process.
If the process itself crashes mid-way, we mark the event `pending` and
Stripe will redeliver — we then repeat, which is safe because each state
transition is idempotent (uses `assert_transition` with `from==to` no-op).

Sprint 1 events handled
-----------------------
· payment_intent.succeeded
· payment_intent.payment_failed
· payment_intent.canceled
· charge.refunded         (updates refund tracking + moves order)
· charge.dispute.created  (freezes playing orders)

All other events are stored and acked (200) but ignored to keep the
Sprint 1 surface tight.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from financial_audit import audit
from order_state import (
    STATE_CANCELLED,
    STATE_DISPUTED,
    STATE_PAID,
    STATE_PAYMENT_FAILED,
    STATE_PAYMENT_PROCESSING,
    STATE_PENDING_REVIEW,
    STATE_PLAYING,
    STATE_REFUNDED,
    STATE_REFUND_PENDING,
    assert_transition,
    InvalidTransition,
)

log = logging.getLogger("stripe_events")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _transition_order(
    db: AsyncIOMotorDatabase,
    *,
    order_id: str,
    to_state: str,
    actor: str,
    reason: str,
    extra_set: dict | None = None,
    event_id: str | None = None,
    stripe_object_id: str | None = None,
) -> str | None:
    """Atomic order transition. Returns the previous state, or None if the
    order wasn't found.

    Uses a filtered update so two concurrent webhook processors cannot
    double-transition — we only update if `status` is still the expected
    `from_state`. If the filter matches nothing we treat it as idempotent
    replay (webhook already applied)."""
    order = await db.orders.find_one({"_id": order_id})
    if not order:
        # An unknown PaymentIntent event — we still ack it (Stripe expects
        # 200), but we log for investigation.
        log.warning("stripe event references unknown order %s", order_id)
        await audit(db, action="stripe.event.unknown_order",
                    actor_kind="webhook", entity_type="order", entity_id=order_id,
                    stripe_event_id=event_id, stripe_object_id=stripe_object_id,
                    reason=reason)
        return None

    from_state = order["status"]
    if from_state == to_state:
        # Duplicate delivery after the state already advanced. Safe no-op.
        return from_state

    try:
        assert_transition(from_state=from_state, to_state=to_state, actor=actor)
    except InvalidTransition as e:
        # Illegal transition. Do NOT force it — just log + audit for admin.
        log.error("stripe webhook rejected illegal transition: %s", e)
        await audit(db, action="stripe.event.illegal_transition",
                    actor_kind="webhook", entity_type="order", entity_id=order_id,
                    stripe_event_id=event_id, stripe_object_id=stripe_object_id,
                    state_before=from_state, state_after=to_state,
                    reason=str(e))
        return from_state

    update_set = {"status": to_state, "updated_at": _utcnow()}
    if extra_set:
        update_set.update(extra_set)

    result = await db.orders.update_one(
        {"_id": order_id, "status": from_state},   # optimistic lock
        {"$set": update_set,
         "$push": {"status_history": {
             "from": from_state, "to": to_state,
             "at": _utcnow(), "by": actor,
             "reason": reason,
             "stripe_event_id": event_id,
         }}}
    )
    if result.modified_count == 1:
        await audit(db, action=f"order.transition.{to_state}",
                    actor_kind="webhook", entity_type="order", entity_id=order_id,
                    stripe_event_id=event_id, stripe_object_id=stripe_object_id,
                    state_before=from_state, state_after=to_state,
                    amount_cents=order.get("amount_cents"),
                    currency=order.get("currency"), reason=reason)
    return from_state


# ─────────────────────────────────────────────────────────────────────
# Individual event handlers
# ─────────────────────────────────────────────────────────────────────
async def _handle_payment_intent_succeeded(db, event: dict) -> str:
    pi = event["data"]["object"]
    order_id = (pi.get("metadata") or {}).get("order_id")
    if not order_id:
        return "no_order_id"

    # Step 1: payment_processing → paid
    prev = await _transition_order(
        db,
        order_id=order_id,
        to_state=STATE_PAID,
        actor="webhook",
        reason="payment_intent.succeeded",
        extra_set={
            "stripe_latest_charge_id": pi.get("latest_charge"),
            "paid_at": _utcnow(),
        },
        event_id=event.get("id"),
        stripe_object_id=pi.get("id"),
    )
    if prev is None:
        return "unknown_order"

    # Step 2: paid → pending_review (immediate, system-driven)
    await _transition_order(
        db,
        order_id=order_id,
        to_state=STATE_PENDING_REVIEW,
        actor="system",
        reason="auto: entering admin review queue",
        event_id=event.get("id"),
        stripe_object_id=pi.get("id"),
    )
    return "ok"


async def _handle_payment_intent_failed(db, event: dict) -> str:
    pi = event["data"]["object"]
    order_id = (pi.get("metadata") or {}).get("order_id")
    if not order_id:
        return "no_order_id"
    err = (pi.get("last_payment_error") or {}).get("message") or "payment_failed"
    await _transition_order(
        db, order_id=order_id, to_state=STATE_PAYMENT_FAILED,
        actor="webhook", reason=f"payment_intent.payment_failed: {err}",
        event_id=event.get("id"), stripe_object_id=pi.get("id"),
    )
    return "ok"


async def _handle_payment_intent_canceled(db, event: dict) -> str:
    pi = event["data"]["object"]
    order_id = (pi.get("metadata") or {}).get("order_id")
    if not order_id:
        return "no_order_id"
    await _transition_order(
        db, order_id=order_id, to_state=STATE_CANCELLED,
        actor="webhook", reason="payment_intent.canceled",
        event_id=event.get("id"), stripe_object_id=pi.get("id"),
    )
    return "ok"


async def _handle_charge_refunded(db, event: dict) -> str:
    """Handles both full and partial refunds coming from Stripe.

    Sprint 1 rule: an order only moves to `refunded` when the FULL amount
    was refunded. Partial refunds leave the order in its current state and
    accumulate refund records for reporting."""
    ch = event["data"]["object"]
    pi_id = ch.get("payment_intent")
    order = await db.orders.find_one({"stripe_payment_intent_id": pi_id})
    if not order:
        return "unknown_order"

    total_refunded = int(ch.get("amount_refunded", 0))
    amount = int(order.get("amount_cents") or 0)
    is_full = total_refunded >= amount > 0

    # Snapshot all refunds embedded in the Charge object
    for r in (ch.get("refunds") or {}).get("data", []) or []:
        await db.refunds.update_one(
            {"stripe_refund_id": r["id"]},
            {"$set": {
                "stripe_refund_id": r["id"],
                "order_id": order["_id"],
                "amount_cents": int(r["amount"]),
                "currency": r["currency"],
                "status": r["status"],
                "reason": r.get("reason"),
                "created_at": datetime.fromtimestamp(int(r["created"]), tz=timezone.utc),
            }},
            upsert=True,
        )

    if is_full and order["status"] == STATE_REFUND_PENDING:
        await _transition_order(
            db, order_id=order["_id"], to_state=STATE_REFUNDED,
            actor="webhook", reason="charge.refunded (full)",
            event_id=event.get("id"), stripe_object_id=ch.get("id"),
        )
    else:
        # No status change; just log the partial refund in audit
        await audit(db, action="stripe.charge.refunded.partial",
                    actor_kind="webhook",
                    entity_type="order", entity_id=order["_id"],
                    stripe_event_id=event.get("id"), stripe_object_id=ch.get("id"),
                    amount_cents=total_refunded, currency=ch.get("currency"),
                    reason=f"amount_refunded={total_refunded}, amount={amount}")
    return "ok"


async def _handle_dispute_created(db, event: dict) -> str:
    """A chargeback was opened by the buyer's bank. If the order is in
    `playing` we freeze it into `disputed`; otherwise we log."""
    disp = event["data"]["object"]
    ch_id = disp.get("charge")
    order = await db.orders.find_one({"stripe_latest_charge_id": ch_id})
    if not order:
        return "unknown_order"
    if order["status"] == STATE_PLAYING:
        await _transition_order(
            db, order_id=order["_id"], to_state=STATE_DISPUTED,
            actor="webhook", reason=f"charge.dispute.created: {disp.get('reason')}",
            event_id=event.get("id"), stripe_object_id=disp.get("id"),
        )
    else:
        await audit(db, action="stripe.dispute.opened",
                    actor_kind="webhook", entity_type="order", entity_id=order["_id"],
                    stripe_event_id=event.get("id"), stripe_object_id=disp.get("id"),
                    reason=disp.get("reason"))
    return "ok"


# ─────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────
_HANDLERS: dict[str, Any] = {
    "payment_intent.succeeded":      _handle_payment_intent_succeeded,
    "payment_intent.payment_failed": _handle_payment_intent_failed,
    "payment_intent.canceled":       _handle_payment_intent_canceled,
    "charge.refunded":               _handle_charge_refunded,
    "charge.dispute.created":        _handle_dispute_created,
}


async def process_event(db: AsyncIOMotorDatabase, event: dict) -> dict:
    """Route the event to the correct handler. Called from the webhook
    route AFTER signature verification and DB dedup.

    Returns:
        {"handled": bool, "result": str}
    """
    etype = event.get("type", "")
    handler = _HANDLERS.get(etype)
    if not handler:
        # Ignored but recorded.
        await audit(db, action="stripe.event.ignored",
                    actor_kind="webhook",
                    stripe_event_id=event.get("id"),
                    metadata={"type": etype})
        return {"handled": False, "result": "ignored"}
    try:
        result = await handler(db, event)
        return {"handled": True, "result": result}
    except Exception as e:
        log.exception("stripe event handler crashed (type=%s id=%s)",
                      etype, event.get("id"))
        await audit(db, action="stripe.event.crashed", actor_kind="webhook",
                    stripe_event_id=event.get("id"), reason=str(e)[:500],
                    metadata={"type": etype})
        raise
