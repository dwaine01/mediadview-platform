"""Two customer/ops features added on trunk after Fase 2B:

  1. DELETE /api/workspace/screens/{screen_id} — «desvincular pantalla» from the
     customer panel: deletes the screen and frees every device linked to it back
     to `pending` with a fresh activation code, so the TV can be paired again.
  2. The frozen key contract of GET /api/devices/{device_id}/check, which the
     Android player reads on every poll (see TestDeviceCheckContract).

The whole lifecycle is exercised against the live server: register a device →
customer connects it with the code → unlink → device is pending with a NEW code
→ the same box re-pairs cleanly.
"""
import uuid

import pytest
import requests

OWNER = {"email": "pizzeria@demo.com", "password": "Pizza1234!"}
ADMIN = {"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}


def _token(base_url, creds):
    r = requests.post(f"{base_url}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def owner_headers(base_url):
    return {"Authorization": f"Bearer {_token(base_url, OWNER)}"}


@pytest.fixture
def admin_headers(base_url):
    return {"Authorization": f"Bearer {_token(base_url, ADMIN)}"}


@pytest.fixture
def paired_screen(base_url, owner_headers):
    """A throwaway device + screen pair, cleaned up afterwards."""
    client_uuid = f"pytest-unlink-{uuid.uuid4().hex[:10]}"
    reg = requests.post(
        f"{base_url}/api/devices/register",
        json={"device_name": "pytest TV", "device_model": "pytest", "client_uuid": client_uuid},
        timeout=20,
    )
    assert reg.status_code == 200, reg.text
    device_id = reg.json()["device_id"]

    conn = requests.post(
        f"{base_url}/api/workspace/screens/connect",
        headers=owner_headers,
        json={"activation_code": reg.json()["activation_code"], "screen_name": "pytest desvincular"},
        timeout=20,
    )
    assert conn.status_code == 200, conn.text
    screen_id = conn.json()["screen"]["id"]

    yield {"device_id": device_id, "screen_id": screen_id, "client_uuid": client_uuid}

    requests.delete(f"{base_url}/api/workspace/screens/{screen_id}", headers=owner_headers, timeout=20)


class TestScreenUnlink:
    def test_unlink_deletes_screen_and_frees_device(self, base_url, owner_headers, paired_screen):
        device_id, screen_id = paired_screen["device_id"], paired_screen["screen_id"]

        before = requests.get(f"{base_url}/api/devices/{device_id}/check", timeout=20).json()
        assert before["status"] == "active"
        assert before["screen_id"] == screen_id
        old_code = before["activation_code"]

        r = requests.delete(f"{base_url}/api/workspace/screens/{screen_id}", headers=owner_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["devices_freed"] == 1
        assert len(body["new_activation_codes"]) == 1

        after = requests.get(f"{base_url}/api/devices/{device_id}/check", timeout=20).json()
        assert after["status"] == "pending"
        assert after["screen_id"] is None
        assert after["screen_name"] is None
        assert after["activation_code"] != old_code
        assert after["activation_code"] == body["new_activation_codes"][0]

        listed = requests.get(f"{base_url}/api/workspace/screens", headers=owner_headers, timeout=20).json()
        assert screen_id not in [s["id"] for s in listed]

    def test_freed_device_can_pair_again(self, base_url, owner_headers, paired_screen):
        device_id, screen_id = paired_screen["device_id"], paired_screen["screen_id"]
        requests.delete(f"{base_url}/api/workspace/screens/{screen_id}", headers=owner_headers, timeout=20)

        new_code = requests.get(f"{base_url}/api/devices/{device_id}/check", timeout=20).json()["activation_code"]
        again = requests.post(
            f"{base_url}/api/workspace/screens/connect",
            headers=owner_headers,
            json={"activation_code": new_code, "screen_name": "pytest reconectada"},
            timeout=20,
        )
        assert again.status_code == 200, again.text
        re_screen = again.json()["screen"]["id"]
        assert re_screen != screen_id
        requests.delete(f"{base_url}/api/workspace/screens/{re_screen}", headers=owner_headers, timeout=20)

    def test_unknown_screen_is_404_and_anonymous_is_401(self, base_url, owner_headers):
        assert requests.delete(f"{base_url}/api/workspace/screens/does-not-exist",
                               headers=owner_headers, timeout=20).status_code == 404
        assert requests.delete(f"{base_url}/api/workspace/screens/does-not-exist",
                               timeout=20).status_code == 401


class TestDeviceCheckContract:
    """Regression guard for the Android player.

    The player reads /check on every poll; a fresh install depends on it to show
    the activation code. An extra/renamed key in this payload is exactly the kind
    of change that can break a TV box in the field, so the contract is frozen
    here: these 6 keys, no more, no less. (A `server_url` field for remote
    repointing was added and then reverted for this reason — reintroduce it only
    together with the Kotlin side.)
    """

    BASE_KEYS = {
        "device_id", "activation_code", "status",
        "screen_id", "screen_name", "activated_at",
    }
    # Only when the device is already paired the handler adds this one.
    ACTIVE_KEYS = BASE_KEYS | {"screen_resolution"}

    def _assert_contract(self, payload, expected):
        assert set(payload) == expected, (
            "El contrato de /check cambió: el player Android puede romperse. "
            f"Extra: {set(payload) - expected} | Faltan: {expected - set(payload)}"
        )

    def test_check_payload_keys_are_frozen_when_paired(self, base_url, paired_screen):
        r = requests.get(f"{base_url}/api/devices/{paired_screen['device_id']}/check", timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "active"
        self._assert_contract(r.json(), self.ACTIVE_KEYS)

    def test_check_payload_keys_are_frozen_when_pending(self, base_url, owner_headers, paired_screen):
        """A freshly installed APK hits exactly this shape to show its code."""
        requests.delete(f"{base_url}/api/workspace/screens/{paired_screen['screen_id']}",
                        headers=owner_headers, timeout=20)
        r = requests.get(f"{base_url}/api/devices/{paired_screen['device_id']}/check", timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pending"
        self._assert_contract(r.json(), self.BASE_KEYS)

    def test_admin_player_server_endpoint_stays_removed(self, base_url, admin_headers):
        assert requests.get(f"{base_url}/api/admin/player-server",
                            headers=admin_headers, timeout=20).status_code == 404
