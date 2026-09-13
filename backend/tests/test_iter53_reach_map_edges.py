"""Iteración 53 · Casos límite del /reach y de la edición admin (Mapa + Alcance).

Complementa a `test_reach_and_map.py` y a `test_nota1_admin_advertising.py` con
los bordes que la nota específica pide y que aún no estaban cubiertos:

- weeks/days_per_week fuera de rango se recortan (nunca 500).
- weeks=0 no rompe el cálculo.
- Horarios inválidos («25:99», «mediodía») → 400 del admin.
- Coordenadas fuera de rango (lat 200, lng -400) → 400 del admin.
- Guardar 07:30/21:30 y verificar que /marketplace/screens/{id} lo devuelve y
  que /reach usa el horario nuevo. Restaurar 07:00/21:00 + coords originales.

Ejecución:
    cd /app/backend && python -m pytest tests/test_iter53_reach_map_edges.py -q
"""
import os

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL") or os.environ["EXPO_PUBLIC_BACKEND_URL"]
ADVERTISER = ("anunciante@demo.com", "Anuncio1234!")
SUPERADMIN = ("superadmin@mediadview.com", "SuperAdmin#2026")
DEMO_CODE = "MV-ADV-FJUSIW"  # supermercado 07:00–21:00, 800–1.200
ORIGINAL_LAT, ORIGINAL_LNG = 14.0998, -87.2043
ORIGINAL_OPEN_FROM, ORIGINAL_OPEN_TO = "07:00", "21:00"


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} → {r.status_code} {r.text[:200]}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def adv_headers():
    return _login(*ADVERTISER)


@pytest.fixture(scope="module")
def admin_headers():
    return _login(*SUPERADMIN)


@pytest.fixture(scope="module")
def demo_screen(adv_headers):
    r = requests.get(f"{BASE}/api/marketplace/screens",
                     params={"here": DEMO_CODE}, headers=adv_headers, timeout=30)
    assert r.status_code == 200
    target = next(s for s in r.json() if s["public_screen_code"] == DEMO_CODE)
    return target


# ── 1) Recorte de weeks/days_per_week sin 500 ─────────────────────────────
def test_weeks_cero_se_acota_sin_500(adv_headers, demo_screen):
    r = requests.post(
        f"{BASE}/api/marketplace/screens/{demo_screen['id']}/reach",
        json={"start_time": "17:00", "end_time": "20:00",
              "days_per_week": 5, "weeks": 0, "slot_seconds": 30},
        headers=adv_headers, timeout=20,
    )
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    # Se acota a mínimo 1 semana
    assert data["weeks"] >= 1
    assert data["days_total"] >= 1
    assert data["reach_total"] > 0


def test_days_per_week_99_se_acota_a_7(adv_headers, demo_screen):
    r = requests.post(
        f"{BASE}/api/marketplace/screens/{demo_screen['id']}/reach",
        json={"start_time": "17:00", "end_time": "20:00",
              "days_per_week": 99, "weeks": 4, "slot_seconds": 30},
        headers=adv_headers, timeout=20,
    )
    assert r.status_code == 200, r.text[:200]
    assert r.json()["days_per_week"] == 7


def test_slot_seconds_extremo_se_acota(adv_headers, demo_screen):
    r = requests.post(
        f"{BASE}/api/marketplace/screens/{demo_screen['id']}/reach",
        json={"start_time": "17:00", "end_time": "20:00",
              "days_per_week": 5, "weeks": 4, "slot_seconds": 9999},
        headers=adv_headers, timeout=20,
    )
    assert r.status_code == 200
    assert 5 <= r.json()["slot_seconds"] <= 120


# ── 2) Sin token → 401/403 ────────────────────────────────────────────────
def test_reach_sin_token_bloquea(demo_screen):
    r = requests.post(
        f"{BASE}/api/marketplace/screens/{demo_screen['id']}/reach",
        json={"weeks": 4}, timeout=20,
    )
    assert r.status_code in (401, 403)


# ── 3) Franja vacía (22:00–22:00) devuelve 0, no un 500 ───────────────────
def test_franja_vacia_no_rompe(adv_headers, demo_screen):
    r = requests.post(
        f"{BASE}/api/marketplace/screens/{demo_screen['id']}/reach",
        json={"start_time": "22:00", "end_time": "22:00",
              "days_per_week": 5, "weeks": 4, "slot_seconds": 30},
        headers=adv_headers, timeout=20,
    )
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert data["hours_selected"] == 0
    assert data["reach_per_day"] == 0
    assert data["reach_total"] == 0


