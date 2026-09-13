"""Iter 61 · Regression suite for the two fixes reported by the owner:

    BUG 1 — Partial payment must mark invoice status='partial' (not 'pending'),
             balance>0 still visible in /collections, then final payment makes
             it 'paid' and removes it from /collections.
    BUG 2 — Manual invoices whose items DO NOT ship line_no must still render
             HTML and PDF (no 500 KeyError). Missing description/day_price/days
             must not print 'undefined' / 'None'.

Plus regressions on:
    - Contract-generated invoice (PENDING_INVOICE) still renders /render and /pdf
    - /api/finance/collections still has total_due, overdue_count, sorted rows
    - /reminder returns 400 with a clear SMTP-password message
    - /clients/{id}/email-log still records failed attempts
"""
import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
SUPER = ("superadmin@mediadview.com", "SuperAdmin#2026")
CLIENT_A = "e2bfc4cb-a0f8-4c0e-ae56-dfbfacc32c7a"
PENDING_INVOICE = "7ce909eb-2cc3-47da-96a9-20d01919d775"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": SUPER[0], "password": SUPER[1]}, timeout=30)
    assert r.status_code == 200, f"login: {r.status_code} {r.text}"
    body = r.json()
    tok = body.get("access_token") or body.get("token")
    assert tok, "no token in login response"
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _create_manual_invoice(headers, items, total=100, days_overdue=3):
    payload = {
        "client_id": CLIENT_A,
        "issue_date": datetime.utcnow().date().isoformat(),
        "due_date": (datetime.utcnow() - timedelta(days=days_overdue)).date().isoformat(),
        "items": items,
        "subtotal": total, "tax": 0, "total": total,
    }
    r = requests.post(f"{BASE_URL}/api/finance/invoices/manual",
                      headers=headers, json=payload, timeout=30)
    assert r.status_code < 300, f"invoice create failed: {r.status_code} {r.text}"
    return r.json()


def _delete_invoice(headers, inv_id):
    try:
        requests.delete(f"{BASE_URL}/api/finance/invoices/{inv_id}",
                        headers=headers, timeout=30)
    except Exception:
        pass


def _delete_payment(headers, pay_id):
    try:
        requests.delete(f"{BASE_URL}/api/finance/payments/{pay_id}",
                        headers=headers, timeout=30)
    except Exception:
        pass


# ─────────────────────────── BUG 1: partial payment ───────────────────────────
class TestBug1PartialPayment:
    def test_partial_then_full_flow(self, headers):
        inv = _create_manual_invoice(headers, [
            {"description": "TEST partial", "day_price": 100, "days": 1, "units": 1, "total": 100}
        ], total=100)
        inv_id = inv["id"]
        payment_ids = []
        try:
            # (a) initially in /collections
            col = requests.get(f"{BASE_URL}/api/finance/collections",
                               headers=headers, timeout=30).json()
            assert any(r["invoice_id"] == inv_id for r in col["rows"]), \
                "new invoice must appear in /collections"

            # (b) $40 partial
            p1 = requests.post(f"{BASE_URL}/api/finance/payments", headers=headers,
                               json={"client_id": CLIENT_A, "invoice_id": inv_id,
                                     "amount": 40, "method": "cash",
                                     "reference": "TEST partial 40"}, timeout=60)
            assert p1.status_code < 300, p1.text
            payment_ids.append(p1.json()["id"])

            inv_after = requests.get(f"{BASE_URL}/api/finance/invoices/{inv_id}",
                                     headers=headers, timeout=30).json()
            assert inv_after["status"] == "partial", \
                f"expected status='partial' after $40, got {inv_after['status']}"
            assert abs(float(inv_after["balance"]) - 60.0) < 0.01, \
                f"expected balance=60, got {inv_after['balance']}"
            assert abs(float(inv_after["amount_paid"]) - 40.0) < 0.01

            # Still in /collections (owner keeps reminding for the $60 balance)
            col2 = requests.get(f"{BASE_URL}/api/finance/collections",
                                headers=headers, timeout=30).json()
            row = next((r for r in col2["rows"] if r["invoice_id"] == inv_id), None)
            assert row is not None, "partial invoice must remain in /collections"
            assert abs(float(row["balance"]) - 60.0) < 0.01

            # (c) $60 to close
            p2 = requests.post(f"{BASE_URL}/api/finance/payments", headers=headers,
                               json={"client_id": CLIENT_A, "invoice_id": inv_id,
                                     "amount": 60, "method": "cash",
                                     "reference": "TEST full 60"}, timeout=60)
            assert p2.status_code < 300, p2.text
            payment_ids.append(p2.json()["id"])

            inv_paid = requests.get(f"{BASE_URL}/api/finance/invoices/{inv_id}",
                                    headers=headers, timeout=30).json()
            assert inv_paid["status"] == "paid", \
                f"expected status='paid', got {inv_paid['status']}"
            assert abs(float(inv_paid["balance"])) < 0.01

            # (d) NO LONGER in /collections
            col3 = requests.get(f"{BASE_URL}/api/finance/collections",
                                headers=headers, timeout=30).json()
            assert not any(r["invoice_id"] == inv_id for r in col3["rows"]), \
                "paid invoice must be excluded from /collections"
        finally:
            for pid in payment_ids:
                _delete_payment(headers, pid)
            _delete_invoice(headers, inv_id)


