"""Nota #1 — validaciones del PUT admin de la ficha comercial.

Cubre lo que test_nota1_venue_detail.py NO cubre: que el superadmin pueda
guardar los campos nuevos de la ficha (establishment_name, location_reference,
audiencia) y que el servidor rechace audiencia negativa o min>max. Se
restaura el estado original al final para no ensuciar la demo.

    cd /app/backend && python -m pytest tests/test_nota1_admin_advertising.py -q
"""
import os
import copy

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL") or os.environ["EXPO_PUBLIC_BACKEND_URL"]
SUPERADMIN = ("superadmin@mediadview.com", "SuperAdmin#2026")
ADVERTISER = ("anunciante@demo.com", "Anuncio1234!")
DEMO_CODE = "MV-ADV-FJUSIW"  # Supermercado La Colonia


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(*SUPERADMIN)}"}


@pytest.fixture(scope="module")
def advertiser_headers():
    return {"Authorization": f"Bearer {_login(*ADVERTISER)}"}


@pytest.fixture(scope="module")
def screen_id(advertiser_headers):
    r = requests.get(f"{BASE}/api/marketplace/screens",
                     params={"here": DEMO_CODE},
                     headers=advertiser_headers, timeout=20)
    assert r.status_code == 200
    screens = r.json()
    assert screens and screens[0]["is_here"]
    return screens[0]["id"]


@pytest.fixture(scope="module")
def original_advertising(admin_headers, screen_id):
    """Snapshot the current advertising doc so we can restore it after the run."""
    r = requests.get(f"{BASE}/api/screens/{screen_id}",
                     headers=admin_headers, timeout=20)
    assert r.status_code == 200
    return copy.deepcopy(r.json().get("advertising") or {})


def test_admin_can_save_venue_fields_and_they_reach_the_marketplace(
        admin_headers, advertiser_headers, screen_id, original_advertising):
    payload = {
        "establishment_name": "TEST_ADMIN Supermercado La Colonia",
        "location_reference": "TEST_ADMIN Nueva referencia de prueba",
        "audience_min": 900,
        "audience_max": 1500,
        "audience_note": "TEST_ADMIN Nota de audiencia",
    }
    r = requests.put(f"{BASE}/api/admin/screens/{screen_id}/advertising",
                     json=payload, headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text[:300]
    adv = r.json()["advertising"]
    for k, v in payload.items():
        assert adv[k] == v, f"admin PUT no guardó {k}: got {adv.get(k)!r}"

    # Verify it reflects in the advertiser-facing marketplace detail
    detail = requests.get(f"{BASE}/api/marketplace/screens/{screen_id}",
                          headers=advertiser_headers, timeout=20).json()
    v = detail["venue"]
    assert v["establishment_name"] == payload["establishment_name"]
    assert v["reference"] == payload["location_reference"]
    assert v["audience"]["min"] == 900 and v["audience"]["max"] == 1500
    assert "900" in v["audience"]["label"] and "1.500" in v["audience"]["label"]


def test_audience_min_greater_than_max_returns_400(admin_headers, screen_id):
    r = requests.put(f"{BASE}/api/admin/screens/{screen_id}/advertising",
                     json={"audience_min": 2000, "audience_max": 500},
                     headers=admin_headers, timeout=20)
    assert r.status_code == 400, f"debía rechazar min>max: {r.status_code} {r.text[:200]}"


def test_negative_audience_returns_400(admin_headers, screen_id):
    r = requests.put(f"{BASE}/api/admin/screens/{screen_id}/advertising",
                     json={"audience_min": -10},
                     headers=admin_headers, timeout=20)
    assert r.status_code == 400, r.text[:200]

    r = requests.put(f"{BASE}/api/admin/screens/{screen_id}/advertising",
                     json={"audience_max": -1},
                     headers=admin_headers, timeout=20)
    assert r.status_code == 400, r.text[:200]


def test_advertiser_cannot_hit_admin_endpoint(advertiser_headers, screen_id):
    r = requests.put(f"{BASE}/api/admin/screens/{screen_id}/advertising",
                     json={"establishment_name": "hack"},
                     headers=advertiser_headers, timeout=20)
    assert r.status_code in (401, 403), r.status_code


def test_zzz_restore_original_state(admin_headers, screen_id, original_advertising):
    """Corre al final (nombre alfabético): deja la pantalla como estaba."""
    restore = {
        "establishment_name": original_advertising.get("establishment_name") or "Supermercado La Colonia",
        "location_reference": original_advertising.get("location_reference") or "Frente al parque central, entrando por la calle peatonal",
        "audience_min": original_advertising.get("audience_min", 800),
        "audience_max": original_advertising.get("audience_max", 1200),
        "audience_note": original_advertising.get("audience_note") or "Mayor tráfico de 5 a 8 pm y los sábados todo el día",
    }
    r = requests.put(f"{BASE}/api/admin/screens/{screen_id}/advertising",
                     json=restore, headers=admin_headers, timeout=20)
    assert r.status_code == 200
