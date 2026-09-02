"""Regression tests for owned playlist professional platform flows."""

import base64
import os
import uuid

import pytest
import requests
from pymongo import MongoClient


BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL") or os.environ.get("TEST_BASE_URL"))
SUPERADMIN_EMAIL = "superadmin@mediadview.com"
SUPERADMIN_PASSWORD = "SuperAdmin#2026"


def _api_url(path: str) -> str:
    if not BASE_URL:
        pytest.skip("EXPO_PUBLIC_BACKEND_URL / EXPO_BACKEND_URL / TEST_BASE_URL not configured")
    return f"{BASE_URL.rstrip('/')}/api{path}"


def _login(email: str, password: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(_api_url("/auth/login"), json={"email": email, "password": password}, timeout=30)
    if response.status_code != 200:
        pytest.skip(f"Login unavailable for {email}: {response.status_code}")
    token = response.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture
def mongo_db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "mediaview_db")]


@pytest.fixture
def tracked_ids():
    return {"playlists": [], "menus": [], "media": [], "users": []}


@pytest.fixture(scope="session")
def superadmin_session():
    return _login(SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)


@pytest.fixture(autouse=True)
def cleanup_entities(mongo_db, tracked_ids):
    yield
    if tracked_ids["playlists"]:
        mongo_db.playlists.delete_many({"id": {"$in": tracked_ids["playlists"]}})
    if tracked_ids["menus"]:
        mongo_db.menus.delete_many({"id": {"$in": tracked_ids["menus"]}})
    if tracked_ids["media"]:
        mongo_db.media.delete_many({"id": {"$in": tracked_ids["media"]}})
    if tracked_ids["users"]:
        mongo_db.users.delete_many({"id": {"$in": tracked_ids["users"]}})


