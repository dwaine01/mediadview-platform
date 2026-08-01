"""
MediAd View — Financial audit log (Fase 5 · Sprint 1 · Etapa A).

Append-only ledger of every financially-relevant action. Kept in a
dedicated Mongo collection so that at deploy-time we can wire a Mongo
user that has ONLY `insert` on `financial_audit` — no update, no delete,
no drop. The audit is our "black box recorder" and must survive a full
compromise of the web-api.

Public API:
    audit(db, *, action, ...) → inserts one entry, never raises to caller
                                (auditing must NEVER break a business flow;
                                 a failure is logged loudly instead)
    next_invoice_number(db, year) → atomic INV-YYYY-000001 generator

Schema (documented once here, enforced by tests):
    {
      _id, ts, request_id, idempotency_key,
      actor_kind: "user"|"guest"|"system"|"webhook",
      actor_id, actor_ip,
      action,                     # e.g. "payment_intent.create", "refund.request"
      entity_type, entity_id,     # e.g. "order", "ord_abc"
      stripe_event_id, stripe_object_id,
      amount_cents, currency,
      state_before, state_after,
      reason, metadata            # free-form
    }
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

log = logging.getLogger("financial_audit")

AUDIT_COLLECTION = "financial_audit"
COUNTER_COLLECTION = "counters"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def audit(
    db: AsyncIOMotorDatabase,
    *,
    action: str,
    actor_kind: str = "system",
    actor_id: Optional[str] = None,
    actor_ip: Optional[str] = None,
    request_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    stripe_event_id: Optional[str] = None,
    stripe_object_id: Optional[str] = None,
    amount_cents: Optional[int] = None,
    currency: Optional[str] = None,
    state_before: Optional[str] = None,
    state_after: Optional[str] = None,
    reason: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Insert one audit entry. NEVER raises — audit failure MUST NOT break
    the business flow (that would be a self-DoS). Failures go to stderr
    via the logger and to Sentry via the observability wiring."""
    doc = {
        "_id": str(uuid.uuid4()),
        "ts": _utcnow(),
        "action": action,
        "actor_kind": actor_kind,
        "actor_id": actor_id,
        "actor_ip": actor_ip,
        "request_id": request_id,
        "idempotency_key": idempotency_key,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "stripe_event_id": stripe_event_id,
        "stripe_object_id": stripe_object_id,
        "amount_cents": amount_cents,
        "currency": currency,
        "state_before": state_before,
        "state_after": state_after,
        "reason": reason,
        "metadata": metadata or {},
    }
    try:
        await db[AUDIT_COLLECTION].insert_one(doc)
    except Exception:
        # Never propagate — log and continue.
        log.exception("financial_audit insert failed (action=%s entity=%s)",
                      action, entity_id)


async def next_invoice_number(db: AsyncIOMotorDatabase, *, year: Optional[int] = None) -> str:
    """Atomically produce the next INV-YYYY-000001 for the given year.

    Uses find_one_and_update with $inc and upsert=True on a small
    `counters` doc, so two concurrent web-api workers can NEVER hand out
    the same number. If Mongo is unavailable we raise — the caller
    (invoice creation) will then also fail cleanly instead of assigning
    a duplicate number.
    """
    year = year or _utcnow().year
    counter_id = f"invoice_number:{year}"
    doc = await db[COUNTER_COLLECTION].find_one_and_update(
        {"_id": counter_id},
        {"$inc": {"seq": 1}, "$setOnInsert": {"year": year, "created_at": _utcnow()}},
        upsert=True,
        return_document=True,  # after increment
    )
    # Motor returns the post-update document because return_document=True
    # maps to pymongo's ReturnDocument.AFTER.
    seq = int(doc["seq"])
    return f"INV-{year}-{seq:06d}"
