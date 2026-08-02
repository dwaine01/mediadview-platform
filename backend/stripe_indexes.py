"""
MediAd View — Stripe-related MongoDB indexes (Fase 5 · Sprint 1 · Etapa A).

Idempotent. Called from server.startup(). Every index here corresponds
to a hard invariant of the Stripe blueprint (see docs/FASE5_STRIPE_ARCHITECTURE.md).

Rules for editing this file:
  · Adding a new index → OK.
  · Renaming/removing → OK only if the collection is empty in prod, or
    with an explicit migration script; NEVER edit silently.
  · Every unique index MUST have a `partialFilterExpression` if the field
    can be NULL, otherwise inserts will collide on the sentinel value.
"""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

log = logging.getLogger("stripe_indexes")


async def ensure_stripe_indexes(db: AsyncIOMotorDatabase) -> None:
    # ── Migration: drop the OLD partial-confirmed index if it exists.
    # In Etapa B (Sprint 1) we tightened the semantics so pending holds
    # also collide with confirmed reservations. See §6 of the blueprint
    # revision after user feedback on concurrency.
    try:
        info = await db.slot_reservations.index_information()
        if "ux_slot_reservations_confirmed" in info:
            await db.slot_reservations.drop_index("ux_slot_reservations_confirmed")
            log.info("dropped old ux_slot_reservations_confirmed (migrating to full unique)")
    except Exception as e:
        log.warning("could not inspect/drop old slot index: %s", e)

    # ── orders (new, source-of-truth) ────────────────────────────────
    await db.orders.create_index("stripe_payment_intent_id",
                                 unique=True,
                                 partialFilterExpression={"stripe_payment_intent_id": {"$type": "string"}},
                                 name="ux_orders_pi")
    await db.orders.create_index("order_number", unique=True, sparse=True, name="ux_orders_number")
    await db.orders.create_index([("status", 1), ("created_at", -1)], name="ix_orders_status_created")
    await db.orders.create_index("guest_email", name="ix_orders_guest_email")
    await db.orders.create_index("customer_id", sparse=True, name="ix_orders_customer")
    await db.orders.create_index("stripe_customer_id", sparse=True, name="ix_orders_stripe_customer")

    # ── stripe_events (webhook dedup — MOST critical unique index) ──
    await db.stripe_events.create_index("event_id", unique=True, name="ux_stripe_events_event_id")
    await db.stripe_events.create_index([("type", 1), ("received_at", -1)], name="ix_stripe_events_type")
    # TTL: keep processed events for 90 days for audit + replay resilience,
    # then let Mongo garbage-collect. Sprint 2 can bump this.
    await db.stripe_events.create_index("received_at", expireAfterSeconds=90 * 24 * 3600,
                                        name="ttl_stripe_events_90d")

    # ── slot_reservations (double-booking guard) ────────────────────
    # Full unique on (screen_id, day, hour) — applies to BOTH pending and
    # confirmed reservations, so two concurrent checkouts for the same slot
    # cannot both win. Pending docs carry `expires_at` so the TTL sweeps
    # them if the buyer abandons before paying; confirmed docs set
    # `expires_at = null` so they persist.
    await db.slot_reservations.create_index(
        [("screen_id", 1), ("day", 1), ("hour", 1)],
        unique=True,
        name="ux_slot_reservations_slot")
    await db.slot_reservations.create_index("order_id", name="ix_slot_reservations_order")
    await db.slot_reservations.create_index("expires_at",
                                            expireAfterSeconds=0,
                                            name="ttl_slot_reservations")

    # ── refunds ─────────────────────────────────────────────────────
    await db.refunds.create_index("stripe_refund_id",
                                  unique=True,
                                  partialFilterExpression={"stripe_refund_id": {"$type": "string"}},
                                  name="ux_refunds_stripe")
    await db.refunds.create_index("order_id", name="ix_refunds_order")

    # ── payment_methods (references only, never PAN) ────────────────
    await db.payment_methods.create_index("stripe_payment_method_id",
                                          unique=True,
                                          partialFilterExpression={"stripe_payment_method_id": {"$type": "string"}},
                                          name="ux_pm_stripe")
    await db.payment_methods.create_index("customer_id", name="ix_pm_customer")

    # ── subscriptions (Sprint 2 will populate; index now to avoid schema churn) ──
    await db.subscriptions.create_index("stripe_subscription_id",
                                        unique=True,
                                        partialFilterExpression={"stripe_subscription_id": {"$type": "string"}},
                                        name="ux_sub_stripe")
    await db.subscriptions.create_index("customer_id", name="ix_sub_customer")

    # ── order_tokens (magic-link for guest checkout) ────────────────
    await db.order_tokens.create_index("jti", unique=True, name="ux_order_tokens_jti")
    await db.order_tokens.create_index("order_id", name="ix_order_tokens_order")
    await db.order_tokens.create_index("expires_at", expireAfterSeconds=0, name="ttl_order_tokens")

    # ── checkout_sessions (media session binding) ───────────────────
    await db.checkout_sessions.create_index("jti", unique=True, name="ux_checkout_sessions_jti")
    await db.checkout_sessions.create_index("expires_at",
                                            expireAfterSeconds=0,
                                            name="ttl_checkout_sessions")
    await db.checkout_sessions.create_index("used_for_order",
                                            sparse=True,
                                            name="ix_checkout_sessions_order")
    # media.checkout_session_jti — one media per session (Sprint 1 rule)
    await db.media.create_index("checkout_session_jti",
                                unique=True,
                                partialFilterExpression={"checkout_session_jti": {"$type": "string"}},
                                name="ux_media_session")

    # ── financial_audit (append-only ledger — LEGACY audit) ─────────
    await db.financial_audit.create_index([("ts", -1)], name="ix_audit_ts")
    await db.financial_audit.create_index("entity_id", sparse=True, name="ix_audit_entity")
    await db.financial_audit.create_index("stripe_event_id", sparse=True, name="ix_audit_event")
    await db.financial_audit.create_index("action", name="ix_audit_action")

    # ── fin_ledger (append-only FINANCIAL LEDGER — Sprint 1 C3) ─────
    # Sole source of financial truth. Only inserts allowed.
    await db.fin_ledger.create_index([("currency", 1), ("entry_number", 1)],
                                     unique=True,
                                     name="ux_fin_ledger_seq")
    await db.fin_ledger.create_index([("ts", -1)], name="ix_fin_ledger_ts")
    await db.fin_ledger.create_index("order_id",         sparse=True, name="ix_fin_ledger_order")
    await db.fin_ledger.create_index("invoice_id",       sparse=True, name="ix_fin_ledger_invoice")
    await db.fin_ledger.create_index("refund_id",        sparse=True, name="ix_fin_ledger_refund")
    await db.fin_ledger.create_index("credit_note_id",   sparse=True, name="ix_fin_ledger_credit_note")
    await db.fin_ledger.create_index("payment_intent_id", sparse=True, name="ix_fin_ledger_pi")
    await db.fin_ledger.create_index("entry_type",       name="ix_fin_ledger_type")
    await db.fin_ledger.create_index("idempotency_key",  unique=True,
                                     partialFilterExpression={"idempotency_key": {"$type": "string"}},
                                     name="ux_fin_ledger_idem")

    # ── refunds (Sprint 1 C3) ───────────────────────────────────────
    # NOTE: extends the legacy `refunds` collection. The old
    # stripe-only unique index remains for Stripe references; we add
    # new indices for the C3 refund lifecycle.
    await db.refunds.create_index("idempotency_key", unique=True,
                                  partialFilterExpression={"idempotency_key": {"$type": "string"}},
                                  name="ux_refunds_idem_c3")
    await db.refunds.create_index("status", name="ix_refunds_status")
    await db.refunds.create_index([("order_id", 1), ("created_at", -1)],
                                  name="ix_refunds_order_created")
    await db.refunds.create_index("provider_ref", sparse=True,
                                  name="ix_refunds_provider_ref")

    # ── fin_credit_notes (Sprint 1 C3) ──────────────────────────────
    # Own numbering CN-YYYY-000001. UNIQUE on refund_id ensures
    # idempotent credit-note-per-refund issuance.
    await db.fin_credit_notes.create_index("refund_id",
                                           unique=True,
                                           partialFilterExpression={"refund_id": {"$type": "string"}},
                                           name="ux_fin_credit_notes_refund")
    await db.fin_credit_notes.create_index("order_id",   sparse=True, name="ix_fin_credit_notes_order")
    await db.fin_credit_notes.create_index("invoice_id", sparse=True, name="ix_fin_credit_notes_invoice")
    await db.fin_credit_notes.create_index([("issued_at", -1)], name="ix_fin_credit_notes_issued")
    await db.fin_credit_notes.create_index("status", name="ix_fin_credit_notes_status")

    # ── counters (invoice numbering, order numbering) ───────────────
    #   _id is naturally unique; no extra index needed. Keep for reference.

    # ── fin_invoices: idempotency on order_id ───────────────────────
    # Only enforced when a value is present (older invoices predate this rule).
    await db.fin_invoices.create_index("order_id",
                                       unique=True,
                                       partialFilterExpression={"order_id": {"$type": "string"}},
                                       name="ux_fin_invoices_order")
    await db.fin_invoices.create_index("stripe_invoice_id",
                                       unique=True,
                                       partialFilterExpression={"stripe_invoice_id": {"$type": "string"}},
                                       name="ux_fin_invoices_stripe")

    log.info("✓ Stripe/finance indexes ensured (orders, stripe_events, slot_reservations, "
             "refunds, payment_methods, subscriptions, order_tokens, financial_audit)")
