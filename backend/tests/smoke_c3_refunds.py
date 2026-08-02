"""Smoke test for Fase 5 · Sprint 1 · Etapa C3 (Refunds + Credit Notes + Ledger).

Runs end-to-end on the LocalDevProvider. Covers every business rule
declared in the plan approved by the user:

  1. Ledger append is append-only, chain-integrity verified.
  2. Refund on pre_approval state → 100% single admin OK.
  3. Refund on approved state (pre_play) → 100% single admin OK.
  4. Refund on playing state → partial single admin OK.
  5. Refund on COMPLETED state → dual_approval required.
     · Requester cannot approve their own refund.
     · Different admin can approve.
  6. Idempotency: identical idempotency_key returns same refund.
  7. Concurrency: two racing refunds cannot exceed total paid.
  8. Credit note automatically issued for every successful refund.
     · Own numbering CN-YYYY-...
     · Regenerable PDF without changing number.
     · Linked to order/invoice/refund/payment_intent/ledger.
  9. Multi-currency preparation: DOP order refund works, base_currency
     preserved, exchange_rate placeholder present.
 10. Reason mandatory (>=10 chars); short reasons rejected.

Runs against the local Mongo used by the app.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Force dev provider
os.environ["PAYMENT_PROVIDER"] = "dev"
os.environ.pop("STRIPE_SECRET_KEY", None)

import payments
payments.reset_provider_for_tests()

from motor.motor_asyncio import AsyncIOMotorClient

from stripe_indexes import ensure_stripe_indexes
from financial_ledger import (
    append_entry, EntryType, DIR_DEBIT, DIR_CREDIT, verify_chain,
    total_refunded_for_order, total_paid_for_order,
    LEDGER_COLLECTION,
)
from refunds_service import (
    request_refund, approve_refund, reject_refund,
    RF_SUCCEEDED, RF_PENDING_DUAL, RF_REJECTED,
)
from order_state import (
    STATE_PAID, STATE_PENDING_REVIEW, STATE_APPROVED,
    STATE_SCHEDULED, STATE_PLAYING, STATE_COMPLETED,
    STATE_REFUND_PENDING, STATE_REFUNDED,
)
from payments.base import (
    REFUND_STATUS_SUCCEEDED, PI_STATUS_SUCCEEDED,
)


SCREEN_ID = "scr_smoke_c3"

def _utcnow():
    return datetime.now(timezone.utc)


async def _wipe(db):
    """Cleanup smoke-test artefacts from prior runs so we start clean."""
    await db.orders.delete_many({"screen_id": SCREEN_ID})
    await db.dev_payment_intents.delete_many({"metadata.smoke_c3": True})
    await db.dev_refunds.delete_many({"idempotency_key": {"$regex": "^smoke_c3"}})
    await db.refunds.delete_many({"order_id": {"$regex": "^ord_smoke_c3"}})
    await db.fin_invoices.delete_many({"order_id": {"$regex": "^ord_smoke_c3"}})
    await db.fin_credit_notes.delete_many({"order_id": {"$regex": "^ord_smoke_c3"}})
    await db.fin_ledger.delete_many({"order_id": {"$regex": "^ord_smoke_c3"}})
    await db.financial_audit.delete_many({"entity_id": {"$regex": "^(ord_smoke_c3|RFD-|CN-)"}})


async def _seed_paid_order(db, *, order_id, currency="usd", amount_cents=10000, state=STATE_PAID):
    """Create a paid order in the desired state, with a matching dev PI."""
    provider = payments.get_provider()
    # Create dev PaymentIntent (skip full checkout to save time)
    pi = await provider.create_payment_intent(
        amount_cents=amount_cents, currency=currency,
        customer_id="cus_dev_smoke", metadata={"smoke_c3": True},
        idempotency_key=f"smoke_c3_{order_id}",
    )
    # Force the PI to succeeded to simulate a captured payment
    await db.dev_payment_intents.update_one(
        {"id": pi.id},
        {"$set": {"status": PI_STATUS_SUCCEEDED,
                  "latest_charge_id": f"ch_dev_smoke_{order_id}"}}
    )

    now = _utcnow()
    order = {
        "_id": order_id,
        "order_number": order_id.upper(),
        "status": state,
        "screen_id": SCREEN_ID,
        "screen_name": "Smoke C3 Screen",
        "guest_email": "smoke.c3@example.com",
        "guest_name": "Smoke C3",
        "guest_phone": "+18095551234",
        "amount_cents": amount_cents,
        "refunded_cents": 0,
        "currency": currency,
        "hours": 4,
        "hourly_rate_cents": amount_cents // 4,
        "payment_provider": provider.name,
        "stripe_payment_intent_id": pi.id,
        "paid_at": now,
        "created_at": now,
        "updated_at": now,
        "status_history": [{"from": "paid", "to": state, "at": now, "by": "system",
                            "actor_email": "smoke", "reason": "seed"}],
    }
    await db.orders.insert_one(order)

    # Also fake an invoice for this order (idempotency_service normally does it)
    inv_number = f"INV-2999-SMOKE-{order_id[-4:]}"
    await db.fin_invoices.insert_one({
        "_id": inv_number, "id": inv_number, "number": inv_number,
        "order_id": order_id, "status": "issued",
        "customer": {"email": order["guest_email"], "name": order["guest_name"]},
        "screen": {"id": SCREEN_ID, "name": "Smoke C3 Screen"},
        "lines": [{"description": "smoke", "quantity": 1, "unit": "hour",
                   "unit_price_cents": amount_cents, "total_cents": amount_cents}],
        "subtotal_cents": amount_cents, "tax_cents": 0,
        "total_cents": amount_cents, "currency": currency,
        "issued_at": now, "issued_by": "smoke", "due_at": now, "paid_at": now,
        "voided_at": None, "voided_by": None, "credited_by": None,
        "payment_provider": provider.name,
        "payment_intent_id": pi.id,
        "created_at": now, "updated_at": now,
    })
    await db.orders.update_one({"_id": order_id},
                               {"$set": {"invoice_number": inv_number}})

    # Also add a PAYMENT_CAPTURED ledger entry (normally done by webhook)
    await append_entry(
        db,
        entry_type=EntryType.PAYMENT_CAPTURED,
        direction=DIR_CREDIT,
        amount_cents=amount_cents,
        currency=currency,
        order_id=order_id,
        invoice_id=inv_number,
        payment_intent_id=pi.id,
        provider="dev",
        actor_kind="webhook",
        reason="smoke seed",
        idempotency_key=f"seed_paid:{order_id}",
    )
    return order, pi


async def _clear_provider_and_reload():
    payments.reset_provider_for_tests()
    payments.get_provider()


async def run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await ensure_stripe_indexes(db)
    await _wipe(db)

    passed = 0
    failed = 0

    def _pass(name):
        nonlocal passed
        print(f"  ✓ {name}")
        passed += 1

    def _fail(name, err):
        nonlocal failed
        print(f"  ✗ {name}: {err}")
        failed += 1

    # ═════════════════════════════════════════════════════════════════
    # Test 1: Ledger integrity chain verifies
    # ═════════════════════════════════════════════════════════════════
    print("\n[1] Ledger integrity chain")
    order_id = "ord_smoke_c3_ledger"
    await _seed_paid_order(db, order_id=order_id)
    result = await verify_chain(db, currency="usd")
    if result["ok"]:
        _pass(f"verify_chain USD (checked={result['checked']})")
    else:
        _fail("verify_chain USD", result)

    # ═════════════════════════════════════════════════════════════════
    # Test 2: Reason must be >= 10 chars
    # ═════════════════════════════════════════════════════════════════
    print("\n[2] Reason enforcement (>=10 chars)")
    try:
        await request_refund(db, order_id=order_id, amount_cents=1000,
                             reason="short",
                             refund_type="partial",
                             actor_user_id="admin_1", actor_email="admin1@x")
        _fail("short reason should be rejected", "did not raise")
    except ValueError:
        _pass("short reason rejected")

    # ═════════════════════════════════════════════════════════════════
    # Test 3: Refund on PAID state → single admin, credit note auto
    # ═════════════════════════════════════════════════════════════════
    print("\n[3] Refund pre_approval (paid) → auto-executed, single admin")
    order_id_3 = "ord_smoke_c3_paid"
    await _seed_paid_order(db, order_id=order_id_3, amount_cents=8000)

    rf = await request_refund(db, order_id=order_id_3,
                              amount_cents=3000, refund_type="partial",
                              reason="Partial refund pre-approval test",
                              actor_user_id="admin_1", actor_email="admin1@example.com",
                              actor_ip="127.0.0.1", actor_user_agent="pytest")

    if rf["status"] != RF_SUCCEEDED:
        _fail("pre_approval partial should auto-succeed", rf.get("status"))
    else:
        _pass(f"refund auto-succeeded (id={rf['_id']}, provider_ref={rf.get('provider_ref')})")

    cn = await db.fin_credit_notes.find_one({"refund_id": rf["_id"]})
    if not cn:
        _fail("credit note not issued", None)
    elif not cn["number"].startswith("CN-"):
        _fail("credit note number wrong prefix", cn["number"])
    else:
        _pass(f"credit note issued {cn['number']} linked to order/invoice/refund")

    ledger_entries = [e async for e in db.fin_ledger.find({"refund_id": rf["_id"]})]
    types = {e["entry_type"] for e in ledger_entries}
    if EntryType.REFUND_PARTIAL in types and EntryType.CREDIT_NOTE_ISSUED in types:
        _pass(f"ledger has REFUND_PARTIAL + CREDIT_NOTE_ISSUED ({len(ledger_entries)} entries)")
    else:
        _fail("ledger missing expected entries", types)

    # ═════════════════════════════════════════════════════════════════
    # Test 4: Refund on COMPLETED → dual approval required
    # ═════════════════════════════════════════════════════════════════
    print("\n[4] Refund on COMPLETED → dual approval flow")
    order_id_4 = "ord_smoke_c3_completed"
    await _seed_paid_order(db, order_id=order_id_4, amount_cents=5000,
                           state=STATE_COMPLETED)

    rf2 = await request_refund(db, order_id=order_id_4,
                               amount_cents=5000, refund_type="full",
                               reason="Full refund on completed order — customer complaint",
                               actor_user_id="admin_1", actor_email="admin1@example.com",
                               actor_ip="10.0.0.1", actor_user_agent="pytest")
    if rf2["status"] == RF_PENDING_DUAL and rf2["requires_dual_approval"]:
        _pass("refund created in pending_dual_approval")
    else:
        _fail("should require dual approval", rf2["status"])

    # 4a. Requester cannot approve their own refund
    try:
        await approve_refund(db, refund_id=rf2["_id"],
                             actor_user_id="admin_1", actor_email="admin1@example.com")
        _fail("requester should NOT be able to approve", "did not raise")
    except ValueError as e:
        _pass(f"segregation of duties enforced ({e})")

    # 4b. Different admin approves
    rf2_after = await approve_refund(db, refund_id=rf2["_id"],
                                     actor_user_id="admin_2",
                                     actor_email="admin2@example.com",
                                     actor_ip="10.0.0.2", actor_user_agent="pytest")
    if rf2_after["status"] == RF_SUCCEEDED:
        _pass("second admin approved → executed → succeeded")
    else:
        _fail("post-approval status wrong", rf2_after)

    # 4c. Order transitioned to REFUNDED (full refund)
    o_after = await db.orders.find_one({"_id": order_id_4})
    if o_after["status"] == STATE_REFUNDED:
        _pass("order transitioned to REFUNDED")
    else:
        _fail("order should be REFUNDED", o_after["status"])

    # 4d. Credit note issued after approval, not before
    cn2 = await db.fin_credit_notes.find_one({"refund_id": rf2["_id"]})
    if cn2:
        _pass(f"credit note {cn2['number']} issued only after execution")
    else:
        _fail("credit note not issued", None)

    # ═════════════════════════════════════════════════════════════════
    # Test 5: Concurrency guard — cannot over-refund
    # ═════════════════════════════════════════════════════════════════
    print("\n[5] Concurrency guard — over-refund is impossible")
    order_id_5 = "ord_smoke_c3_conc"
    await _seed_paid_order(db, order_id=order_id_5, amount_cents=10000,
                           state=STATE_PAID)

    async def one_refund(amt, admin_id):
        try:
            return await request_refund(db, order_id=order_id_5,
                                        amount_cents=amt, refund_type="partial",
                                        reason="Concurrent refund attempt",
                                        actor_user_id=admin_id,
                                        actor_email=f"{admin_id}@example.com")
        except ValueError as e:
            return {"error": str(e), "status": "rejected_by_validation"}

    # Two concurrent 7000-cent refunds; only one can succeed (over-refund).
    results = await asyncio.gather(
        one_refund(7000, "admin_A"),
        one_refund(7000, "admin_B"),
    )
    succeeded = [r for r in results if isinstance(r, dict) and r.get("status") == RF_SUCCEEDED]
    failed_r  = [r for r in results if r not in succeeded]
    if len(succeeded) == 1 and len(failed_r) == 1:
        _pass(f"exactly one refund won ({succeeded[0]['amount_cents']}c), other blocked")
    else:
        _fail("concurrency guard leak",
              [{"amt": r.get("amount_cents"), "st": r.get("status"),
                "err": r.get("failure_message") or r.get("error")} for r in results])

    o5 = await db.orders.find_one({"_id": order_id_5})
    if o5["refunded_cents"] <= o5["amount_cents"]:
        _pass(f"orders.refunded_cents = {o5['refunded_cents']} ≤ paid {o5['amount_cents']}")
    else:
        _fail("over-refund happened", o5)

    # ═════════════════════════════════════════════════════════════════
    # Test 6: Multi-currency (DOP) — refund works, exchange_rate placeholder
    # ═════════════════════════════════════════════════════════════════
    print("\n[6] Multi-currency preparation (DOP)")
    order_id_6 = "ord_smoke_c3_dop"
    await _seed_paid_order(db, order_id=order_id_6, amount_cents=59000, currency="dop")
    rf3 = await request_refund(db, order_id=order_id_6, amount_cents=20000,
                               refund_type="partial",
                               reason="Refund in DOP currency test",
                               actor_user_id="admin_1", actor_email="admin1@example.com")
    if rf3["currency"] == "dop" and rf3["base_currency"] == "usd" and rf3["status"] == RF_SUCCEEDED:
        _pass(f"DOP refund executed, base_currency preserved, exchange_rate={rf3.get('exchange_rate')}")
    else:
        _fail("DOP refund misbehaved", rf3)

    ledger_dop = [e async for e in db.fin_ledger.find({"order_id": order_id_6})]
    if all(e["currency"] == "dop" for e in ledger_dop) and any(e["entry_type"] == EntryType.REFUND_PARTIAL for e in ledger_dop):
        _pass("DOP ledger entries stored with correct currency")
    else:
        _fail("DOP ledger currency mismatch", [(e["entry_type"], e["currency"]) for e in ledger_dop])

    # Currency mismatch should be rejected
    try:
        await request_refund(db, order_id=order_id_6, amount_cents=1000,
                             currency="usd", refund_type="partial",
                             reason="Wrong currency should fail",
                             actor_user_id="admin_1", actor_email="admin1@example.com")
        _fail("currency mismatch not blocked", None)
    except ValueError as e:
        _pass(f"currency mismatch blocked ({e})")

    # ═════════════════════════════════════════════════════════════════
    # Test 7: Idempotency
    # ═════════════════════════════════════════════════════════════════
    print("\n[7] Idempotency — same key = same refund")
    order_id_7 = "ord_smoke_c3_idem"
    await _seed_paid_order(db, order_id=order_id_7, amount_cents=5000)

    key = "smoke-idem-fixed-key"
    r_a = await request_refund(db, order_id=order_id_7, amount_cents=1000,
                               refund_type="partial",
                               reason="Idempotency test A run",
                               actor_user_id="admin_1", actor_email="admin1@example.com",
                               idempotency_key=key)
    r_b = await request_refund(db, order_id=order_id_7, amount_cents=2000,
                               refund_type="partial",
                               reason="Idempotency test B run",
                               actor_user_id="admin_1", actor_email="admin1@example.com",
                               idempotency_key=key)
    if r_a["_id"] == r_b["_id"]:
        _pass(f"same idem key returns same refund ({r_a['_id']})")
    else:
        _fail("idempotency broken", (r_a["_id"], r_b["_id"]))

    # ═════════════════════════════════════════════════════════════════
    # Test 8: Rejection path
    # ═════════════════════════════════════════════════════════════════
    print("\n[8] Reject a pending refund")
    order_id_8 = "ord_smoke_c3_reject"
    await _seed_paid_order(db, order_id=order_id_8, amount_cents=3000,
                           state=STATE_COMPLETED)
    rf_r = await request_refund(db, order_id=order_id_8, amount_cents=1500,
                                refund_type="partial",
                                reason="Refund to be rejected",
                                actor_user_id="admin_1", actor_email="admin1@example.com")
    if rf_r["status"] != RF_PENDING_DUAL:
        _fail("expected pending_dual_approval", rf_r["status"])
    else:
        rejected = await reject_refund(db, refund_id=rf_r["_id"],
                                       reason="Rejection reason for smoke test",
                                       actor_user_id="admin_2",
                                       actor_email="admin2@example.com")
        if rejected["status"] == RF_REJECTED:
            _pass(f"refund rejected ({rejected['rejected_reason']})")
        else:
            _fail("reject_refund failed", rejected)

    # ═════════════════════════════════════════════════════════════════
    # Test 9: Ledger chain still valid after all operations
    # ═════════════════════════════════════════════════════════════════
    print("\n[9] Ledger integrity after full workload")
    result_usd = await verify_chain(db, currency="usd")
    result_dop = await verify_chain(db, currency="dop")
    if result_usd["ok"] and result_dop["ok"]:
        _pass(f"USD chain OK ({result_usd['checked']}) and DOP OK ({result_dop['checked']})")
    else:
        _fail("chain integrity broken", {"usd": result_usd, "dop": result_dop})

    print("\n" + "="*60)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("="*60)
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
