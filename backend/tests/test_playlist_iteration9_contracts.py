"""Iteration 9 regression: playlists scheduling/realtime/versioning/auth contracts."""

import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["TEST_BASE_URL"].rstrip("/")
TEST_EMAIL = os.environ.get("TEST_SUPERADMIN_EMAIL", "superadmin@mediadview.com")
TEST_PASSWORD = os.environ.get("TEST_SUPERADMIN_PASSWORD", "SuperAdmin#2026")


@pytest.fixture
def session():
    """Auth/login + API session for protected playlist and menu flows."""
    s = requests.Session()
    login = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=20,
    )
    if login.status_code != 200:
        pytest.skip(f"superadmin login unavailable: {login.status_code}")
    s.headers.update(
        {
            "Authorization": f"Bearer {login.json()['access_token']}",
            "Content-Type": "application/json",
        }
    )
    return s


@pytest.fixture
def mongo_db():
    """Mongo fixture for test data setup/teardown and heartbeat manipulation."""
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    try:
        yield db
    finally:
        client.close()


def test_sse_screen_endpoint_returns_connected_event():
    """Realtime SSE channel contract: must return text/event-stream + connected event."""
    screen_id = f"TEST-sse-{uuid.uuid4().hex[:8]}"
    with requests.get(
        f"{BASE_URL}/api/events/screen/{screen_id}",
        stream=True,
        timeout=(10, 30),
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in (response.headers.get("content-type") or "")
        lines = []
        for raw in response.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            lines.append(raw)
            if raw == "":
                break
            if len(lines) > 10:
                break
        assert any(line.strip() == "event: connected" for line in lines)


def test_playlist_publish_schedule_versions_delivery_and_menu_delete_block(session, mongo_db):
    """Playlist CRUD/scheduling/version bump + delivery heartbeat + menu dependency block."""
    suffix = uuid.uuid4().hex[:8]
    screen_id = f"TEST-pl-screen-{suffix}"
    device_id = f"TEST-pl-device-{suffix}"
    menu_id = None
    playlist_id = None

    mongo_db.screens.insert_one(
        {
            "id": screen_id,
            "name": f"TEST Screen {suffix}",
            "status": "active",
            "location": {"city": "Austin", "state": "TX"},
            "specs": {"resolution": "1920x1080"},
            "playlist_version": 0,
        }
    )
    mongo_db.devices.insert_one(
        {
            "id": device_id,
            "screen_id": screen_id,
            "status": "active",
            "last_heartbeat": datetime.utcnow(),
        }
    )

    try:
        menu = session.post(
            f"{BASE_URL}/api/menus",
            json={
                "name": f"TEST_Menu_{suffix}",
                "template_id": "classic",
                "restaurant_name": "TEST Restaurant",
            },
            timeout=20,
        )
        assert menu.status_code == 200, menu.text
        menu_id = menu.json()["id"]

        create_playlist = session.post(
            f"{BASE_URL}/api/playlists",
            json={
                "name": f"TEST_Playlist_{suffix}",
                "items": [
                    {
                        "type": "menu",
                        "ref_id": menu_id,
                        "title": "Menu",
                        "duration": 60,
                    }
                ],
            },
            timeout=20,
        )
        assert create_playlist.status_code == 200, create_playlist.text
        playlist_id = create_playlist.json()["id"]

        before_publish = mongo_db.screens.find_one({"id": screen_id})["playlist_version"]
        publish = session.post(
            f"{BASE_URL}/api/playlists/{playlist_id}/publish",
            json={
                "screen_ids": [screen_id],
                "priority": 77,
                "schedule": {
                    "mode": "scheduled",
                    "timezone": "America/Mexico_City",
                    "days": [1, 3, 5],
                    "start_time": "08:00",
                    "end_time": "20:00",
                    "start_date": "2026-01-10",
                    "end_date": "2026-02-10",
                },
            },
            timeout=20,
        )
        assert publish.status_code == 200, publish.text

        after_publish = mongo_db.screens.find_one({"id": screen_id})["playlist_version"]
        assert after_publish == before_publish + 1

        get_playlist = session.get(f"{BASE_URL}/api/playlists/{playlist_id}", timeout=20)
        assert get_playlist.status_code == 200
        payload = get_playlist.json()
        assert payload["priority"] == 77
        assert payload["schedule"]["mode"] == "scheduled"
        assert payload["schedule"]["timezone"] == "America/Mexico_City"
        assert payload["schedule"]["days"] == [1, 3, 5]
        assert payload["schedule"]["start_date"] == "2026-01-10"
        assert payload["schedule"]["end_date"] == "2026-02-10"

        online = session.get(f"{BASE_URL}/api/playlists/{playlist_id}/delivery-status", timeout=20)
        assert online.status_code == 200, online.text
        assert online.json()[0]["device_status"] == "online"

        mongo_db.devices.update_one(
            {"id": device_id},
            {"$set": {"last_heartbeat": datetime.utcnow() - timedelta(minutes=5)}},
        )
        offline = session.get(f"{BASE_URL}/api/playlists/{playlist_id}/delivery-status", timeout=20)
        assert offline.status_code == 200
        assert offline.json()[0]["device_status"] == "offline"

        before_update = mongo_db.screens.find_one({"id": screen_id})["playlist_version"]
        update_playlist = session.put(
            f"{BASE_URL}/api/playlists/{playlist_id}",
            json={
                "items": [
                    {
                        "type": "menu",
                        "ref_id": menu_id,
                        "title": "Menu Updated",
                        "duration": 90,
                    }
                ]
            },
            timeout=20,
        )
        assert update_playlist.status_code == 200, update_playlist.text
        after_update = mongo_db.screens.find_one({"id": screen_id})["playlist_version"]
        assert after_update == before_update + 1

        playlist_version_before_menu_edit = (
            mongo_db.playlists.find_one({"id": playlist_id}, {"version": 1})["version"]
        )
        screen_version_before_menu_edit = mongo_db.screens.find_one({"id": screen_id})["playlist_version"]
        menu_edit = session.put(
            f"{BASE_URL}/api/menus/{menu_id}",
            json={"subtitle": "TEST update triggers playlist version bump"},
            timeout=20,
        )
        assert menu_edit.status_code == 200, menu_edit.text
        playlist_version_after_menu_edit = (
            mongo_db.playlists.find_one({"id": playlist_id}, {"version": 1})["version"]
        )
        assert playlist_version_after_menu_edit == playlist_version_before_menu_edit + 1
        screen_version_after_menu_edit = mongo_db.screens.find_one({"id": screen_id})["playlist_version"]
        assert screen_version_after_menu_edit == screen_version_before_menu_edit + 1

        blocked = session.delete(f"{BASE_URL}/api/menus/{menu_id}", timeout=20)
        assert blocked.status_code == 409
        assert isinstance(blocked.json().get("detail"), dict)
        used_by = blocked.json()["detail"].get("used_by") or []
        assert any(row.get("id") == playlist_id for row in used_by)

        before_delete = mongo_db.screens.find_one({"id": screen_id})["playlist_version"]
        delete_playlist = session.delete(f"{BASE_URL}/api/playlists/{playlist_id}", timeout=20)
        assert delete_playlist.status_code == 200, delete_playlist.text
        after_delete = mongo_db.screens.find_one({"id": screen_id})["playlist_version"]
        assert after_delete == before_delete + 1

    finally:
        if playlist_id:
            mongo_db.playlists.delete_many({"id": playlist_id})
        if menu_id:
            mongo_db.menus.delete_many({"id": menu_id})
        mongo_db.devices.delete_many({"id": device_id})
        mongo_db.screens.delete_many({"id": screen_id})


def test_publish_to_multiple_screens_bumps_each_version(session, mongo_db):
    """Publish to many screens: response includes all assignments and bumps all versions."""
    suffix = uuid.uuid4().hex[:8]
    screen_a = f"TEST-pl-multi-a-{suffix}"
    screen_b = f"TEST-pl-multi-b-{suffix}"
    menu_id = None
    playlist_id = None

    mongo_db.screens.insert_many(
        [
            {
                "id": screen_a,
                "name": f"TEST Screen A {suffix}",
                "status": "active",
                "location": {"city": "Dallas", "state": "TX"},
                "specs": {"resolution": "1920x1080"},
                "playlist_version": 0,
            },
            {
                "id": screen_b,
                "name": f"TEST Screen B {suffix}",
                "status": "active",
                "location": {"city": "Houston", "state": "TX"},
                "specs": {"resolution": "1920x1080"},
                "playlist_version": 0,
            },
        ]
    )
    try:
        menu = session.post(
            f"{BASE_URL}/api/menus",
            json={
                "name": f"TEST_Menu_multi_{suffix}",
                "template_id": "classic",
                "restaurant_name": "TEST Multi",
            },
            timeout=20,
        )
        assert menu.status_code == 200, menu.text
        menu_id = menu.json()["id"]

        playlist = session.post(
            f"{BASE_URL}/api/playlists",
            json={
                "name": f"TEST_Playlist_multi_{suffix}",
                "items": [{"type": "menu", "ref_id": menu_id, "title": "Menu", "duration": 45}],
            },
            timeout=20,
        )
        assert playlist.status_code == 200, playlist.text
        playlist_id = playlist.json()["id"]

        publish = session.post(
            f"{BASE_URL}/api/playlists/{playlist_id}/publish",
            json={
                "screen_ids": [screen_a, screen_b],
                "priority": 25,
                "schedule": {"mode": "always"},
            },
            timeout=20,
        )
        assert publish.status_code == 200, publish.text
        assert set(publish.json()["screen_ids"]) == {screen_a, screen_b}

        version_a = mongo_db.screens.find_one({"id": screen_a})["playlist_version"]
        version_b = mongo_db.screens.find_one({"id": screen_b})["playlist_version"]
        assert version_a >= 1
        assert version_b >= 1
    finally:
        if playlist_id:
            mongo_db.playlists.delete_many({"id": playlist_id})
        if menu_id:
            mongo_db.menus.delete_many({"id": menu_id})
        mongo_db.screens.delete_many({"id": {"$in": [screen_a, screen_b]}})
