"""La contraseña del correo no puede fallar en silencio.

La contraseña SMTP se guarda cifrada con una llave derivada del secreto del
servidor. Cuando ese secreto cambió (un redespliegue), la contraseña guardada
el 03/06/2026 quedó ilegible: el sistema intentaba autenticarse con una
contraseña vacía y el proveedor contestaba «535 authentication failed». Durante
meses las facturas dejaron de salir y el error no decía qué hacer.

Lo que se prueba: que el sistema detecte que la contraseña guardada no se puede
leer y lo diga con instrucciones, en vez de mandar al dueño a buscar el
problema en su proveedor de correo.

    cd /app/backend && python -m pytest tests/test_smtp_password_readable.py -q
"""
import os

import pytest
import requests

from finance_email import (
    SMTP_PASSWORD_UNREADABLE,
    _derive,
    decrypt_password,
    encrypt_password,
    password_is_readable,
)

BASE = os.environ.get("TEST_BASE_URL") or os.environ["EXPO_PUBLIC_BACKEND_URL"]
ADMIN = ("superadmin@mediadview.com", "SuperAdmin#2026")


@pytest.fixture(scope="module")
def headers():
    response = requests.post(f"{BASE}/api/auth/login",
                             json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=20)
    assert response.status_code == 200, response.text[:200]
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_la_contrasena_va_y_vuelve():
    token = encrypt_password("clave-del-correo")
    assert token and token != "clave-del-correo"
    assert decrypt_password(token) == "clave-del-correo"
    assert password_is_readable(token) is True


def test_una_contrasena_de_otra_llave_se_detecta():
    """Lo que pasó en producción: cifrada con un secreto que ya no existe."""
    from cryptography.fernet import Fernet

    ajena = Fernet(_derive("un-secreto-que-ya-no-existe"))
    token = ajena.encrypt(b"clave-del-correo").decode()
    assert decrypt_password(token) == "", "no debería poder leerla"
    assert password_is_readable(token) is False, \
        "si no se puede leer, hay que avisarlo y no intentar el envío"


def test_sin_contrasena_no_hay_aviso_falso():
    assert password_is_readable("") is False
    assert decrypt_password("") == ""


def test_las_llaves_viejas_siguen_sirviendo_para_leer():
    """Con FERNET_KEY puesta, lo cifrado con la llave derivada aún se lee."""
    from cryptography.fernet import Fernet

    from finance_email import _fernet_keys

    keys = _fernet_keys()
    assert len(keys) >= 2, "debe haber llaves de respaldo para no perder datos"
    vieja = Fernet(keys[-1])
    token = vieja.encrypt(b"clave-vieja").decode()
    assert decrypt_password(token) == "clave-vieja"


def test_el_panel_avisa_que_hay_que_reescribir_la_contrasena(headers):
    response = requests.get(f"{BASE}/api/finance/settings/email", headers=headers, timeout=20)
    assert response.status_code == 200, response.text[:200]
    body = response.json()
    assert "password_readable" in body, "el panel necesita saber si se puede leer"
    if body.get("password_set") and not body["password_readable"]:
        assert body["password_warning"] == SMTP_PASSWORD_UNREADABLE
        assert "Email Settings" in body["password_warning"], \
            "el aviso tiene que decir dónde arreglarlo"


def test_el_envio_explica_el_problema_en_vez_de_un_535(headers):
    settings = requests.get(f"{BASE}/api/finance/settings/email",
                            headers=headers, timeout=20).json()
    if settings.get("password_readable"):
        pytest.skip("la contraseña guardada se puede leer: no hay nada que avisar")
    invoices = requests.get(f"{BASE}/api/finance/invoices", headers=headers, timeout=30).json()
    assert invoices, "no hay facturas para probar el envío"
    response = requests.post(f"{BASE}/api/finance/invoices/{invoices[0]['id']}/send",
                             headers=headers, json={"to": "prueba@ejemplo.com"}, timeout=60)
    assert response.status_code == 400, \
        f"debería ser un 400 con instrucciones, no {response.status_code}"
    detail = response.json()["detail"]
    assert detail == SMTP_PASSWORD_UNREADABLE
    assert "authentication failed" not in detail.lower()


def test_las_facturas_y_contratos_se_siguen_generando(headers):
    """El cobro no depende del correo: generar e imprimir tiene que seguir igual."""
    clients = requests.get(f"{BASE}/api/finance/clients", headers=headers, timeout=30).json()
    assert clients, "no hay clientes cargados"
    invoices = requests.get(f"{BASE}/api/finance/invoices", headers=headers, timeout=30).json()
    assert invoices
    invoice_id = invoices[0]["id"]
    assert requests.get(f"{BASE}/api/finance/invoices/{invoice_id}/render",
                        headers=headers, timeout=30).status_code == 200
    pdf = requests.get(f"{BASE}/api/finance/invoices/{invoice_id}/pdf",
                       headers=headers, timeout=60)
    assert pdf.status_code == 200 and len(pdf.content) > 5000
