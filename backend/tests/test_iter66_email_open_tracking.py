"""¿Cuándo vio el cliente el correo?

Pedido del dueño: «¿cómo podemos saber cuándo el cliente ve el correo?».
Se rastrea con dos señales, de la más fuerte a la más débil:
  · **click** en «View Invoice Online» → `viewed_at` (no se puede bloquear);
  · **apertura** del correo vía píxel 1x1 → `opened_at` + `open_count` (puede no
    registrarse si el cliente tiene las imágenes bloqueadas).
El id del historial se genera ANTES de armar el correo porque viaja dentro de
él; por eso `log_email(..., log_id=...)`.
"""
import os
import uuid
from datetime import datetime

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")
FIN = f"{BASE_URL}/api/finance"

load_dotenv("/app/backend/.env")


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


@pytest.fixture
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def movimiento(db):
    """Una fila del historial, como la que deja un envío real."""
    log_id = str(uuid.uuid4())
    db.fin_email_log.insert_one({
        "id": log_id, "client_id": None, "invoice_id": None, "kind": "invoice",
        "to": "cliente@example.com", "subject": f"TEST_seen {log_id[:8]}",
        "ok": True, "error": "", "sent_at": datetime.utcnow().isoformat(),
        "opened_at": None, "open_count": 0, "viewed_at": None,
    })
    yield log_id
    db.fin_email_log.delete_many({"id": log_id})


