"""
MediAd View — Financial Ledger (Fase 5 · Sprint 1 · Etapa C3).

APPEND-ONLY LIBRO MAYOR FINANCIERO.

Design principles
-----------------
1. Single source of financial truth. Any monetary movement in MediAd View
   (invoice issuance, payment capture, refund, credit note, manual
   adjustment, order cancellation) MUST also insert one immutable entry
   in the `fin_ledger` collection.

2. Entries are IMMUTABLE. There is no `update()` or `delete()` API here.
   A correction is expressed as a NEW compensating entry (reversal), never
   by editing the past.

3. Integrity chain. Every entry stores `hash_prev` (the hash of the
   preceding entry in the same currency scope) and `hash_self` (the sha256
   of its own canonical form). Any tamper attempt breaks the chain and
   is detectable by `verify_chain()`.

4. Multi-currency ready. `currency`, `base_currency` and
   `exchange_rate` are first-class fields. USD is the current base
   currency; DOP is a supported currency. Business logic never assumes
   a specific currency.

5. Tax-model ready. Each entry can carry `tax_breakdown` — a list of
   `{name, rate, amount_cents}` items. Kept generic so we can support
   sales tax, VAT, ITBIS, IVA, GST, etc. without a data migration.

6. Concurrency-safe amount validation. `total_refunded_for_order()`
   returns the sum of prior successful refund entries; callers use a
   conditional atomic update on `orders.refunded_cents` to prevent
   over-refunds under load. This module gives them the reads; the write
   guard lives in the refund service.

Schema of one entry (frozen — Sprint 2 will only add, never rename):
    {
      _id: str (uuid),
      entry_number: int (monotonic per currency, filled by counters),
      ts: datetime (UTC),
      entry_type: str,              # see EntryType.* constants below
      direction: str,               # DEBIT | CREDIT (accounting convention)
      amount_cents: int,            # ALWAYS positive; direction encodes sign
      currency: str,                # ISO-4217 lowercase (e.g. "usd", "dop")
      base_currency: str,           # "usd" for now
      exchange_rate: float | None,  # null when currency == base_currency
      tax_cents_total: int,         # sum of tax_breakdown[].amount_cents
      tax_breakdown: [ {name, rate, amount_cents}, ... ],

      # Cross-refs (any subset may be present, at least one MUST be)
      order_id: str | None,
      invoice_id: str | None,
      credit_note_id: str | None,
      refund_id: str | None,
      payment_intent_id: str | None,

      # Provider info
      provider: str,                # 'dev' | 'stripe' | 'system'
      provider_ref: str | None,     # provider-native reference

      # Who / how
      actor_kind: str,              # 'admin' | 'system' | 'webhook'
      actor_user_id: str | None,
      actor_email: str | None,
      actor_ip: str | None,
      actor_user_agent: str | None,
      reason: str,                  # mandatory business reason
      idempotency_key: str | None,  # dedup for retries

      # DR preparation (empty for USA operations)
      rnc: str | None,
      ncf: str | None,

      # Integrity chain
      hash_prev: str | None,
      hash_self: str,

      metadata: dict,               # free-form audit metadata
    }
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

log = logging.getLogger("financial_ledger")

LEDGER_COLLECTION = "fin_ledger"
COUNTER_COLLECTION = "counters"


# ─────────────────────────────────────────────────────────────────────
# Entry types (extend freely; NEVER remove or rename existing ones)
# ─────────────────────────────────────────────────────────────────────
class EntryType:
    INVOICE_ISSUED       = "INVOICE_ISSUED"        # DEBIT
    PAYMENT_CAPTURED     = "PAYMENT_CAPTURED"      # CREDIT
    REFUND_FULL          = "REFUND_FULL"           # DEBIT (money going back)
    REFUND_PARTIAL       = "REFUND_PARTIAL"        # DEBIT
    CREDIT_NOTE_ISSUED   = "CREDIT_NOTE_ISSUED"    # DEBIT (offsets invoice)
    ORDER_CANCELLED      = "ORDER_CANCELLED"       # informational
    MANUAL_ADJUSTMENT    = "MANUAL_ADJUSTMENT"     # either direction
    CHARGEBACK           = "CHARGEBACK"            # DEBIT
    REFUND_REJECTED      = "REFUND_REJECTED"       # informational (no money)


DIR_DEBIT  = "DEBIT"
DIR_CREDIT = "CREDIT"
DIR_INFO   = "INFO"


# ─────────────────────────────────────────────────────────────────────
# Supported currencies (extend freely — data model is currency-agnostic)
# ─────────────────────────────────────────────────────────────────────
SUPPORTED_CURRENCIES = {"usd", "dop", "eur", "mxn", "brl", "cad", "ars"}
BASE_CURRENCY = "usd"


def is_supported_currency(code: str) -> bool:
    return (code or "").lower() in SUPPORTED_CURRENCIES


def normalise_currency(code: Optional[str]) -> str:
    c = (code or BASE_CURRENCY).lower()
    if c not in SUPPORTED_CURRENCIES:
        raise ValueError(f"currency {c!r} is not supported. "
                         f"Allowed: {sorted(SUPPORTED_CURRENCIES)}")
    return c


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(doc: dict) -> str:
    """Deterministic serialisation for hashing. Skips volatile fields."""
    skip = {"hash_self", "hash_prev", "_id", "entry_number"}
    payload = {k: v for k, v in sorted(doc.items()) if k not in skip}
    def default(o):
        if isinstance(o, datetime):
            # Truncate to millisecond precision — BSON only stores ms,
            # so any microsecond diff would break the chain after a
            # round-trip through Mongo.
            o = o.astimezone(timezone.utc)
            micros = (o.microsecond // 1000) * 1000
            return o.replace(microsecond=micros).isoformat()
        return str(o)
    return json.dumps(payload, sort_keys=True, default=default, separators=(",", ":"))


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _next_ledger_number(db: AsyncIOMotorDatabase, currency: str) -> int:
    """Atomically produce the next per-currency ledger sequence number."""
    counter_id = f"ledger_seq:{currency}"
    doc = await db[COUNTER_COLLECTION].find_one_and_update(
        {"_id": counter_id},
        {"$inc": {"seq": 1},
         "$setOnInsert": {"currency": currency, "created_at": _utcnow()}},
        upsert=True,
        return_document=True,
    )
    return int(doc["seq"])


async def next_credit_note_number(db: AsyncIOMotorDatabase, *, year: Optional[int] = None) -> str:
    """Atomically produce the next CN-YYYY-000001."""
    year = year or _utcnow().year
    counter_id = f"credit_note_number:{year}"
    doc = await db[COUNTER_COLLECTION].find_one_and_update(
        {"_id": counter_id},
        {"$inc": {"seq": 1},
         "$setOnInsert": {"year": year, "created_at": _utcnow()}},
        upsert=True,
        return_document=True,
    )
    return f"CN-{year}-{int(doc['seq']):06d}"


async def next_refund_number(db: AsyncIOMotorDatabase, *, year: Optional[int] = None) -> str:
    """Atomically produce the next RFD-YYYY-000001."""
    year = year or _utcnow().year
    counter_id = f"refund_number:{year}"
    doc = await db[COUNTER_COLLECTION].find_one_and_update(
        {"_id": counter_id},
        {"$inc": {"seq": 1},
         "$setOnInsert": {"year": year, "created_at": _utcnow()}},
        upsert=True,
        return_document=True,
    )
    return f"RFD-{year}-{int(doc['seq']):06d}"


# ─────────────────────────────────────────────────────────────────────
# Core: append_entry — the ONLY write API of this module
# ─────────────────────────────────────────────────────────────────────
async def append_entry(
    db: AsyncIOMotorDatabase,
    *,
    entry_type: str,
    direction: str,
    amount_cents: int,
    currency: str = BASE_CURRENCY,
    order_id: Optional[str] = None,
    invoice_id: Optional[str] = None,
    credit_note_id: Optional[str] = None,
    refund_id: Optional[str] = None,
    payment_intent_id: Optional[str] = None,
    provider: str = "system",
    provider_ref: Optional[str] = None,
    actor_kind: str = "system",
    actor_user_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    actor_ip: Optional[str] = None,
    actor_user_agent: Optional[str] = None,
    reason: str = "",
    idempotency_key: Optional[str] = None,
    tax_breakdown: Optional[list[dict]] = None,
    exchange_rate: Optional[float] = None,
    rnc: Optional[str] = None,
    ncf: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Append an immutable ledger entry. Returns the persisted document.

    Idempotent when `idempotency_key` is provided: a repeat call with the
    same key returns the existing entry unchanged (no duplicate row).

    NEVER raises for auditing side-effects — the caller MUST NOT depend
    on ledger success to move business state. That said, we DO raise if
    the arguments are invalid (bad currency, bad direction, negative
    amount) because those are programmer errors, not runtime issues.
    """
    if amount_cents < 0:
        raise ValueError("amount_cents must be non-negative")
    if direction not in (DIR_DEBIT, DIR_CREDIT, DIR_INFO):
        raise ValueError(f"invalid direction {direction!r}")
    currency = normalise_currency(currency)

    # Fast idempotency: if key present and prior entry exists, return it.
    if idempotency_key:
        prior = await db[LEDGER_COLLECTION].find_one({"idempotency_key": idempotency_key})
        if prior:
            return prior

    tax_breakdown = tax_breakdown or []
    tax_total = int(sum(int(t.get("amount_cents", 0)) for t in tax_breakdown))

    now = _utcnow()
    seq = await _next_ledger_number(db, currency)

    # Chain: fetch hash_self of the last entry FOR THIS CURRENCY.
    last = await db[LEDGER_COLLECTION].find_one(
        {"currency": currency},
        sort=[("entry_number", -1)],
        projection={"hash_self": 1},
    )
    hash_prev = (last or {}).get("hash_self")

    doc = {
        "_id": str(uuid.uuid4()),
        "entry_number": seq,
        "ts": now,
        "entry_type": entry_type,
        "direction": direction,
        "amount_cents": int(amount_cents),
        "currency": currency,
        "base_currency": BASE_CURRENCY,
        "exchange_rate": exchange_rate if currency != BASE_CURRENCY else None,
        "tax_cents_total": tax_total,
        "tax_breakdown": tax_breakdown,
        "order_id": order_id,
        "invoice_id": invoice_id,
        "credit_note_id": credit_note_id,
        "refund_id": refund_id,
        "payment_intent_id": payment_intent_id,
        "provider": provider,
        "provider_ref": provider_ref,
        "actor_kind": actor_kind,
        "actor_user_id": actor_user_id,
        "actor_email": actor_email,
        "actor_ip": actor_ip,
        "actor_user_agent": actor_user_agent,
        "reason": reason,
        "idempotency_key": idempotency_key,
        "rnc": rnc,
        "ncf": ncf,
        "hash_prev": hash_prev,
        "metadata": metadata or {},
    }
    doc["hash_self"] = _hash(f"{hash_prev or ''}|{_canonical_json(doc)}")

    try:
        await db[LEDGER_COLLECTION].insert_one(doc)
    except Exception as e:
        # Duplicate idempotency_key race: fetch and return the winner.
        if idempotency_key:
            prior = await db[LEDGER_COLLECTION].find_one({"idempotency_key": idempotency_key})
            if prior:
                return prior
        log.exception("fin_ledger insert failed: %s", e)
        raise
    log.info("ledger append #%s %s %s %d %s (order=%s)",
             seq, entry_type, direction, amount_cents, currency, order_id)
    return doc


