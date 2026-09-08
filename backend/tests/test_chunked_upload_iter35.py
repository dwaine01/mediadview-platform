"""Chunked media upload for videos (iteración 35).

The marketplace failed with "Load failed" when a customer picked a phone video:
the base64 JSON endpoint needs the whole file in memory and the request dies at
the proxy. Videos now go up in 2 MB chunks.
"""
import os
import uuid

import pytest
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001") + "/api"
# Sin MEDIA_DIR, usa la carpeta media del propio repo (en CI no existe /app).
MEDIA_DIR = os.environ.get("MEDIA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media")


def _sample_video():
    videos = sorted(
        (os.path.join(MEDIA_DIR, f) for f in os.listdir(MEDIA_DIR) if f.endswith(".mp4")),
        key=os.path.getsize)
    if not videos:
        pytest.skip("no sample mp4 available in this environment")
    return open(videos[0], "rb").read()


@pytest.fixture(scope="module")
def customer():
    email = f"chunk_{uuid.uuid4().hex[:8]}@test.com"
    r = requests.post(f"{BASE}/auth/register", timeout=30, json={
        "name": "Chunk Tester", "email": email, "password": "Passw0rd!",
        "company_name": "Videos SA",
    })
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _upload_in_chunks(head, payload, filename="clip.mp4", mime="video/mp4",
                      width=1080, height=1920, duration=20.0):
    init = requests.post(f"{BASE}/media/chunk/init", headers=head, timeout=30, json={
        "filename": filename, "content_type": mime, "size": len(payload),
        "width": width, "height": height, "duration_seconds": duration,
    })
    assert init.status_code == 200, init.text
    body = init.json()
    size = body["chunk_size"]
    for off in range(0, len(payload), size):
        r = requests.post(f"{BASE}/media/chunk/{body['upload_id']}", timeout=120,
                          headers={**head, "Content-Type": "application/octet-stream"},
                          data=payload[off:off + size])
        assert r.status_code == 200, r.text
    return body["upload_id"], requests.post(
        f"{BASE}/media/chunk/{body['upload_id']}/complete", headers=head, timeout=120)


def test_video_uploads_in_chunks_and_is_served_back(customer):
    raw = _sample_video()
    _uid, done = _upload_in_chunks(customer, raw)
    assert done.status_code == 200, done.text
    media = done.json()
    assert media["type"] == "video"
    assert media["size"] == len(raw)
    assert media["orientation"] == "portrait"

    served = requests.get(f"{BASE}/player/media/{media['id']}", timeout=120)
    assert served.status_code == 200
    assert served.content == raw, "the reassembled file differs from the original"


def test_progress_is_reported_per_chunk(customer):
    raw = _sample_video()
    init = requests.post(f"{BASE}/media/chunk/init", headers=customer, timeout=30, json={
        "filename": "clip.mp4", "content_type": "video/mp4", "size": len(raw),
        "width": 1920, "height": 1080, "duration_seconds": 12.0,
    }).json()
    percents = []
    for off in range(0, len(raw), init["chunk_size"]):
        r = requests.post(f"{BASE}/media/chunk/{init['upload_id']}", timeout=120,
                          headers={**customer, "Content-Type": "application/octet-stream"},
                          data=raw[off:off + init["chunk_size"]])
        percents.append(r.json()["percent"])
    assert percents == sorted(percents) and percents[-1] == 100.0, percents


def test_oversized_video_is_rejected_before_any_byte_moves(customer):
    r = requests.post(f"{BASE}/media/chunk/init", headers=customer, timeout=30, json={
        "filename": "huge.mp4", "content_type": "video/mp4",
        "size": 900 * 1024 * 1024, "duration_seconds": 30.0,
    })
    assert r.status_code == 400, r.text
    assert "max" in r.text.lower()


def test_disallowed_type_is_rejected_at_init(customer):
    r = requests.post(f"{BASE}/media/chunk/init", headers=customer, timeout=30, json={
        "filename": "malware.exe", "content_type": "application/octet-stream", "size": 1024,
    })
    assert r.status_code in (400, 415), r.text


def test_truncated_upload_does_not_create_media(customer):
    raw = _sample_video()
    init = requests.post(f"{BASE}/media/chunk/init", headers=customer, timeout=30, json={
        "filename": "clip.mp4", "content_type": "video/mp4", "size": len(raw),
        "width": 1080, "height": 1920, "duration_seconds": 10.0,
    }).json()
    requests.post(f"{BASE}/media/chunk/{init['upload_id']}", timeout=120,
                  headers={**customer, "Content-Type": "application/octet-stream"},
                  data=raw[:1024])
    done = requests.post(f"{BASE}/media/chunk/{init['upload_id']}/complete",
                         headers=customer, timeout=60)
    assert done.status_code == 400, done.text
    assert "incomplete" in done.text.lower()


def test_fake_video_bytes_are_rejected_on_complete(customer):
    fake = b"this is definitely not a video" * 40
    init = requests.post(f"{BASE}/media/chunk/init", headers=customer, timeout=30, json={
        "filename": "clip.mp4", "content_type": "video/mp4", "size": len(fake),
        "width": 1080, "height": 1920, "duration_seconds": 5.0,
    }).json()
    requests.post(f"{BASE}/media/chunk/{init['upload_id']}", timeout=60,
                  headers={**customer, "Content-Type": "application/octet-stream"}, data=fake)
    done = requests.post(f"{BASE}/media/chunk/{init['upload_id']}/complete",
                         headers=customer, timeout=60)
    assert done.status_code == 415, done.text


def test_a_chunked_video_can_be_published_on_a_matching_screen(customer):
    admin = requests.post(f"{BASE}/auth/v2/login", timeout=30, json={
        "email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}).json()["access_token"]
    screen = requests.post(f"{BASE}/admin/screens", timeout=30,
                           headers={"Authorization": f"Bearer {admin}"}, json={
        "name": f"VIDEO {uuid.uuid4().hex[:4]}",
        "location": {"city": "Video City", "address": "1 St", "state": "VC"},
        "specs": {"size": "55in", "type": "LED", "resolution": "1080x1920",
                  "orientation": "portrait"},
        "operation_type": "PUBLIC_ADVERTISING",
    }).json()

    raw = _sample_video()
    _uid, done = _upload_in_chunks(customer, raw)
    media_id = done.json()["id"]

    published = requests.post(f"{BASE}/campaigns", headers=customer, timeout=30, json={
        "name": "Video promo", "screen_id": screen["id"],
        "schedule": {"start_date": None, "end_date": None, "start_time": "00:00",
                     "end_time": "23:59", "slot_duration": 15, "frequency": 5},
        "media_ids": [media_id],
    })
    assert published.status_code == 200, published.text
    assert published.json()["media_ids"] == [media_id]
