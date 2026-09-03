"""Playlist autosave persistence regression tests (delete/reorder/duration/display)."""

import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

# Try loading .env from the local dev environment; silently ignored in CI (env vars are set directly)
_env_candidates = [
    Path(__file__).parents[3] / "frontend" / ".env",  # /app/frontend/.env (Emergent local)
    Path(__file__).parents[2] / ".env",                # /app/backend/.env fallback
]
for _env_path in _env_candidates:
    if _env_path.exists():
        load_dotenv(_env_path)
        break

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("TEST_BASE_URL")
TEST_EMAIL = os.environ.get("TEST_SUPERADMIN_EMAIL", "superadmin@mediadview.com")
TEST_PASSWORD = os.environ.get("TEST_SUPERADMIN_PASSWORD", "SuperAdmin#2026")


@pytest.fixture(scope="module")
def app_base_url():
    if not BASE_URL:
        pytest.skip("EXPO_PUBLIC_BACKEND_URL is required for public endpoint testing")
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    try:
        yield db
    finally:
        client.close()


@pytest.fixture
def authed_session(app_base_url):
    session = requests.Session()
    login = session.post(
        f"{app_base_url}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=25,
    )
    if login.status_code != 200:
        pytest.skip(f"superadmin login unavailable: {login.status_code}")
    token = login.json().get("access_token")
    session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return session


@pytest.fixture
def seed_playlist_with_two_menus(authed_session, app_base_url, mongo_db):
    suffix = uuid.uuid4().hex[:8]
    menu_ids = []
    playlist_id = None

    try:
        for idx in (1, 2):
            name = f"TEST_AUTOSAVE_MENU_{suffix}_{idx}"
            created = authed_session.post(
                f"{app_base_url}/api/menus",
                json={
                    "name": name,
                    "template_id": "classic",
                    "restaurant_name": name,
                    "currency": "USD",
                    "currency_symbol": "$",
                },
                timeout=25,
            )
            assert created.status_code == 200, created.text
            menu_ids.append(created.json()["id"])

        playlist = authed_session.post(
            f"{app_base_url}/api/playlists",
            json={
                "name": f"TEST_AUTOSAVE_PLAYLIST_{suffix}",
                "description": "Autosave regression",
                "management_mode": "admin",
                "items": [
                    {
                        "id": f"item_{suffix}_1",
                        "type": "menu",
                        "ref_id": menu_ids[0],
                        "title": "Menu 1",
                        "duration": 45,
                        "display_mode": "cover",
                        "transition": "fade",
                        "order": 0,
                    },
                    {
                        "id": f"item_{suffix}_2",
                        "type": "menu",
                        "ref_id": menu_ids[1],
                        "title": "Menu 2",
                        "duration": 60,
                        "display_mode": "contain",
                        "transition": "fade",
                        "order": 1,
                    },
                ],
            },
            timeout=25,
        )
        assert playlist.status_code == 200, playlist.text
        playlist_id = playlist.json()["id"]

        yield {
            "playlist_id": playlist_id,
            "menu_1": menu_ids[0],
            "menu_2": menu_ids[1],
        }
    finally:
        if playlist_id:
            mongo_db.playlists.delete_many({"id": playlist_id})
        if menu_ids:
            mongo_db.menus.delete_many({"id": {"$in": menu_ids}})


