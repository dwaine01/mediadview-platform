"""Reconnect a device to an EXISTING screen (POST /workspace/screens/connect + screen_id).

Why this exists: reinstalling the player app wipes its local storage, so the TV
registers as a brand-new device and shows a fresh pairing code. Until now the
only way to pair it was `connect`, which ALWAYS created a new screen — so the
customer ended up with an empty new screen (the TV showing «waiting for
content») while every playlist, menu and promo stayed on the old screen, which
then showed up as offline. That's exactly the bug duarte reported.
"""
import uuid

import pytest
import requests

OWNER = {"email": "pizzeria@demo.com", "password": "Pizza1234!"}


@pytest.fixture
def owner_headers(base_url):
    r = requests.post(f"{base_url}/api/auth/login", json=OWNER, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register_device(base_url):
    r = requests.post(
        f"{base_url}/api/devices/register",
        json={"device_name": "pytest reconnect", "device_model": "pytest",
              "client_uuid": f"pytest-reconnect-{uuid.uuid4().hex[:10]}"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def screen_with_a_device(base_url, owner_headers):
    """A screen paired to a device, like any screen already working in the field."""
    dev = _register_device(base_url)
    conn = requests.post(
        f"{base_url}/api/workspace/screens/connect",
        headers=owner_headers,
        json={"activation_code": dev["activation_code"], "screen_name": "pytest reconnect base"},
        timeout=20,
    )
    assert conn.status_code == 200, conn.text
    screen_id = conn.json()["screen"]["id"]
    yield {"screen_id": screen_id, "device_id": dev["device_id"], "device_token": dev["device_token"]}
    requests.delete(f"{base_url}/api/workspace/screens/{screen_id}", headers=owner_headers, timeout=20)


class TestReconnectToExistingScreen:
    def test_reinstalled_device_reuses_the_screen_instead_of_creating_one(
            self, base_url, owner_headers, screen_with_a_device):
        screen_id = screen_with_a_device["screen_id"]
        before = requests.get(f"{base_url}/api/workspace/screens", headers=owner_headers, timeout=20).json()

        # The app was reinstalled: same TV, brand-new device + code.
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
        assert body["screen"]["id"] == screen_id          # same screen, not a new one
        assert body["device_id"] == fresh["device_id"]

        after = requests.get(f"{base_url}/api/workspace/screens", headers=owner_headers, timeout=20).json()
        assert len(after) == len(before), "no debe crearse una pantalla nueva al reconectar"

        # The new device is now the active one for that screen...
        chk = requests.get(f"{base_url}/api/devices/{fresh['device_id']}/check", timeout=20).json()
        assert chk["status"] == "active"
        assert chk["screen_id"] == screen_id

        # ...and it serves that screen's content, not an empty playlist shell.
        pl = requests.get(f"{base_url}/api/devices/{fresh['device_id']}/playlist",
                          headers={"X-Device-Token": fresh["device_token"]}, timeout=20)
        assert pl.status_code == 200, pl.text
        assert pl.json()["screen_id"] == screen_id

    def test_previous_device_is_freed_so_only_one_box_serves_the_screen(
            self, base_url, owner_headers, screen_with_a_device):
        old_device = screen_with_a_device["device_id"]
        fresh = _register_device(base_url)
        requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": fresh["activation_code"],
                  "screen_id": screen_with_a_device["screen_id"]},
            timeout=20,
        )
        old = requests.get(f"{base_url}/api/devices/{old_device}/check", timeout=20).json()
        assert old["status"] == "pending"
        assert old["screen_id"] is None

    def test_unknown_or_foreign_screen_is_404_and_new_screen_path_still_works(
            self, base_url, owner_headers):
        dev = _register_device(base_url)
        bad = requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": dev["activation_code"], "screen_id": "does-not-exist"},
            timeout=20,
        )
        assert bad.status_code == 404

        # The original behaviour (create a new screen by name) is untouched.
        ok = requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": dev["activation_code"], "screen_name": "pytest brand new"},
            timeout=20,
        )
        assert ok.status_code == 200, ok.text
        assert ok.json().get("reconnected") is None
        requests.delete(f"{base_url}/api/workspace/screens/{ok.json()['screen']['id']}",
                        headers=owner_headers, timeout=20)

    def test_code_is_still_required_and_validated(self, base_url, owner_headers, screen_with_a_device):
        short = requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": "ABC", "screen_id": screen_with_a_device["screen_id"]},
            timeout=20,
        )
        assert short.status_code == 400
        unknown = requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": "ZZZZZZ", "screen_id": screen_with_a_device["screen_id"]},
            timeout=20,
        )
        assert unknown.status_code == 404
