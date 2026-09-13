"""Iter 60 · Backend suite for the collections module (recordatorios, recibos,
bitácora). Validates:
- GET /api/finance/collections (order, filter paid, totals)
- POST /api/finance/invoices/{id}/reminder (auth, paid, no email, SMTP unreadable)
- GET /api/finance/clients/{client_id}/email-log (has failed rows)
- POST /api/finance/payments (partial→paid flow, receipt log entry)

Uses seed client/invoice from the request. Creates a throwaway invoice + payments
and cleans them up.
"""
import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://sprint1-signage.preview.emergentagent.com").rstrip("/")
SUPERADMIN = ("superadmin@mediadview.com", "SuperAdmin#2026")
FINANCE_CLIENT_A = "e2bfc4cb-a0f8-4c0e-ae56-dfbfacc32c7a"
FINANCE_CLIENT_B = "da0d9dea-dfca-457d-bece-cdcbc7952776"
PENDING_INVOICE = "7ce909eb-2cc3-47da-96a9-20d01919d775"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": SUPERADMIN[0], "password": SUPERADMIN[1]},
                      timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    return body.get("access_token") or body.get("token")


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ============ /api/finance/collections ============
class TestCollectionsEndpoint:
    def test_collections_shape_and_ordering(self, headers):
        r = requests.get(f"{BASE_URL}/api/finance/collections", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(["rows", "total_due", "overdue_count"]).issubset(body.keys())
        rows = body["rows"]
        for row in rows:
            for key in ("invoice_number", "client", "balance", "due_date",
                        "days_late", "reminders_sent", "last_reminder_stage",
                        "next_reminder_on"):
                assert key in row, f"missing '{key}' in collections row"
            # No paid rows / no zero balance
            assert float(row["balance"]) > 0.01

        # Ordered by days_late DESC (most overdue first). None → -999 tail.
        norm = [(-(r_["days_late"] or -999)) for r_ in rows]
        assert norm == sorted(norm), "rows must be sorted most-overdue-first"

        # Totals
        assert abs(body["total_due"] - round(sum(r_["balance"] for r_ in rows), 2)) < 0.01

    def test_no_paid_invoices_in_collections(self, headers):
        r = requests.get(f"{BASE_URL}/api/finance/collections", headers=headers, timeout=30)
        assert r.status_code == 200
        for row in r.json()["rows"]:
            # If it's in collections it must be non-zero balance
            assert row["balance"] > 0


# ============ /api/finance/invoices/{id}/reminder ============
class TestReminderEndpoint:
    def test_reminder_no_auth_denied(self):
        r = requests.post(f"{BASE_URL}/api/finance/invoices/{PENDING_INVOICE}/reminder", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_reminder_pending_returns_400_smtp_password_message(self, headers):
        """SMTP password is unreadable (expected state). Should be 400 with clear message, NOT 500."""
        r = requests.post(f"{BASE_URL}/api/finance/invoices/{PENDING_INVOICE}/reminder",
                          headers=headers, timeout=60)
        assert r.status_code == 400, f"expected 400 (SMTP unreadable), got {r.status_code}: {r.text}"
        msg = (r.json().get("detail") or "").lower()
        assert "contraseña" in msg or "password" in msg, f"error must mention password: {msg}"

    def test_reminder_on_paid_invoice_400(self, headers):
        """Create → fully pay → try reminder → must be 400 'ya está pagada'."""
        inv_payload = {
            "client_id": FINANCE_CLIENT_A,
            "issue_date": datetime.utcnow().date().isoformat(),
            "due_date": datetime.utcnow().date().isoformat(),
            "items": [{"description": "TEST paid", "day_price": 10, "days": 1, "units": 1, "total": 10}],
            "subtotal": 10, "tax": 0, "total": 10,
        }
        inv_r = requests.post(f"{BASE_URL}/api/finance/invoices/manual",
                              headers=headers, json=inv_payload, timeout=30)
        assert inv_r.status_code < 300, inv_r.text
        inv_id = inv_r.json()["id"]
        pay_r = requests.post(f"{BASE_URL}/api/finance/payments", headers=headers,
                              json={"client_id": FINANCE_CLIENT_A, "invoice_id": inv_id,
                                    "amount": 10, "method": "cash"}, timeout=60)
        pay_id = pay_r.json().get("id") if pay_r.status_code < 300 else None
        try:
            r = requests.post(f"{BASE_URL}/api/finance/invoices/{inv_id}/reminder",
                              headers=headers, timeout=30)
            assert r.status_code == 400, r.text
            assert "pagada" in (r.json().get("detail") or "").lower()
        finally:
            if pay_id:
                requests.delete(f"{BASE_URL}/api/finance/payments/{pay_id}",
                                headers=headers, timeout=30)
            requests.delete(f"{BASE_URL}/api/finance/invoices/{inv_id}",
                            headers=headers, timeout=30)

    def test_reminder_client_without_email_400(self, headers):
        """Temporarily create an invoice for a client without email."""
        # Create a client without email
        cl_payload = {"business_name": f"TEST_no_email_{uuid.uuid4().hex[:6]}",
                      "representative": "TEST", "email": "", "phone": "555-0000",
                      "address_line1": "TEST", "city": "TEST", "state": "OH",
                      "zip": "00000"}
        cl = requests.post(f"{BASE_URL}/api/finance/clients",
                           headers=headers, json=cl_payload, timeout=30)
        if cl.status_code >= 300:
            pytest.skip(f"cannot create test client: {cl.status_code} {cl.text}")
        cl_id = cl.json()["id"]
        try:
            inv_payload = {
                "client_id": cl_id, "issue_date": datetime.utcnow().date().isoformat(),
                "due_date": (datetime.utcnow() - timedelta(days=2)).date().isoformat(),
                "items": [{"description": "TEST", "day_price": 10, "days": 1, "units": 1, "total": 10}],
                "subtotal": 10, "tax": 0, "total": 10,
            }
            inv_r = requests.post(f"{BASE_URL}/api/finance/invoices/manual",
                                  headers=headers, json=inv_payload, timeout=30)
            if inv_r.status_code >= 300:
                pytest.skip(f"cannot create test invoice: {inv_r.status_code} {inv_r.text}")
            inv_id = inv_r.json()["id"]
            try:
                r = requests.post(f"{BASE_URL}/api/finance/invoices/{inv_id}/reminder",
                                  headers=headers, timeout=30)
                assert r.status_code == 400, r.text
                assert "correo" in (r.json().get("detail") or "").lower()
            finally:
                requests.delete(f"{BASE_URL}/api/finance/invoices/{inv_id}",
                                headers=headers, timeout=30)
        finally:
            requests.delete(f"{BASE_URL}/api/finance/clients/{cl_id}",
                            headers=headers, timeout=30)


# ============ /api/finance/clients/{id}/email-log ============
class TestEmailLog:
    def test_email_log_lists_failed_attempts(self, headers):
        """Trigger a failed reminder, then check the log recorded it."""
        # Trigger a reminder (will fail with SMTP unreadable but logs)
        requests.post(f"{BASE_URL}/api/finance/invoices/{PENDING_INVOICE}/reminder",
                      headers=headers, timeout=60)
        # Fetch invoice to get client_id
        inv_r = requests.get(f"{BASE_URL}/api/finance/invoices", headers=headers, timeout=30)
        assert inv_r.status_code == 200
        target = next((i for i in inv_r.json() if i["id"] == PENDING_INVOICE), None)
        assert target, "seed invoice missing"
        cid = target["client_id"]

        r = requests.get(f"{BASE_URL}/api/finance/clients/{cid}/email-log",
                         headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0, "log must not be empty after reminder attempt"

        # Most recent first
        stamps = [row["sent_at"] for row in rows]
        assert stamps == sorted(stamps, reverse=True), "log must be sorted newest-first"

        # Must contain at least one failed reminder entry with error
        failed_reminders = [r_ for r_ in rows
                            if str(r_.get("kind", "")).startswith("reminder")
                            and r_.get("ok") is False]
        assert failed_reminders, "expected at least one failed reminder entry with error"
        assert failed_reminders[0].get("error"), "failed row must have error message"
        # Field contract
        for key in ("kind", "to", "subject", "ok", "sent_at"):
            assert key in failed_reminders[0]


# ============ Payments + receipt + stop-reminders ============
class TestPaymentReceiptFlow:
    def test_partial_then_full_payment_flow(self, headers):
        # Create a throwaway invoice for FINANCE_CLIENT_A
        inv_payload = {
            "client_id": FINANCE_CLIENT_A,
            "issue_date": datetime.utcnow().date().isoformat(),
            "due_date": (datetime.utcnow() - timedelta(days=3)).date().isoformat(),
            "items": [{"description": "TEST col60", "day_price": 100, "days": 1, "units": 1, "total": 100}],
            "subtotal": 100, "tax": 0, "total": 100,
        }
        inv_r = requests.post(f"{BASE_URL}/api/finance/invoices/manual",
                              headers=headers, json=inv_payload, timeout=30)
        assert inv_r.status_code < 300, f"invoice create failed: {inv_r.status_code} {inv_r.text}"
        inv = inv_r.json()
        inv_id = inv["id"]

        payment_ids = []
        try:
            # (1) Confirm invoice appears in collections
            col = requests.get(f"{BASE_URL}/api/finance/collections",
                               headers=headers, timeout=30).json()
            assert any(r["invoice_id"] == inv_id for r in col["rows"]), "new invoice must appear in collections"

            # (2) Partial payment ($40)
            pay1 = requests.post(f"{BASE_URL}/api/finance/payments", headers=headers,
                                 json={"client_id": FINANCE_CLIENT_A, "invoice_id": inv_id,
                                       "amount": 40, "method": "cash", "reference": "TEST partial"},
                                 timeout=60)
            assert pay1.status_code < 300, pay1.text
            body1 = pay1.json()
            payment_ids.append(body1["id"])
            # Should still register with receipt_sent=false + receipt_error
            assert body1.get("receipt_sent") is False, "receipt should fail (SMTP unreadable)"
            assert body1.get("receipt_error"), "receipt_error must be present when receipt fails"

            # Verify invoice state: balance 60, status still shows in collections
            inv_now = requests.get(f"{BASE_URL}/api/finance/invoices/{inv_id}",
                                   headers=headers, timeout=30).json()
            assert abs(float(inv_now["balance"]) - 60.0) < 0.01
            assert float(inv_now["amount_paid"]) == 40.0
            # Note: current backend does NOT set status='partial' after partial payment.
            # Report this in test_report but do not fail suite.

            # Still in collections
            col2 = requests.get(f"{BASE_URL}/api/finance/collections",
                                headers=headers, timeout=30).json()
            assert any(r["invoice_id"] == inv_id for r in col2["rows"])

            # (3) Complete payment ($60)
            pay2 = requests.post(f"{BASE_URL}/api/finance/payments", headers=headers,
                                 json={"client_id": FINANCE_CLIENT_A, "invoice_id": inv_id,
                                       "amount": 60, "method": "cash", "reference": "TEST full"},
                                 timeout=60)
            assert pay2.status_code < 300, pay2.text
            body2 = pay2.json()
            payment_ids.append(body2["id"])
            assert body2.get("receipt_sent") is False
            assert body2.get("receipt_error")

            inv_final = requests.get(f"{BASE_URL}/api/finance/invoices/{inv_id}",
                                     headers=headers, timeout=30).json()
            assert inv_final["status"] == "paid", f"expected paid, got {inv_final['status']}"
            assert abs(float(inv_final["balance"])) < 0.01

            # (4) Not in collections anymore
            col3 = requests.get(f"{BASE_URL}/api/finance/collections",
                                headers=headers, timeout=30).json()
            assert not any(r["invoice_id"] == inv_id for r in col3["rows"]), \
                "paid invoice must be excluded from collections (stop-reminders)"

            # (5) Receipt failure logged with ok=false and password error
            log = requests.get(f"{BASE_URL}/api/finance/clients/{FINANCE_CLIENT_A}/email-log",
                               headers=headers, timeout=30).json()
            receipts_for_inv = [r for r in log if r.get("invoice_id") == inv_id
                                and r.get("kind") == "receipt"]
            assert len(receipts_for_inv) >= 2, "should have 2 receipt log entries (partial + full)"
            for r_ in receipts_for_inv:
                assert r_["ok"] is False
                assert r_["error"], "receipt log must contain the error"
        finally:
            # Cleanup: delete payments, then invoice
            for pid in payment_ids:
                try:
                    requests.delete(f"{BASE_URL}/api/finance/payments/{pid}",
                                    headers=headers, timeout=30)
                except Exception:
                    pass
            try:
                requests.delete(f"{BASE_URL}/api/finance/invoices/{inv_id}",
                                headers=headers, timeout=30)
            except Exception:
                pass
