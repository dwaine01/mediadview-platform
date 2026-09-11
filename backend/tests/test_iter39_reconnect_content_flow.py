"""Iter39 extra coverage — reconnection preserves published content.

The user reported that after reinstalling the APK the TV showed the «waiting
for content» screen. Root cause: `connect` always created a NEW screen so all
playlists/menus stayed on the old one. These tests exercise the whole loop:
publish content to a screen, simulate an APK reinstall (fresh device), reconnect
using `screen_id`, and verify the new device receives total_items > 0 with
media_id and download_url on each item.
"""
import uuid

import pytest
import requests

OWNER = {"email": "pizzeria@demo.com", "password": "Pizza1234!"}


def _token(base_url, creds):
    r = requests.post(f"{base_url}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def owner_headers(base_url):
    return {"Authorization": f"Bearer {_token(base_url, OWNER)}"}


def _register_device(base_url):
    r = requests.post(
        f"{base_url}/api/devices/register",
        json={"device_name": "pytest iter39", "device_model": "pytest",
              "client_uuid": f"pytest-iter39-{uuid.uuid4().hex[:10]}"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _find_screen_with_content(base_url, owner_headers):
    """Return (screen_id, screen_name) of an org screen that already has a
    published playlist with at least one item; else None.
    """
    screens = requests.get(f"{base_url}/api/workspace/screens",
                           headers=owner_headers, timeout=20).json()
    playlists = requests.get(f"{base_url}/api/workspace/playlists",
                             headers=owner_headers, timeout=20).json()
    for s in screens:
        for p in playlists:
            if (p.get("status") == "published"
                    and s["id"] in (p.get("screen_ids") or [])
                    and len(p.get("items") or []) > 0):
                return s["id"], s.get("name")
    return None


class TestReconnectPreservesPublishedContent:
    """Central user-visible fix: content must survive an APK reinstall."""

    def test_reconnected_device_gets_the_original_screens_playlist(
            self, base_url, owner_headers):
        found = _find_screen_with_content(base_url, owner_headers)
        if not found:
            pytest.skip("no screen in the pizzeria org has published content right now")
        screen_id, screen_name = found

        # Baseline before pairing.
        before = requests.get(f"{base_url}/api/workspace/screens",
                              headers=owner_headers, timeout=20).json()
        before_count = len(before)

        # Simulate a fresh APK install: brand-new device + code.
        fresh = _register_device(base_url)
        r = requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": fresh["activation_code"], "screen_id": screen_id},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reconnected"] is True
        assert body["screen"]["id"] == screen_id
        assert body["screen"]["name"] == screen_name

        # No new screen was created.
        after = requests.get(f"{base_url}/api/workspace/screens",
                             headers=owner_headers, timeout=20).json()
        assert len(after) == before_count, "reconnect must not add a screen"

        # /check reports it active on the SAME screen.
        chk = requests.get(f"{base_url}/api/devices/{fresh['device_id']}/check",
                           timeout=20).json()
        assert chk["status"] == "active"
        assert chk["screen_id"] == screen_id

        # And the player playlist is non-empty with real playable items.
        pl = requests.get(
            f"{base_url}/api/devices/{fresh['device_id']}/playlist",
            headers={"X-Device-Token": fresh["device_token"]},
            timeout=20,
        )
        assert pl.status_code == 200, pl.text
        data = pl.json()
        assert data["screen_id"] == screen_id
        assert data.get("total_items", 0) > 0, (
            "Reconnected device is receiving 0 items — this was exactly the "
            "bug duarte reported."
        )
        for item in data.get("items", []):
            # Every item must be actually playable on the TV.
            assert item.get("media_id"), f"missing media_id: {item}"
            assert item.get("download_url"), f"missing download_url: {item}"

    def test_screen_id_from_another_org_is_404(self, base_url, owner_headers):
        """Trying to reconnect using a screen_id that does NOT belong to my org
        must fail with 404 (not leak that the id exists elsewhere)."""
        # A UUID with the right shape but not in this org.
        foreign = str(uuid.uuid4())
        dev = _register_device(base_url)
        r = requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": dev["activation_code"], "screen_id": foreign},
            timeout=20,
        )
        assert r.status_code == 404, r.text

    def test_connect_without_screen_id_or_name_is_400(self, base_url, owner_headers):
        dev = _register_device(base_url)
        r = requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": dev["activation_code"]},
            timeout=20,
        )
        assert r.status_code == 400, r.text
