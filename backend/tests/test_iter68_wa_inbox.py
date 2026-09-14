"""Bandeja de entrada de WhatsApp — lo que escriben los clientes se lee acá.

Meta no guarda un historial que se pueda recuperar después: si el mensaje
entrante no se guarda cuando llega el webhook, se pierde. Por eso se fija acá
el camino completo: llega el webhook → aparece la conversación → se ve el hilo
(texto y archivos) → se vincula con la ficha del cliente.
"""
import os
import sys
import time
import uuid

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")
FIN = f"{BASE_URL}/api/finance"
WA = f"{BASE_URL}/api/whatsapp"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def phone(mongo_db):
    """Un número distinto por corrida para no mezclarse con datos reales."""
    tel = "1614" + str(int(time.time()))[-7:]
    yield tel
    # La bandeja es real: lo que dejan las pruebas se limpia para que el dueño
    # no vea conversaciones inventadas.
    mongo_db.wa_messages.delete_many({"$or": [{"to": tel}, {"from": tel}]})
    mongo_db.wa_conversations.delete_many({"phone": tel})


def webhook(mensajes=None, estados=None):
    valor = {"messaging_product": "whatsapp"}
    if mensajes:
        valor["messages"] = mensajes
    if estados:
        valor["statuses"] = estados
    return requests.post(f"{WA}/webhook", timeout=30, json={
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": valor}]}]})


class TestLlegaUnMensaje:
    def test_el_texto_del_cliente_queda_guardado_y_arma_la_conversacion(self, headers, phone):
        mid = "wamid.TEST" + uuid.uuid4().hex
        assert webhook([{"id": mid, "from": phone, "type": "text",
                         "text": {"body": "Hola, quiero pagar mi factura"}}]).status_code == 200

        r = requests.get(f"{FIN}/whatsapp/inbox", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        conv = next((c for c in r.json()["rows"] if c["phone"] == phone), None)
        assert conv, "la conversación tiene que aparecer en la bandeja"
        assert conv["last_message"] == "Hola, quiero pagar mi factura"
        assert conv["last_direction"] == "in"
        assert conv["unread"] >= 1, "un mensaje nuevo se marca como no leído"
        assert conv["window_open"] is True, "recién escribió: se puede responder libre"

    def test_meta_reintenta_y_no_se_duplica(self, headers, phone):
        mid = "wamid.DUP" + uuid.uuid4().hex
        msg = [{"id": mid, "from": phone, "type": "text", "text": {"body": "repetido"}}]
        webhook(msg)
        webhook(msg)
        hilo = requests.get(f"{FIN}/whatsapp/inbox/{phone}", headers=headers, timeout=30).json()
        iguales = [m for m in hilo["messages"] if m.get("message_id") == mid]
        assert len(iguales) == 1, "Meta reintenta el webhook: no puede duplicar el mensaje"

    def test_la_foto_y_el_pdf_guardan_el_id_para_bajarlos_despues(self, headers, phone):
        webhook([{"id": "wamid.IMG" + uuid.uuid4().hex, "from": phone, "type": "image",
                  "image": {"id": "media-123", "mime_type": "image/jpeg",
                            "caption": "así quedó la pantalla"}}])
        webhook([{"id": "wamid.DOC" + uuid.uuid4().hex, "from": phone, "type": "document",
                  "document": {"id": "media-456", "mime_type": "application/pdf",
                               "filename": "comprobante.pdf"}}])
        msgs = requests.get(f"{FIN}/whatsapp/inbox/{phone}", headers=headers,
                            timeout=30).json()["messages"]
        img = next(m for m in msgs if (m.get("media") or {}).get("media_id") == "media-123")
        assert img["media"]["kind"] == "image"
        assert img["text"] == "así quedó la pantalla", "el pie de foto es el texto"
        doc = next(m for m in msgs if (m.get("media") or {}).get("media_id") == "media-456")
        assert doc["media"]["filename"] == "comprobante.pdf"

    def test_una_nota_de_voz_o_ubicacion_no_se_pierde(self):
        from whatsapp import parse_inbound
        voz = parse_inbound({"type": "audio", "audio": {"id": "m1", "mime_type": "audio/ogg"}})
        assert voz["media"]["media_id"] == "m1" and voz["media"]["kind"] == "audio"
        ubi = parse_inbound({"type": "location",
                             "location": {"latitude": 1, "longitude": 2, "name": "El local"}})
        assert "El local" in ubi["text"] and ubi["media"] is None
        raro = parse_inbound({"type": "reaction", "reaction": {"emoji": "👍"}})
        assert raro["text"] == "[reaction]", "un tipo nuevo de Meta no puede romper el webhook"


class TestHiloYLectura:
    def test_marcar_como_leido_pone_el_contador_en_cero(self, headers, phone):
        r = requests.post(f"{FIN}/whatsapp/inbox/{phone}/read", headers=headers, timeout=30)
        assert r.status_code == 200
        conv = next(c for c in requests.get(f"{FIN}/whatsapp/inbox", headers=headers,
                                            timeout=30).json()["rows"] if c["phone"] == phone)
        assert conv["unread"] == 0

    def test_los_mensajes_vienen_del_mas_viejo_al_mas_nuevo(self, headers, phone):
        msgs = requests.get(f"{FIN}/whatsapp/inbox/{phone}", headers=headers,
                            timeout=30).json()["messages"]
        fechas = [m["sent_at"] for m in msgs]
        assert fechas == sorted(fechas), "el chat se lee de arriba hacia abajo"

    def test_pide_sesion(self, phone):
        for url in (f"{FIN}/whatsapp/inbox", f"{FIN}/whatsapp/inbox/{phone}",
                    f"{FIN}/whatsapp/media/media-123"):
            assert requests.get(url, timeout=30).status_code in (401, 403)


class TestNumeroDesconocido:
    def test_se_da_de_alta_el_cliente_desde_el_chat_y_el_hilo_queda_vinculado(self, headers, phone):
        nombre = f"TEST_inbox {uuid.uuid4().hex[:6]}"
        r = requests.post(f"{FIN}/whatsapp/inbox/{phone}/link", headers=headers, timeout=30,
                          json={"business_name": nombre, "representative": "Josue",
                                "email": "inbox@example.com"})
        assert r.status_code == 200, r.text
        client_id = r.json()["client_id"]

        hilo = requests.get(f"{FIN}/whatsapp/inbox/{phone}", headers=headers, timeout=30).json()
        assert hilo["client"]["id"] == client_id
        assert hilo["client"]["business_name"] == nombre
        assert hilo["client"]["open_count"] == 0 and hilo["client"]["balance"] == 0
        assert all(m["client_id"] == client_id for m in hilo["messages"]), \
            "los mensajes viejos también quedan con el cliente"

        cl = requests.get(f"{FIN}/clients/{client_id}", headers=headers, timeout=30).json()
        assert cl["whatsapp"].replace("+", "") == phone
        assert cl["wa_invoice_notify"] is True

        requests.delete(f"{FIN}/clients/{client_id}/purge", headers=headers,
                        params={"confirm_name": nombre, "force": "true"}, timeout=30)

    def test_sin_nombre_de_negocio_no_crea_nada(self, headers, phone):
        r = requests.post(f"{FIN}/whatsapp/inbox/{phone}/link", headers=headers,
                          json={"business_name": "  "}, timeout=30)
        assert r.status_code == 400
        assert "nombre" in r.json()["detail"].lower()

    def test_vincular_con_un_cliente_que_no_existe_avisa(self, headers, phone):
        r = requests.post(f"{FIN}/whatsapp/inbox/{phone}/link", headers=headers,
                          json={"client_id": "no-existe"}, timeout=30)
        assert r.status_code == 404


class TestVentanaDe24Horas:
    """Meta sólo permite texto libre 24 h después del último mensaje del cliente."""

    def test_sin_mensaje_entrante_la_ventana_esta_cerrada(self):
        from whatsapp import window_open
        assert window_open({}) is False
        assert window_open({"last_inbound_at": "2020-01-01T00:00:00"}) is False
        from datetime import datetime
        assert window_open({"last_inbound_at": datetime.utcnow().isoformat()}) is True

    def test_responder_con_el_canal_apagado_explica_que_falta(self, headers, phone):
        r = requests.post(f"{FIN}/whatsapp/inbox/{phone}/reply", headers=headers,
                          json={"text": "Buenas"}, timeout=30)
        assert r.status_code == 400
        assert "no está conectado" in r.json()["detail"]

    def test_un_mensaje_vacio_no_se_manda(self, headers, phone):
        r = requests.post(f"{FIN}/whatsapp/inbox/{phone}/reply", headers=headers,
                          json={"text": "   "}, timeout=30)
        assert r.status_code == 400


class TestLoEnviadoAparaceEnElHilo:
    def test_la_bitacora_de_salida_marca_direccion_y_arma_conversacion(self):
        """Si sólo se guardara lo entrante, el dueño vería la respuesta del
        cliente sin saber qué se le había mandado."""
        import inspect

        import whatsapp as wa
        src = inspect.getsource(wa.log_wa)
        assert '"direction": "out"' in src
        assert "upsert_conversation(db, to" in src
