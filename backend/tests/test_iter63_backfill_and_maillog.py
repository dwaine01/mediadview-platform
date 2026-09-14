"""Facturar meses atrasados de un cliente + historial de correos.

Pedido del dueño: «Dulce Vida se dio de alta debiendo julio, agosto y
septiembre: quiero generar esas tres facturas, que se manden solas a su correo,
poder imprimirlas, y ver en el panel un historial de los correos que salieron».
"""
import os
import uuid
from datetime import date, datetime

import pytest
import requests

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")
FIN = f"{BASE_URL}/api/finance"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def cliente_con_contrato(headers):
    """Cliente nuevo con un contrato activo que cubre todo el año: es el
    escenario de «se dio de alta debiendo meses»."""
    tag = uuid.uuid4().hex[:6]
    r = requests.post(f"{FIN}/clients", headers=headers, json={
        "business_name": f"Dulce Vida Test {tag}",
        "representative": "Josue",
        "email": f"dulce.{tag}@example.com",
        "phone": "614-555-0000",
        "address_line1": "1 Test St", "city": "Columbus", "state": "OH", "zip": "43205",
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    client = r.json()

    year = date.today().year
    r = requests.post(f"{FIN}/contracts", headers=headers, json={
        "client_id": client["id"],
        "start_date": f"{year}-01-01",
        "term_months": 12,
        "screens": [{"model": "MAV-30540S", "units": 1, "day_price": 8.5,
                     "location": "Test", "description": "LED"}],
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    contract = r.json()["contract"] if "contract" in r.json() else r.json()
    yield client, contract

    # Limpieza: las facturas creadas por el test no deben quedar en la base.
    invs = requests.get(f"{FIN}/invoices", headers=headers, timeout=30).json()
    for inv in invs:
        if inv.get("client_id") == client["id"]:
            requests.delete(f"{FIN}/invoices/{inv['id']}", headers=headers, timeout=30)


def _tres_meses():
    hoy = date.today()
    out = []
    for k in (2, 1, 0):
        m = hoy.month - k
        y = hoy.year
        while m <= 0:
            m += 12
            y -= 1
        out.append(f"{y}-{m:02d}")
    return out


class TestBackfill:
    def test_genera_los_tres_meses_de_una_sola_vez(self, headers, cliente_con_contrato):
        client, _ = cliente_con_contrato
        periods = _tres_meses()
        r = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": client["id"], "periods": periods, "send_email": False}, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 3, data
        creadas = [x for x in data["results"] if x["status"] == "created"]
        assert {x["period"] for x in creadas} == set(periods)
        for x in creadas:
            assert x["invoice_number"], "cada factura tiene que salir numerada"
            assert x["total"] > 0

    def test_no_duplica_si_el_mes_ya_esta_facturado(self, headers, cliente_con_contrato):
        client, _ = cliente_con_contrato
        periods = _tres_meses()
        r = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": client["id"], "periods": periods, "send_email": False}, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 0
        assert data["skipped"] == 3
        for x in data["results"]:
            assert "Ya existía" in x["detail"]
            assert x["invoice_number"], "tiene que decir cuál es la factura que ya existe"

    def test_las_facturas_quedan_con_vencimiento_el_dia_1(self, headers, cliente_con_contrato):
        client, _ = cliente_con_contrato
        invs = [i for i in requests.get(f"{FIN}/invoices", headers=headers, timeout=30).json()
                if i.get("client_id") == client["id"]]
        assert len(invs) >= 3
        for inv in invs:
            assert inv["due_date"].endswith("-01"), inv["due_date"]
            assert inv["period_start"].endswith("-01")
            assert inv["status"] in ("pending", "overdue")

    def test_se_pueden_imprimir(self, headers, cliente_con_contrato):
        """El PDF de cada factura atrasada tiene que abrir (es lo que se imprime)."""
        client, _ = cliente_con_contrato
        invs = [i for i in requests.get(f"{FIN}/invoices", headers=headers, timeout=30).json()
                if i.get("client_id") == client["id"]]
        for inv in invs[:3]:
            p = requests.get(f"{FIN}/invoices/{inv['id']}/pdf", timeout=60)
            assert p.status_code == 200
            assert p.content[:4] == b"%PDF"
            assert len(p.content) > 5000

    def test_pide_al_menos_un_mes(self, headers, cliente_con_contrato):
        client, _ = cliente_con_contrato
        r = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": client["id"], "periods": [], "send_email": False}, timeout=30)
        assert r.status_code == 400

    def test_rechaza_periodo_mal_escrito(self, headers, cliente_con_contrato):
        client, _ = cliente_con_contrato
        r = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": client["id"], "periods": ["julio"], "send_email": False}, timeout=30)
        assert r.status_code == 400
        assert "inválido" in r.json()["detail"].lower()

    def test_cliente_inexistente_da_404(self, headers):
        r = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": "no-existe", "periods": ["2026-07"], "send_email": False}, timeout=30)
        assert r.status_code == 404


class TestHistorialDeCorreos:
    def test_el_historial_responde_con_su_resumen(self, headers):
        r = requests.get(f"{FIN}/email-log?limit=50", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "rows" in data and isinstance(data["rows"], list)
        assert "total_ok" in data and "total_failed" in data

    def test_cada_movimiento_dice_cliente_tipo_y_resultado(self, headers, cliente_con_contrato):
        """Se inyecta un movimiento de cada tipo y el historial tiene que
        devolverlos con el nombre del cliente resuelto."""
        from pymongo import MongoClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        client, _ = cliente_con_contrato
        marca = uuid.uuid4().hex[:8]
        tipos = ["invoice", "reminder:pre_due", "reminder:late_7", "receipt"]
        db.fin_email_log.insert_many([{
            "id": str(uuid.uuid4()), "client_id": client["id"], "invoice_id": None,
            "kind": k, "to": client["email"], "subject": f"{marca} {k}",
            "ok": True, "error": "", "sent_at": datetime.utcnow().isoformat(),
        } for k in tipos])
        try:
            r = requests.get(f"{FIN}/email-log?limit=300&client_id={client['id']}",
                             headers=headers, timeout=30)
            assert r.status_code == 200
            rows = r.json()["rows"]
            kinds = {x["kind"] for x in rows}
            assert set(tipos).issubset(kinds), kinds
            for x in rows:
                assert x["client_name"] == client["business_name"]
                assert x["to"] == client["email"]
        finally:
            db.fin_email_log.delete_many({"subject": {"$regex": marca}})

    def test_filtra_los_recordatorios_por_prefijo(self, headers, cliente_con_contrato):
        from pymongo import MongoClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        client, _ = cliente_con_contrato
        marca = uuid.uuid4().hex[:8]
        db.fin_email_log.insert_many([
            {"id": str(uuid.uuid4()), "client_id": client["id"], "invoice_id": None,
             "kind": "reminder:late_15", "to": "a@b.com", "subject": f"{marca} r",
             "ok": True, "error": "", "sent_at": datetime.utcnow().isoformat()},
            {"id": str(uuid.uuid4()), "client_id": client["id"], "invoice_id": None,
             "kind": "invoice", "to": "a@b.com", "subject": f"{marca} i",
             "ok": True, "error": "", "sent_at": datetime.utcnow().isoformat()},
        ])
        try:
            r = requests.get(f"{FIN}/email-log?limit=300&client_id={client['id']}&kind=reminder",
                             headers=headers, timeout=30)
            kinds = {x["kind"] for x in r.json()["rows"]}
            assert kinds and all(k.startswith("reminder") for k in kinds), kinds
        finally:
            db.fin_email_log.delete_many({"subject": {"$regex": marca}})

    def test_solo_errores(self, headers, cliente_con_contrato):
        from pymongo import MongoClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        client, _ = cliente_con_contrato
        marca = uuid.uuid4().hex[:8]
        db.fin_email_log.insert_one({
            "id": str(uuid.uuid4()), "client_id": client["id"], "invoice_id": None,
            "kind": "invoice", "to": "a@b.com", "subject": f"{marca} falla",
            "ok": False, "error": "535 authentication failed",
            "sent_at": datetime.utcnow().isoformat()})
        try:
            r = requests.get(f"{FIN}/email-log?limit=300&only_errors=true", headers=headers, timeout=30)
            rows = r.json()["rows"]
            assert rows and all(x["ok"] is False for x in rows)
            assert any("535" in (x.get("error") or "") for x in rows)
        finally:
            db.fin_email_log.delete_many({"subject": {"$regex": marca}})

    def test_el_historial_pide_sesion(self):
        r = requests.get(f"{FIN}/email-log", timeout=30)
        assert r.status_code in (401, 403)


class TestEnvioQuedaRegistrado:
    def test_si_el_correo_no_sale_el_historial_dice_por_que(self, headers, cliente_con_contrato):
        """En dev no hay SMTP real: el envío falla. Lo importante es que la
        factura se crea igual, el error se explica y queda en el historial
        (antes el dueño veía «no pasó nada» y no sabía qué corregir)."""
        client, _ = cliente_con_contrato
        hoy = date.today()
        if hoy.month == 12:
            pytest.skip("en diciembre no queda mes futuro dentro del contrato")
        futuro = f"{hoy.year}-{hoy.month + 1:02d}"
        r = requests.post(f"{FIN}/invoices/generate-for-client", headers=headers, json={
            "client_id": client["id"], "periods": [futuro], "send_email": True}, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        # El contrato es de 12 meses, así que el año que viene puede no estar
        # cubierto: si no se creó nada, no hay nada que verificar.
        if data["created"] == 0:
            pytest.skip("el contrato no cubre ese período")
        fila = [x for x in data["results"] if x["status"] == "created"][0]
        if fila["emailed"]:
            pytest.skip("hay SMTP configurado en este entorno: el correo salió")
        assert fila["detail"], "si no se pudo enviar, tiene que decir el motivo"
        log = requests.get(f"{FIN}/email-log?limit=50&client_id={client['id']}",
                           headers=headers, timeout=30).json()["rows"]
        assert any(not x["ok"] and x["kind"] == "invoice" for x in log), log
