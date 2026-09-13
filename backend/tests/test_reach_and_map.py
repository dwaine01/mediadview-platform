"""Mapa por zona y alcance estimado: las dos cosas que el anunciante mira.

El mapa necesita coordenadas y horario en la ficha; el alcance necesita que la
cuenta sea consistente y explicable. Los dos salen de los mismos datos que el
panel ya guarda, así que lo que se prueba es que esos datos lleguen completos y
que la aritmética no invente audiencia.

    cd /app/backend && python -m pytest tests/test_reach_and_map.py -q
"""
import os

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL") or os.environ["EXPO_PUBLIC_BACKEND_URL"]
ADVERTISER = ("anunciante@demo.com", "Anuncio1234!")
DEMO_CODE = "MV-ADV-FJUSIW"      # Supermercado: 800–1.200 personas/día, abre 07:00–21:00


@pytest.fixture(scope="module")
def headers():
    response = requests.post(f"{BASE}/api/auth/login",
                             json={"email": ADVERTISER[0], "password": ADVERTISER[1]},
                             timeout=20)
    assert response.status_code == 200, response.text[:200]
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def demo(headers):
    response = requests.get(f"{BASE}/api/marketplace/screens",
                            params={"here": DEMO_CODE}, headers=headers, timeout=30)
    assert response.status_code == 200
    screens = response.json()
    target = next(s for s in screens if s["public_screen_code"] == DEMO_CODE)
    return screens, target


def reach(headers, screen_id, **kwargs):
    body = {"start_time": "17:00", "end_time": "20:00", "days_per_week": 5,
            "weeks": 4, "slot_seconds": 30}
    body.update(kwargs)
    response = requests.post(f"{BASE}/api/marketplace/screens/{screen_id}/reach",
                             json=body, headers=headers, timeout=20)
    return response


# ── Mapa ──────────────────────────────────────────────────────────────────
def test_las_pantallas_de_demo_estan_en_el_mapa(demo):
    _screens, target = demo
    venue = target["venue"]
    assert -90 <= venue["lat"] <= 90 and -180 <= venue["lng"] <= 180
    assert venue["open_from"] and venue["open_to"] and venue["hours_label"]
    assert venue["hours_are_default"] is False, "el horario tiene que ser el real del local"


def test_el_mapa_puede_dibujar_casi_todo_el_catalogo(demo):
    screens, _target = demo
    con_mapa = [s for s in screens if s["venue"]["lat"] is not None]
    assert len(con_mapa) >= 4, "sin coordenadas no hay mapa que mostrar"


# ── Alcance ───────────────────────────────────────────────────────────────
def test_el_alcance_sale_de_la_franja_elegida(headers, demo):
    _screens, target = demo
    data = reach(headers, target["id"]).json()
    assert data["people_per_day_venue"] == 1000          # promedio de 800–1.200
    assert data["hours_open"] == 14.0                    # 07:00 a 21:00
    assert data["hours_selected"] == 3.0                 # 17:00 a 20:00
    assert data["days_total"] == 20                      # 5 días × 4 semanas
    assert data["reach_per_day"] == round(1000 * 3 / 14)
    assert data["reach_total"] == data["reach_per_day"] * 20
    assert data["plays_per_hour"] >= 1 and data["plays_per_day"] >= 1
    assert "estimación" in data["note"].lower()


def test_mas_horas_nunca_da_menos_gente(headers, demo):
    _screens, target = demo
    corto = reach(headers, target["id"], start_time="17:00", end_time="18:00").json()
    largo = reach(headers, target["id"], start_time="17:00", end_time="21:00").json()
    assert largo["reach_per_day"] > corto["reach_per_day"]


def test_la_franja_se_recorta_al_horario_del_local(headers, demo):
    """Pedir de 00:00 a 23:00 no puede inventar gente fuera del horario."""
    _screens, target = demo
    data = reach(headers, target["id"], start_time="00:00", end_time="23:00").json()
    assert data["hours_selected"] == data["hours_open"]
    assert data["reach_per_day"] == data["people_per_day_venue"]
    assert data["window"]["clipped"] is True


def test_el_alcance_exige_sesion(demo):
    _screens, target = demo
    response = requests.post(f"{BASE}/api/marketplace/screens/{target['id']}/reach",
                             json={"weeks": 4}, timeout=20)
    assert response.status_code in (401, 403)


def test_sin_trafico_cargado_no_se_inventa_un_numero(headers, demo):
    screens, _target = demo
    sin_datos = [s for s in screens if not (s["venue"]["audience"] or {}).get("label")]
    if not sin_datos:
        pytest.skip("todas las pantallas tienen tráfico cargado")
    response = reach(headers, sin_datos[0]["id"])
    assert response.status_code == 400
    assert "tráfico" in response.json()["detail"].lower()
