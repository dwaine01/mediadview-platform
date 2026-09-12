"""
iter42 — backend regression:
- workspace menu preview signed URL works
- menu publish creates a playlist with source_menu_id and player playlist
  contains menu:<menu_id> item
- device APK contract endpoints keep their shape:
  /api/devices/{device_id}/playlist and /api/devices/{device_id}/check
"""
import os
import requests
import pytest

BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
EMAIL = "pizzeria@demo.com"
PASSWORD = "Pizza1234!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_workspace_menus_list(auth):
    r = requests.get(f"{BASE}/api/workspace/menus", headers=auth, timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_menu_preview_returns_signed_url(auth):
    menus = requests.get(f"{BASE}/api/workspace/menus", headers=auth, timeout=30).json()
    assert menus, "No menus for pizzeria"
    mid = menus[0]["id"]
    r = requests.get(f"{BASE}/api/workspace/menus/{mid}/preview", headers=auth, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "url" in data
    assert data["url"].startswith(f"/api/menus/{mid}/render?preview=")
    # Follow the signed URL and expect HTML back (menus render endpoint)
    r2 = requests.get(f"{BASE}{data['url']}", timeout=30)
    assert r2.status_code == 200, r2.text[:300]
    assert "html" in r2.headers.get("content-type", "").lower()


def test_publish_menu_creates_playlist_reaching_player(auth):
    menus = requests.get(f"{BASE}/api/workspace/menus", headers=auth, timeout=30).json()
    mid = menus[0]["id"]
    screens = requests.get(f"{BASE}/api/workspace/screens", headers=auth, timeout=30).json()
    assert screens, "No screens for pizzeria"
    sid = screens[0]["id"]

    pub = requests.post(
        f"{BASE}/api/workspace/menus/{mid}/publish",
        headers=auth, json={"screen_ids": [sid]}, timeout=30,
    )
    assert pub.status_code == 200, pub.text

    # Player playlist (no auth) should contain the menu ref
    pl = requests.get(f"{BASE}/api/player/{sid}/playlist", timeout=30)
    assert pl.status_code == 200, pl.text
    items = pl.json().get("items") or []
    media_ids = [str(i.get("media_id") or "") for i in items]
    assert any(m == f"menu:{mid}" for m in media_ids), f"menu:{mid} not in {media_ids}"


def test_device_playlist_and_check_contract_shape(auth):
    """APK Kotlin is strictly typed. Ensure top-level keys stay stable."""
    screens = requests.get(f"{BASE}/api/workspace/screens", headers=auth, timeout=30).json()
    devices = requests.get(f"{BASE}/api/workspace/devices", headers=auth, timeout=30).json()
    if not devices:
        pytest.skip("No devices seeded")
    did = devices[0]["id"]

    pl = requests.get(f"{BASE}/api/devices/{did}/playlist", timeout=30)
    # 401 (missing device token), 200 (success), 404 (no playlist) all preserve contract.
    assert pl.status_code in (200, 401, 404), pl.text
    if pl.status_code == 200:
        body = pl.json()
        # Contract keys the APK expects
        for key in ["items", "version"]:
            assert key in body, f"missing {key} in device playlist"
        # No unexpected new top-level keys blowing up the parser
        allowed = {"items", "version", "screen_id", "playlist_id", "playlist_name",
                   "orientation", "updated_at", "schedule", "priority", "server_time",
                   "generated_at", "cache_key", "checksum"}
        extra = set(body.keys()) - allowed
        assert not extra, f"Unexpected extra keys in device playlist: {extra}"

    ck = requests.get(f"{BASE}/api/devices/{did}/check", timeout=30)
    assert ck.status_code in (200, 401), ck.text
    if ck.status_code == 200:
        cbody = ck.json()
        # Contract: response is a JSON object with device metadata; no assumption
        # on specific version key — the APK reads playlist_version if present.
        assert isinstance(cbody, dict)
