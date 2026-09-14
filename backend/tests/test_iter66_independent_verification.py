"""Verificación independiente iter66 — seguimiento de aperturas de correo.

Este archivo es un smoke test paralelo que insertó T1 (agente de QA) para
confirmar de forma independiente lo que test_iter66_email_open_tracking.py ya
prueba: píxel PNG real sin auth, incremento de open_count sin sobreescribir
opened_at, id inexistente devuelve píxel, render?t=<id> marca viewed_at,
render sin ?t no marca, y el resumen del panel incluye total_seen.
"""
import os
import uuid
from datetime import datetime

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")
FIN = f"{BASE_URL}/api/finance"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@mediadview.com",
        "password": "SuperAdmin#2026",
    }, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


@pytest.fixture
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def seeded_log(db):
    log_id = str(uuid.uuid4())
    db.fin_email_log.insert_one({
        "id": log_id, "client_id": None, "invoice_id": None, "kind": "invoice",
        "to": "qa@example.com", "subject": f"TEST_qa {log_id[:8]}",
        "ok": True, "error": "", "sent_at": datetime.utcnow().isoformat(),
        "opened_at": None, "open_count": 0, "viewed_at": None,
    })
    yield log_id
    db.fin_email_log.delete_many({"id": log_id})


# -------- pixel behavior --------
def test_pixel_returns_valid_png_no_cache(seeded_log):
    r = requests.get(f"{FIN}/email-log/{seeded_log}/open.png", timeout=30)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    # magic bytes
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert "no-store" in r.headers.get("cache-control", "").lower()


def test_pixel_no_auth_required(seeded_log):
    # explícitamente sin Authorization
    sess = requests.Session()
    r = sess.get(f"{FIN}/email-log/{seeded_log}/open.png", timeout=30)
    assert r.status_code == 200


def test_pixel_records_first_open_and_counts(seeded_log, db):
    requests.get(f"{FIN}/email-log/{seeded_log}/open.png", timeout=30)
    row = db.fin_email_log.find_one({"id": seeded_log})
    first_open = row["opened_at"]
    assert first_open
    assert row["open_count"] == 1

    # 2 aperturas más — cuenta sube, opened_at no cambia
    requests.get(f"{FIN}/email-log/{seeded_log}/open.png", timeout=30)
    requests.get(f"{FIN}/email-log/{seeded_log}/open.png", timeout=30)
    row = db.fin_email_log.find_one({"id": seeded_log})
    assert row["open_count"] == 3
    assert row["opened_at"] == first_open


def test_pixel_unknown_id_still_returns_png():
    r = requests.get(f"{FIN}/email-log/{uuid.uuid4()}/open.png", timeout=30)
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


# -------- render tracking --------
def test_render_with_t_marks_viewed_at(admin_headers, db, seeded_log):
    tag = uuid.uuid4().hex[:6]
    cl = requests.post(f"{FIN}/clients", headers=admin_headers, json={
        "business_name": f"TEST_qa_render {tag}", "representative": "T",
        "email": f"qa.{tag}@example.com", "phone": "1",
        "address_line1": "1", "city": "Columbus", "state": "OH", "zip": "43205",
    }, timeout=30).json()
    inv_resp = requests.post(f"{FIN}/invoices/manual", headers=admin_headers, json={
        "client_id": cl["id"], "issue_date": "2026-08-01", "due_date": "2026-08-01",
        "items": [{"description": "LED", "day_price": 8.5, "days": 30, "total": 255}],
    }, timeout=30).json()
    inv = inv_resp.get("invoice", inv_resp)

    try:
        r = requests.get(f"{FIN}/invoices/{inv['id']}/render?t={seeded_log}", timeout=30)
        assert r.status_code == 200
        assert "INVOICE TO:" in r.text
        row = db.fin_email_log.find_one({"id": seeded_log})
        assert row["viewed_at"], "click must be recorded"
    finally:
        requests.delete(f"{FIN}/invoices/{inv['id']}/purge", headers=admin_headers, timeout=30)
        requests.delete(f"{FIN}/clients/{cl['id']}/purge", headers=admin_headers,
                        params={"confirm_name": cl["business_name"], "force": "true"},
                        timeout=30)


