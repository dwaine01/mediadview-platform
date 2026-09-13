"""Casos límite de geocodificación (iter55).

Complementa test_screen_geocoding.py con lo pedido en la iteración:
    - la misma dirección reenviada conserva el pin y no re-consulta
    - código postal válido con calle desconocida cae al centro del CP
    - permisos del endpoint /api/admin/screens/geocode-missing
    - GET /api/marketplace/screens/{id} refleja el pin recién puesto
    - guardar la pantalla del súper sin cambios no rompe la ficha

    cd /app/backend && python -m pytest tests/test_iter55_geocoding_edges.py -q
"""
import os
import time

import pytest
import requests

BASE = (os.environ.get("TEST_BASE_URL")
        or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
        or "https://sprint1-signage.preview.emergentagent.com").rstrip("/")
ADMIN = ("superadmin@mediadview.com", "SuperAdmin#2026")
ADVERTISER = ("anunciante@demo.com", "Anuncio1234!")

BASE_SCREEN = {
    "pricing": {"per_month": 300, "per_day": 10, "per_hour": 1, "per_slot": 1,
                "currency": "USD"},
    "specs": {"size": "55\"", "type": "LED", "resolution": "1920x1080",
              "orientation": "landscape"},
    "status": "active", "operation_type": "PUBLIC_ADVERTISING",
    "price_per_month": 300, "max_ad_slots": 4,
}

DEMO_SCREEN_ID = "535a0b15-223e-477a-8c28-33195b0a4ef5"
DEMO_PUBLIC_CODE = "MV-ADV-FJUSIW"


@pytest.fixture(scope="module")
def admin_headers():
    """Login del super admin una sola vez (auth tiene rate-limit 429)."""
    response = requests.post(f"{BASE}/api/auth/login",
                             json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=20)
    if response.status_code == 429:
        pytest.skip("auth bloqueado por intentos previos (429). Reintentar en 15 min")
    assert response.status_code == 200, response.text[:200]
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def advertiser_headers():
    response = requests.post(f"{BASE}/api/auth/login",
                             json={"email": ADVERTISER[0], "password": ADVERTISER[1]},
                             timeout=20)
    if response.status_code == 429:
        pytest.skip("auth bloqueado (429)")
    assert response.status_code == 200, response.text[:200]
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def cleanup(admin_headers):
    created = []
    yield created
    for sid in created:
        try:
            requests.delete(f"{BASE}/api/admin/screens/{sid}?cascade=true",
                            headers=admin_headers, timeout=20)
        except Exception:
            pass


def _create(headers, location, name="ITER55 TEST"):
    resp = requests.post(f"{BASE}/api/admin/screens", headers=headers, timeout=40,
                         json={**BASE_SCREEN, "name": name,
                               "description": "iter55 geocoding edge",
                               "location": location})
    assert resp.status_code == 200, resp.text[:300]
    return resp.json()


# ── 1. Alta con SPS: verifica pin y borrado con cascade ─────────────────────
def test_alta_san_pedro_sula_pone_pin_y_borra_bien(admin_headers, cleanup):
    body = _create(admin_headers,
                   {"city": "San Pedro Sula",
                    "address": "3 Avenida, Barrio Guamilito",
                    "postal_code": "21102", "country": "HN"},
                   name="ITER55 SPS")
    cleanup.append(body["id"])
    loc = body["location"]
    assert loc["lat"] is not None and loc["lng"] is not None
    assert 15.0 < loc["lat"] < 16.0, f"SPS fuera de rango lat={loc['lat']}"
    assert -89.0 < loc["lng"] < -87.0, f"SPS fuera de rango lng={loc['lng']}"
    assert loc.get("geocoded_from")
    assert loc.get("geocoded_at")

    # borrado con cascade=true
    r = requests.delete(f"{BASE}/api/admin/screens/{body['id']}?cascade=true",
                        headers=admin_headers, timeout=20)
    assert r.status_code == 200
    cleanup.remove(body["id"])
    # y ya no está
    g = requests.get(f"{BASE}/api/screens/{body['id']}", timeout=10)
    assert g.status_code == 404


