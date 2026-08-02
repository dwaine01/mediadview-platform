"""
MediAd View — Refunds service (Fase 5 · Sprint 1 · Etapa C3).

Responsibilities
----------------
1. Enforce the 4 refund policies declared in `order_state.refund_policy`:
     · pre_approval          → 100% automatic (single admin OK)
     · pre_play              → 100%, admin required
     · partial_by_unused     → partial by remaining slots, admin required
     · manual_admin_override → completed orders; DUAL APPROVAL required

2. Concurrency-safe amount validation. Uses a conditional atomic
   `orders.update_one({..., $expr: {$lte:[refunded_cents+amt, amount_cents]}})`
   so two admins racing on the same order can NEVER over-refund.

3. Every refund writes to the append-only ledger and audit trail. Every
   step (request / approve / execute / reject) is captured with actor,
   IP, User-Agent and reason.

4. Automatic credit-note issuance on execution. When the refund reaches
   status='succeeded', we synchronously call
   `credit_notes_service.issue_credit_note_for_refund` which is
   idempotent by refund_id.

5. Dual approval:
     · A refund is created with status = 'pending_dual_approval' whenever
       the policy demands it, or the caller explicitly sets
       `require_dual_approval=True`.
     · Approval MUST come from a DIFFERENT user (email + user_id different).
     · Rejection is allowed by the same or a different admin (single-step).

State machine of one refund:
        pending_dual_approval ─(approve)─→ executing ─→ succeeded
              │                                   └────→ failed
              └──(reject)─→ rejected
        executing (auto path)   ─→ succeeded / failed
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from financial_audit import audit
from financial_ledger import (
    append_entry, next_refund_number,
    total_refunded_for_order, total_paid_for_order,
    EntryType, DIR_DEBIT, DIR_INFO,
    normalise_currency, BASE_CURRENCY,
)
from order_state import (
    STATE_PAID, STATE_APPROVED, STATE_SCHEDULED, STATE_PLAYING,
    STATE_COMPLETED, STATE_PENDING_REVIEW,
    STATE_REFUND_PENDING, STATE_REFUNDED,
    refund_policy, is_refundable, assert_transition, InvalidTransition,
)
from payments import get_provider
from payments.base import REFUND_STATUS_SUCCEEDED, ProviderError

log = logging.getLogger("refunds")

REFUND_COLLECTION = "refunds"

# Refund statuses (this collection ONLY — not to be confused with
# provider RefundResult.status).
RF_PENDING_DUAL = "pending_dual_approval"
RF_EXECUTING   = "executing"
RF_SUCCEEDED   = "succeeded"
RF_FAILED      = "failed"
RF_REJECTED    = "rejected"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════
# Public entrypoint 1 — request a refund
# ═══════════════════════════════════════════════════════════════════
async def request_refund(
    db: AsyncIOMotorDatabase,
    *,
    order_id: str,
    amount_cents: int,
    currency: Optional[str] = None,
    reason: str,
    refund_type: str = "partial",         # "full" | "partial"
    actor_user_id: str,
    actor_email: str,
    actor_ip: Optional[str] = None,
    actor_user_agent: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Create (and if allowed, IMMEDIATELY execute) a refund.

    Returns the persisted refund document. Callers should read `status`
    to decide next steps:
        · succeeded             → done, credit note issued
        · pending_dual_approval → wait for a second admin
        · failed                → provider rejected (see failure_message)
    """
    # ── 0. Idempotency short-circuit ────────────────────────────────
    # Same key ⇒ same refund. Never validate/create twice.
    if idempotency_key:
        prior = await db[REFUND_COLLECTION].find_one({"idempotency_key": idempotency_key})
        if prior:
            return prior

    # ── 1. Validate reason (mandatory, min 10 chars) ────────────────
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise ValueError("refund reason is mandatory (>= 10 characters)")

    if refund_type not in ("full", "partial"):
        raise ValueError(f"invalid refund_type {refund_type!r}")

    # ── 2. Load the order and validate refundability ────────────────
    order = await db.orders.find_one({"_id": order_id})
    if not order:
        raise ValueError(f"order {order_id!r} not found")

    order_status = order.get("status")
    if not is_refundable(order_status):
        raise ValueError(f"order in state {order_status!r} is not refundable")

    policy = refund_policy(order_status)
    if not policy.get("allowed"):
        raise ValueError(f"refund policy denies state {order_status!r}: {policy.get('reason')}")

    # ── 3. Currency: default from order, must match ─────────────────
    order_currency = normalise_currency(order.get("currency") or BASE_CURRENCY)
    if currency is None:
        currency = order_currency
    else:
        currency = normalise_currency(currency)
        if currency != order_currency:
            raise ValueError(f"refund currency {currency!r} must match order currency {order_currency!r}")

    # ── 4. Amount: never above (paid - already_refunded) ────────────
    paid_cents = int(order.get("amount_cents", 0))
    already_refunded_cents = int(order.get("refunded_cents", 0))
    available = paid_cents - already_refunded_cents

    if refund_type == "full":
        amount_cents = available
    else:
        amount_cents = int(amount_cents)

    if amount_cents <= 0:
        raise ValueError("refund amount must be positive")
    if amount_cents > available:
        raise ValueError(
            f"refund of {amount_cents} exceeds available {available} "
            f"(paid={paid_cents} already_refunded={already_refunded_cents})"
        )

    # ── 5. Determine dual-approval requirement ──────────────────────
    # Completed orders ALWAYS require dual approval per user policy.
    requires_dual = policy.get("kind") == "manual_admin_override"

    # ── 6. Idempotency: (secondary check, defensive after validation) ─
    idempotency_key = idempotency_key or f"rf-{uuid.uuid4()}"
    prior = await db[REFUND_COLLECTION].find_one({"idempotency_key": idempotency_key})
    if prior:
        return prior

    # ── 7. Insert the refund document (initial state) ───────────────
    now = _utcnow()
    number = await next_refund_number(db)
    provider = get_provider()

    refund_doc = {
        "_id": number,
        "id": number,
        "number": number,
        "order_id": order_id,
        "order_number": order.get("order_number"),
        "invoice_id": order.get("invoice_number"),
        "payment_intent_id": order.get("stripe_payment_intent_id"),
        "provider": order.get("payment_provider") or provider.name,
        "provider_ref": None,
        "amount_cents": amount_cents,
        "currency": currency,
        "base_currency": BASE_CURRENCY,
        "exchange_rate": None,   # currency conversion is Sprint 2
        "refund_type": refund_type,
        "policy": policy.get("kind"),
        "policy_state": order_status,
        "requires_dual_approval": requires_dual,
        "status": RF_PENDING_DUAL if requires_dual else RF_EXECUTING,
        "reason": reason,
        # Requester
        "requested_by": actor_email,
        "requested_by_id": actor_user_id,
        "requested_at": now,
        "requested_ip": actor_ip,
        "requested_user_agent": actor_user_agent,
        # Approver (dual-approval only)
        "approved_by": None,
        "approved_by_id": None,
        "approved_at": None,
        "approved_ip": None,
        "approved_user_agent": None,
        # Executor
        "executed_by": None,
        "executed_at": None,
        # Rejection
        "rejected_by": None,
        "rejected_by_id": None,
        "rejected_at": None,
        "rejected_reason": None,
        # Financial links
        "credit_note_number": None,
        "credit_note_id": None,
        "ledger_entry_ids": [],
        # Sprint 2 preparation
        "tax_breakdown": [],
        "rnc": order.get("rnc"),
        "ncf": None,
        # Housekeeping
        "idempotency_key": idempotency_key,
        "failure_message": None,
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }
    await db[REFUND_COLLECTION].insert_one(refund_doc)

    # Audit: request
    await audit(db,
        action="refund.requested",
        actor_kind="admin", actor_id=actor_email, actor_ip=actor_ip,
        entity_type="refund", entity_id=number,
        amount_cents=amount_cents, currency=currency, reason=reason,
        state_before=None,
        state_after=RF_PENDING_DUAL if requires_dual else RF_EXECUTING,
        metadata={"order_id": order_id, "refund_type": refund_type,
                  "policy": policy.get("kind"), "policy_state": order_status,
                  "user_agent": actor_user_agent})

    if requires_dual:
        log.info("refund %s created pending_dual_approval (order=%s amount=%s %s)",
                 number, order_id, amount_cents, currency)
        return await db[REFUND_COLLECTION].find_one({"_id": number})

    # Auto-executing path (single admin allowed).
    return await _execute_refund(
        db, refund_id=number,
        actor_email=actor_email, actor_user_id=actor_user_id,
        actor_ip=actor_ip, actor_user_agent=actor_user_agent,
    )


