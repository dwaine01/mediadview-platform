"""Marketplace publication rules (iteración 33).

Covers:
  • media upload stores pixel size + orientation
  • a file whose orientation does not match the screen is rejected (422)
  • the creative can be swapped at most MAX_MEDIA_CHANGES (2) times
  • deleting a paid publication archives it (no refund) and hides it from the portal
  • the player playlist advertises the screen orientation so the APK self-rotates
"""
import base64
import io
import os
import uuid

import pytest
import requests
from PIL import Image

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001") + "/api"
ADMIN = {"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}


def _png(width: int, height: int) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE}/auth/v2/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def customer():
    email = f"mkt_{uuid.uuid4().hex[:8]}@test.com"
    r = requests.post(f"{BASE}/auth/register", json={
        "name": "Marketplace Tester", "email": email, "password": "Passw0rd!",
        "company_name": "Taller Don Luis",
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def screens(admin_token):
    """One landscape and one portrait screen owned by the admin."""
    head = {"Authorization": f"Bearer {admin_token}"}
    out = {}
    for orientation in ("landscape", "portrait"):
        body = {
            "name": f"ORIENT TEST {orientation} {uuid.uuid4().hex[:4]}",
            "location": {"city": "Test City", "address": "1 Test Ave", "state": "TC"},
            "specs": {"size": "55in", "type": "LED", "resolution": "1920x1080",
                      "orientation": orientation},
            "operation_type": "PUBLIC_ADVERTISING",
        }
        r = requests.post(f"{BASE}/admin/screens", json=body, headers=head, timeout=30)
        assert r.status_code in (200, 201), r.text
        out[orientation] = r.json()["id"]
    return out


def _upload(token, w, h):
    r = requests.post(f"{BASE}/media/upload", headers={"Authorization": f"Bearer {token}"}, json={
        "filename": f"ad_{w}x{h}.png", "content_type": "image/png",
        "data": _png(w, h), "width": w, "height": h,
    }, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def _publish(token, screen_id, media_id, name="Publicación"):
    return requests.post(f"{BASE}/campaigns", headers={"Authorization": f"Bearer {token}"}, json={
        "name": name, "screen_id": screen_id,
        "schedule": {"start_date": None, "end_date": None, "start_time": "00:00",
                     "end_time": "23:59", "slot_duration": 15, "frequency": 5},
        "media_ids": [media_id],
    }, timeout=30)


def test_upload_returns_pixel_size_and_orientation(customer):
    land = _upload(customer, 1920, 1080)
    port = _upload(customer, 1080, 1920)
    assert (land["width"], land["height"]) == (1920, 1080)
    assert land["orientation"] == "landscape"
    assert port["orientation"] == "portrait"


def test_portrait_file_rejected_on_landscape_screen(customer, screens):
    portrait = _upload(customer, 1080, 1920)
    r = _publish(customer, screens["landscape"], portrait["id"])
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["required_orientation"] == "landscape"
    assert detail["file_orientation"] == "portrait"


def test_landscape_file_rejected_on_portrait_screen(customer, screens):
    landscape = _upload(customer, 1920, 1080)
    r = _publish(customer, screens["portrait"], landscape["id"])
    assert r.status_code == 422, r.text


def test_matching_orientation_publishes(customer, screens):
    portrait = _upload(customer, 1080, 1920)
    r = _publish(customer, screens["portrait"], portrait["id"])
    assert r.status_code == 200, r.text
    assert r.json()["media_ids"] == [portrait["id"]]


def test_two_media_changes_then_blocked(customer, screens):
    head = {"Authorization": f"Bearer {customer}"}
    first = _upload(customer, 1080, 1920)
    camp = _publish(customer, screens["portrait"], first["id"], name="Cambios").json()
    cid = camp["id"]

    for expected_left in (1, 0):
        new = _upload(customer, 1080, 1920)
        r = requests.put(f"{BASE}/campaigns/{cid}/media", headers=head,
                         json={"media_ids": [new["id"]]}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["media_changes_left"] == expected_left

    third = _upload(customer, 1080, 1920)
    r = requests.put(f"{BASE}/campaigns/{cid}/media", headers=head,
                     json={"media_ids": [third["id"]]}, timeout=30)
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["media_changes_used"] == 2


def test_wrong_orientation_swap_does_not_consume_a_change(customer, screens):
    head = {"Authorization": f"Bearer {customer}"}
    first = _upload(customer, 1080, 1920)
    cid = _publish(customer, screens["portrait"], first["id"], name="No consume").json()["id"]

    bad = _upload(customer, 1920, 1080)
    r = requests.put(f"{BASE}/campaigns/{cid}/media", headers=head,
                     json={"media_ids": [bad["id"]]}, timeout=30)
    assert r.status_code == 422, r.text

    detail = requests.get(f"{BASE}/campaigns/{cid}", headers=head, timeout=30).json()
    assert detail["media_changes_used"] == 0
    assert detail["media_changes_left"] == 2
    assert detail["screen_orientation"] == "portrait"


def test_delete_paid_publication_archives_it_without_refund(customer, screens):
    head = {"Authorization": f"Bearer {customer}"}
    media = _upload(customer, 1080, 1920)
    cid = _publish(customer, screens["portrait"], media["id"], name="A eliminar").json()["id"]

    pay = requests.post(f"{BASE}/payments", headers=head,
                        json={"campaign_id": cid, "method": "card", "card_last4": "4242"}, timeout=30)
    assert pay.status_code in (200, 201), pay.text

    r = requests.delete(f"{BASE}/campaigns/{cid}", headers=head, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["refunded"] is False

    listed = requests.get(f"{BASE}/campaigns", headers=head, timeout=30).json()
    assert cid not in [c["id"] for c in listed]

    detail = requests.get(f"{BASE}/campaigns/{cid}", headers=head, timeout=30).json()
    assert detail["status"] == "archived"
    # Payment history survives: no refund is issued.
    payments = requests.get(f"{BASE}/payments", headers=head, timeout=30).json()
    assert any(p.get("campaign_id") == cid for p in payments)


def test_archived_publication_is_not_playable(customer, screens):
    head = {"Authorization": f"Bearer {customer}"}
    media = _upload(customer, 1080, 1920)
    cid = _publish(customer, screens["portrait"], media["id"], name="Fuera de pantalla").json()["id"]
    requests.post(f"{BASE}/payments", headers=head,
                  json={"campaign_id": cid, "method": "card", "card_last4": "4242"}, timeout=30)
    requests.delete(f"{BASE}/campaigns/{cid}", headers=head, timeout=30)

    playlist = requests.get(f"{BASE}/player/{screens['portrait']}/playlist", timeout=30).json()
    assert all(item.get("campaign_id") != cid for item in playlist["items"])


def test_player_playlist_exposes_screen_orientation(screens):
    for orientation, sid in screens.items():
        data = requests.get(f"{BASE}/player/{sid}/playlist", timeout=30).json()
        assert data["orientation"] == orientation
