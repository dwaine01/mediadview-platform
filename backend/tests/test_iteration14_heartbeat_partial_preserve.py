"""Iteration 14 regression tests for heartbeat partial updates."""

import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_ENV = BACKEND_DIR.parent / "frontend" / ".env"


def _public_base_url() -> str:
    env = dotenv_values(FRONTEND_ENV)
    base_url = (
        os.environ.get("TEST_BASE_URL")
        or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
        or env.get("EXPO_PUBLIC_BACKEND_URL")
    )
    if not base_url:
        pytest.fail("TEST_BASE_URL/EXPO_PUBLIC_BACKEND_URL is missing")
    return base_url.rstrip("/")


BASE_URL = _public_base_url()
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture
def api_session():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def mongo_db():
    if not MONGO_URL or not DB_NAME:
        pytest.fail("MONGO_URL/DB_NAME missing in environment")
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        yield db
    finally:
        client.close()


# device heartbeat module: full heartbeat followed by partial heartbeat should preserve diagnostics
def test_partial_heartbeat_preserves_existing_diagnostics_fields(api_session, mongo_db):
    device_id = f"TEST-it14-{uuid.uuid4().hex[:10]}"
    screen_id = f"TEST-it14-screen-{uuid.uuid4().hex[:10]}"
    mongo_db.devices.insert_one({"id": device_id, "screen_id": screen_id, "status": "active"})

    try:
        full = api_session.post(
            f"{BASE_URL}/api/devices/{device_id}/heartbeat",
            json={
                "status": "online",
                "device_id": device_id,
                "screen_id": screen_id,
                "current_playlist": "playlist:it14",
                "current_media_id": "media:it14",
                "resolution": "1920x1080",
                "orientation": "landscape",
            },
            timeout=20,
        )
        assert full.status_code == 200, full.text

        partial = api_session.post(
            f"{BASE_URL}/api/devices/{device_id}/heartbeat",
            json={"status": "online", "device_id": device_id, "screen_id": screen_id},
            timeout=20,
        )
        assert partial.status_code == 200, partial.text

        diagnostics = mongo_db.devices.find_one({"id": device_id}, {"_id": 0, "diagnostics": 1})["diagnostics"]
        assert diagnostics["current_playlist"] == "playlist:it14"
        assert diagnostics["current_media_id"] == "media:it14"
        assert diagnostics["resolution"] == "1920x1080"
        assert diagnostics["orientation"] == "landscape"

        # Ensure partial heartbeat did not write nulls for untouched fields
        assert diagnostics.get("current_playlist") is not None
        assert diagnostics.get("current_media_id") is not None
        assert diagnostics.get("resolution") is not None
        assert diagnostics.get("orientation") is not None
    finally:
        mongo_db.devices.delete_many({"id": device_id})
