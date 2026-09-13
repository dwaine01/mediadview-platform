"""De la dirección al pin: el que instala una pantalla no sabe su latitud.

Lo que se prueba es la promesa: se carga calle, ciudad y código postal y la
pantalla aparece en el mapa del anunciante sin que nadie toque coordenadas. Y
lo que no se debe romper: una dirección que no existe no impide guardar, y
mudar la pantalla mueve el pin en vez de dejarlo en la esquina vieja.

    cd /app/backend && python -m pytest tests/test_screen_geocoding.py -q
"""
import os

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL") or os.environ["EXPO_PUBLIC_BACKEND_URL"]
ADMIN = ("superadmin@mediadview.com", "SuperAdmin#2026")

BASE_SCREEN = {
    "pricing": {"per_month": 300, "per_day": 10, "per_hour": 1, "per_slot": 1,
                "currency": "USD"},
    "specs": {"size": "55\"", "type": "LED", "resolution": "1920x1080",
              "orientation": "landscape"},
    "status": "active", "operation_type": "PUBLIC_ADVERTISING",
    "price_per_month": 300, "max_ad_slots": 4,
}


@pytest.fixture(scope="module")
def headers():
    response = requests.post(f"{BASE}/api/auth/login",
                             json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=20)
    assert response.status_code == 200, response.text[:200]
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def screen(headers):
    """Crea una pantalla de prueba y la borra al terminar."""
    created = []

    def make(location, name="GEO TEST pantalla"):
        response = requests.post(f"{BASE}/api/admin/screens", headers=headers, timeout=40,
                                 json={**BASE_SCREEN, "name": name,
                                       "description": "prueba de geocodificación",
                                       "location": location})
        assert response.status_code == 200, response.text[:300]
        body = response.json()
        created.append(body["id"])
        return body

    yield make
    for screen_id in created:
        requests.delete(f"{BASE}/api/admin/screens/{screen_id}?cascade=true",
                        headers=headers, timeout=20)


def test_la_direccion_con_codigo_postal_pone_el_pin_sola(screen):
    body = screen({"city": "Tegucigalpa", "address": "Avenida Miguel de Cervantes",
                   "state": "Francisco Morazan", "postal_code": "11101", "country": "HN"})
    location = body["location"]
    assert location["lat"] is not None and location["lng"] is not None, \
        "la pantalla quedó sin ubicación en el mapa"
    assert 13 < location["lat"] < 16 and -90 < location["lng"] < -85, \
        f"el pin cayó fuera de Honduras: {location['lat']}, {location['lng']}"
    assert location["geocoded_from"]


def test_una_direccion_inventada_no_impide_guardar(screen):
    body = screen({"city": "Nowhereville", "address": "Calle inexistente xyzq 999",
                   "postal_code": "", "country": "HN"}, name="GEO TEST sin ubicar")
    assert body["id"]
    assert body["location"].get("lat") is None, "no debería inventar un pin"


def test_mudar_la_pantalla_mueve_el_pin(headers, screen):
    body = screen({"city": "Tegucigalpa", "address": "Avenida Miguel de Cervantes",
                   "postal_code": "11101", "country": "HN"}, name="GEO TEST mudanza")
    before = (body["location"]["lat"], body["location"]["lng"])
    response = requests.put(f"{BASE}/api/admin/screens/{body['id']}", headers=headers,
                            timeout=40,
                            json={"location": {"city": "San Pedro Sula",
                                               "address": "3 Avenida, Barrio Guamilito",
                                               "postal_code": "21102", "country": "HN"}})
    assert response.status_code == 200, response.text[:200]
    after_location = response.json()["location"]
    after = (after_location["lat"], after_location["lng"])
    assert after[0] is not None
    assert after != before, "el pin quedó en la dirección vieja"
    assert 15 < after[0] < 16, f"San Pedro Sula está en otra latitud: {after[0]}"


def test_las_coordenadas_a_mano_ganan(headers, screen):
    """Si el dueño corrige el pin a mano, el buscador no se lo pisa."""
    body = screen({"city": "Tegucigalpa", "address": "Avenida Miguel de Cervantes",
                   "postal_code": "11101", "country": "HN"}, name="GEO TEST manual")
    response = requests.put(f"{BASE}/api/admin/screens/{body['id']}", headers=headers,
                            timeout=40,
                            json={"location": {"city": "Tegucigalpa",
                                               "address": "Avenida Miguel de Cervantes",
                                               "postal_code": "11101", "country": "HN",
                                               "lat": 14.5, "lng": -87.5}})
    assert response.status_code == 200
    location = response.json()["location"]
    assert (location["lat"], location["lng"]) == (14.5, -87.5)


def test_el_pin_llega_hasta_el_mapa_del_anunciante(headers, screen):
    body = screen({"city": "Tegucigalpa", "address": "Avenida Miguel de Cervantes",
                   "postal_code": "11101", "country": "HN"}, name="GEO TEST catalogo")
    response = requests.get(f"{BASE}/api/marketplace/screens/{body['id']}",
                            headers=headers, timeout=20)
    assert response.status_code == 200, response.text[:200]
    venue = response.json()["venue"]
    assert venue["lat"] == body["location"]["lat"]
    assert venue["lng"] == body["location"]["lng"]
