"""Nota #1 — el anunciante ve DÓNDE va a aparecer su publicidad antes de pagar.

Lo que se prueba es la promesa comercial, no el código: la ficha de la ubicación
tiene que traer negocio, dirección, ciudad, cómo llegar, tráfico estimado y la
foto real de la pantalla instalada; y la pantalla cuyo QR escaneó el anunciante
tiene que venir marcada y primera en la lista.

    cd /app/backend && python -m pytest tests/test_nota1_venue_detail.py -q
"""
import os

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL") or os.environ["EXPO_PUBLIC_BACKEND_URL"]
ADVERTISER = ("anunciante@demo.com", "Anuncio1234!")
DEMO_CODE = "MV-ADV-FJUSIW"   # Supermercado La Colonia (seed_public_ad_screens.py)


@pytest.fixture(scope="module")
def token():
    response = requests.post(f"{BASE}/api/auth/login",
                             json={"email": ADVERTISER[0], "password": ADVERTISER[1]},
                             timeout=20)
    assert response.status_code == 200, response.text[:200]
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def catalog(headers):
    response = requests.get(f"{BASE}/api/marketplace/screens",
                            params={"here": DEMO_CODE}, headers=headers, timeout=30)
    assert response.status_code == 200, response.text[:200]
    return response.json()


def test_la_pantalla_escaneada_viene_marcada_y_primera(catalog):
    assert catalog, "el catálogo del anunciante está vacío"
    assert catalog[0]["is_here"] is True, "la pantalla del QR no quedó primera"
    assert sum(1 for s in catalog if s["is_here"]) == 1


def test_el_catalogo_no_muestra_pantallas_de_prueba(catalog):
    basura = [s["name"] for s in catalog
              if s["name"].startswith(("TEST_", "CHAIN ", "DISKLESS ", "ORIENT TEST",
                                       "VIDEO ", "ITER36 ", "MgrScreen-"))]
    assert not basura, f"pantallas de prueba visibles al anunciante: {basura[:5]}"


def test_cada_tarjeta_trae_la_ficha_de_la_ubicacion(catalog):
    for screen in catalog:
        venue = screen["venue"]
        assert venue["establishment_name"], f"{screen['id']} sin nombre de establecimiento"
        for key in ("address", "city", "reference", "audience", "photo_url", "has_photo"):
            assert key in venue, f"falta {key} en la ficha de {screen['id']}"


def test_ficha_detallada_completa_antes_de_pagar(headers, catalog):
    """Las 4 pantallas de demo tienen la ficha completa: es el estándar."""
    demo = [s for s in catalog if s["venue"]["has_photo"]]
    assert len(demo) >= 4, "faltan las pantallas de demostración con ficha completa"
    for screen in demo:
        response = requests.get(f"{BASE}/api/marketplace/screens/{screen['id']}",
                                params={"here": DEMO_CODE}, headers=headers, timeout=20)
        assert response.status_code == 200, response.text[:200]
        detail = response.json()
        venue = detail["venue"]
        assert venue["establishment_name"] and venue["address"] and venue["city"]
        assert venue["reference"], "sin referencia de cómo llegar"
        assert venue["audience"]["label"], "sin tráfico estimado"
        assert detail["max_ad_slots"] >= 1
        assert detail["pricing"]["price_per_month"], "sin precio mensual"
        # La foto se sirve como imagen, no como base64 dentro del JSON.
        assert "photo_base64" not in str(detail)
        photo = requests.get(f"{BASE}{venue['photo_url']}", timeout=30)
        assert photo.status_code == 200
        assert photo.headers["content-type"].startswith("image/")
        assert int(photo.headers["content-length"]) > 10_000


def test_la_ficha_exige_sesion(catalog):
    response = requests.get(f"{BASE}/api/marketplace/screens/{catalog[0]['id']}", timeout=20)
    assert response.status_code in (401, 403)


def test_la_landing_del_qr_es_publica_y_trae_la_ficha():
    response = requests.get(f"{BASE}/api/advertise/{DEMO_CODE}", timeout=20)
    assert response.status_code == 200, response.text[:200]
    venue = response.json()["venue"]
    assert venue["establishment_name"] == "Supermercado La Colonia"
    assert venue["audience"]["label"]
    assert venue["photo_url"]
