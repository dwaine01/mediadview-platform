# Campaign Scheduler Tests — MediaView Fase 3
# Tests: state machine transitions, idempotency, concurrency, playlist filtering
# TEST-1 through TEST-10 as specified in review_request

import asyncio
import uuid
from datetime import datetime, timedelta

import motor.motor_asyncio
import pytest
import requests

BASE_URL = "https://menu-studio-3.preview.emergentagent.com"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "mediaview_db"

# PUBLIC_ADVERTISING screen IDs (verified in DB)
SCREEN_MIAMI = "d2643527-d359-441d-afc2-f51b0812d76b"
SCREEN_NY = "b51e3122-fe52-4def-b17f-1f84c9a62550"
SCREEN_RBAC = "c1f1b2ef-0231-475b-8a9c-1c089e82514d"

# Dates
TODAY = datetime.utcnow().strftime("%Y-%m-%d")
PAST = (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d")
PAST_2 = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
FUTURE = (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%d")
FUTURE_2 = (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    """Get admin JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "rbac.mwadmin@test.com",
        "password": "RbacTest#2026"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def db_client():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_campaign(name, status, start_date, end_date, payment_status="mocked_paid", screens=None):
    """Build a minimal ad_campaign document for direct DB insertion."""
    if screens is None:
        screens = [SCREEN_MIAMI]
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "status": status,
        "payment_status": payment_status,
        "start_date": start_date,
        "end_date": end_date,
        "selected_screens": screens,
        "creative_url": "https://example.com/ad.jpg",
        "slot_duration_seconds": 15,
        "advertiser_name": "TEST_Advertiser",
        "created_at": datetime.utcnow(),
    }


def run_scheduler(admin_headers):
    """Helper: POST /api/admin/campaign-scheduler/run-now"""
    resp = requests.post(f"{BASE_URL}/api/admin/campaign-scheduler/run-now", headers=admin_headers)
    assert resp.status_code == 200, f"run-now failed: {resp.text}"
    return resp.json()


def get_campaign_status(db, campaign_id):
    """Get campaign status from MongoDB directly."""
    async def _get():
        c = await db.ad_campaigns.find_one({"id": campaign_id}, {"_id": 0, "status": 1})
        return c["status"] if c else None
    return run_async(_get())


def get_transition_count(db, campaign_id):
    """Count transitions for a campaign in campaign_transitions."""
    async def _get():
        return await db.campaign_transitions.count_documents({"campaign_id": campaign_id})
    return run_async(_get())


def insert_campaign(db, doc):
    async def _ins():
        await db.ad_campaigns.insert_one(doc)
    run_async(_ins())


def delete_campaign(db, campaign_id):
    async def _del():
        await db.ad_campaigns.delete_one({"id": campaign_id})
        await db.campaign_transitions.delete_many({"campaign_id": campaign_id})
    run_async(_del())


# ── TEST-1: APPROVED + future start_date → SCHEDULED ──────────────────────────

class TestT1ApprovedToScheduled:
    """TEST-1: APPROVED with future start_date → scheduler makes APPROVED→SCHEDULED"""

    def test_approved_to_scheduled(self, admin_headers, db_client):
        c = make_campaign("TEST_T1_Approved_Future", "APPROVED", FUTURE, FUTURE_2)
        insert_campaign(db_client, c)
        try:
            result = run_scheduler(admin_headers)
            new_status = get_campaign_status(db_client, c["id"])
            assert new_status == "SCHEDULED", f"Expected SCHEDULED, got {new_status}"
            # Verify transition logged
            count = get_transition_count(db_client, c["id"])
            assert count >= 1, "No transition logged in campaign_transitions"
            # Find transition details
            async def _get_transition():
                return await db_client.campaign_transitions.find_one({"campaign_id": c["id"]}, {"_id": 0})
            t = run_async(_get_transition())
            assert t["old_status"] == "APPROVED"
            assert t["new_status"] == "SCHEDULED"
            print(f"TEST-1 PASS: APPROVED→SCHEDULED for campaign {c['id']}")
        finally:
            delete_campaign(db_client, c["id"])


# ── TEST-2: SCHEDULED + start_date today → ACTIVE ─────────────────────────────

class TestT2ScheduledToActive:
    """TEST-2: SCHEDULED with start_date=today (<=today) → scheduler makes SCHEDULED→ACTIVE"""

    def test_scheduled_to_active(self, admin_headers, db_client):
        c = make_campaign("TEST_T2_Scheduled_Today", "SCHEDULED", TODAY, FUTURE)
        insert_campaign(db_client, c)
        try:
            run_scheduler(admin_headers)
            new_status = get_campaign_status(db_client, c["id"])
            assert new_status == "ACTIVE", f"Expected ACTIVE, got {new_status}"
            t = run_async(db_client.campaign_transitions.find_one({"campaign_id": c["id"]}, {"_id": 0}))
            assert t is not None, "No transition logged"
            assert t["old_status"] == "SCHEDULED"
            assert t["new_status"] == "ACTIVE"
            print(f"TEST-2 PASS: SCHEDULED→ACTIVE for campaign {c['id']}")
        finally:
            delete_campaign(db_client, c["id"])


# ── TEST-3: ACTIVE campaign appears in playlist with is_ad=true ───────────────

class TestT3ActiveInPlaylist:
    """TEST-3: ACTIVE campaign with screen_id → appears in GET /api/player/{screen_id}/playlist with is_ad=True"""

    def test_active_in_playlist(self, admin_headers, db_client):
        c = make_campaign("TEST_T3_Active_Playlist", "ACTIVE", PAST, FUTURE, screens=[SCREEN_MIAMI])
        insert_campaign(db_client, c)
        try:
            resp = requests.get(f"{BASE_URL}/api/player/{SCREEN_MIAMI}/playlist")
            assert resp.status_code == 200, f"Playlist GET failed: {resp.text}"
            data = resp.json()
            items = data.get("items") or data.get("playlist") or []
            ad_items = [i for i in items if i.get("is_ad") and f"ad:{c['id']}" == i.get("campaign_id")]
            assert len(ad_items) >= 1, f"Active campaign not found in playlist. Items: {items}"
            print("TEST-3 PASS: Active campaign appears in playlist with is_ad=true")
        finally:
            delete_campaign(db_client, c["id"])


# ── TEST-4: ACTIVE + past end_date → COMPLETED ────────────────────────────────

class TestT4ActiveToCompleted:
    """TEST-4: ACTIVE campaign with end_date<=today → scheduler makes ACTIVE→COMPLETED"""

    def test_active_to_completed(self, admin_headers, db_client):
        c = make_campaign("TEST_T4_Active_Expired", "ACTIVE", PAST_2, PAST)
        insert_campaign(db_client, c)
        try:
            run_scheduler(admin_headers)
            new_status = get_campaign_status(db_client, c["id"])
            assert new_status == "COMPLETED", f"Expected COMPLETED, got {new_status}"
            t = run_async(db_client.campaign_transitions.find_one({"campaign_id": c["id"]}, {"_id": 0}))
            assert t is not None, "No transition logged"
            assert t["old_status"] == "ACTIVE"
            assert t["new_status"] == "COMPLETED"
            print(f"TEST-4 PASS: ACTIVE→COMPLETED for campaign {c['id']}")
        finally:
            delete_campaign(db_client, c["id"])


# ── TEST-5: COMPLETED campaign NOT in playlist ────────────────────────────────

class TestT5CompletedNotInPlaylist:
    """TEST-5: COMPLETED campaign does NOT appear in GET /api/player/{screen_id}/playlist"""

    def test_completed_not_in_playlist(self, db_client):
        c = make_campaign("TEST_T5_Completed_Playlist", "COMPLETED", PAST_2, PAST, screens=[SCREEN_MIAMI])
        insert_campaign(db_client, c)
        try:
            resp = requests.get(f"{BASE_URL}/api/player/{SCREEN_MIAMI}/playlist")
            assert resp.status_code == 200
            data = resp.json()
            items = data.get("items") or data.get("playlist") or []
            ad_items = [i for i in items if f"ad:{c['id']}" == i.get("campaign_id")]
            assert len(ad_items) == 0, f"COMPLETED campaign should NOT be in playlist: {ad_items}"
            print("TEST-5 PASS: COMPLETED campaign excluded from playlist")
        finally:
            delete_campaign(db_client, c["id"])


# ── TEST-6: REJECTED campaign stays REJECTED ──────────────────────────────────

class TestT6RejectedStaysRejected:
    """TEST-6: REJECTED campaign with past start_date → stays REJECTED (never auto-activated)"""

    def test_rejected_stays_rejected(self, admin_headers, db_client):
        c = make_campaign("TEST_T6_Rejected", "REJECTED", PAST, FUTURE)
        insert_campaign(db_client, c)
        try:
            run_scheduler(admin_headers)
            new_status = get_campaign_status(db_client, c["id"])
            assert new_status == "REJECTED", f"Expected REJECTED, got {new_status}"
            count = get_transition_count(db_client, c["id"])
            assert count == 0, f"REJECTED campaign should not have transitions, got {count}"
            print("TEST-6 PASS: REJECTED campaign stays REJECTED")
        finally:
            delete_campaign(db_client, c["id"])


# ── TEST-7: PENDING_REVIEW not activated ──────────────────────────────────────

class TestT7PendingReviewNotActivated:
    """TEST-7: PENDING_REVIEW with past start_date → NOT activated"""

    def test_pending_review_not_activated(self, admin_headers, db_client):
        c = make_campaign("TEST_T7_PendingReview", "PENDING_REVIEW", PAST, FUTURE)
        insert_campaign(db_client, c)
        try:
            run_scheduler(admin_headers)
            new_status = get_campaign_status(db_client, c["id"])
            assert new_status == "PENDING_REVIEW", f"Expected PENDING_REVIEW, got {new_status}"
            count = get_transition_count(db_client, c["id"])
            assert count == 0, f"PENDING_REVIEW should not have transitions, got {count}"
            print("TEST-7 PASS: PENDING_REVIEW stays PENDING_REVIEW")
        finally:
            delete_campaign(db_client, c["id"])


# ── TEST-8: Idempotency — 3 runs with no pending changes → 0 transitions ──────

class TestT8Idempotency:
    """TEST-8: Run scheduler 3 times with no pending transitions → 0 on runs 2 and 3"""

    def test_idempotency(self, admin_headers, db_client):
        # Run #1 may have transitions from existing data — that's fine
        run_scheduler(admin_headers)
        # Run #2
        result2 = run_scheduler(admin_headers)
        # Run #3
        result3 = run_scheduler(admin_headers)
        # Both run 2 and 3 should have 0 transitions (assuming no new campaigns appeared)
        t2 = result2["result"]["total"]
        t3 = result3["result"]["total"]
        assert t2 == 0, f"Run 2 should have 0 transitions, got {t2}"
        assert t3 == 0, f"Run 3 should have 0 transitions, got {t3}"
        print("TEST-8 PASS: Idempotency confirmed — runs 2 and 3 have 0 transitions")


# ── TEST-9: Concurrency — only 1 transition for same campaign ─────────────────

class TestT9Concurrency:
    """TEST-9: Two concurrent /run-now calls → only 1 transition for a campaign"""

    def test_concurrent_scheduler_runs(self, admin_headers, db_client):
        c = make_campaign("TEST_T9_Concurrent", "APPROVED", TODAY, FUTURE)
        insert_campaign(db_client, c)
        try:
            # Fire two concurrent requests
            import concurrent.futures
            def call_run_now():
                return requests.post(
                    f"{BASE_URL}/api/admin/campaign-scheduler/run-now",
                    headers=admin_headers
                )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(call_run_now), executor.submit(call_run_now)]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]

            for r in results:
                assert r.status_code == 200, f"run-now failed: {r.text}"

            # Verify exactly 1 transition in campaign_transitions
            count = get_transition_count(db_client, c["id"])
            assert count == 1, f"Expected exactly 1 transition, got {count}"

            # Verify final status is ACTIVE (start_date is today)
            final_status = get_campaign_status(db_client, c["id"])
            assert final_status == "ACTIVE", f"Expected ACTIVE after concurrent runs, got {final_status}"
            print(f"TEST-9 PASS: Concurrent runs produced exactly 1 transition. Count={count}")
        finally:
            delete_campaign(db_client, c["id"])


# ── TEST-10: Campaign targeting 3 screens → appears in all 3 playlists when ACTIVE ──

class TestT10MultiScreenCampaign:
    """TEST-10: Campaign targeting 3 screens → appears in all 3 when ACTIVE, disappears when COMPLETED"""

    def test_multi_screen_active_and_completed(self, admin_headers, db_client):
        screens = [SCREEN_MIAMI, SCREEN_NY, SCREEN_RBAC]
        c = make_campaign("TEST_T10_MultiScreen", "APPROVED", TODAY, FUTURE, screens=screens)
        insert_campaign(db_client, c)
        try:
            # Activate the campaign
            run_scheduler(admin_headers)
            final_status = get_campaign_status(db_client, c["id"])
            assert final_status == "ACTIVE", f"Expected ACTIVE, got {final_status}"

            # Check all 3 playlists contain the ad
            for screen_id in screens:
                resp = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist")
                assert resp.status_code == 200
                data = resp.json()
                items = data.get("items") or data.get("playlist") or []
                ad_items = [i for i in items if f"ad:{c['id']}" == i.get("campaign_id")]
                assert len(ad_items) >= 1, f"ACTIVE campaign not in playlist for screen {screen_id}"

            # Now complete the campaign by setting end_date to past
            async def _expire():
                await db_client.ad_campaigns.update_one(
                    {"id": c["id"]},
                    {"$set": {"status": "ACTIVE", "end_date": PAST}}
                )
            run_async(_expire())

            run_scheduler(admin_headers)
            final_status = get_campaign_status(db_client, c["id"])
            assert final_status == "COMPLETED", f"Expected COMPLETED, got {final_status}"

            # Verify COMPLETED campaign NOT in any of the 3 playlists
            for screen_id in screens:
                resp = requests.get(f"{BASE_URL}/api/player/{screen_id}/playlist")
                assert resp.status_code == 200
                data = resp.json()
                items = data.get("items") or data.get("playlist") or []
                ad_items = [i for i in items if f"ad:{c['id']}" == i.get("campaign_id")]
                assert len(ad_items) == 0, f"COMPLETED campaign still in playlist for screen {screen_id}"

            print("TEST-10 PASS: Multi-screen campaign appears in all 3 playlists when ACTIVE, disappears when COMPLETED")
        finally:
            delete_campaign(db_client, c["id"])


# ── TEST: Scheduler status endpoint ───────────────────────────────────────────

class TestSchedulerStatus:
    """Scheduler status endpoint returns expected fields."""

    def test_scheduler_status(self, admin_headers):
        resp = requests.get(f"{BASE_URL}/api/admin/campaign-scheduler/status", headers=admin_headers)
        assert resp.status_code == 200, f"Status failed: {resp.text}"
        data = resp.json()
        assert "scheduler_running" in data
        assert data["scheduler_running"] is True
        assert "counts" in data
        assert "APPROVED" in data["counts"]
        assert "ACTIVE" in data["counts"]
        assert "COMPLETED" in data["counts"]
        print(f"Scheduler status: running={data['scheduler_running']}, counts={data['counts']}")