class TestPixelDeApertura:
    def test_devuelve_un_png_de_verdad_y_sin_cache(self, movimiento):
        r = requests.get(f"{FIN}/email-log/{movimiento}/open.png", timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        # Sin esto el lector de correo cachea el píxel y la segunda apertura no
        # se registra nunca.
        assert "no-store" in r.headers.get("cache-control", "")

    def test_no_pide_sesion(self, movimiento):
        """Lo llama el buzón del cliente: si pidiera token, no habría registro."""
        r = requests.get(f"{FIN}/email-log/{movimiento}/open.png", timeout=30)
        assert r.status_code == 200

    def test_anota_la_apertura_y_la_cuenta(self, movimiento, db, headers):
        requests.get(f"{FIN}/email-log/{movimiento}/open.png", timeout=30)
        fila = db.fin_email_log.find_one({"id": movimiento})
        primera = fila["opened_at"]
        assert primera, "tiene que quedar la fecha de la primera apertura"
        assert fila["open_count"] == 1

        requests.get(f"{FIN}/email-log/{movimiento}/open.png", timeout=30)
        requests.get(f"{FIN}/email-log/{movimiento}/open.png", timeout=30)
        fila = db.fin_email_log.find_one({"id": movimiento})
        assert fila["open_count"] == 3
        assert fila["opened_at"] == primera, "la primera apertura no se sobreescribe"

    def test_un_id_que_no_existe_igual_devuelve_el_pixel(self):
        """Un correo viejo o borrado no puede romperle la vista al cliente."""
        r = requests.get(f"{FIN}/email-log/{uuid.uuid4()}/open.png", timeout=30)
        assert r.status_code == 200
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


class TestClickEnVerFacturaOnline:
    def test_abrir_la_factura_desde_el_correo_queda_registrado(self, headers, db, movimiento):
        tag = uuid.uuid4().hex[:6]
        cl = requests.post(f"{FIN}/clients", headers=headers, json={
            "business_name": f"TEST_seen {tag}", "representative": "T",
            "email": f"seen.{tag}@example.com", "phone": "1",
            "address_line1": "1", "city": "Columbus", "state": "OH", "zip": "43205",
        }, timeout=30).json()
        inv = requests.post(f"{FIN}/invoices/manual", headers=headers, json={
            "client_id": cl["id"], "issue_date": "2026-08-01", "due_date": "2026-08-01",
            "items": [{"description": "LED", "day_price": 8.5, "days": 30, "total": 255}],
        }, timeout=30).json()
        inv = inv.get("invoice", inv)

        r = requests.get(f"{FIN}/invoices/{inv['id']}/render?t={movimiento}", timeout=30)
        assert r.status_code == 200
        assert "INVOICE TO:" in r.text, "la factura online tiene que seguir abriendo"
        fila = db.fin_email_log.find_one({"id": movimiento})
        assert fila["viewed_at"], "el click tiene que quedar anotado"

        requests.delete(f"{FIN}/invoices/{inv['id']}/purge", headers=headers, timeout=30)
        requests.delete(f"{FIN}/clients/{cl['id']}/purge", headers=headers,
                        params={"confirm_name": cl["business_name"], "force": "true"}, timeout=30)

    def test_sin_el_parametro_no_marca_nada(self, headers, db, movimiento):
        """Que el dueño abra la factura desde el panel no cuenta como «el
        cliente la vio»."""
        tag = uuid.uuid4().hex[:6]
        cl = requests.post(f"{FIN}/clients", headers=headers, json={
            "business_name": f"TEST_seen2 {tag}", "representative": "T",
            "email": f"seen2.{tag}@example.com", "phone": "1",
            "address_line1": "1", "city": "Columbus", "state": "OH", "zip": "43205",
        }, timeout=30).json()
        inv = requests.post(f"{FIN}/invoices/manual", headers=headers, json={
            "client_id": cl["id"], "issue_date": "2026-08-01", "due_date": "2026-08-01",
            "items": [{"description": "LED", "day_price": 8.5, "days": 30, "total": 255}],
        }, timeout=30).json()
        inv = inv.get("invoice", inv)
        requests.get(f"{FIN}/invoices/{inv['id']}/render", timeout=30)
        assert db.fin_email_log.find_one({"id": movimiento})["viewed_at"] is None

        requests.delete(f"{FIN}/invoices/{inv['id']}/purge", headers=headers, timeout=30)
        requests.delete(f"{FIN}/clients/{cl['id']}/purge", headers=headers,
                        params={"confirm_name": cl["business_name"], "force": "true"}, timeout=30)


class TestElHistorialLoMuestra:
    def test_el_resumen_cuenta_los_vistos(self, headers, db, movimiento):
        requests.get(f"{FIN}/email-log/{movimiento}/open.png", timeout=30)
        data = requests.get(f"{FIN}/email-log?limit=300", headers=headers, timeout=30).json()
        assert "total_seen" in data and data["total_seen"] >= 1
        fila = [x for x in data["rows"] if x["id"] == movimiento]
        assert fila, "el movimiento tiene que estar en la lista"
        assert fila[0]["opened_at"], "el panel necesita la fecha de apertura"
        assert fila[0]["open_count"] >= 1


class TestLosCorreosLlevanElSeguimiento:
    def test_la_factura_lleva_pixel_y_link_rastreado(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from finance_email import render_invoice_email_html

        inv = {"id": "inv1", "invoice_number": "OH1", "period_start": "2026-08-01",
               "period_end": "2026-08-31", "issue_date": "2026-07-25",
               "due_date": "2026-08-01", "total": 100.0, "balance": 100.0}
        cl = {"business_name": "Test", "representative": "T", "email": "a@b.com"}
        html = render_invoice_email_html(inv, cl, base_url="https://www.mediadview.com",
                                         track_id="LOG123")
        assert "/api/finance/email-log/LOG123/open.png" in html
        assert "/api/finance/invoices/inv1/render?t=LOG123" in html

    def test_sin_track_id_no_hay_seguimiento(self):
        """Una vista previa en el panel no debe pedir el píxel ni marcar nada."""
        import sys
        sys.path.insert(0, "/app/backend")
        from finance_email import render_invoice_email_html

        html = render_invoice_email_html(
            {"id": "inv1", "invoice_number": "OH1"}, {"business_name": "T"},
            base_url="https://www.mediadview.com")
        assert "open.png" not in html
        assert "?t=" not in html

    def test_los_remitentes_generan_el_id_antes_de_armar_el_correo(self):
        """Si el id se generara después, no podría viajar dentro del correo."""
        import inspect
        import sys
        sys.path.insert(0, "/app/backend")
        import finance_scheduler

        factura = inspect.getsource(finance_scheduler._send_invoice_email)
        assert "track_id=log_id" in factura
        assert "log_id=log_id" in factura, "el envío tiene que guardar ESE id"

        plano = inspect.getsource(finance_scheduler._send_plain_email)
        assert "tracking_pixel(" in plano, "recordatorios y recibos también se rastrean"
        assert "log_id=log_id" in plano