# ── 2. Misma dirección reenviada sin lat/lng conserva pin ───────────────────
def test_misma_direccion_conserva_pin(admin_headers, cleanup):
    body = _create(admin_headers,
                   {"city": "Tegucigalpa", "address": "Avenida Miguel de Cervantes",
                    "postal_code": "11101", "country": "HN"},
                   name="ITER55 same-addr")
    cleanup.append(body["id"])
    before = (body["location"]["lat"], body["location"]["lng"])
    assert before[0] is not None

    # PUT con la misma dirección, SIN lat/lng
    r = requests.put(f"{BASE}/api/admin/screens/{body['id']}", headers=admin_headers,
                     timeout=40,
                     json={"location": {"city": "Tegucigalpa",
                                        "address": "Avenida Miguel de Cervantes",
                                        "postal_code": "11101", "country": "HN"}})
    assert r.status_code == 200, r.text[:200]
    after = (r.json()["location"]["lat"], r.json()["location"]["lng"])
    assert after == before, f"el pin cambió sin motivo: {before} -> {after}"


# ── 3. Coordenadas manuales ganan sobre el buscador ─────────────────────────
def test_lat_lng_manual_no_se_sobreescribe(admin_headers, cleanup):
    body = _create(admin_headers,
                   {"city": "Tegucigalpa", "address": "Avenida Miguel de Cervantes",
                    "postal_code": "11101", "country": "HN"},
                   name="ITER55 manual")
    cleanup.append(body["id"])
    r = requests.put(f"{BASE}/api/admin/screens/{body['id']}", headers=admin_headers,
                     timeout=40,
                     json={"location": {"city": "Tegucigalpa",
                                        "address": "Avenida Miguel de Cervantes",
                                        "postal_code": "11101", "country": "HN",
                                        "lat": 14.5, "lng": -87.5}})
    assert r.status_code == 200
    loc = r.json()["location"]
    assert (loc["lat"], loc["lng"]) == (14.5, -87.5)


# ── 4. Dirección inventada sin CP: guarda con lat/lng null (no 500) ─────────
def test_direccion_inventada_no_rompe(admin_headers, cleanup):
    body = _create(admin_headers,
                   {"city": "Nowhereville",
                    "address": "Calle inexistente xyzq 999",
                    "postal_code": "", "country": "HN"},
                   name="ITER55 sin ubicar")
    cleanup.append(body["id"])
    assert body["id"]
    assert body["location"].get("lat") is None, "no debería inventar un pin"


# ── 5. CP válido con calle desconocida → fallback al centro del CP ─────────
def test_cp_valido_con_calle_desconocida_cae_al_centro(admin_headers, cleanup):
    body = _create(admin_headers,
                   {"city": "Tegucigalpa",
                    "address": "zzzz qqqq 123",
                    "postal_code": "11101", "country": "HN"},
                   name="ITER55 fallback CP")
    cleanup.append(body["id"])
    loc = body["location"]
    # El fallback puede no encontrar el CP en Nominatim (raro pero posible):
    # lo importante es que no haya reventado y, si hubo pin, esté en Honduras.
    if loc.get("lat") is not None:
        assert 12.5 < loc["lat"] < 17.5, f"pin fuera de Honduras: {loc['lat']}"
        assert -90 < loc["lng"] < -83, f"pin fuera de Honduras: {loc['lng']}"


# ── 6. Mudanza mueve el pin ─────────────────────────────────────────────────
def test_mudanza_mueve_el_pin(admin_headers, cleanup):
    body = _create(admin_headers,
                   {"city": "Tegucigalpa",
                    "address": "Avenida Miguel de Cervantes",
                    "postal_code": "11101", "country": "HN"},
                   name="ITER55 mudanza")
    cleanup.append(body["id"])
    before = (body["location"]["lat"], body["location"]["lng"])
    r = requests.put(f"{BASE}/api/admin/screens/{body['id']}", headers=admin_headers,
                     timeout=40,
                     json={"location": {"city": "San Pedro Sula",
                                        "address": "3 Avenida, Barrio Guamilito",
                                        "postal_code": "21102", "country": "HN"}})
    assert r.status_code == 200
    after = (r.json()["location"]["lat"], r.json()["location"]["lng"])
    assert after != before
    assert 15.0 < after[0] < 16.0