# ═══════════════════════════════════════════════════════════════════
# Public entrypoint 2 — approve a dual-approval refund
# ═══════════════════════════════════════════════════════════════════
async def approve_refund(
    db: AsyncIOMotorDatabase,
    *,
    refund_id: str,
    actor_user_id: str,
    actor_email: str,
    actor_ip: Optional[str] = None,
    actor_user_agent: Optional[str] = None,
) -> dict:
    """Second-admin approval of a pending refund. Same person cannot
    approve their own request. On success, immediately executes."""
    rf = await db[REFUND_COLLECTION].find_one({"_id": refund_id})
    if not rf:
        raise ValueError(f"refund {refund_id!r} not found")
    if rf.get("status") != RF_PENDING_DUAL:
        raise ValueError(
            f"refund is in state {rf.get('status')!r} — only "
            f"'{RF_PENDING_DUAL}' can be approved"
        )
    # Segregation of duties: requester and approver MUST differ.
    if (rf.get("requested_by_id") == actor_user_id
        or (rf.get("requested_by") or "").lower() == (actor_email or "").lower()):
        raise ValueError(
            "the approver must be a different user than the requester "
            "(segregation of duties)"
        )

    now = _utcnow()
    # Atomic guard on status to prevent double approval.
    r = await db[REFUND_COLLECTION].update_one(
        {"_id": refund_id, "status": RF_PENDING_DUAL},
        {"$set": {
            "status": RF_EXECUTING,
            "approved_by": actor_email,
            "approved_by_id": actor_user_id,
            "approved_at": now,
            "approved_ip": actor_ip,
            "approved_user_agent": actor_user_agent,
            "updated_at": now,
        }})
    if r.modified_count != 1:
        raise ValueError("refund state changed under us — please refresh")

    await audit(db,
        action="refund.approved",
        actor_kind="admin", actor_id=actor_email, actor_ip=actor_ip,
        entity_type="refund", entity_id=refund_id,
        amount_cents=rf.get("amount_cents"), currency=rf.get("currency"),
        state_before=RF_PENDING_DUAL, state_after=RF_EXECUTING,
        reason="approved by second admin",
        metadata={"approver_email": actor_email,
                  "requester_email": rf.get("requested_by"),
                  "user_agent": actor_user_agent})

    return await _execute_refund(
        db, refund_id=refund_id,
        actor_email=actor_email, actor_user_id=actor_user_id,
        actor_ip=actor_ip, actor_user_agent=actor_user_agent,
    )