# ─────────────────────────────────────────────────────────────────────
# Read helpers
# ─────────────────────────────────────────────────────────────────────
async def get_ledger_for_order(
    db: AsyncIOMotorDatabase, *, order_id: str, limit: int = 500,
) -> list[dict]:
    cursor = db[LEDGER_COLLECTION].find({"order_id": order_id}).sort("entry_number", 1).limit(limit)
    return [d async for d in cursor]


async def total_refunded_for_order(
    db: AsyncIOMotorDatabase, *, order_id: str, currency: Optional[str] = None,
) -> int:
    """Sum of successful refund entries in the ledger.

    Uses only ledger entries — the ledger is authoritative. Filter by
    currency if given, else sum by matching entry currency separately."""
    q: dict = {
        "order_id": order_id,
        "entry_type": {"$in": [EntryType.REFUND_FULL, EntryType.REFUND_PARTIAL]},
    }
    if currency:
        q["currency"] = normalise_currency(currency)
    total = 0
    async for e in db[LEDGER_COLLECTION].find(q, {"amount_cents": 1}):
        total += int(e.get("amount_cents", 0))
    return total


async def total_paid_for_order(
    db: AsyncIOMotorDatabase, *, order_id: str, currency: Optional[str] = None,
) -> int:
    q: dict = {
        "order_id": order_id,
        "entry_type": EntryType.PAYMENT_CAPTURED,
    }
    if currency:
        q["currency"] = normalise_currency(currency)
    total = 0
    async for e in db[LEDGER_COLLECTION].find(q, {"amount_cents": 1}):
        total += int(e.get("amount_cents", 0))
    return total


async def verify_chain(
    db: AsyncIOMotorDatabase, *, currency: str = BASE_CURRENCY, limit: int = 10000,
) -> dict:
    """Walk the ledger and verify every entry's hash chain. Useful for
    monitoring/audit endpoints. Returns
       {"ok": bool, "checked": int, "broken_entry_number": int|None}.
    """
    currency = normalise_currency(currency)
    prev = None
    checked = 0
    cursor = db[LEDGER_COLLECTION].find({"currency": currency}).sort("entry_number", 1).limit(limit)
    async for e in cursor:
        checked += 1
        recomputed = _hash(f"{e.get('hash_prev') or ''}|{_canonical_json(e)}")
        if recomputed != e.get("hash_self"):
            return {"ok": False, "checked": checked,
                    "broken_entry_number": e.get("entry_number"),
                    "expected_hash": recomputed, "stored_hash": e.get("hash_self")}
        if prev is not None and e.get("hash_prev") != prev:
            return {"ok": False, "checked": checked,
                    "broken_entry_number": e.get("entry_number"),
                    "prev_link": "broken"}
        prev = e.get("hash_self")
    return {"ok": True, "checked": checked, "broken_entry_number": None}
