"""P0 player contracts: diagnostics command handshake and playlist display_mode normalization."""

import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_ENV = BACKEND_DIR.parent / "frontend" / ".env"


def _public_base_url() -> str:
    env = dotenv_values(FRONTEND_ENV)
    base_url = (
        os.environ.get("TEST_BASE_URL")
        or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
        or env.get("EXPO_PUBLIC_BACKEND_URL")
    )
    if not base_url:
        pytest.fail("TEST_BASE_URL/EXPO_PUBLIC_BACKEND_URL is missing")
    return base_url.rstrip("/")


BASE_URL = _public_base_url()
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture
def api_session():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def mongo_db():
    if not MONGO_URL or not DB_NAME:
        pytest.fail("MONGO_URL/DB_NAME missing in environment")
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        yield db
    finally:
        client.close()


@pytest.fixture
def admin_session(api_session):
    # auth module: superadmin login for protected admin routes
    email = "superadmin@mediadview.com"
    password = "SuperAdmin#2026"
    login = api_session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )
    if login.status_code != 200:
        pytest.skip(f"superadmin login unavailable: {login.status_code}")
    token = login.json().get("access_token")
    api_session.headers.update({"Authorization": f"Bearer {token}"})
    return api_session


@pytest.mark.parametrize("command", ["show_diagnostics", "hide_diagnostics"])
def test_admin_command_roundtrip_through_heartbeat(admin_session, api_session, mongo_db, command):
    # player commands module: command accepted + returned exactly once in heartbeat
    suffix = uuid.uuid4().hex[:10]
    device_id = f"TEST-p0-command-{suffix}"
    screen_id = f"TEST-p0-command-screen-{suffix}"
    mongo_db.devices.insert_one({"id": device_id, "screen_id": screen_id, "status": "active"})
    try:
        cmd_response = admin_session.put(
            f"{BASE_URL}/api/admin/devices/{device_id}/command",
            params={"command": command},
            timeout=20,
        )
        assert cmd_response.status_code == 200, cmd_response.text

        heartbeat_first = api_session.post(
            f"{BASE_URL}/api/devices/{device_id}/heartbeat",
            json={"status": "online", "screen_id": screen_id, "device_id": device_id},
            timeout=20,
        )
        assert heartbeat_first.status_code == 200, heartbeat_first.text
        assert heartbeat_first.json().get("command") == command

        heartbeat_second = api_session.post(
            f"{BASE_URL}/api/devices/{device_id}/heartbeat",
            json={"status": "online", "screen_id": screen_id, "device_id": device_id},
            timeout=20,
        )
        assert heartbeat_second.status_code == 200
        assert "command" not in heartbeat_second.json()
    finally:
        mongo_db.devices.delete_many({"id": device_id})


def test_playlist_display_mode_is_normalized_and_delivered_as_cover(admin_session, api_session, mongo_db):
    # playlist/player module: invalid display_mode -> cover, then delivered to device playlist contract
    suffix = uuid.uuid4().hex[:10]
    menu_id = None
    playlist_id = None
    screen_id = f"TEST-p0-screen-{suffix}"
    device_id = f"TEST-p0-device-{suffix}"

    mongo_db.screens.insert_one({
        "id": screen_id,
        "name": "TEST P0 Screen",
        "status": "active",
        "location": {"city": "Columbus", "state": "OH"},
        "specs": {"resolution": "1920x1080"},
        "playlist_version": 0,
    })
    mongo_db.devices.insert_one({"id": device_id, "screen_id": screen_id, "status": "active"})

    try:
        menu = admin_session.post(
            f"{BASE_URL}/api/menus",
            json={
                "name": f"TEST P0 Menu {suffix}",
                "template_id": "classic",
                "restaurant_name": "TEST Restaurant",
            },
            timeout=20,
        )
        assert menu.status_code == 200, menu.text
        menu_id = menu.json()["id"]

        created = admin_session.post(
            f"{BASE_URL}/api/playlists",
            json={
                "name": f"TEST P0 Playlist {suffix}",
                "items": [{
                    "type": "menu",
                    "ref_id": menu_id,
                    "title": "P0 Menu",
                    "duration": 60,
                    "display_mode": "contain",
                }],
            },
            timeout=20,
        )
        assert created.status_code == 200, created.text
        playlist_id = created.json()["id"]

        updated = admin_session.put(
            f"{BASE_URL}/api/playlists/{playlist_id}",
            json={"items": [{
                "id": created.json()["items"][0]["id"],
                "type": "menu",
                "ref_id": menu_id,
                "title": "P0 Menu",
                "duration": 60,
                "display_mode": "INVALID_MODE",
            }]},
            timeout=20,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["items"][0]["display_mode"] == "cover"

        published = admin_session.post(
            f"{BASE_URL}/api/playlists/{playlist_id}/publish",
            json={"screen_ids": [screen_id], "schedule": {"mode": "always"}, "priority": 50},
            timeout=20,
        )
        assert published.status_code == 200, published.text

        device_playlist = api_session.get(
            f"{BASE_URL}/api/devices/{device_id}/playlist",
            timeout=20,
        )
        assert device_playlist.status_code == 200, device_playlist.text
        payload = device_playlist.json()
        assert payload["total_items"] >= 1
        assert payload["items"][0]["display_mode"] == "cover"
    finally:
        if playlist_id:
            mongo_db.playlists.delete_many({"id": playlist_id})
        if menu_id:
            mongo_db.menus.delete_many({"id": menu_id})
        mongo_db.devices.delete_many({"id": device_id})
        mongo_db.screens.delete_many({"id": screen_id})
