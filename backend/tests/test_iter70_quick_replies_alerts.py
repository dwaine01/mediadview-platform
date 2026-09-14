"""Respuestas rápidas y aviso de mensajes sin responder.

Dos cosas que el dueño pidió mientras Meta revisa las plantillas:
 1. Frases guardadas para contestar en la bandeja sin escribir lo mismo cada vez.
 2. Un correo cuando un cliente escribió y nadie contestó (un mensaje sin
    respuesta es un cobro que se enfría).
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")
FIN = f"{BASE_URL}/api/finance"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


class TestRespuestasRapidas:
    def test_la_primera_vez_ya_vienen_frases_escritas(self, headers):
        """Una lista vacía no le sirve a nadie: se siembran las más usadas."""
        rows = requests.get(f"{FIN}/whatsapp/quick-replies", headers=headers,
                            timeout=30).json()
        assert len(rows) >= 5
        assert any("{saldo}" in r["text"] for r in rows), \
            "al menos una tiene que completar el saldo del cliente"
        assert all(r["id"] and r["title"] and r["text"] for r in rows)

    def test_no_se_duplican_al_volver_a_pedirlas(self, headers):
        uno = requests.get(f"{FIN}/whatsapp/quick-replies", headers=headers, timeout=30).json()
        dos = requests.get(f"{FIN}/whatsapp/quick-replies", headers=headers, timeout=30).json()
        assert len(uno) == len(dos)

    def test_crear_editar_y_borrar(self, headers):
        titulo = f"TEST {uuid.uuid4().hex[:5]}"
        r = requests.post(f"{FIN}/whatsapp/quick-replies", headers=headers, timeout=30,
                          json={"title": titulo, "text": "Hola {nombre}, te debo {saldo}"})
        assert r.status_code == 200, r.text
        qr = r.json()

        r = requests.patch(f"{FIN}/whatsapp/quick-replies/{qr['id']}", headers=headers,
                           json={"text": "Texto corregido"}, timeout=30)
        assert r.status_code == 200
        rows = requests.get(f"{FIN}/whatsapp/quick-replies", headers=headers, timeout=30).json()
        assert next(x for x in rows if x["id"] == qr["id"])["text"] == "Texto corregido"

        assert requests.delete(f"{FIN}/whatsapp/quick-replies/{qr['id']}",
                               headers=headers, timeout=30).status_code == 200
        rows = requests.get(f"{FIN}/whatsapp/quick-replies", headers=headers, timeout=30).json()
        assert not [x for x in rows if x["id"] == qr["id"]]

    def test_no_guarda_una_respuesta_vacia(self, headers):
        r = requests.post(f"{FIN}/whatsapp/quick-replies", headers=headers,
                          json={"title": " ", "text": " "}, timeout=30)
        assert r.status_code == 400

    def test_borrar_algo_que_no_existe_avisa(self, headers):
        assert requests.delete(f"{FIN}/whatsapp/quick-replies/no-existe",
                               headers=headers, timeout=30).status_code == 404

    def test_pide_sesion(self):
        assert requests.get(f"{FIN}/whatsapp/quick-replies",
                            timeout=30).status_code in (401, 403)


class TestConfiguracionDelAviso:
    def test_trae_valores_usables_por_defecto(self, headers):
        d = requests.get(f"{FIN}/whatsapp/alerts", headers=headers, timeout=30).json()
        assert d["enabled"] is True
        assert d["minutes"] == 60
        assert "@" in d["to_email"], "por defecto usa el correo de facturación ya configurado"

    def test_guarda_el_tiempo_de_espera_y_el_destino(self, headers):
        r = requests.put(f"{FIN}/whatsapp/alerts", headers=headers, timeout=30,
                         json={"enabled": True, "minutes": 30, "to_email": "dueno@example.com"})
        assert r.status_code == 200
        d = requests.get(f"{FIN}/whatsapp/alerts", headers=headers, timeout=30).json()
        assert d["minutes"] == 30 and d["to_email"] == "dueno@example.com"
        requests.put(f"{FIN}/whatsapp/alerts", headers=headers,
                     json={"enabled": True, "minutes": 60, "to_email": ""}, timeout=30)

    def test_rechaza_esperas_absurdas(self, headers):
        for m in (1, 5000):
            r = requests.put(f"{FIN}/whatsapp/alerts", headers=headers,
                             json={"enabled": True, "minutes": m}, timeout=30)
            assert r.status_code == 400, f"{m} minutos no tiene sentido"


class TestJobDeMensajesSinResponder:
    """El job corre cada 10 minutos: se prueba con la base directamente."""

    @pytest.fixture
    def escena(self, mongo_db):
        tel = "1614" + uuid.uuid4().int.__str__()[:7]
        mongo_db.fin_settings.update_one(
            {"_id": "wa_alerts"},
            {"$set": {"enabled": True, "minutes": 60, "to_email": "dueno@example.com"}},
            upsert=True)
        yield tel, mongo_db
        mongo_db.wa_conversations.delete_many({"phone": tel})
        mongo_db.fin_settings.update_one({"_id": "wa_alerts"},
                                         {"$set": {"to_email": ""}})

    def correr(self, monkeypatch, capturado):
        import finance_scheduler as fs
        from motor.motor_asyncio import AsyncIOMotorClient

        async def falso_envio(db, client, subject, html, *, kind, invoice_id=None):
            capturado.append({"to": client.get("email"), "subject": subject,
                              "html": html, "kind": kind})
            return True

        monkeypatch.setattr(fs, "_send_plain_email", falso_envio)
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        asyncio.run(fs.unanswered_whatsapp_job(db))
        cli.close()

    def test_avisa_una_conversacion_vieja_sin_respuesta(self, escena, monkeypatch):
        tel, mdb = escena
        viejo = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        mdb.wa_conversations.insert_one({
            "id": str(uuid.uuid4()), "phone": tel, "client_name": "",
            "last_message": "¿Me pueden pasar el total?", "last_direction": "in",
            "last_inbound_at": viejo, "last_at": viejo, "unread": 1})
        salidas = []
        self.correr(monkeypatch, salidas)
        assert len(salidas) == 1, "tiene que salir un correo"
        assert salidas[0]["to"] == "dueno@example.com"
        assert "sin responder" in salidas[0]["subject"]
        assert "¿Me pueden pasar el total?" in salidas[0]["html"]
        assert "Número sin ficha de cliente" in salidas[0]["html"]
        # Y no vuelve a avisar por el mismo mensaje.
        otras = []
        self.correr(monkeypatch, otras)
        assert otras == [], "el mismo mensaje no se avisa dos veces"

    def test_un_mensaje_recien_llegado_no_molesta(self, escena, monkeypatch):
        tel, mdb = escena
        ahora = datetime.utcnow().isoformat()
        mdb.wa_conversations.insert_one({
            "id": str(uuid.uuid4()), "phone": tel, "last_message": "Hola",
            "last_direction": "in", "last_inbound_at": ahora, "last_at": ahora, "unread": 1})
        salidas = []
        self.correr(monkeypatch, salidas)
        assert salidas == [], "hay que darle tiempo al dueño de contestar"

    def test_si_ya_contestaron_no_avisa(self, escena, monkeypatch):
        tel, mdb = escena
        viejo = (datetime.utcnow() - timedelta(hours=5)).isoformat()
        mdb.wa_conversations.insert_one({
            "id": str(uuid.uuid4()), "phone": tel, "last_message": "Gracias",
            "last_direction": "out", "last_inbound_at": viejo, "last_at": viejo, "unread": 0})
        salidas = []
        self.correr(monkeypatch, salidas)
        assert salidas == []

    def test_con_el_aviso_apagado_no_manda_nada(self, escena, monkeypatch):
        tel, mdb = escena
        viejo = (datetime.utcnow() - timedelta(hours=5)).isoformat()
        mdb.wa_conversations.insert_one({
            "id": str(uuid.uuid4()), "phone": tel, "last_message": "Hola",
            "last_direction": "in", "last_inbound_at": viejo, "last_at": viejo, "unread": 1})
        mdb.fin_settings.update_one({"_id": "wa_alerts"}, {"$set": {"enabled": False}})
        salidas = []
        self.correr(monkeypatch, salidas)
        mdb.fin_settings.update_one({"_id": "wa_alerts"}, {"$set": {"enabled": True}})
        assert salidas == []

    def test_sin_correo_de_destino_no_explota(self, escena, monkeypatch):
        tel, mdb = escena
        viejo = (datetime.utcnow() - timedelta(hours=5)).isoformat()
        mdb.wa_conversations.insert_one({
            "id": str(uuid.uuid4()), "phone": tel, "last_message": "Hola",
            "last_direction": "in", "last_inbound_at": viejo, "last_at": viejo, "unread": 1})
        mdb.fin_settings.update_one({"_id": "wa_alerts"}, {"$set": {"to_email": "ZZZ"}})
        mdb.fin_settings.update_one({"_id": "email"}, {"$set": {"_tmp": 1}}, upsert=True)
        salidas = []
        self.correr(monkeypatch, salidas)   # no debe lanzar excepción
        assert len(salidas) <= 1