def _create_menu(session: requests.Session, tracked_ids, suffix: str, theme: dict | None = None) -> dict:
    response = session.post(
        _api_url("/menus"),
        json={
            "name": f"TEST Menu {suffix}",
            "template_id": "classic",
            "restaurant_name": f"TEST Restaurant {suffix}",
            "currency": "USD",
            "currency_symbol": "$",
            "theme": theme or {},
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text
    menu = response.json()
    tracked_ids["menus"].append(menu["id"])
    return menu


def _create_media(session: requests.Session, tracked_ids, suffix: str) -> dict:
    pixel = base64.b64encode(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+AvzZVwAAAABJRU5ErkJggg=="
    )).decode()
    response = session.post(
        _api_url("/media/upload"),
        json={"filename": f"TEST-{suffix}.png", "content_type": "image/png", "data": pixel},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    media = response.json()
    tracked_ids["media"].append(media["id"])
    return media


# Module: owned playlists CRUD/timeline/edit/publish/player behavior
def test_owned_playlist_timeline_edit_publish_and_player_contract(superadmin_session, mongo_db, tracked_ids):
    admin = superadmin_session
    suffix = uuid.uuid4().hex[:8]

    screens_res = admin.get(_api_url("/screens"), timeout=30)
    assert screens_res.status_code == 200
    screens = screens_res.json()
    if not screens:
        pytest.skip("No screens available")
    screen_id = screens[0]["id"]

    menu = _create_menu(admin, tracked_ids, suffix)
    media = _create_media(admin, tracked_ids, suffix)

    create_res = admin.post(
        _api_url("/playlists"),
        json={
            "name": f"TEST Playlist {suffix}",
            "description": "Initial description",
            "management_mode": "admin",
            "items": [
                {"type": "menu", "ref_id": menu["id"], "title": menu["name"], "duration": 55},
                {"type": "media", "ref_id": media["id"], "title": media["filename"], "duration": 20},
            ],
        },
        timeout=30,
    )
    assert create_res.status_code == 200, create_res.text
    playlist = create_res.json()
    tracked_ids["playlists"].append(playlist["id"])

    update_res = admin.put(
        _api_url(f"/playlists/{playlist['id']}"),
        json={
            "name": f"TEST Playlist Updated {suffix}",
            "description": "Updated description",
            "items": [
                {"type": "media", "ref_id": media["id"], "title": media["filename"], "duration": 33},
                {"type": "menu", "ref_id": menu["id"], "title": menu["name"], "duration": 66},
            ],
        },
        timeout=30,
    )
    assert update_res.status_code == 200, update_res.text

    get_res = admin.get(_api_url(f"/playlists/{playlist['id']}"), timeout=30)
    assert get_res.status_code == 200
    updated = get_res.json()
    assert updated["name"].startswith("TEST Playlist Updated")
    assert updated["items"][0]["type"] == "media"
    assert updated["items"][0]["duration"] == 33
    assert updated["items"][1]["type"] == "menu"
    assert updated["items"][1]["duration"] == 66

    publish_res = admin.post(
        _api_url(f"/playlists/{playlist['id']}/publish"),
        json={"screen_ids": [screen_id], "schedule": {"mode": "always"}, "priority": 77},
        timeout=30,
    )
    assert publish_res.status_code == 200, publish_res.text
    assert publish_res.json()["screen_ids"] == [screen_id]

    status_res = admin.get(_api_url(f"/playlists/{playlist['id']}/delivery-status"), timeout=30)
    assert status_res.status_code == 200
    assert any(row["id"] == screen_id for row in status_res.json())

    player_res = admin.get(_api_url(f"/player/{screen_id}/playlist"), timeout=30)
    assert player_res.status_code == 200, player_res.text
    items = player_res.json().get("items", [])
    playlist_items = [item for item in items if item.get("playlist_id") == playlist["id"]]
    assert playlist_items
    assert any(item.get("content_type") == "widget" and "/api/menus/" in (item.get("media_url") or "") for item in playlist_items)


# Module: menu publish integration and public link + approval workflow
def test_menu_prepare_playlist_public_link_qr_pending_approval_flow(superadmin_session, mongo_db, tracked_ids):
    admin = superadmin_session
    suffix = uuid.uuid4().hex[:8]

    menu = _create_menu(admin, tracked_ids, f"menupub-{suffix}")

    prepare_res = admin.post(_api_url(f"/menus/{menu['id']}/prepare-playlist"), timeout=30)
    assert prepare_res.status_code == 200, prepare_res.text
    playlist = prepare_res.json()
    tracked_ids["playlists"].append(playlist["id"])
    assert playlist.get("source_menu_id") == menu["id"]

    share_res = admin.post(
        _api_url(f"/playlists/{playlist['id']}/share"),
        json={"permission": "editor", "require_approval": True, "expires_days": 7, "allow_upload": True},
        timeout=30,
    )
    assert share_res.status_code == 200, share_res.text
    share = share_res.json()
    token = share["url"].split("token=")[-1]

    portal_res = requests.get(f"{BASE_URL.rstrip('/')}/api/public/playlist?token={token}", timeout=30)
    assert portal_res.status_code == 200
    assert "public-playlist-portal" in portal_res.text

    public_data = requests.get(_api_url(f"/public/playlists/{token}"), timeout=30)
    assert public_data.status_code == 200
    assert public_data.json()["id"] == playlist["id"]

    qr_res = requests.get(_api_url(f"/public/playlists/{token}/qr"), timeout=30)
    assert qr_res.status_code == 200
    assert qr_res.headers["content-type"].startswith("image/png")

    pixel = base64.b64encode(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+AvzZVwAAAABJRU5ErkJggg=="
    )).decode()
    submit_res = requests.post(
        _api_url(f"/public/playlists/{token}/media"),
        json={"filename": f"TEST-public-{suffix}.png", "content_type": "image/png", "data": pixel},
        timeout=30,
    )
    assert submit_res.status_code == 200, submit_res.text
    assert submit_res.json()["status"] == "pending"
    pending_item = submit_res.json()["item"]
    tracked_ids["media"].append(pending_item["ref_id"])

    details_res = admin.get(_api_url(f"/playlists/{playlist['id']}"), timeout=30)
    assert details_res.status_code == 200
    assert any(item["id"] == pending_item["id"] for item in details_res.json().get("pending_items", []))

    approve_res = admin.post(_api_url(f"/playlists/{playlist['id']}/pending/{pending_item['id']}/approve"), timeout=30)
    assert approve_res.status_code == 200, approve_res.text
    final_res = admin.get(_api_url(f"/playlists/{playlist['id']}"), timeout=30)
    assert final_res.status_code == 200
    assert any(item.get("ref_id") == pending_item["ref_id"] for item in final_res.json().get("items", []))


# Module: menu theme/color persistence and render parity
def test_menu_theme_colors_persist_and_render(superadmin_session, mongo_db, tracked_ids):
    admin = superadmin_session
    suffix = uuid.uuid4().hex[:8]
    theme = {"bg": "#112233", "bg2": "#223344", "text": "#f1f5f9", "text2": "#93c5fd", "accent": "#22d3ee"}

    menu = _create_menu(admin, tracked_ids, f"theme-{suffix}", theme=theme)
    menu_id = menu["id"]

    update_res = admin.put(_api_url(f"/menus/{menu_id}"), json={"theme": theme}, timeout=30)
    assert update_res.status_code == 200, update_res.text
    assert update_res.json().get("theme", {}).get("accent") == "#22d3ee"

    render_res = requests.get(_api_url(f"/menus/{menu_id}/render"), timeout=30)
    assert render_res.status_code == 200
    html = render_res.text
    assert "#112233" in html
    assert "#22d3ee" in html


# Module: client scoping + allow_client_publish gate
def test_client_only_sees_assigned_playlists_and_publish_gate(superadmin_session, mongo_db, tracked_ids):
    admin = superadmin_session
    suffix = uuid.uuid4().hex[:8]

    # Create two customer accounts for visibility gating checks
    customer_a_email = f"test.customer.a.{suffix}@example.com"
    customer_b_email = f"test.customer.b.{suffix}@example.com"
    customer_password = "TestPass#2026"
    for email in [customer_a_email, customer_b_email]:
        reg = requests.post(
            _api_url("/auth/register"),
            json={"name": f"TEST {email.split('@')[0]}", "email": email, "password": customer_password, "company_name": "TEST"},
            timeout=30,
        )
        assert reg.status_code == 200, reg.text
        tracked_ids["users"].append(reg.json()["user"]["id"])

    customer_a = _login(customer_a_email, customer_password)

    users_res = admin.get(_api_url("/admin/users"), timeout=30)
    assert users_res.status_code == 200
    users = users_res.json()
    user_a = next(user for user in users if user["email"] == customer_a_email)
    user_b = next(user for user in users if user["email"] == customer_b_email)

    screens_res = admin.get(_api_url("/screens"), timeout=30)
    assert screens_res.status_code == 200
    screens = screens_res.json()
    if not screens:
        pytest.skip("No screens available")
    screen_id = screens[0]["id"]

    menu = _create_menu(admin, tracked_ids, f"client-{suffix}")

    assigned_res = admin.post(
        _api_url("/playlists"),
        json={
            "name": f"TEST Client Assigned {suffix}",
            "management_mode": "client",
            "client_user_id": user_a["id"],
            "allow_client_publish": False,
            "allowed_screen_ids": [screen_id],
            "items": [{"type": "menu", "ref_id": menu["id"], "title": menu["name"], "duration": 40}],
        },
        timeout=30,
    )
    assert assigned_res.status_code == 200, assigned_res.text
    assigned = assigned_res.json()
    tracked_ids["playlists"].append(assigned["id"])

    hidden_res = admin.post(
        _api_url("/playlists"),
        json={
            "name": f"TEST Client Hidden {suffix}",
            "management_mode": "client",
            "client_user_id": user_b["id"],
            "allow_client_publish": False,
            "items": [{"type": "menu", "ref_id": menu["id"], "title": menu["name"], "duration": 40}],
        },
        timeout=30,
    )
    assert hidden_res.status_code == 200, hidden_res.text
    hidden = hidden_res.json()
    tracked_ids["playlists"].append(hidden["id"])

    customer_list = customer_a.get(_api_url("/playlists"), timeout=30)
    assert customer_list.status_code == 200
    ids = {playlist["id"] for playlist in customer_list.json()}
    assert assigned["id"] in ids
    assert hidden["id"] not in ids

    denied_publish = customer_a.post(
        _api_url(f"/playlists/{assigned['id']}/publish"),
        json={"screen_ids": [screen_id], "schedule": {"mode": "always"}, "priority": 20},
        timeout=30,
    )
    assert denied_publish.status_code == 403

    enable_publish = admin.put(_api_url(f"/playlists/{assigned['id']}"), json={"allow_client_publish": True}, timeout=30)
    assert enable_publish.status_code == 200, enable_publish.text

    allowed_publish = customer_a.post(
        _api_url(f"/playlists/{assigned['id']}/publish"),
        json={"screen_ids": [screen_id], "schedule": {"mode": "always"}, "priority": 25},
        timeout=30,
    )
    assert allowed_publish.status_code == 200, allowed_publish.text


# Module: campaigns remain separate from playlist flows
def test_campaigns_endpoint_stays_independent_from_playlist_creation(superadmin_session, mongo_db, tracked_ids):
    admin = superadmin_session
    suffix = uuid.uuid4().hex[:8]

    before_res = admin.get(_api_url("/admin/campaigns"), timeout=30)
    assert before_res.status_code == 200, before_res.text
    before_count = len(before_res.json())

    menu = _create_menu(admin, tracked_ids, f"sep-{suffix}")
    create_res = admin.post(
        _api_url("/playlists"),
        json={
            "name": f"TEST Separation {suffix}",
            "management_mode": "admin",
            "items": [{"type": "menu", "ref_id": menu["id"], "title": menu["name"], "duration": 30}],
        },
        timeout=30,
    )
    assert create_res.status_code == 200, create_res.text
    tracked_ids["playlists"].append(create_res.json()["id"])

    after_res = admin.get(_api_url("/admin/campaigns"), timeout=30)
    assert after_res.status_code == 200, after_res.text
    assert len(after_res.json()) == before_count
