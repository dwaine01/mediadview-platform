"""Iteración 36 — Video en el panel: miniatura, disponibilidad y reproducción.

Verifies the fix for the two bugs reported by the MediaView owner:
  1. Panel showed empty box for videos (rendered inside <img>).
  2. Uploaded video never played because its file was gone from ephemeral disk.

Backend side of the fix exposes:
  - /api/admin/campaigns  →  media_info[] with type/orientation/available booleans
  - /api/admin/campaigns  →  media_available flag (all files still there)

Also re-checks:
  - Approved video shows up in /api/player/{screen}/playlist and its bytes are served.
  - Chunk retries with the SAME X-Chunk-Offset are idempotent (no duplicated bytes).
  - Small images still upload via the legacy /api/media/upload path.
  - Orientation mismatch still blocks campaign creation.
"""
import base64
import io
import os
import uuid

import pytest
import requests
from PIL import Image

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001") + "/api"
# Sin MEDIA_DIR, usa la carpeta media del propio repo (en CI no existe /app).
MEDIA_DIR = os.environ.get("MEDIA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media")
ADMIN = {"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}


# ─────────────────────────────────────────────────────────────────────────────
# helpers / fixtures

def _sample_video_bytes():
    files = sorted(
        (os.path.join(MEDIA_DIR, f) for f in os.listdir(MEDIA_DIR) if f.endswith(".mp4")),
        key=os.path.getsize,
    )
    if not files:
        pytest.skip("no mp4 sample available")
    with open(files[0], "rb") as fh:
        return fh.read()


def _png_b64(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 120, 220)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(scope="module")
def admin_head():
    r = requests.post(f"{BASE}/auth/v2/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def customer_head():
    email = f"iter36_{uuid.uuid4().hex[:8]}@test.com"
    r = requests.post(f"{BASE}/auth/register", timeout=30, json={
        "name": "Iter36 Customer", "email": email,
        "password": "Passw0rd!", "company_name": "Iter36 SA",
    })
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def portrait_screen(admin_head):
    r = requests.post(f"{BASE}/admin/screens", headers=admin_head, timeout=30, json={
        "name": f"ITER36 P {uuid.uuid4().hex[:4]}",
        "location": {"city": "TestVille", "address": "1 St", "state": "TS"},
        "specs": {"size": "55in", "type": "LED", "resolution": "1080x1920",
                  "orientation": "portrait"},
        "operation_type": "PUBLIC_ADVERTISING",
    })
    r.raise_for_status()
    return r.json()


def _upload_video_chunked(head, payload, filename="clip.mp4", w=1080, h=1920, dur=15.0):
    init = requests.post(f"{BASE}/media/chunk/init", headers=head, timeout=30, json={
        "filename": filename, "content_type": "video/mp4",
        "size": len(payload), "width": w, "height": h, "duration_seconds": dur,
    })
    assert init.status_code == 200, init.text
    body = init.json()
    csize = body["chunk_size"]
    upload_id = body["upload_id"]
    for off in range(0, len(payload), csize):
        r = requests.post(
            f"{BASE}/media/chunk/{upload_id}",
            headers={**head, "Content-Type": "application/octet-stream",
                     "X-Chunk-Offset": str(off)},
            data=payload[off:off + csize], timeout=120,
        )
        assert r.status_code == 200, r.text
    done = requests.post(f"{BASE}/media/chunk/{upload_id}/complete",
                         headers=head, timeout=120)
    assert done.status_code == 200, done.text
    return done.json()


@pytest.fixture(scope="module")
def pending_video_campaign(customer_head, portrait_screen):
    raw = _sample_video_bytes()
    media = _upload_video_chunked(customer_head, raw)
    campaign = requests.post(f"{BASE}/campaigns", headers=customer_head, timeout=30, json={
        "name": "Iter36 promo",
        "screen_id": portrait_screen["id"],
        "schedule": {"start_date": None, "end_date": None, "start_time": "00:00",
                     "end_time": "23:59", "slot_duration": 15, "frequency": 5},
        "media_ids": [media["id"]],
    })
    assert campaign.status_code == 200, campaign.text
    campaign = campaign.json()
    pay = requests.post(f"{BASE}/payments", headers=customer_head, timeout=30, json={
        "campaign_id": campaign["id"], "method": "card", "card_last4": "4242"})
    assert pay.status_code == 200, pay.text
    return {"campaign": campaign, "media": media, "raw": raw}


# ─────────────────────────────────────────────────────────────────────────────
# admin_list_campaigns: media_info + media_available

class TestAdminCampaignsMediaInfo:

    def test_pending_video_campaign_reports_media_info(self, admin_head, pending_video_campaign):
        cid = pending_video_campaign["campaign"]["id"]
        mid = pending_video_campaign["media"]["id"]
        r = requests.get(f"{BASE}/admin/campaigns", headers=admin_head, timeout=30)
        assert r.status_code == 200, r.text
        row = next((c for c in r.json() if c["id"] == cid), None)
        assert row is not None, "campaign missing from admin listing"
        # New fields
        assert "media_info" in row and isinstance(row["media_info"], list)
        assert "media_available" in row
        info = next((i for i in row["media_info"] if i["id"] == mid), None)
        assert info is not None
        assert info["type"] == "video"
        assert info["content_type"].startswith("video/")
        assert info["orientation"] == "portrait"
        assert info["available"] is True
        assert row["media_available"] is True

    def test_media_available_flips_to_false_when_file_disappears(
            self, admin_head, pending_video_campaign):
        mid = pending_video_campaign["media"]["id"]
        cid = pending_video_campaign["campaign"]["id"]
        # We need the stored_filename to move it out of the way.
        detail = requests.get(f"{BASE}/media/{mid}", timeout=30).json()
        stored = detail.get("stored_filename")
        if not stored:
            pytest.skip("no stored_filename on this deployment")
        path = os.path.join(MEDIA_DIR, stored)
        if not os.path.isfile(path):
            pytest.skip("stored file missing before the test starts")
        # Confirm the media has no inline base64 mirror (so removing the disk
        # copy really makes it unavailable).
        # We rely on the chunked upload path which sets data=None.
        backup = path + ".gone"
        os.rename(path, backup)
        try:
            r = requests.get(f"{BASE}/admin/campaigns", headers=admin_head, timeout=30)
            row = next(c for c in r.json() if c["id"] == cid)
            info = next(i for i in row["media_info"] if i["id"] == mid)
            assert info["available"] is False, (
                "media_available should be False when the disk copy is gone "
                "and no inline bytes exist")
            assert row["media_available"] is False
        finally:
            os.rename(backup, path)
        # Sanity: restored → available again.
        r = requests.get(f"{BASE}/admin/campaigns", headers=admin_head, timeout=30)
        row = next(c for c in r.json() if c["id"] == cid)
        info = next(i for i in row["media_info"] if i["id"] == mid)
        assert info["available"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Approved video → playlist → bytes

class TestPlayerVideoPipeline:

    def test_approved_video_shows_up_in_playlist_and_bytes_are_served(
            self, admin_head, pending_video_campaign, portrait_screen):
        cid = pending_video_campaign["campaign"]["id"]
        mid = pending_video_campaign["media"]["id"]
        raw = pending_video_campaign["raw"]
        # Approve
        appr = requests.put(f"{BASE}/admin/campaigns/{cid}/approve",
                            headers=admin_head, timeout=30)
        assert appr.status_code == 200, appr.text
        # Playlist
        pl = requests.get(f"{BASE}/player/{portrait_screen['id']}/playlist",
                          timeout=30).json()
        items = pl.get("items", [])
        found = [i for i in items if i.get("media_id") == mid]
        assert found, f"video item missing from playlist: {items}"
        item = found[0]
        assert (item.get("content_type") or "").startswith("video/")
        # Bytes are served
        served = requests.get(f"{BASE}/player/media/{mid}", timeout=120)
        assert served.status_code == 200
        assert served.content == raw, "served bytes differ from the original"


# ─────────────────────────────────────────────────────────────────────────────
# Regression: chunked upload idempotency + legacy image path + orientation gate

class TestChunkedRegression:

    def test_resending_the_same_chunk_does_not_corrupt_the_file(self, customer_head):
        raw = _sample_video_bytes()
        init = requests.post(f"{BASE}/media/chunk/init", headers=customer_head,
                             timeout=30, json={
                                 "filename": "idem.mp4", "content_type": "video/mp4",
                                 "size": len(raw), "width": 1080, "height": 1920,
                                 "duration_seconds": 12.0,
                             }).json()
        uid = init["upload_id"]
        csize = init["chunk_size"]
        # Send chunk 0
        off = 0
        chunk = raw[off:off + csize]
        r1 = requests.post(
            f"{BASE}/media/chunk/{uid}",
            headers={**customer_head, "Content-Type": "application/octet-stream",
                     "X-Chunk-Offset": str(off)},
            data=chunk, timeout=60)
        assert r1.status_code == 200, r1.text
        received_1 = r1.json()["received"]
        # Re-send the SAME chunk with the SAME offset — must be a no-op
        r2 = requests.post(
            f"{BASE}/media/chunk/{uid}",
            headers={**customer_head, "Content-Type": "application/octet-stream",
                     "X-Chunk-Offset": str(off)},
            data=chunk, timeout=60)
        assert r2.status_code == 200, r2.text
        assert r2.json()["received"] == received_1, (
            "duplicated chunk inflated the received counter")
        # Send the remaining chunks
        for o in range(csize, len(raw), csize):
            requests.post(
                f"{BASE}/media/chunk/{uid}",
                headers={**customer_head, "Content-Type": "application/octet-stream",
                         "X-Chunk-Offset": str(o)},
                data=raw[o:o + csize], timeout=120).raise_for_status()
        done = requests.post(f"{BASE}/media/chunk/{uid}/complete",
                             headers=customer_head, timeout=120)
        assert done.status_code == 200, done.text
        media = done.json()
        assert media["size"] == len(raw)
        served = requests.get(f"{BASE}/player/media/{media['id']}", timeout=120)
        assert served.status_code == 200
        assert served.content == raw, "byte-for-byte mismatch after chunk retry"

    def test_small_image_still_uploads_via_legacy_endpoint(self, customer_head):
        payload = _png_b64(1920, 1080)
        r = requests.post(f"{BASE}/media/upload", headers=customer_head, timeout=30,
                          json={"filename": "poster.png", "content_type": "image/png",
                                "data": payload, "width": 1920, "height": 1080})
        assert r.status_code == 200, r.text
        media = r.json()
        assert media["type"] == "image"
        assert media["orientation"] == "landscape"

    def test_orientation_mismatch_still_blocks_campaign_creation(
            self, customer_head, portrait_screen):
        # Landscape image → portrait screen should be rejected.
        img = requests.post(f"{BASE}/media/upload", headers=customer_head, timeout=30,
                            json={"filename": "wide.png", "content_type": "image/png",
                                  "data": _png_b64(1920, 1080),
                                  "width": 1920, "height": 1080}).json()
        r = requests.post(f"{BASE}/campaigns", headers=customer_head, timeout=30, json={
            "name": "bad orientation",
            "screen_id": portrait_screen["id"],
            "schedule": {"start_date": None, "end_date": None, "start_time": "00:00",
                         "end_time": "23:59", "slot_duration": 15, "frequency": 5},
            "media_ids": [img["id"]],
        })
        assert r.status_code in (400, 409, 422), (
            f"orientation gate is off: {r.status_code} {r.text}")
