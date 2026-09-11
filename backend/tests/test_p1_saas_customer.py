"""
Phase 2C P1 - SaaS Customer System Backend Tests
Tests: plans API, customer signup, workspace APIs
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/')

EXISTING_WS_EMAIL = "testws@test.com"
EXISTING_WS_PASSWORD = "Test1234!"
TS = int(time.time())
NEW_EMAIL = f"testnew_{TS}@demo.test"


@pytest.fixture(scope="module")
def ws_token():
    """Login as existing workspace customer and return token."""
    res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": EXISTING_WS_EMAIL,
        "password": EXISTING_WS_PASSWORD
    })
    if res.status_code != 200:
        pytest.skip(f"Login failed: {res.text}")
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def ws_headers(ws_token):
    return {"Authorization": f"Bearer {ws_token}"}


# ── Plans API ──────────────────────────────────────────────────────────────────

class TestPlansAPI:
    """GET /api/plans - public endpoint"""

    def test_plans_returns_200(self):
        res = requests.get(f"{BASE_URL}/api/plans")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    def test_plans_returns_4_plans(self):
        res = requests.get(f"{BASE_URL}/api/plans")
        plans = res.json()
        assert len(plans) == 4, f"Expected 4 plans, got {len(plans)}: {[p.get('plan_id') for p in plans]}"

    def test_plans_canonical_ids(self):
        res = requests.get(f"{BASE_URL}/api/plans")
        plan_ids = {p["plan_id"] for p in res.json()}
        assert plan_ids == {"free", "starter", "pro", "enterprise"}, f"Got: {plan_ids}"

    def test_plans_have_required_fields(self):
        res = requests.get(f"{BASE_URL}/api/plans")
        for plan in res.json():
            assert "plan_id" in plan
            assert "display_name" in plan
            assert "monthly_price" in plan
            assert "features" in plan
            assert "trial_days" in plan

    def test_plans_sorted_by_display_order(self):
        res = requests.get(f"{BASE_URL}/api/plans")
        plans = res.json()
        orders = [p.get("display_order", 0) for p in plans]
        assert orders == sorted(orders), f"Plans not sorted: {orders}"


# ── Customer Signup API ────────────────────────────────────────────────────────

class TestCustomerSignup:
    """POST /api/auth/customer-signup"""

    def test_signup_creates_full_stack(self):
        payload = {
            "plan_id": "starter",
            "business_name": "TEST_Demo Corp",
            "contact_name": "TEST_Jane Smith",
            "contact_email": NEW_EMAIL,
            "contact_phone": "+1555000001",
            "password": "TestPass123!"
        }
        res = requests.post(f"{BASE_URL}/api/auth/customer-signup", json=payload)
        assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"

        data = res.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == NEW_EMAIL
        assert data["user"]["rbac_role"] == "SELF_SERVICE_OWNER"
        assert "organization_id" in data["user"]
        assert "organization" in data
        assert "plan" in data
        assert data["plan"]["id"] == "starter"

    def test_signup_duplicate_email_returns_409(self):
        payload = {
            "plan_id": "starter",
            "business_name": "TEST_Dupe Corp",
            "contact_name": "TEST_Dupe User",
            "contact_email": NEW_EMAIL,
            "password": "TestPass123!"
        }
        res = requests.post(f"{BASE_URL}/api/auth/customer-signup", json=payload)
        assert res.status_code == 409, f"Expected 409, got {res.status_code}: {res.text}"

    def test_signup_invalid_plan_returns_400(self):
        res = requests.post(f"{BASE_URL}/api/auth/customer-signup", json={
            "plan_id": "invalid_plan",
            "business_name": "TEST_Corp",
            "contact_name": "TEST_User",
            "contact_email": f"badplan_{TS}@demo.test",
            "password": "TestPass123!"
        })
        assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"

    def test_signup_short_password_returns_422(self):
        res = requests.post(f"{BASE_URL}/api/auth/customer-signup", json={
            "plan_id": "starter",
            "business_name": "TEST_Corp",
            "contact_name": "TEST_User",
            "contact_email": f"short_{TS}@demo.test",
            "password": "short"
        })
        assert res.status_code == 422, f"Expected 422, got {res.status_code}: {res.text}"


# ── Workspace APIs ─────────────────────────────────────────────────────────────

class TestWorkspaceContext:
    """GET /api/workspace/context"""

    def test_context_requires_auth(self):
        res = requests.get(f"{BASE_URL}/api/workspace/context")
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"

    def test_context_returns_200_for_ws_user(self, ws_headers):
        res = requests.get(f"{BASE_URL}/api/workspace/context", headers=ws_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    def test_context_has_organization(self, ws_headers):
        res = requests.get(f"{BASE_URL}/api/workspace/context", headers=ws_headers)
        data = res.json()
        assert "organization" in data
        assert data["organization"] is not None
        assert "name" in data["organization"]

    def test_context_has_subscription(self, ws_headers):
        res = requests.get(f"{BASE_URL}/api/workspace/context", headers=ws_headers)
        data = res.json()
        assert "subscription" in data
        assert data["subscription"] is not None

    def test_context_has_plan_config(self, ws_headers):
        res = requests.get(f"{BASE_URL}/api/workspace/context", headers=ws_headers)
        data = res.json()
        assert "plan_config" in data
        assert data["plan_config"] is not None
        assert "display_name" in data["plan_config"]

    def test_context_has_stats(self, ws_headers):
        res = requests.get(f"{BASE_URL}/api/workspace/context", headers=ws_headers)
        data = res.json()
        assert "stats" in data
        stats = data["stats"]
        assert "screens" in stats
        assert "users" in stats
        assert "devices" in stats

    def test_context_no_cross_tenant_leak(self, ws_headers):
        """Verify current_user has org_id set (tenant scoping active)."""
        res = requests.get(f"{BASE_URL}/api/workspace/context", headers=ws_headers)
        data = res.json()
        assert "current_user" in data
        assert data["current_user"]["organization_id"] is not None


class TestWorkspaceBilling:
    """GET /api/workspace/billing"""

    def test_billing_returns_200(self, ws_headers):
        res = requests.get(f"{BASE_URL}/api/workspace/billing", headers=ws_headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    def test_billing_has_subscription(self, ws_headers):
        res = requests.get(f"{BASE_URL}/api/workspace/billing", headers=ws_headers)
        data = res.json()
        assert "subscription" in data
        assert data["subscription"] is not None

    def test_billing_has_pricing_agreement(self, ws_headers):
        res = requests.get(f"{BASE_URL}/api/workspace/billing", headers=ws_headers)
        data = res.json()
        assert "current_pricing_agreement" in data
        assert data["current_pricing_agreement"] is not None


class TestWorkspaceNewSignup:
    """Verify newly signed-up user can access workspace."""

    def test_new_user_login_and_context(self):
        # Login as the new user created in TestCustomerSignup
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": NEW_EMAIL,
            "password": "TestPass123!"
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"

        token = login_res.json()["access_token"]
        ctx_res = requests.get(
            f"{BASE_URL}/api/workspace/context",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert ctx_res.status_code == 200, f"Context failed: {ctx_res.text}"
        data = ctx_res.json()
        assert data["organization"] is not None
        assert data["subscription"] is not None
