"""Regression coverage for real-time owned-playlist delivery."""

import asyncio
import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests
from pymongo import MongoClient

from realtime import manager


BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


@pytest.mark.asyncio
async def test_screen_event_subscribers_receive_playlist_updates():
    screen_id = f"TEST-events-{uuid.uuid4().hex[:8]}"
    queue = await manager.subscribe_events("screen", screen_id)
    try:
        await manager.broadcast_screen(screen_id, "playlist.updated", {"reason": "test"})
        payload = await asyncio.wait_for(queue.get(), timeout=1)
        assert payload["event"] == "playlist.updated"
        assert payload["screen_id"] == screen_id
        assert payload["data"]["reason"] == "test"
    finally:
        await manager.unsubscribe_events("screen", screen_id, queue)
    assert manager.event_room_size("screen", screen_id) == 0


def test_menu_edits_bump_screen_version_and_delivery_uses_heartbeat():
    session = requests.Session()
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"},
        timeout=20,
    )
    if login.status_code != 200:
        pytest.skip(f"superadmin login unavailable: {login.status_code}")
    session.headers.update({
        "Authorization": f"Bearer {login.json()['access_token']}",
        "Content-Type": "application/json",
    })

    suffix = uuid.uuid4().hex[:10]
    screen_id = f"TEST-realtime-screen-{suffix}"
    device_id = f"TEST-realtime-device-{suffix}"
    db_client = MongoClient(os.environ["MONGO_URL"])
    db = db_client[os.environ.get("DB_NAME", "mediaview_db")]
    menu_id = None
    playlist_id = None
    db.screens.insert_one({
        "id": screen_id,
        "name": "TEST Realtime Screen",
        "status": "active",
        "location": {"city": "Columbus", "state": "OH"},
        "specs": {"resolution": "1920x1080"},
        "playlist_version": 0,
    })
    db.devices.insert_one({
        "id": device_id,
        "screen_id": screen_id,
        "status": "active",
        "last_heartbeat": datetime.utcnow(),
    })
    try:
        menu_response = session.post(f"{BASE_URL}/api/menus", json={
            "name": f"TEST Realtime Menu {suffix}",
            "template_id": "classic",
            "restaurant_name": "TEST Restaurant",
        }, timeout=20)
        assert menu_response.status_code == 200, menu_response.text
        menu_id = menu_response.json()["id"]

        playlist_response = session.post(f"{BASE_URL}/api/playlists", json={
            "name": f"TEST Realtime Playlist {suffix}",
            "items": [{"type": "menu", "ref_id": menu_id, "title": "Menu", "duration": 60}],
        }, timeout=20)
        assert playlist_response.status_code == 200, playlist_response.text
        playlist_id = playlist_response.json()["id"]

        published = session.post(f"{BASE_URL}/api/playlists/{playlist_id}/publish", json={
            "screen_ids": [screen_id],
            "schedule": {"mode": "always"},
            "priority": 20,
        }, timeout=20)
        assert published.status_code == 200, published.text
        before = db.screens.find_one({"id": screen_id})["playlist_version"]

        updated = session.put(
            f"{BASE_URL}/api/menus/{menu_id}",
            json={"subtitle": "Updated for immediate delivery"},
            timeout=20,
        )
        assert updated.status_code == 200, updated.text
        after = db.screens.find_one({"id": screen_id})["playlist_version"]
        assert after == before + 1

        delivery = session.get(
            f"{BASE_URL}/api/playlists/{playlist_id}/delivery-status",
            timeout=20,
        )
        assert delivery.status_code == 200, delivery.text
        assert delivery.json()[0]["device_status"] == "online"
        assert delivery.json()[0]["last_seen"]

        db.devices.update_one(
            {"id": device_id},
            {"$set": {"last_heartbeat": datetime.utcnow() - timedelta(minutes=5)}},
        )
        offline = session.get(
            f"{BASE_URL}/api/playlists/{playlist_id}/delivery-status",
            timeout=20,
        )
        assert offline.status_code == 200
        assert offline.json()[0]["device_status"] == "offline"

        blocked_delete = session.delete(f"{BASE_URL}/api/menus/{menu_id}", timeout=20)
        assert blocked_delete.status_code == 409
    finally:
        if playlist_id:
            db.playlists.delete_many({"id": playlist_id})
        if menu_id:
            db.menus.delete_many({"id": menu_id})
        db.devices.delete_many({"id": device_id})
        db.screens.delete_many({"id": screen_id})
        db_client.close()