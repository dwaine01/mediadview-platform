"""
Phase 2C P1 — Backend tests: Landing, Plans API, Workspace Context, Workspace sub-routes
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/')

@pytest.fixture
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s

@pytest.fixture
def ws_token(session):
    """Login as workspace user and return bearer token"""
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "testws@test.com",
        "password": "Test1234!"
    })
    if resp.status_code != 200:
        pytest.skip(f"Login failed: {resp.status_code} {resp.text}")
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return token

# ── Plans API (public, no auth) ─────────────────────────────────────────

class TestPlansPublic:
    def test_get_plans_returns_200(self, session):
        resp = session.get(f"{BASE_URL}/api/plans")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_get_plans_returns_4_plans(self, session):
        resp = session.get(f"{BASE_URL}/api/plans")
        assert resp.status_code == 200
        data = resp.json()
        plans = data if isinstance(data, list) else data.get("plans", [])
        assert len(plans) >= 4, f"Expected 4 plans, got {len(plans)}"

    def test_plan_ids_include_expected(self, session):
        resp = session.get(f"{BASE_URL}/api/plans")
        data = resp.json()
        plans = data if isinstance(data, list) else data.get("plans", [])
        ids = [p.get("plan_id") for p in plans]
        for expected in ["free", "starter", "pro", "enterprise"]:
            assert expected in ids, f"Plan '{expected}' missing from {ids}"

    def test_plans_response_time(self, session):
        start = time.time()
        session.get(f"{BASE_URL}/api/plans")
        elapsed = time.time() - start
        assert elapsed < 2.0, f"Plans API took {elapsed:.2f}s (>2s)"

# ── Workspace Context ────────────────────────────────────────────────────

class TestWorkspaceContext:
    def test_context_requires_auth(self, session):
        resp = session.get(f"{BASE_URL}/api/workspace/context")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"

    def test_context_returns_200_for_ws_user(self, session, ws_token):
        session.headers["Authorization"] = f"Bearer {ws_token}"
        start = time.time()
        resp = session.get(f"{BASE_URL}/api/workspace/context")
        elapsed = time.time() - start
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        assert elapsed < 2.0, f"Context took {elapsed:.2f}s (>2s)"

    def test_context_has_required_fields(self, session, ws_token):
        session.headers["Authorization"] = f"Bearer {ws_token}"
        resp = session.get(f"{BASE_URL}/api/workspace/context")
        data = resp.json()
        for field in ["organization", "stats"]:
            assert field in data, f"Field '{field}' missing from context"

    def test_context_stats_has_screens_users_devices(self, session, ws_token):
        session.headers["Authorization"] = f"Bearer {ws_token}"
        resp = session.get(f"{BASE_URL}/api/workspace/context")
        stats = resp.json().get("stats", {})
        for key in ["screens", "users", "devices"]:
            assert key in stats, f"Stats missing '{key}'"

    def test_context_has_organization_name(self, session, ws_token):
        session.headers["Authorization"] = f"Bearer {ws_token}"
        resp = session.get(f"{BASE_URL}/api/workspace/context")
        org = resp.json().get("organization") or {}
        assert org.get("name"), "Organization name should not be empty"

# ── Workspace sub-routes ─────────────────────────────────────────────────

class TestWorkspaceSubRoutes:
    def test_screens_list(self, session, ws_token):
        session.headers["Authorization"] = f"Bearer {ws_token}"
        resp = session.get(f"{BASE_URL}/api/workspace/screens")
        assert resp.status_code == 200, f"Screens list: {resp.status_code} {resp.text}"

    def test_menus_list(self, session, ws_token):
        session.headers["Authorization"] = f"Bearer {ws_token}"
        resp = session.get(f"{BASE_URL}/api/workspace/menus")
        assert resp.status_code == 200, f"Menus list: {resp.status_code} {resp.text}"

    def test_billing(self, session, ws_token):
        session.headers["Authorization"] = f"Bearer {ws_token}"
        resp = session.get(f"{BASE_URL}/api/workspace/billing")
        assert resp.status_code == 200, f"Billing: {resp.status_code} {resp.text}"

    def test_billing_has_plan_config(self, session, ws_token):
        session.headers["Authorization"] = f"Bearer {ws_token}"
        resp = session.get(f"{BASE_URL}/api/workspace/billing")
        data = resp.json()
        assert "subscription" in data or "plan_config" in data, "Billing should have subscription or plan_config"

    def test_screens_list_is_array(self, session, ws_token):
        session.headers["Authorization"] = f"Bearer {ws_token}"
        resp = session.get(f"{BASE_URL}/api/workspace/screens")
        data = resp.json()
        assert isinstance(data, list), f"Screens should be a list, got {type(data)}"

    def test_menus_list_is_array(self, session, ws_token):
        session.headers["Authorization"] = f"Bearer {ws_token}"
        resp = session.get(f"{BASE_URL}/api/workspace/menus")
        data = resp.json()
        assert isinstance(data, list), f"Menus should be a list, got {type(data)}"