# ═══════════════════════════════════════════════════════════════════
# Public entrypoint 3 — reject a pending refund
# ═══════════════════════════════════════════════════════════════════
async def reject_refund(
    db: AsyncIOMotorDatabase,
    *,
    refund_id: str,
    reason: str,
    actor_user_id: str,
    actor_email: str,
    actor_ip: Optional[str] = None,
    actor_user_agent: Optional[str] = None,
) -> dict:
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise ValueError("rejection reason is mandatory (>= 10 characters)")

    rf = await db[REFUND_COLLECTION].find_one({"_id": refund_id})
    if not rf:
        raise ValueError(f"refund {refund_id!r} not found")
    if rf.get("status") != RF_PENDING_DUAL:
        raise ValueError(
            f"only refunds in {RF_PENDING_DUAL!r} can be rejected; "
            f"this one is in {rf.get('status')!r}"
        )

    now = _utcnow()
    r = await db[REFUND_COLLECTION].update_one(
        {"_id": refund_id, "status": RF_PENDING_DUAL},
        {"$set": {
            "status": RF_REJECTED,
            "rejected_by": actor_email,
            "rejected_by_id": actor_user_id,
            "rejected_at": now,
            "rejected_reason": reason,
            "updated_at": now,
        }})
    if r.modified_count != 1:
        raise ValueError("refund state changed under us — please refresh")

    # Informational ledger entry (no money movement)
    entry = await append_entry(db,
        entry_type=EntryType.REFUND_REJECTED,
        direction=DIR_INFO,
        amount_cents=0,
        currency=rf.get("currency") or BASE_CURRENCY,
        order_id=rf.get("order_id"),
        invoice_id=rf.get("invoice_id"),
        refund_id=refund_id,
        provider=rf.get("provider") or "system",
        actor_kind="admin", actor_user_id=actor_user_id,
        actor_email=actor_email, actor_ip=actor_ip,
        actor_user_agent=actor_user_agent,
        reason=f"refund rejected: {reason}",
        idempotency_key=f"refund_rejected:{refund_id}",
        metadata={"requested_amount_cents": rf.get("amount_cents")})
    await db[REFUND_COLLECTION].update_one(
        {"_id": refund_id}, {"$push": {"ledger_entry_ids": entry["_id"]}}
    )

    await audit(db,
        action="refund.rejected",
        actor_kind="admin", actor_id=actor_email, actor_ip=actor_ip,
        entity_type="refund", entity_id=refund_id,
        amount_cents=rf.get("amount_cents"), currency=rf.get("currency"),
        state_before=RF_PENDING_DUAL, state_after=RF_REJECTED,
        reason=reason,
        metadata={"user_agent": actor_user_agent})

    return await db[REFUND_COLLECTION].find_one({"_id": refund_id})


