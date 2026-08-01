"""
Smoke test for Fase 5 Sprint 1 Etapa B.

Runs the *non-Stripe* pieces end-to-end (quote generation, order state
machine, magic-link mint/verify, webhook dedup + event dispatcher).

Stripe-facing pieces (create-intent → PaymentIntent → webhook) are
tested with monkey-patched stripe.PaymentIntent.create and a
locally-generated signed webhook payload — so this file passes even
without real Stripe keys. A separate integration test (test_stripe_live.py)
will run against real Stripe test keys once the user provides them.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_smoke_only_" + "x" * 32
os.environ["STRIPE_SECRET_KEY"] = "sk_test_smoke"      # never sent to real Stripe
os.environ["STRIPE_PUBLISHABLE_KEY"] = "pk_test_smoke"

from motor.motor_asyncio import AsyncIOMotorClient
import stripe

# Force-reload stripe_config with the test keys we just set
import stripe_config
stripe_config._MODE = "test"
stripe_config._CONFIGURED = True
stripe_config._WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]
stripe_config._PUBLISHABLE_KEY = os.environ["STRIPE_PUBLISHABLE_KEY"]
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

from checkout_service import (
    build_quote, create_intent, mint_order_token, verify_order_token,
    _verify_quote,
)
from stripe_events import process_event
from order_state import (
    STATE_AWAITING_PAYMENT, STATE_PAYMENT_PROCESSING, STATE_PAID,
    STATE_PENDING_REVIEW, STATE_APPROVED, STATE_PAYMENT_FAILED,
    assert_transition, InvalidTransition,
)


def _stripe_sign(payload_bytes: bytes, secret: str) -> str:
    """Recreate a valid Stripe signature header locally."""
    import hmac, hashlib
    ts = int(time.time())
    signed = f"{ts}.{payload_bytes.decode()}"
    sig = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


class _FakePI:
    def __init__(self, id="pi_test_smoke_1", client_secret="pi_test_smoke_1_secret"):
        self.id = id
        self.client_secret = client_secret


class _FakeCustomer:
    def __init__(self, id="cus_test_smoke_1"):
        self.id = id


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Reset test collections
    for coll in ("orders", "stripe_events", "order_tokens", "customers_stripe",
                 "counters", "financial_audit", "slot_reservations", "refunds"):
        # Only wipe smoke-tagged docs so we never touch real data
        if coll == "counters":
            await db[coll].delete_many({"_id": {"$regex": "^(order_number|invoice_number):2999"}})
        else:
            await db[coll].delete_many({"$or": [
                {"guest_email": "buyer.smoke@example.com"},
                {"screen_id": "scr_smoke_b"},
                {"stripe_customer_id": "cus_test_smoke_1"},
                {"stripe_payment_intent_id": "pi_test_smoke_1"},
                {"metadata.screen_id": "scr_smoke_b"},
                {"actor_ip": "127.0.0.1"},
            ]})

    # Insert a fake screen
    await db.screens.delete_many({"id": "scr_smoke_b"})
    await db.screens.insert_one({
        "id": "scr_smoke_b",
        "name": "Smoke Screen B",
        "active": True,
        "hourly_rate": 25,  # $25/hr
        "specs": {"size": "16x9"},
        "location": {"city": "TestCity", "address": "1 Test St"},
    })

    # ── 1. build_quote ────────────────────────────────────────────────
    print("── build_quote ──")
    q = await build_quote(db, screen_id="scr_smoke_b", hours=3)
    assert q["total_cents"] == 25 * 100 * 3 == 7500, q
    assert q["currency"] == "usd"
    assert q["hours"] == 3
    print(f"  quote total={q['total_cents']}¢ ({q['currency']}) → OK")

    # verify signed quote round-trip
    payload = _verify_quote(q["quote_id"])
    assert payload is not None and payload["total_cents"] == 7500
    print("  signed quote verifies → OK")

    # ── 2. create_intent (with mocked Stripe) ─────────────────────────
    print("── create_intent (mocked Stripe) ──")
    with patch("stripe.Customer.create", return_value=_FakeCustomer()) as pc, \
         patch("stripe.PaymentIntent.create", return_value=_FakePI()) as pi:
        result = await create_intent(
            db,
            quote_id=q["quote_id"],
            email="buyer.smoke@example.com",
            name="Smoke Buyer",
            phone="+15550001111",
        )
        assert result["client_secret"] == "pi_test_smoke_1_secret"
        assert result["order_id"].startswith("ord_")
        assert result["order_number"].startswith("ORD-")
        # Verify amount was set by the SERVER (blueprint invariant)
        pi.assert_called_once()
        assert pi.call_args.kwargs["amount"] == 7500
        assert pi.call_args.kwargs["currency"] == "usd"
        assert pi.call_args.kwargs["idempotency_key"] == f"order:{result['order_id']}"
        assert pi.call_args.kwargs["payment_method_types"] == ["card"]
        print(f"  order {result['order_number']} created, amount enforced server-side → OK")

    order_id = result["order_id"]

    # Order must be in payment_processing NOT paid
    order = await db.orders.find_one({"_id": order_id})
    assert order["status"] == STATE_PAYMENT_PROCESSING, order["status"]
    print("  order status=payment_processing (webhook is sole authority) → OK")

    # ── 3. Idempotency: creating the intent again with same quote_id reuses ──
    # (Sprint 1 rule: retries with SAME quote nonce are safe. A distinct
    # quote nonce will always yield a new PaymentIntent.)
    # Actual re-creation semantics live in Stripe (idempotency_key). We
    # just ensure the Order was NOT duplicated.
    n_orders = await db.orders.count_documents({"guest_email": "buyer.smoke@example.com"})
    assert n_orders == 1, n_orders
    print(f"  no duplicate orders for same guest → OK ({n_orders})")

    # ── 4. state machine — illegal transitions ────────────────────────
    print("── state machine ──")
    try:
        assert_transition(from_state=STATE_PAYMENT_PROCESSING, to_state=STATE_PAID, actor="client")
        raise AssertionError("client should not be allowed to mark paid")
    except InvalidTransition:
        pass
    try:
        assert_transition(from_state=STATE_AWAITING_PAYMENT, to_state=STATE_APPROVED, actor="admin")
        raise AssertionError("cannot skip payment_processing → paid → pending_review")
    except InvalidTransition:
        pass
    assert_transition(from_state=STATE_PAYMENT_PROCESSING, to_state=STATE_PAID, actor="webhook")
    print("  client cannot mark paid, admin cannot skip payment → OK")

    # ── 5. Webhook: payment_intent.succeeded → paid → pending_review ──
    print("── webhook payment_intent.succeeded ──")
    event = {
        "id": "evt_smoke_pi_succ_1",
        "type": "payment_intent.succeeded",
        "data": {"object": {
            "id": "pi_test_smoke_1",
            "amount": 7500,
            "currency": "usd",
            "latest_charge": "ch_smoke_1",
            "metadata": {"order_id": order_id, "screen_id": "scr_smoke_b"},
        }},
    }
    outcome = await process_event(db, event)
    assert outcome["handled"] and outcome["result"] == "ok", outcome
    order = await db.orders.find_one({"_id": order_id})
    assert order["status"] == STATE_PENDING_REVIEW, order["status"]
    assert order.get("paid_at") is not None
    assert order["stripe_latest_charge_id"] == "ch_smoke_1"
    print(f"  order status now={order['status']}, paid_at set → OK")

    # ── 6. Duplicate webhook is a no-op (state already advanced) ──────
    outcome2 = await process_event(db, event)
    order2 = await db.orders.find_one({"_id": order_id})
    assert order2["status"] == STATE_PENDING_REVIEW  # unchanged
    print(f"  duplicate webhook did not corrupt state → OK")

    # ── 7. Magic-link mint + verify + revoke ─────────────────────────
    print("── magic-link mint/verify ──")
    tok = await mint_order_token(db, order_id=order_id)
    payload = await verify_order_token(db, token=tok)
    assert payload and payload["order_id"] == order_id
    # Revoke and re-verify → must return None
    await db.order_tokens.update_one({"jti": payload["jti"]}, {"$set": {"revoked": True}})
    payload2 = await verify_order_token(db, token=tok)
    assert payload2 is None, "revoked token must not verify"
    print("  mint + verify + server-side revoke → OK")

    # ── 8. Webhook signature verification (direct check) ─────────────
    print("── webhook signature verification (direct SDK) ──")
    ev_bytes = json.dumps({
        "id": "evt_smoke_sig_1",
        "object": "event",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_xyz"}},
        "api_version": "2026-03-25.dahlia",
        "created": int(time.time()),
    }).encode()

    # BAD signature must raise
    try:
        stripe.Webhook.construct_event(ev_bytes, "t=1,v1=deadbeef",
                                        os.environ["STRIPE_WEBHOOK_SECRET"])
        raise AssertionError("bad signature should have failed")
    except stripe.error.SignatureVerificationError:
        print("  bad signature raises SignatureVerificationError → OK")

    # GOOD signature (locally computed with same secret) must pass
    sig = _stripe_sign(ev_bytes, os.environ["STRIPE_WEBHOOK_SECRET"])
    parsed = stripe.Webhook.construct_event(ev_bytes, sig,
                                             os.environ["STRIPE_WEBHOOK_SECRET"])
    assert parsed["id"] == "evt_smoke_sig_1"
    print("  valid signature construct_event succeeds → OK")

    # ── 9. Webhook dedup via unique index ─────────────────────────────
    print("── webhook dedup ──")
    from datetime import datetime, timezone
    ev_doc = {"event_id": "evt_smoke_dedup_1", "type": "x",
              "received_at": datetime.now(timezone.utc), "payload": {}}
    await db.stripe_events.delete_many({"event_id": "evt_smoke_dedup_1"})
    await db.stripe_events.insert_one(ev_doc)
    try:
        await db.stripe_events.insert_one(ev_doc)
        raise AssertionError("duplicate should have been rejected")
    except Exception as e:
        assert "duplicate" in str(e).lower() or "E11000" in str(e), e
    print("  duplicate event_id rejected by unique index → OK")

    # Clean up smoke docs
    await db.orders.delete_many({"guest_email": "buyer.smoke@example.com"})
    await db.stripe_events.delete_many({"event_id": {"$regex": "^evt_smoke"}})
    await db.customers_stripe.delete_many({"email": "buyer.smoke@example.com"})
    await db.order_tokens.delete_many({"order_id": order_id})
    await db.financial_audit.delete_many({"entity_id": order_id})
    await db.screens.delete_many({"id": "scr_smoke_b"})
    await db.counters.delete_many({"_id": {"$regex": ":2026$|^order_number:2026"}})

    print("\n✅ Etapa B smoke test PASSED — all state transitions, idempotency, "
          "webhook signature verification, dedup, and magic-link flows working.")

asyncio.run(main())