def test_render_without_t_does_not_mark(admin_headers, db, seeded_log):
    tag = uuid.uuid4().hex[:6]
    cl = requests.post(f"{FIN}/clients", headers=admin_headers, json={
        "business_name": f"TEST_qa_norender {tag}", "representative": "T",
        "email": f"qanr.{tag}@example.com", "phone": "1",
        "address_line1": "1", "city": "Columbus", "state": "OH", "zip": "43205",
    }, timeout=30).json()
    inv_resp = requests.post(f"{FIN}/invoices/manual", headers=admin_headers, json={
        "client_id": cl["id"], "issue_date": "2026-08-01", "due_date": "2026-08-01",
        "items": [{"description": "LED", "day_price": 8.5, "days": 30, "total": 255}],
    }, timeout=30).json()
    inv = inv_resp.get("invoice", inv_resp)

    try:
        # forzar seeded_log a estado limpio antes de la llamada
        db.fin_email_log.update_one({"id": seeded_log}, {"$set": {"viewed_at": None}})
        r = requests.get(f"{FIN}/invoices/{inv['id']}/render", timeout=30)
        assert r.status_code == 200
        row = db.fin_email_log.find_one({"id": seeded_log})
        assert row["viewed_at"] is None
    finally:
        requests.delete(f"{FIN}/invoices/{inv['id']}/purge", headers=admin_headers, timeout=30)
        requests.delete(f"{FIN}/clients/{cl['id']}/purge", headers=admin_headers,
                        params={"confirm_name": cl["business_name"], "force": "true"},
                        timeout=30)


# -------- email-log endpoint --------
def test_email_log_list_returns_open_and_view_fields(admin_headers, db, seeded_log):
    # generar apertura para que aparezca en el resumen
    requests.get(f"{FIN}/email-log/{seeded_log}/open.png", timeout=30)
    data = requests.get(f"{FIN}/email-log?limit=300", headers=admin_headers,
                       timeout=30).json()
    assert "total_seen" in data
    assert data["total_seen"] >= 1
    rows = [x for x in data["rows"] if x["id"] == seeded_log]
    assert rows, "seeded log must appear"
    row = rows[0]
    assert row.get("opened_at")
    assert row.get("open_count", 0) >= 1
    # viewed_at debe estar como llave (aunque sea None)
    assert "viewed_at" in row


# -------- template rendering --------
def test_template_with_track_id_includes_pixel_and_link():
    import sys
    sys.path.insert(0, "/app/backend")
    from finance_email import render_invoice_email_html

    inv = {"id": "invqa", "invoice_number": "OHQA", "period_start": "2026-08-01",
           "period_end": "2026-08-31", "issue_date": "2026-07-25",
           "due_date": "2026-08-01", "total": 100.0, "balance": 100.0}
    cl = {"business_name": "QA", "representative": "T", "email": "a@b.com"}
    html = render_invoice_email_html(inv, cl, base_url="https://x.example.com",
                                     track_id="TRK-QA-1")
    assert "/api/finance/email-log/TRK-QA-1/open.png" in html
    assert "/api/finance/invoices/invqa/render?t=TRK-QA-1" in html


def test_template_without_track_id_has_no_tracking():
    import sys
    sys.path.insert(0, "/app/backend")
    from finance_email import render_invoice_email_html

    html = render_invoice_email_html(
        {"id": "invqa", "invoice_number": "OHQA"}, {"business_name": "Q"},
        base_url="https://x.example.com")
    assert "open.png" not in html
    assert "?t=" not in html


def test_scheduler_wires_track_id_in_all_branches():
    """Confirma que el envío guarda con log_id y arma el correo con track_id=log_id."""
    import inspect
    import sys
    sys.path.insert(0, "/app/backend")
    import finance_scheduler

    src_invoice = inspect.getsource(finance_scheduler._send_invoice_email)
    assert "track_id=log_id" in src_invoice
    assert src_invoice.count("log_id=log_id") >= 3, (
        "todas las ramas del envío de factura deben persistir el mismo log_id")

    src_plain = inspect.getsource(finance_scheduler._send_plain_email)
    assert "tracking_pixel(" in src_plain
    assert src_plain.count("log_id=log_id") >= 3, (
        "recordatorios y recibos: todas las ramas deben persistir log_id")


def test_manual_send_endpoint_wires_track_id():
    """POST /api/finance/invoices/{id}/send también debe rastrear."""
    import inspect
    import sys
    sys.path.insert(0, "/app/backend")
    import finance_email

    src = inspect.getsource(finance_email)
    # El endpoint manual está dentro de setup_finance_email_routes
    assert "track_id=log_id" in src
    # Buscar log_email con log_id=log_id
    assert "log_id=log_id" in src