# ── 4) Pantalla sin tráfico cargado → 400 con 'tráfico' ───────────────────
def test_pantalla_sin_trafico_devuelve_400(adv_headers):
    r = requests.get(f"{BASE}/api/marketplace/screens",
                     headers=adv_headers, timeout=30)
    assert r.status_code == 200
    sin_datos = [s for s in r.json()
                 if not (s["venue"].get("audience") or {}).get("label")]
    if not sin_datos:
        pytest.skip("todas las pantallas del catálogo tienen tráfico cargado")
    resp = requests.post(
        f"{BASE}/api/marketplace/screens/{sin_datos[0]['id']}/reach",
        json={"start_time": "10:00", "end_time": "12:00",
              "days_per_week": 5, "weeks": 4, "slot_seconds": 30},
        headers=adv_headers, timeout=20,
    )
    assert resp.status_code == 400
    assert "tráfico" in resp.json()["detail"].lower()


# ── 5) Admin PUT: horario inválido → 400 ─────────────────────────────────
def test_admin_horario_25_99_devuelve_400(admin_headers, demo_screen):
    r = requests.put(
        f"{BASE}/api/admin/screens/{demo_screen['id']}/advertising",
        json={"open_from": "25:99", "open_to": "21:00"},
        headers=admin_headers, timeout=20,
    )
    assert r.status_code == 400
    assert "horario" in r.json()["detail"].lower()


def test_admin_horario_mediodia_texto_devuelve_400(admin_headers, demo_screen):
    r = requests.put(
        f"{BASE}/api/admin/screens/{demo_screen['id']}/advertising",
        json={"open_from": "mediodía", "open_to": "21:00"},
        headers=admin_headers, timeout=20,
    )
    assert r.status_code == 400


# ── 6) Admin PUT: coordenadas fuera de rango → 400 ────────────────────────
def test_admin_lat_200_devuelve_400(admin_headers, demo_screen):
    r = requests.put(
        f"{BASE}/api/admin/screens/{demo_screen['id']}/advertising",
        json={"lat": 200.0}, headers=admin_headers, timeout=20,
    )
    assert r.status_code == 400
    assert "latitud" in r.json()["detail"].lower()


def test_admin_lng_menos_400_devuelve_400(admin_headers, demo_screen):
    r = requests.put(
        f"{BASE}/api/admin/screens/{demo_screen['id']}/advertising",
        json={"lng": -400.0}, headers=admin_headers, timeout=20,
    )
    assert r.status_code == 400
    assert "longitud" in r.json()["detail"].lower()


# ── 7) Admin PUT: guardar 07:30/21:30 + coords y verificar propagación ────
def test_admin_guarda_nuevo_horario_y_coords_y_reach_los_usa(
    admin_headers, adv_headers, demo_screen,
):
    new_lat, new_lng = 14.1010, -87.2050
    r = requests.put(
        f"{BASE}/api/admin/screens/{demo_screen['id']}/advertising",
        json={"open_from": "07:30", "open_to": "21:30",
              "lat": new_lat, "lng": new_lng},
        headers=admin_headers, timeout=20,
    )
    assert r.status_code == 200, r.text[:200]

    # GET marketplace/screens/{id} devuelve venue actualizado
    detail = requests.get(
        f"{BASE}/api/marketplace/screens/{demo_screen['id']}",
        headers=adv_headers, timeout=20,
    ).json()
    v = detail["venue"]
    assert v["open_from"] == "07:30"
    assert v["open_to"] == "21:30"
    assert v["hours_label"] == "07:30 a 21:30"
    assert v["hours_are_default"] is False
    assert abs(v["lat"] - new_lat) < 1e-6
    assert abs(v["lng"] - new_lng) < 1e-6

    # /reach: hours_open ahora es 14.0 (21:30 - 07:30 = 14h). Antes también daba
    # 14 con 07:00–21:00, así que probamos con una franja que sólo tiene sentido
    # con el horario nuevo: 07:00–07:30 se recorta a 07:30–07:30 = 0h.
    reach = requests.post(
        f"{BASE}/api/marketplace/screens/{demo_screen['id']}/reach",
        json={"start_time": "07:00", "end_time": "07:30",
              "days_per_week": 5, "weeks": 4, "slot_seconds": 30},
        headers=adv_headers, timeout=20,
    ).json()
    assert reach["hours_open"] == 14.0
    assert reach["hours_selected"] == 0  # se recortó al horario nuevo
    assert reach["venue_hours"] == {"from": "07:30", "to": "21:30"}


# ── 8) Restaurar estado original (corre al final por orden alfabético) ────
def test_zzz_restore_estado_original(admin_headers, demo_screen):
    r = requests.put(
        f"{BASE}/api/admin/screens/{demo_screen['id']}/advertising",
        json={"open_from": ORIGINAL_OPEN_FROM, "open_to": ORIGINAL_OPEN_TO,
              "lat": ORIGINAL_LAT, "lng": ORIGINAL_LNG},
        headers=admin_headers, timeout=20,
    )
    assert r.status_code == 200