# Module: playlist autosave persistence for delete + source refresh/reopen behavior
def test_delete_persists_after_refresh_and_reopen(authed_session, app_base_url, seed_playlist_with_two_menus):
    seeded = seed_playlist_with_two_menus
    playlist_id = seeded["playlist_id"]

    before = authed_session.get(f"{app_base_url}/api/playlists/{playlist_id}", timeout=25)
    assert before.status_code == 200, before.text
    original_items = before.json().get("items", [])
    assert len(original_items) == 2

    kept = [item for item in original_items if item.get("ref_id") == seeded["menu_1"]]
    update = authed_session.put(
        f"{app_base_url}/api/playlists/{playlist_id}",
        json={"items": kept},
        timeout=25,
    )
    assert update.status_code == 200, update.text

    refresh_menus = authed_session.get(f"{app_base_url}/api/menus", timeout=25)
    assert refresh_menus.status_code == 200, refresh_menus.text
    refresh_media = authed_session.get(f"{app_base_url}/api/media", timeout=25)
    assert refresh_media.status_code == 200, refresh_media.text

    reopened = authed_session.get(f"{app_base_url}/api/playlists/{playlist_id}", timeout=25)
    assert reopened.status_code == 200, reopened.text
    reopened_items = reopened.json().get("items", [])

    assert len(reopened_items) == 1
    assert reopened_items[0].get("ref_id") == seeded["menu_1"]
    assert all(item.get("ref_id") != seeded["menu_2"] for item in reopened_items)


# Module: playlist autosave persistence for reorder + duration + display_mode updates
def test_reorder_duration_display_mode_persist(authed_session, app_base_url, seed_playlist_with_two_menus):
    seeded = seed_playlist_with_two_menus
    playlist_id = seeded["playlist_id"]

    playlist = authed_session.get(f"{app_base_url}/api/playlists/{playlist_id}", timeout=25)
    assert playlist.status_code == 200, playlist.text
    items = playlist.json().get("items", [])
    assert len(items) == 2

    by_ref = {item["ref_id"]: item for item in items}
    item_a = dict(by_ref[seeded["menu_1"]])
    item_b = dict(by_ref[seeded["menu_2"]])

    item_b["order"] = 0
    item_b["duration"] = 33
    item_b["display_mode"] = "stretch"
    item_a["order"] = 1
    item_a["duration"] = 77
    item_a["display_mode"] = "contain"

    saved = authed_session.put(
        f"{app_base_url}/api/playlists/{playlist_id}",
        json={"items": [item_b, item_a]},
        timeout=25,
    )
    assert saved.status_code == 200, saved.text

    reopened = authed_session.get(f"{app_base_url}/api/playlists/{playlist_id}", timeout=25)
    assert reopened.status_code == 200, reopened.text
    reopened_items = sorted(reopened.json().get("items", []), key=lambda x: x.get("order", 0))

    assert reopened_items[0].get("ref_id") == seeded["menu_2"]
    assert reopened_items[0].get("duration") == 33
    assert reopened_items[0].get("display_mode") == "stretch"
    assert reopened_items[1].get("ref_id") == seeded["menu_1"]
    assert reopened_items[1].get("duration") == 77
    assert reopened_items[1].get("display_mode") == "contain"


# Module: latest rapid edit should persist after sequential quick updates
def test_latest_quick_update_not_lost(authed_session, app_base_url, seed_playlist_with_two_menus):
    seeded = seed_playlist_with_two_menus
    playlist_id = seeded["playlist_id"]

    playlist = authed_session.get(f"{app_base_url}/api/playlists/{playlist_id}", timeout=25)
    assert playlist.status_code == 200, playlist.text
    items = playlist.json().get("items", [])
    assert len(items) == 2

    first_payload = []
    second_payload = []
    for item in items:
        first = dict(item)
        second = dict(item)
        first["duration"] = 20
        first["display_mode"] = "cover"
        second["duration"] = 95
        second["display_mode"] = "contain"
        first_payload.append(first)
        second_payload.append(second)

    first_save = authed_session.put(
        f"{app_base_url}/api/playlists/{playlist_id}",
        json={"items": first_payload},
        timeout=25,
    )
    assert first_save.status_code == 200, first_save.text

    second_save = authed_session.put(
        f"{app_base_url}/api/playlists/{playlist_id}",
        json={"items": second_payload},
        timeout=25,
    )
    assert second_save.status_code == 200, second_save.text

    reopened = authed_session.get(f"{app_base_url}/api/playlists/{playlist_id}", timeout=25)
    assert reopened.status_code == 200, reopened.text
    reopened_items = reopened.json().get("items", [])

    assert all(item.get("duration") == 95 for item in reopened_items)
    assert all(item.get("display_mode") == "contain" for item in reopened_items)
