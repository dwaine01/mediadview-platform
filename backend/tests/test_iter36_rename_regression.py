"""
Regression tests for the create_player_domain_routes rename (iter 2B-5 aftermath).

Goal: prove BOTH factories are still registered:
  - player_routes.create_player_domain_routes (16 player/devices routes)
  - colorlight_player.create_player_routes (Direct-Player /cls/* and /wp-json/* routes)

A 404 with detail "Screen not found" / "Device not found" is CORRECT and expected
because the handler executed. What we must NOT see is FastAPI's own routing 404
(detail == "Not Found"), which would mean the route was never registered.
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")

SUPERADMIN_EMAIL = "superadmin@mediadview.com"
SUPERADMIN_PASSWORD = "SuperAdmin#2026"


def _login(email: str, password: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:300]}"
    body = r.json()
    return body.get("access_token") or body["token"]


def _is_routing_404(resp: requests.Response) -> bool:
    """True only if FastAPI's built-in "Not Found" (route not registered)."""
    if resp.status_code != 404:
        return False
    try:
        return resp.json().get("detail") == "Not Found"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 1) The 16 routes registered by create_player_domain_routes (renamed factory)
# ---------------------------------------------------------------------------

FAKE_SCREEN = "00000000-0000-0000-0000-0000000000ff"
FAKE_MEDIA = "00000000-0000-0000-0000-0000000000ee"
FAKE_DEVICE = "00000000-0000-0000-0000-0000000000dd"