# ────────────────── BUG 2: manual invoice items without line_no ──────────────
class TestBug2ManualInvoiceRender:
    def test_render_and_pdf_without_line_no(self, headers):
        # 4 items, none with line_no
        items = [
            {"description": "Servicio A", "day_price": 100, "days": 1, "units": 1, "total": 100},
            {"description": "Servicio B", "day_price": 50,  "days": 2, "units": 1, "total": 100},
            {"description": "Servicio C", "day_price": 25,  "days": 4, "units": 1, "total": 100},
            {"description": "Servicio D", "day_price": 10,  "days": 10, "units": 1, "total": 100},
        ]
        inv = _create_manual_invoice(headers, items, total=400)
        inv_id = inv["id"]
        try:
            # /render
            r = requests.get(f"{BASE_URL}/api/finance/invoices/{inv_id}/render",
                             headers=headers, timeout=30)
            assert r.status_code == 200, f"/render should be 200, got {r.status_code}: {r.text[:200]}"
            html = r.text
            assert "Servicio A" in html and "Servicio D" in html, "descriptions must be visible"
            # numbered 01..04 auto-generated
            for expected in (">01<", ">02<", ">03<", ">04<"):
                assert expected in html, f"expected line-number cell {expected} in rendered HTML"
            # No leaked None/undefined
            assert "None" not in html.replace("None-", ""), "HTML must not contain 'None'"
            assert "undefined" not in html, "HTML must not contain 'undefined'"

            # /pdf
            p = requests.get(f"{BASE_URL}/api/finance/invoices/{inv_id}/pdf",
                             headers=headers, timeout=60)
            assert p.status_code == 200, f"/pdf should be 200, got {p.status_code}: {p.text[:200]}"
            assert len(p.content) > 5 * 1024, f"pdf should be >5KB, got {len(p.content)} bytes"
            # PDFs start with %PDF
            assert p.content[:4] == b"%PDF", "response must be a real PDF"
        finally:
            _delete_invoice(headers, inv_id)

    def test_render_with_minimal_item_fields(self, headers):
        # Item with ONLY description + total (no day_price, no days, no units, no line_no)
        items = [{"description": "Servicio único", "total": 100}]
        inv = _create_manual_invoice(headers, items, total=100)
        inv_id = inv["id"]
        try:
            r = requests.get(f"{BASE_URL}/api/finance/invoices/{inv_id}/render",
                             headers=headers, timeout=30)
            assert r.status_code == 200, f"/render should be 200, got {r.status_code}: {r.text[:200]}"
            html = r.text
            assert "Servicio único" in html, "description must render"
            assert ">01<" in html, "line numbering must default to 01"
            assert "undefined" not in html, "must not print 'undefined'"
            # Rough check: no leftover 'None' from missing fields (the HTML uses 'or 0' / 'or ''')
            # Allow substrings that contain 'None' legitimately? None expected here.
            assert " None" not in html and ">None<" not in html, "must not print 'None'"

            p = requests.get(f"{BASE_URL}/api/finance/invoices/{inv_id}/pdf",
                             headers=headers, timeout=60)
            assert p.status_code == 200
            assert len(p.content) > 5 * 1024
            assert p.content[:4] == b"%PDF"
        finally:
            _delete_invoice(headers, inv_id)


# ────────────────────────── Regressions ──────────────────────────
class TestRegressionContractInvoice:
    def test_contract_invoice_render(self, headers):
        r = requests.get(f"{BASE_URL}/api/finance/invoices/{PENDING_INVOICE}/render",
                         headers=headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        # numbering original: line_no should be preserved (probably '01' etc.)
        html = r.text
        # La factura online ahora es la misma hoja que el PDF (ver
        # finance.INVOICE_DOC_CSS): tabla de líneas con clase `items`.
        assert '<table class="items">' in html and "</table>" in html
        assert ">01<" in html, "contract invoice line numbering must remain"
        # Y tiene que traer las piezas propias del PDF, no el diseño viejo.
        for piece in ("INVOICE TO:", "PERIOD DATE", "INVOICE DUE", "INVOICE #",
                      "DAY PRICE($)", "Thank You For Your Business"):
            assert piece in html, f"la factura online debe verse como el PDF: falta {piece}"

    def test_contract_invoice_pdf(self, headers):
        p = requests.get(f"{BASE_URL}/api/finance/invoices/{PENDING_INVOICE}/pdf",
                         headers=headers, timeout=60)
        assert p.status_code == 200
        assert len(p.content) > 5 * 1024
        assert p.content[:4] == b"%PDF"


class TestRegressionCollections:
    def test_collections_shape(self, headers):
        r = requests.get(f"{BASE_URL}/api/finance/collections",
                         headers=headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "rows" in body and "total_due" in body and "overdue_count" in body
        # Sorted by days_late DESC (None last)
        norm = [(-(row.get("days_late") or -999)) for row in body["rows"]]
        assert norm == sorted(norm), "rows must be sorted most-overdue-first"

    def test_reminder_smtp_password_message(self, headers):
        r = requests.post(f"{BASE_URL}/api/finance/invoices/{PENDING_INVOICE}/reminder",
                          headers=headers, timeout=60)
        assert r.status_code == 400, r.text
        msg = (r.json().get("detail") or "").lower()
        assert "contraseña" in msg or "password" in msg

    def test_email_log_records_failed(self, headers):
        # trigger one failed reminder
        requests.post(f"{BASE_URL}/api/finance/invoices/{PENDING_INVOICE}/reminder",
                      headers=headers, timeout=60)
        # get client id
        inv_r = requests.get(f"{BASE_URL}/api/finance/invoices/{PENDING_INVOICE}",
                             headers=headers, timeout=30)
        assert inv_r.status_code == 200
        cid = inv_r.json()["client_id"]
        r = requests.get(f"{BASE_URL}/api/finance/clients/{cid}/email-log",
                         headers=headers, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and rows, "email log must not be empty"
        failed = [row for row in rows if row.get("ok") is False and row.get("error")]
        assert failed, "must contain at least one failed entry with error"
