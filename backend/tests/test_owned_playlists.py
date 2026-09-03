import base64
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
TEST_EMAIL = os.environ.get("TEST_SUPERADMIN_EMAIL", "superadmin@mediadview.com")
TEST_PASSWORD = os.environ.get("TEST_SUPERADMIN_PASSWORD", "SuperAdmin#2026")


@pytest.fixture
def client():
    session = requests.Session()
    login = session.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    if login.status_code != 200:
        pytest.skip(f"superadmin login unavailable: {login.status_code}")
    session.headers.update({"Authorization": f"Bearer {login.json()['access_token']}", "Content-Type": "application/json"})
    return session


@pytest.fixture
def mongo_db():
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "mediaview_db")]
    try:
        yield db
    finally:
        client.close()


def test_owned_playlist_publish_player_and_public_approval(client, mongo_db):
    suffix = uuid.uuid4().hex[:10]
    menu_name = f"TEST Playlist Menu {suffix}"
    menu = client.post(f"{BASE_URL}/api/menus", json={
        "name": menu_name,
        "template_id": "classic",
        "restaurant_name": menu_name,
        "currency": "USD",
        "currency_symbol": "$",
    }, timeout=20)
    assert menu.status_code == 200, menu.text
    menu_id = menu.json()["id"]

    # H3 security fix: draft menus are excluded from player playlists.
    # Publish the menu first so it appears correctly in the player.
    menu_publish = client.put(f"{BASE_URL}/api/menus/{menu_id}",
                              json={"status": "published"}, timeout=20)
    assert menu_publish.status_code == 200, f"Menu publish failed: {menu_publish.text}"

    screens = client.get(f"{BASE_URL}/api/screens", timeout=20)
    assert screens.status_code == 200
    screen_list = screens.json()
    if not screen_list:
        pytest.skip("No screens available for playlist publish test")
    screen_id = screen_list[0]["id"]

    playlist = client.post(f"{BASE_URL}/api/playlists", json={
        "name": f"TEST Owned Playlist {suffix}",
        "management_mode": "admin",
        "items": [{"type": "menu", "ref_id": menu_id, "title": menu_name, "duration": 45}],
    }, timeout=20)
    assert playlist.status_code == 200, playlist.text
    playlist_id = playlist.json()["id"]

    try:
        published = client.post(f"{BASE_URL}/api/playlists/{playlist_id}/publish", json={
            "screen_ids": [screen_id],
            "schedule": {"mode": "always"},
            "priority": 80,
        }, timeout=20)
        assert published.status_code == 200, published.text
        assert published.json()["screen_ids"] == [screen_id]

        player = client.get(f"{BASE_URL}/api/player/{screen_id}/playlist", timeout=20)
        assert player.status_code == 200, player.text
        matching = [item for item in player.json()["items"] if item.get("playlist_id") == playlist_id]
        assert matching
        assert matching[0]["content_type"] == "widget"
        assert matching[0]["download_url"] == f"/api/menus/{menu_id}/render"
        version = client.get(f"{BASE_URL}/api/player/{screen_id}/version", timeout=20)
        assert version.status_code == 200
        assert version.json()["playlist_version"] == player.json()["playlist_version"]

        shared = client.post(f"{BASE_URL}/api/playlists/{playlist_id}/share", json={
            "permission": "editor",
            "require_approval": True,
            "expires_days": 7,
            "allow_upload": True,
        }, timeout=20)
        assert shared.status_code == 200, shared.text
        token = shared.json()["url"].split("token=")[-1]
        after_share = client.get(f"{BASE_URL}/api/playlists/{playlist_id}", timeout=20).json()
        assert after_share["management_mode"] == "admin"
        assert "token_hash" not in after_share["public_access"]

        public_view = requests.get(f"{BASE_URL}/api/public/playlists/{token}", timeout=20)
        assert public_view.status_code == 200
        assert public_view.json()["name"].startswith("TEST Owned Playlist")

        qr = requests.get(f"{BASE_URL}/api/public/playlists/{token}/qr", timeout=20)
        assert qr.status_code == 200
        assert qr.headers["content-type"].startswith("image/png")

        pixel = base64.b64encode(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+AvzZVwAAAABJRU5ErkJggg=="
        )).decode()
        submitted = requests.post(f"{BASE_URL}/api/public/playlists/{token}/media", json={
            "filename": f"TEST-public-{suffix}.png", "content_type": "image/png", "data": pixel,
        }, timeout=20)
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "pending"
        item_id = submitted.json()["item"]["id"]
        public_after_submission = requests.get(f"{BASE_URL}/api/public/playlists/{token}", timeout=20).json()
        assert public_after_submission["pending_count"] == 1
        assert "pending_items" not in public_after_submission

        pending = client.get(f"{BASE_URL}/api/playlists/{playlist_id}", timeout=20).json()["pending_items"]
        assert any(item["id"] == item_id for item in pending)
        approved = client.post(f"{BASE_URL}/api/playlists/{playlist_id}/pending/{item_id}/approve", timeout=20)
        assert approved.status_code == 200, approved.text
        final = client.get(f"{BASE_URL}/api/playlists/{playlist_id}", timeout=20).json()
        assert any(item["ref_id"] == submitted.json()["item"]["ref_id"] for item in final["items"])
    finally:
        mongo_db.playlists.delete_many({"id": playlist_id})
        mongo_db.menus.delete_many({"id": menu_id})
        mongo_db.media.delete_many({"filename": f"TEST-public-{suffix}.png"})