def test_player_playlist_route_registered():
    r = requests.get(f"{BASE_URL}/api/player/{FAKE_SCREEN}/playlist", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_player_version_route_registered():
    r = requests.get(f"{BASE_URL}/api/player/{FAKE_SCREEN}/version", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_player_schedule_route_registered():
    r = requests.get(f"{BASE_URL}/api/player/{FAKE_SCREEN}/schedule", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_player_status_route_registered():
    r = requests.get(f"{BASE_URL}/api/player/{FAKE_SCREEN}/status", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_player_export_route_registered():
    r = requests.get(f"{BASE_URL}/api/player/{FAKE_SCREEN}/export", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_player_diagnose_route_registered():
    # requires admin; without a token it should NOT be a routing 404 (usually 401/403)
    r = requests.get(f"{BASE_URL}/api/player/{FAKE_SCREEN}/diagnose", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_player_web_html_route_registered():
    r = requests.get(f"{BASE_URL}/api/player/{FAKE_SCREEN}/web", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_player_test_html_route_registered():
    r = requests.get(f"{BASE_URL}/api/player/{FAKE_SCREEN}/test", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_player_media_route_registered():
    r = requests.get(f"{BASE_URL}/api/player/media/{FAKE_MEDIA}", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_devices_pair_route_registered():
    r = requests.post(
        f"{BASE_URL}/api/devices/pair",
        json={"pairing_code": "XXXX-XXXX", "pairing_secret": "bogus"},
        timeout=10,
    )
    # Not-registered routing 404 must not happen. Bad pairing usually returns 400/401/404-with-detail.
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_devices_register_route_registered():
    r = requests.post(
        f"{BASE_URL}/api/devices/register",
        json={"pairing_token": "bogus"},
        timeout=10,
    )
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_devices_check_route_registered():
    r = requests.get(f"{BASE_URL}/api/devices/{FAKE_DEVICE}/check", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_devices_heartbeat_route_registered():
    r = requests.post(f"{BASE_URL}/api/devices/{FAKE_DEVICE}/heartbeat", json={}, timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_devices_update_check_route_registered():
    r = requests.get(f"{BASE_URL}/api/devices/{FAKE_DEVICE}/update-check", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_devices_log_route_registered():
    r = requests.post(
        f"{BASE_URL}/api/devices/{FAKE_DEVICE}/log",
        json={"level": "info", "message": "test"},
        timeout=10,
    )
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


def test_devices_playlist_route_registered():
    r = requests.get(f"{BASE_URL}/api/devices/{FAKE_DEVICE}/playlist", timeout=10)
    assert not _is_routing_404(r), f"route not registered: {r.status_code} {r.text[:200]}"


# ---------------------------------------------------------------------------
# 2) The OTHER factory: colorlight_player.create_player_routes (Direct Player)
# ---------------------------------------------------------------------------

def test_colorlight_devices_listing_registered():
    """GET /api/cls/devices  → must be registered (may require auth)."""
    r = requests.get(f"{BASE_URL}/api/cls/devices", timeout=10)
    assert not _is_routing_404(r), f"colorlight route not registered: {r.status_code} {r.text[:200]}"


def test_colorlight_device_status_registered():
    r = requests.get(f"{BASE_URL}/api/cls/devices/{FAKE_DEVICE}/status", timeout=10)
    assert not _is_routing_404(r), f"colorlight route not registered: {r.status_code} {r.text[:200]}"


def test_colorlight_commands_registered():
    r = requests.get(f"{BASE_URL}/api/cls/commands/{FAKE_DEVICE}", timeout=10)
    assert not _is_routing_404(r), f"colorlight route not registered: {r.status_code} {r.text[:200]}"


def test_colorlight_command_post_registered():
    r = requests.post(f"{BASE_URL}/api/cls/command", json={}, timeout=10)
    assert not _is_routing_404(r), f"colorlight route not registered: {r.status_code} {r.text[:200]}"


def test_colorlight_brightness_registered():
    r = requests.post(f"{BASE_URL}/api/cls/brightness", json={}, timeout=10)
    assert not _is_routing_404(r), f"colorlight route not registered: {r.status_code} {r.text[:200]}"


def test_colorlight_schedule_get_registered():
    r = requests.get(f"{BASE_URL}/api/cls/schedule/{FAKE_DEVICE}", timeout=10)
    assert not _is_routing_404(r), f"colorlight route not registered: {r.status_code} {r.text[:200]}"


def test_colorlight_wpjson_screen_status_registered():
    """PUT /api/wp-json/screen/v1/status — legacy protocol path."""
    r = requests.put(f"{BASE_URL}/api/wp-json/screen/v1/status", json={}, timeout=10)
    assert not _is_routing_404(r), f"colorlight route not registered: {r.status_code} {r.text[:200]}"


def test_colorlight_wpjson_programs_registered():
    r = requests.get(f"{BASE_URL}/api/wp-json/wp/v2/programs", timeout=10)
    assert not _is_routing_404(r), f"colorlight route not registered: {r.status_code} {r.text[:200]}"


# ---------------------------------------------------------------------------
# 3) End-to-end device lifecycle against the renamed factory
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def superadmin_token():
    return _login(SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)


@pytest.fixture(scope="module")
def paired_screen(superadmin_token):
    """Create a fresh screen via /api/admin/screens and return pairing info."""
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    payload = {
        "name": f"TEST_rename_regression_{uuid.uuid4().hex[:6]}",
        "location": {"city": "TEST_iter36", "address": "TEST_iter36 st 1", "country": "US"},
        "specs": {"resolution": "1920x1080", "orientation": "landscape"},
        "operation_type": "SELF_SERVICE",
    }
    r = requests.post(
        f"{BASE_URL}/api/admin/screens",
        headers=headers,
        json=payload,
        timeout=15,
    )
    if r.status_code not in (200, 201):
        pytest.skip(f"cannot create screen for lifecycle test: {r.status_code} {r.text[:300]}")
    data = r.json()
    if not data.get("pairing_code") or not data.get("pairing_secret"):
        pytest.skip(f"screen created but no pairing fields returned: {data}")
    return data


def test_device_lifecycle_end_to_end(paired_screen):
    pairing_code = paired_screen["pairing_code"]
    pairing_secret = paired_screen["pairing_secret"]

    # 1) /api/devices/pair (customer pairing flow — screen already has admin-provided codes)
    r = requests.post(
        f"{BASE_URL}/api/devices/pair",
        json={"pairing_code": pairing_code, "pairing_secret": pairing_secret},
        timeout=15,
    )
    assert r.status_code == 200, f"pair failed: {r.status_code} {r.text[:300]}"
    pair_data = r.json()
    assert pair_data.get("ok") is True
    device_id = pair_data["device_id"]
    screen_id = pair_data["screen_id"]

    # 2) /api/devices/register (independent factory-first flow: registers a fresh client and
    #    hands out a device_token). Uses a stable client_uuid so subsequent calls are idempotent.
    client_uuid = f"TEST_uuid_{uuid.uuid4().hex[:12]}"
    r = requests.post(
        f"{BASE_URL}/api/devices/register",
        json={
            "client_uuid": client_uuid,
            "device_name": "TEST_iter36",
            "device_model": "iter36-regression",
            "os_version": "Android 11",
            "app_version": "1.0.0",
        },
        timeout=15,
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:300]}"
    reg = r.json()
    reg_device_id = reg["device_id"]
    device_token = reg["device_token"]
    assert reg["status"] == "pending"
    reg_headers = {"Authorization": f"Bearer {device_token}"}

    # 3) /api/devices/{id}/check (public poll from Player App)
    r = requests.get(f"{BASE_URL}/api/devices/{reg_device_id}/check", timeout=15)
    assert r.status_code == 200, f"check failed: {r.status_code} {r.text[:300]}"

    # 4) /api/devices/{id}/heartbeat (needs device token; grace mode adopts on first call)
    r = requests.post(
        f"{BASE_URL}/api/devices/{reg_device_id}/heartbeat",
        headers=reg_headers,
        json={"status": "online", "cpu_percent": 10, "memory_percent": 20},
        timeout=15,
    )
    assert r.status_code == 200, f"heartbeat failed: {r.status_code} {r.text[:300]}"

    # 5) /api/devices/{id}/update-check
    r = requests.get(
        f"{BASE_URL}/api/devices/{reg_device_id}/update-check",
        headers=reg_headers,
        timeout=15,
    )
    assert r.status_code == 200, f"update-check failed: {r.status_code} {r.text[:300]}"

    # 6) /api/devices/{id}/log
    r = requests.post(
        f"{BASE_URL}/api/devices/{reg_device_id}/log",
        headers=reg_headers,
        json={"level": "info", "message": "TEST_rename_regression"},
        timeout=15,
    )
    assert r.status_code in (200, 201, 204), f"log failed: {r.status_code} {r.text[:300]}"

    # 7) /api/devices/{id}/playlist  — device from /pair already has a screen_id linked
    r = requests.get(f"{BASE_URL}/api/devices/{device_id}/playlist", timeout=15)
    assert r.status_code == 200, f"device playlist failed: {r.status_code} {r.text[:300]}"
    pl = r.json()
    assert pl.get("screen_id") == screen_id or "items" in pl


# ---------------------------------------------------------------------------
# 4) Backend health sanity
# ---------------------------------------------------------------------------

def test_health_endpoint():
    r = requests.get(f"{BASE_URL}/api/health", timeout=10)
    assert r.status_code == 200