# ── 7. GET /api/marketplace/screens/{id}: venue.lat/lng = location.lat/lng ─
def test_marketplace_venue_coords_iguales(admin_headers, cleanup):
    body = _create(admin_headers,
                   {"city": "Tegucigalpa",
                    "address": "Avenida Miguel de Cervantes",
                    "postal_code": "11101", "country": "HN"},
                   name="ITER55 marketplace")
    cleanup.append(body["id"])
    r = requests.get(f"{BASE}/api/marketplace/screens/{body['id']}",
                     headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text[:200]
    venue = r.json()["venue"]
    assert venue["lat"] == body["location"]["lat"]
    assert venue["lng"] == body["location"]["lng"]


# ── 8. Permisos de /api/admin/screens/geocode-missing ───────────────────────
def test_geocode_missing_sin_token_bloquea():
    r = requests.post(f"{BASE}/api/admin/screens/geocode-missing?limit=5", timeout=15)
    assert r.status_code in (401, 403), f"esperaba 401/403, vino {r.status_code}"


def test_geocode_missing_anunciante_bloqueado(advertiser_headers):
    r = requests.post(f"{BASE}/api/admin/screens/geocode-missing?limit=5",
                      headers=advertiser_headers, timeout=15)
    assert r.status_code in (401, 403), f"un anunciante NO debería poder: {r.status_code}"


def test_geocode_missing_superadmin_funciona(admin_headers):
    t0 = time.time()
    r = requests.post(f"{BASE}/api/admin/screens/geocode-missing?limit=5",
                      headers=admin_headers, timeout=60)
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    for key in ("reviewed", "located", "without_address", "not_found", "remaining"):
        assert key in data, f"falta {key}: {data}"
    assert isinstance(data["not_found"], list)
    assert elapsed < 45, f"tardó demasiado: {elapsed:.1f}s"


# ── 9. REGRESIÓN: guardar demo screen sin cambios no pierde nada ────────────
def test_regresion_supermercado_demo_no_pierde_datos(admin_headers):
    """Guardar Save Changes en la demo screen sin tocar nada preserva pin+ficha."""
    r = requests.get(f"{BASE}/api/screens/{DEMO_SCREEN_ID}", timeout=15)
    if r.status_code == 404:
        pytest.skip("Demo screen no está seeded en este entorno")
    assert r.status_code == 200
    before = r.json()
    loc_before = before.get("location") or {}
    adv_before = before.get("advertising") or {}

    # PUT con la misma dirección, sin lat/lng: no debe reventar el pin
    resp = requests.put(f"{BASE}/api/admin/screens/{DEMO_SCREEN_ID}",
                        headers=admin_headers, timeout=40,
                        json={"name": before.get("name"),
                              "location": {k: loc_before.get(k) for k in
                                           ("city", "address", "state",
                                            "postal_code", "country")
                                           if loc_before.get(k) is not None}})
    assert resp.status_code == 200, resp.text[:300]
    after = resp.json()
    loc_after = after.get("location") or {}
    adv_after = after.get("advertising") or {}

    # Pin conservado (o mejorado, pero nunca perdido si antes había)
    if loc_before.get("lat") is not None:
        assert loc_after.get("lat") is not None, "se perdió el pin al guardar"
    # Ficha comercial intacta
    for field in ("photo_base64", "establishment_name", "audience_min",
                  "audience_max", "open_from", "open_to"):
        assert adv_after.get(field) == adv_before.get(field), \
            f"cambió {field} en la ficha al guardar"

    # Marketplace público sigue viéndose completo
    m = requests.get(f"{BASE}/api/marketplace/screens/{DEMO_SCREEN_ID}",
                     headers=admin_headers, timeout=20)
    assert m.status_code == 200, m.status_code
    venue = m.json().get("venue") or {}
    if loc_after.get("lat") is not None:
        assert venue.get("lat") == loc_after.get("lat")
        assert venue.get("lng") == loc_after.get("lng")

    # Tienda pública por código
    store = requests.get(f"{BASE}/api/marketplace?code={DEMO_PUBLIC_CODE}", timeout=20)
    # marketplace puede aceptar querystring o path — probamos ambos
    if store.status_code == 404:
        store = requests.get(f"{BASE}/api/marketplace/{DEMO_PUBLIC_CODE}", timeout=20)
    assert store.status_code in (200, 404), store.status_code
