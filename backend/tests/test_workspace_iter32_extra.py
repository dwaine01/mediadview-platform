"""Iter32 extra coverage — expiración de promo, cambios de precio en el
reporte semanal, weeks_ago=2, acceso de empleado, bump de versión al marcar
un producto como agotado, y promo tipo imagen."""
import os
import asyncio
from datetime import datetime, timedelta

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.environ.get("MV_BASE", "http://localhost:8001")
OWNER = ("pizzeria@demo.com", "Pizza1234!")
EMPLEADO = ("empleado@demo.com", "Empleado123!")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "mediaview_db")


# ── helpers ────────────────────────────────────────────────────────────────
def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": password}, timeout=30)
    return r


def _login_headers(email, password):
    r = _login(email, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def owner_headers():
    return _login_headers(*OWNER)


# ── Sold-out sube la versión de todas las pantallas donde se muestra ───────
def test_sold_out_bumps_screen_version(owner_headers):
    h = owner_headers
    menu = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=30).json()[0]
    item = menu["items"][1]  # usar otro item para no chocar con el baseline

    screens = requests.get(f"{BASE}/api/workspace/screens", headers=h, timeout=30).json()
    # Elegimos una pantalla que publique este menú
    target = None
    for s in screens:
        pl_ref = s.get("active_menu_id") or s.get("current_menu_id") or s.get("menu_id")
        if pl_ref == menu["id"]:
            target = s
            break
    if not target:
        pytest.skip("no hay pantalla mostrando este menú")

    v0 = requests.get(f"{BASE}/api/player/{target['id']}/version", timeout=30).json()["playlist_version"]

    try:
        r = requests.put(f"{BASE}/api/workspace/menus/{menu['id']}/items/{item['id']}",
                         headers=h, timeout=30, json={"available": False})
        assert r.status_code == 200, r.text
        v1 = requests.get(f"{BASE}/api/player/{target['id']}/version", timeout=30).json()["playlist_version"]
        assert v1 > v0, f"la versión debe subir tras agotar un producto ({v0} -> {v1})"
    finally:
        requests.put(f"{BASE}/api/workspace/menus/{menu['id']}/items/{item['id']}",
                     headers=h, timeout=30, json={"available": True})


# ── Promo tipo imagen ──────────────────────────────────────────────────────
def _pick_owner_image(headers):
    lib = requests.get(f"{BASE}/api/media?type=image", headers=headers, timeout=30)
    if lib.status_code != 200:
        return None
    for m in lib.json():
        if m.get("type") == "image" and m.get("id"):
            return m
    return None


def test_launch_image_promo(owner_headers):
    h = owner_headers
    img = _pick_owner_image(h)
    if not img:
        pytest.skip("owner no tiene imágenes en su biblioteca")
    resp = requests.post(f"{BASE}/api/workspace/promos", headers=h, timeout=60, json={
        "kind": "image", "media_id": img["id"], "duration_minutes": 15,
    })
    assert resp.status_code == 201, resp.text
    promo = resp.json()
    try:
        assert promo["kind"] == "image"
        assert promo["media_id"] == img["id"]
        # aparece en active
        active = requests.get(f"{BASE}/api/workspace/promos/active", headers=h, timeout=30).json()
        assert any(p["id"] == promo["id"] for p in active)
        # se impone en now-playing
        live = requests.get(f"{BASE}/api/workspace/now-playing", headers=h, timeout=30).json()
        playing = [s["now_playing"] for s in live if s.get("now_playing")]
        assert playing and all(p["playlist_name"] == promo["name"] for p in playing)
    finally:
        stop = requests.delete(f"{BASE}/api/workspace/promos/{promo['id']}", headers=h, timeout=30)
        assert stop.status_code == 200


