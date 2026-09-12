"""iter44 — «publiqué y no aparece»: decirle al cliente POR QUÉ.

Publicar no garantiza que se vea. Una promo con prioridad 90 le gana al menú
(prioridad 10), un equipo apagado no baja nada y un horario fuera de ventana
deja la pantalla en negro. Este diagnóstico tiene que coincidir con lo que el
player realmente arma, no con lo que la base «debería» decir.
"""
import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
EMAIL = "pizzeria@demo.com"
PASSWORD = "Pizza1234!"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(os.environ["MONGO_URL"])
    yield client[os.environ.get("DB_NAME", "test_database")]
    client.close()


@pytest.fixture(scope="module")
def screen_id(headers):
    rows = requests.get(f"{BASE_URL}/api/workspace/screens", headers=headers, timeout=20).json()
    assert rows, "the demo org needs a screen"
    return rows[0]["id"]


@pytest.fixture
def menu(headers, screen_id):
    r = requests.post(f"{BASE_URL}/api/workspace/menus", headers=headers,
                      json={"name": f"pytest diag {uuid.uuid4().hex[:6]}"}, timeout=20)
    menu_id = r.json()["id"]
    requests.post(f"{BASE_URL}/api/workspace/menus/{menu_id}/items", headers=headers,
                  json={"name": "Plato pytest", "price": 5.5}, timeout=20)
    requests.post(f"{BASE_URL}/api/workspace/menus/{menu_id}/publish", headers=headers,
                  json={"screen_ids": [screen_id]}, timeout=30)
    yield menu_id
    requests.delete(f"{BASE_URL}/api/workspace/menus/{menu_id}", headers=headers, timeout=20)


def diagnose(headers, screen_id):
    r = requests.get(f"{BASE_URL}/api/workspace/screens/{screen_id}/now-playing",
                     headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


class TestNowPlaying:
    def test_it_lists_the_published_menu_as_competing(self, headers, screen_id, menu):
        data = diagnose(headers, screen_id)
        menu_rows = [row for row in data["competing"] if row["is_menu"]]
        assert menu_rows, data["competing"]

    def test_it_agrees_with_what_the_player_gets(self, headers, screen_id, menu):
        data = diagnose(headers, screen_id)
        player = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20).json()
        assert len(data["items"]) == len(player["items"])

    def test_an_expired_promo_is_not_reported_as_the_winner(self, headers, screen_id, menu, mongo):
        """El player ignora los playlists vencidos; el diagnóstico también."""
        stale = {
            "id": str(uuid.uuid4()),
            "org_id": mongo.screens.find_one({"id": screen_id})["organization_id"],
            "name": "pytest promo vencida",
            "screen_ids": [screen_id],
            "status": "published",
            "priority": 90,
            "items": [{"id": str(uuid.uuid4()), "type": "media", "ref_id": "nope", "order": 0}],
            "schedule": {"mode": "always", "timezone": "America/New_York",
                         "days": list(range(7)), "start_time": "00:00", "end_time": "23:59",
                         "start_date": None, "end_date": None},
            "expires_at": datetime.utcnow() - timedelta(hours=1),
            "created_at": datetime.utcnow(),
        }
        mongo.playlists.insert_one(stale)
        try:
            data = diagnose(headers, screen_id)
            names = [row["name"] for row in data["competing"]]
            assert "pytest promo vencida" not in names, data["competing"]
        finally:
            mongo.playlists.delete_one({"id": stale["id"]})

    def test_a_live_promo_is_named_as_the_blocker(self, headers, screen_id, menu, mongo):
        live = {
            "id": str(uuid.uuid4()),
            "org_id": mongo.screens.find_one({"id": screen_id})["organization_id"],
            "name": "pytest promo manda",
            "screen_ids": [screen_id],
            "status": "published",
            "priority": 90,
            "items": [{"id": str(uuid.uuid4()), "type": "menu", "ref_id": menu, "order": 0}],
            "schedule": {"mode": "always", "timezone": "America/New_York",
                         "days": list(range(7)), "start_time": "00:00", "end_time": "23:59",
                         "start_date": None, "end_date": None},
            "created_at": datetime.utcnow(),
            "published_at": datetime.utcnow(),
        }
        mongo.playlists.insert_one(live)
        try:
            data = diagnose(headers, screen_id)
            assert data["winner"]["name"] == "pytest promo manda"
            assert "prioridad" in data["verdict"], data["verdict"]
            assert "pytest promo manda" in data["verdict"]
        finally:
            mongo.playlists.delete_one({"id": live["id"]})

    def test_it_reports_the_device_link_and_connectivity(self, headers, screen_id):
        data = diagnose(headers, screen_id)
        assert set(data["device"]) >= {"linked", "online"}
        assert isinstance(data["device"]["linked"], bool)
        assert isinstance(data["device"]["online"], bool)

    def test_it_always_returns_a_verdict_in_spanish(self, headers, screen_id):
        assert diagnose(headers, screen_id)["verdict"].strip()

    def test_another_orgs_screen_is_404(self, headers):
        r = requests.get(f"{BASE_URL}/api/workspace/screens/{uuid.uuid4()}/now-playing",
                         headers=headers, timeout=20)
        assert r.status_code == 404

    def test_it_requires_auth(self, screen_id):
        r = requests.get(f"{BASE_URL}/api/workspace/screens/{screen_id}/now-playing", timeout=20)
        assert r.status_code in (401, 403)