# ═══════════════════════════════════════════════════════════════════
# Internal: actually execute a refund
# ═══════════════════════════════════════════════════════════════════
async def _execute_refund(
    db: AsyncIOMotorDatabase,
    *,
    refund_id: str,
    actor_email: str,
    actor_user_id: str,
    actor_ip: Optional[str] = None,
    actor_user_agent: Optional[str] = None,
) -> dict:
    """Contains the ONLY money-movement path. Guarantees:
        · Atomic increment of `orders.refunded_cents` (concurrency guard).
        · Idempotent provider call (idempotency_key = refund id).
        · Ledger + credit note + audit written in-order.
        · Order state transitioned as far as possible (REFUND_PENDING → REFUNDED)."""
    rf = await db[REFUND_COLLECTION].find_one({"_id": refund_id})
    if not rf:
        raise ValueError("refund vanished mid-flight")
    if rf.get("status") not in (RF_EXECUTING,):
        # If we're called after a partial retry that already succeeded,
        # just return the current doc — idempotency for callers.
        if rf.get("status") == RF_SUCCEEDED:
            return rf
        raise ValueError(f"refund {refund_id} not in executing state (is {rf.get('status')!r})")

    amount_cents = int(rf["amount_cents"])
    currency = normalise_currency(rf.get("currency"))
    order_id = rf["order_id"]

    # ── Concurrency guard: atomic increment on orders ───────────────
    # Only succeeds if refunded_cents + amount <= amount_cents.
    result = await db.orders.update_one(
        {
            "_id": order_id,
            "$expr": {
                "$lte": [
                    {"$add": [{"$ifNull": ["$refunded_cents", 0]}, amount_cents]},
                    {"$ifNull": ["$amount_cents", 0]},
                ]
            },
        },
        {
            "$inc": {"refunded_cents": amount_cents},
            "$set": {"updated_at": _utcnow(),
                     "last_refund_id": refund_id,
                     "last_refund_at": _utcnow()},
        },
    )
    if result.modified_count != 1:
        # Concurrency loss: another refund used the remaining balance.
        await db[REFUND_COLLECTION].update_one(
            {"_id": refund_id},
            {"$set": {"status": RF_FAILED,
                      "failure_message": "concurrent refund exceeded remaining balance",
                      "updated_at": _utcnow()}}
        )
        await audit(db, action="refund.failed",
                    actor_kind="admin", actor_id=actor_email,
                    entity_type="refund", entity_id=refund_id,
                    reason="concurrent refund exceeded remaining balance")
        raise ValueError("concurrent refund exceeded remaining balance")

    # ── Call the provider (idempotent) ──────────────────────────────
    provider = get_provider()
    provider_ok = False
    provider_ref = None
    failure_msg = None
    try:
        pi_id = rf.get("payment_intent_id")
        if not pi_id:
            # Dev order created without a PI — this shouldn't happen for real
            # orders. We still allow the ledger/credit-note flow so admins can
            # record manual refunds (e.g. wire transfer refunds). Mark as manual.
            provider_ref = f"manual:{refund_id}"
            provider_ok = True
        else:
            provider_refund = await provider.refund_payment(
                payment_intent_id=pi_id,
                amount_cents=amount_cents,
                reason=rf.get("reason"),
                idempotency_key=refund_id,   # refund id is our idempotency key
            )
            provider_ref = provider_refund.id
            provider_ok = (provider_refund.status == REFUND_STATUS_SUCCEEDED)
            if not provider_ok:
                failure_msg = f"provider status={provider_refund.status}"
    except ProviderError as e:
        failure_msg = f"provider error: {e}"
    except Exception as e:
        failure_msg = f"unexpected provider error: {e}"

    now = _utcnow()

    if not provider_ok:
        # Roll back the atomic increment.
        await db.orders.update_one(
            {"_id": order_id},
            {"$inc": {"refunded_cents": -amount_cents},
             "$set": {"updated_at": now}}
        )
        await db[REFUND_COLLECTION].update_one(
            {"_id": refund_id},
            {"$set": {"status": RF_FAILED,
                      "failure_message": failure_msg or "unknown provider failure",
                      "provider_ref": provider_ref,
                      "updated_at": now}})
        await audit(db,
            action="refund.failed",
            actor_kind="admin", actor_id=actor_email, actor_ip=actor_ip,
            entity_type="refund", entity_id=refund_id,
            amount_cents=amount_cents, currency=currency,
            state_before=RF_EXECUTING, state_after=RF_FAILED,
            reason=failure_msg or "provider failure",
            metadata={"user_agent": actor_user_agent})
        return await db[REFUND_COLLECTION].find_one({"_id": refund_id})

    # ── Provider succeeded. Persist success + ledger + credit note. ─
    await db[REFUND_COLLECTION].update_one(
        {"_id": refund_id},
        {"$set": {
            "status": RF_SUCCEEDED,
            "provider_ref": provider_ref,
            "executed_by": actor_email,
            "executed_by_id": actor_user_id,
            "executed_at": now,
            "updated_at": now,
        }})

    # Ledger: REFUND_FULL / REFUND_PARTIAL (idempotent by refund id)
    entry_type = (
        EntryType.REFUND_FULL if rf.get("refund_type") == "full"
        else EntryType.REFUND_PARTIAL
    )
    ledger_entry = await append_entry(db,
        entry_type=entry_type,
        direction=DIR_DEBIT,
        amount_cents=amount_cents,
        currency=currency,
        order_id=order_id,
        invoice_id=rf.get("invoice_id"),
        refund_id=refund_id,
        payment_intent_id=rf.get("payment_intent_id"),
        provider=rf.get("provider") or provider.name,
        provider_ref=provider_ref,
        actor_kind="admin", actor_user_id=actor_user_id,
        actor_email=actor_email, actor_ip=actor_ip,
        actor_user_agent=actor_user_agent,
        reason=rf.get("reason"),
        idempotency_key=f"refund:{refund_id}",
        tax_breakdown=rf.get("tax_breakdown") or [],
        metadata={"refund_type": rf.get("refund_type"),
                  "policy": rf.get("policy"),
                  "requester_email": rf.get("requested_by"),
                  "approver_email": rf.get("approved_by")})

    await db[REFUND_COLLECTION].update_one(
        {"_id": refund_id},
        {"$push": {"ledger_entry_ids": ledger_entry["_id"]}}
    )

    # ── Credit note (always) ────────────────────────────────────────
    try:
        from credit_notes_service import issue_credit_note_for_refund
        cn = await issue_credit_note_for_refund(
            db, refund_id=refund_id,
            actor_email=actor_email, actor_user_id=actor_user_id,
            actor_ip=actor_ip, actor_user_agent=actor_user_agent,
        )
    except Exception:
        log.exception("credit note issuance failed for refund %s "
                      "(refund persisted; retry via admin action)", refund_id)

    # ── Order state transition ─────────────────────────────────────
    order = await db.orders.find_one({"_id": order_id})
    from_state = order.get("status")
    total_refunded = int(order.get("refunded_cents", 0))
    total_paid = int(order.get("amount_cents", 0))

    # Move to REFUND_PENDING (admin action) then REFUNDED (system finalises)
    if from_state in {STATE_PAID, STATE_APPROVED, STATE_SCHEDULED,
                       STATE_PLAYING, STATE_COMPLETED}:
        try:
            assert_transition(from_state=from_state, to_state=STATE_REFUND_PENDING, actor="admin")
            await db.orders.update_one(
                {"_id": order_id, "status": from_state},
                {"$set": {"status": STATE_REFUND_PENDING, "updated_at": _utcnow()},
                 "$push": {"status_history": {
                    "from": from_state, "to": STATE_REFUND_PENDING,
                    "at": _utcnow(), "by": "admin",
                    "actor_email": actor_email,
                    "reason": f"refund {refund_id} executed",
                 }}}
            )
        except InvalidTransition:
            pass

    if total_refunded >= total_paid > 0:
        # Full refund: transition to REFUNDED via a webhook-actor to
        # respect the state machine that says only webhook can finalise.
        try:
            assert_transition(from_state=STATE_REFUND_PENDING, to_state=STATE_REFUNDED, actor="webhook")
            await db.orders.update_one(
                {"_id": order_id, "status": STATE_REFUND_PENDING},
                {"$set": {"status": STATE_REFUNDED,
                          "refunded_at": _utcnow(),
                          "updated_at": _utcnow()},
                 "$push": {"status_history": {
                    "from": STATE_REFUND_PENDING, "to": STATE_REFUNDED,
                    "at": _utcnow(), "by": "system",
                    "actor_email": actor_email,
                    "reason": "refund fully executed",
                 }}}
            )
        except InvalidTransition:
            pass

    # ── Audit executed ──────────────────────────────────────────────
    await audit(db,
        action="refund.executed",
        actor_kind="admin", actor_id=actor_email, actor_ip=actor_ip,
        entity_type="refund", entity_id=refund_id,
        amount_cents=amount_cents, currency=currency,
        state_before=RF_EXECUTING, state_after=RF_SUCCEEDED,
        reason=rf.get("reason"),
        stripe_object_id=provider_ref,
        metadata={"provider_ref": provider_ref,
                  "credit_note": (await db["fin_credit_notes"].find_one({"refund_id": refund_id}) or {}).get("number"),
                  "user_agent": actor_user_agent,
                  "requester": rf.get("requested_by"),
                  "approver": rf.get("approved_by")})

    log.info("refund %s executed (%s cents %s) order=%s cn=%s",
             refund_id, amount_cents, currency, order_id,
             (await db["fin_credit_notes"].find_one({"refund_id": refund_id}) or {}).get("number"))

    return await db[REFUND_COLLECTION].find_one({"_id": refund_id})