# ── Promo expirada deja de reproducirse sin borrarla ───────────────────────
def test_expired_promo_disappears_from_active_and_live(owner_headers):
    h = owner_headers
    resp = requests.post(f"{BASE}/api/workspace/promos", headers=h, timeout=60, json={
        "kind": "text", "text": "Iter32 expira", "duration_minutes": 15,
    })
    assert resp.status_code == 201
    promo = resp.json()

    async def force_expire():
        client = AsyncIOMotorClient(MONGO_URL)
        try:
            db = client[DB_NAME]
            past = datetime.utcnow() - timedelta(minutes=1)
            r = await db.playlists.update_one(
                {"id": promo["id"]},
                {"$set": {"expires_at": past}},
            )
            assert r.modified_count == 1
        finally:
            client.close()

    try:
        asyncio.run(force_expire())

        active = requests.get(f"{BASE}/api/workspace/promos/active", headers=h, timeout=30).json()
        assert not any(p["id"] == promo["id"] for p in active), "expirada no debe listarse"

        live = requests.get(f"{BASE}/api/workspace/now-playing", headers=h, timeout=30).json()
        playing = [s["now_playing"] for s in live if s.get("now_playing")]
        # ninguno debe ser la promo
        assert not any(p.get("playlist_name") == promo["name"] for p in playing), \
            "promo expirada no debe seguir al aire"

        # sigue en Mongo (soft-stop) → borrarla vía API responde 200 o 404 pero no debe romper
    finally:
        requests.delete(f"{BASE}/api/workspace/promos/{promo['id']}", headers=h, timeout=30)


# ── Reporte semanal — price_changes con from/to y correo ───────────────────
def test_weekly_report_captures_price_change(owner_headers):
    h = owner_headers
    menu = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=30).json()[0]
    item = menu["items"][0]
    original_price = item.get("price")
    new_price = round(float(original_price or 10) + 1.11, 2)
    try:
        r = requests.put(f"{BASE}/api/workspace/menus/{menu['id']}/items/{item['id']}",
                         headers=h, timeout=30, json={"price": new_price})
        assert r.status_code == 200, r.text

        report = requests.get(f"{BASE}/api/workspace/reports/weekly", headers=h, timeout=30).json()
        pc = report.get("price_changes") or []
        assert isinstance(pc, list)
        match = [p for p in pc if p.get("item") == item["name"]
                 and float(p.get("to")) == new_price]
        assert match, f"debe listar el cambio de precio de {item['name']}"
        first = match[0]
        assert first.get("who") == OWNER[0]
        assert first.get("from") is not None

        # etiquetas en español para "menu_item.updated" también
        labels = {c["action"]: c["label"] for c in report.get("changes", [])}
        assert labels.get("menu_item.updated") == "Cambios en productos"
    finally:
        requests.put(f"{BASE}/api/workspace/menus/{menu['id']}/items/{item['id']}",
                     headers=h, timeout=30, json={"price": original_price})


# ── Reporte semanal — weeks_ago=2 ──────────────────────────────────────────
def test_weekly_report_weeks_ago_2(owner_headers):
    h = owner_headers
    r = requests.get(f"{BASE}/api/workspace/reports/weekly?weeks_ago=2", headers=h, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["period"]["is_current_week"] is False
    cur = requests.get(f"{BASE}/api/workspace/reports/weekly", headers=h, timeout=30).json()
    prev = requests.get(f"{BASE}/api/workspace/reports/weekly?weeks_ago=1", headers=h, timeout=30).json()
    labels = {cur["period"]["label"], prev["period"]["label"], body["period"]["label"]}
    assert len(labels) == 3, f"cada semana debe tener label único: {labels}"


# ── Reporte semanal — empleado autenticado también puede verlo ─────────────
def test_weekly_report_accessible_to_employee():
    r = _login(*EMPLEADO)
    if r.status_code != 200:
        pytest.skip(f"empleado no puede iniciar sesión ({r.status_code})")
    body = r.json()
    if body.get("must_change_password"):
        pytest.skip("empleado con contraseña temporal — sin acceso a /workspace/*")
    h = {"Authorization": f"Bearer {body['access_token']}"}
    rep = requests.get(f"{BASE}/api/workspace/reports/weekly", headers=h, timeout=30)
    assert rep.status_code == 200, rep.text
    data = rep.json()
    assert "totals" in data and "screens" in data


# ── Reporte semanal — sin token: 401/403 ───────────────────────────────────
def test_weekly_report_requires_auth():
    r = requests.get(f"{BASE}/api/workspace/reports/weekly", timeout=30)
    assert r.status_code in (401, 403)
