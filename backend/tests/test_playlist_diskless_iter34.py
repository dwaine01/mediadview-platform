"""Playlist resilience when the ephemeral disk copy is gone (iteración 34).

Render wipes the container filesystem on every deploy, so legacy media loses its
`stored_filename` copy while the base64 payload survives in Mongo. The playlist
must keep serving those items instead of handing the TV an empty playlist.
"""
import base64
import io
import os
import uuid

import pytest
import requests
from PIL import Image

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001") + "/api"
MEDIA_DIR = os.environ.get("MEDIA_DIR", "/app/backend/media")
ADMIN = {"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}


def _png(width, height):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 40, 40)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(scope="module")
def ctx():
    admin = requests.post(f"{BASE}/auth/v2/login", json=ADMIN, timeout=30).json()["access_token"]
    head = {"Authorization": f"Bearer {admin}"}
    screen = requests.post(f"{BASE}/admin/screens", headers=head, timeout=30, json={
        "name": f"DISKLESS {uuid.uuid4().hex[:4]}",
        "location": {"city": "Test", "address": "1 St", "state": "TS"},
        "specs": {"size": "55in", "type": "LED", "resolution": "1920x1080",
                  "orientation": "landscape"},
        "operation_type": "PUBLIC_ADVERTISING",
    }).json()

    email = f"diskless_{uuid.uuid4().hex[:8]}@test.com"
    user = requests.post(f"{BASE}/auth/register", timeout=30, json={
        "name": "Diskless", "email": email, "password": "Passw0rd!", "company_name": "Diskless",
    }).json()["access_token"]
    uhead = {"Authorization": f"Bearer {user}"}

    media = requests.post(f"{BASE}/media/upload", headers=uhead, timeout=60, json={
        "filename": "poster.png", "content_type": "image/png",
        "data": _png(1920, 1080), "width": 1920, "height": 1080,
    }).json()

    campaign = requests.post(f"{BASE}/campaigns", headers=uhead, timeout=30, json={
        "name": "Poster", "screen_id": screen["id"],
        "schedule": {"start_date": None, "end_date": None, "start_time": "00:00",
                     "end_time": "23:59", "slot_duration": 15, "frequency": 5},
        "media_ids": [media["id"]],
    }).json()
    # Payment + admin approval are what make a campaign playable.
    requests.post(f"{BASE}/payments", headers=uhead, timeout=30,
                  json={"campaign_id": campaign["id"], "method": "card", "card_last4": "4242"})
    approved = requests.put(f"{BASE}/admin/campaigns/{campaign['id']}/approve",
                            headers=head, timeout=30)
    assert approved.status_code == 200, approved.text
    return {"screen_id": screen["id"], "media": media, "campaign_id": campaign["id"]}


def test_playlist_survives_a_wiped_disk(ctx):
    sid, media = ctx["screen_id"], ctx["media"]
    before = requests.get(f"{BASE}/player/{sid}/playlist", timeout=30).json()
    assert before["total_items"] >= 1, before

    detail = requests.get(f"{BASE}/media/{media['id']}", timeout=30).json()
    stored = detail.get("stored_filename")
    if not stored or not os.path.isfile(os.path.join(MEDIA_DIR, stored)):
        pytest.skip("this deployment does not keep a disk copy to remove")

    path = os.path.join(MEDIA_DIR, stored)
    backup = path + ".bak"
    os.rename(path, backup)
    try:
        after = requests.get(f"{BASE}/player/{sid}/playlist", timeout=30).json()
        assert after["total_items"] == before["total_items"], (
            "the item was dropped even though Mongo still holds the bytes")
        # And the bytes are actually served.
        served = requests.get(f"{BASE}/player/media/{media['id']}", timeout=60)
        assert served.status_code == 200, served.text
        assert len(served.content) > 100
    finally:
        os.rename(backup, path)
