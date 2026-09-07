"""Orientation chain across the three levels (iteración 34).

Level 1 — superadmin creates/edits a screen in the panel
Level 2 — SaaS workspace customer connects a screen with the 6-char code
Level 3 — the player playlist that the APK reads

The screen orientation must survive every level: it is what makes the TV rotate
itself and what the marketplace validates uploads against.
"""
import os
import uuid

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001") + "/api"
ADMIN = {"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}
WORKSPACE = {"email": "testws@test.com", "password": "Test1234!"}


def _token(creds):
    r = requests.post(f"{BASE}/auth/v2/login", json=creds, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin():
    return {"Authorization": f"Bearer {_token(ADMIN)}"}


@pytest.fixture(scope="module")
def workspace():
    """Fresh self-service org so the plan screen limit does not get in the way."""
    email = f"chain_{uuid.uuid4().hex[:8]}@test.com"
    r = requests.post(f"{BASE}/auth/customer-signup", timeout=60, json={
        "plan_id": "pro", "billing_cycle": "monthly",
        "business_name": "Cadena Orientación", "contact_name": "Chain Owner",
        "contact_email": email, "password": "Passw0rd!",
    })
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {_token({'email': email, 'password': 'Passw0rd!'})}"}


def _playlist_orientation(screen_id):
    r = requests.get(f"{BASE}/player/{screen_id}/playlist", timeout=30)
    r.raise_for_status()
    return r.json()["orientation"]


# ── Level 1: superadmin panel ───────────────────────────────────────────────
def _admin_screen(admin, orientation):
    body = {
        "name": f"CHAIN {orientation} {uuid.uuid4().hex[:4]}",
        "location": {"city": "Chain City", "address": "1 Chain St", "state": "CH"},
        "specs": {"size": "55in", "type": "LED", "resolution": "1920x1080",
                  "orientation": orientation},
        "pricing": {"per_month": 500},
        "operation_type": "PUBLIC_ADVERTISING",
    }
    r = requests.post(f"{BASE}/admin/screens", json=body, headers=admin, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_level1_admin_screen_reaches_the_player(admin, orientation):
    sid = _admin_screen(admin, orientation)
    assert _playlist_orientation(sid) == orientation


def test_level1_editing_another_field_keeps_the_orientation(admin):
    """Editing the price must not silently flip the screen back to landscape."""
    sid = _admin_screen(admin, "portrait")
    r = requests.put(f"{BASE}/admin/screens/{sid}",
                     json={"pricing": {"per_month": 999}}, headers=admin, timeout=30)
    assert r.status_code == 200, r.text
    assert _playlist_orientation(sid) == "portrait"


def test_level1_admin_can_switch_orientation(admin):
    sid = _admin_screen(admin, "landscape")
    r = requests.put(f"{BASE}/admin/screens/{sid}", headers=admin, timeout=30, json={
        "specs": {"size": "55in", "type": "LED", "resolution": "1920x1080",
                  "orientation": "portrait"},
    })
    assert r.status_code == 200, r.text
    assert _playlist_orientation(sid) == "portrait"


# ── Level 2: workspace customer ─────────────────────────────────────────────
def _pending_device():
    """Registers a player and returns (activation_code, device_token)."""
    r = requests.post(f"{BASE}/devices/register", timeout=30, json={
        "device_name": "Chain Test TV",
        "client_uuid": f"chain-{uuid.uuid4().hex[:12]}",
        "platform": "android_tv",
        "app_version": "3.3.3-diagnostic",
    })
    assert r.status_code in (200, 201), r.text
    body = r.json()
    return body["activation_code"], body.get("device_token")


def _connect(workspace, orientation):
    code, _token_unused = _pending_device()
    r = requests.post(f"{BASE}/workspace/screens/connect", headers=workspace, timeout=30, json={
        "activation_code": code,
        "screen_name": f"Vidriera {uuid.uuid4().hex[:4]}",
        "orientation": orientation,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["screen"]


@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_level2_connected_screen_stores_and_serves_orientation(workspace, orientation):
    screen = _connect(workspace, orientation)
    assert screen["specs"]["orientation"] == orientation
    assert _playlist_orientation(screen["id"]) == orientation


def test_level2_customer_can_flip_orientation_and_the_player_follows(workspace):
    screen = _connect(workspace, "landscape")
    sid = screen["id"]
    before = requests.get(f"{BASE}/player/{sid}/playlist", timeout=30).json()["playlist_version"]

    r = requests.patch(f"{BASE}/workspace/screens/{sid}",
                       json={"orientation": "portrait"}, headers=workspace, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["specs"]["orientation"] == "portrait"

    after = requests.get(f"{BASE}/player/{sid}/playlist", timeout=30).json()
    assert after["orientation"] == "portrait"
    # A bumped version is what makes the TV re-sync and rotate right away.
    assert after["playlist_version"] > before


def test_level2_rename_does_not_touch_orientation(workspace):
    screen = _connect(workspace, "portrait")
    sid = screen["id"]
    r = requests.patch(f"{BASE}/workspace/screens/{sid}",
                       json={"name": "Vidriera Renombrada"}, headers=workspace, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Vidriera Renombrada"
    assert _playlist_orientation(sid) == "portrait"


def test_level2_workspace_created_screen_defaults_to_landscape(workspace):
    r = requests.post(f"{BASE}/workspace/screens", headers=workspace, timeout=30,
                      json={"name": f"Manual {uuid.uuid4().hex[:4]}"})
    assert r.status_code in (200, 201), r.text
    screen = r.json()
    assert screen["specs"]["orientation"] == "landscape"
    assert _playlist_orientation(screen["id"]) == "landscape"


# ── Level 3: what the APK reads ─────────────────────────────────────────────
def test_level3_device_playlist_matches_screen_playlist(workspace):
    """The device endpoint the APK polls must report the same orientation."""
    code, device_token = _pending_device()
    r = requests.post(f"{BASE}/workspace/screens/connect", headers=workspace, timeout=30, json={
        "activation_code": code, "screen_name": f"APK {uuid.uuid4().hex[:4]}",
        "orientation": "portrait",
    })
    assert r.status_code in (200, 201), r.text
    payload = r.json()
    sid, device_id = payload["screen"]["id"], payload["device_id"]

    device = requests.get(f"{BASE}/devices/{device_id}/playlist", timeout=30,
                          headers={"X-Device-Token": device_token})
    assert device.status_code == 200, device.text
    assert device.json()["orientation"] == "portrait"
    assert _playlist_orientation(sid) == "portrait"
