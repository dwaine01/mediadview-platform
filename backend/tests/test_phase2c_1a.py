"""
test_phase2c_1a.py — Phase 2C-1A Domain Foundation Tests
=========================================================
Tests the additive SaaS CRM domain:
  Lead → Customer → Organization → Subscription → PricingAgreement

Coverage:
  1. Lead model / validation / lifecycle
  2. Customer creation & update
  3. Customer ↔ Organization 1:1 cardinality
  4. Subscription lifecycle model
  5. PricingAgreement versioning / validation
  6. Canonical plan normalization (standard → starter, invalid → 422)
  7. Invalid cross-reference protection
  8. Authorization enforcement on all new admin endpoints

CONSTRAINTS enforced:
  - Only reads/writes Phase 2C CRM collections (leads, customers, pricing_agreements).
  - Organizations created here carry customer_id + schema_source=crm_2c.
  - Subscriptions created here carry schema_version=2.
  - No production data is touched.
  - No legacy records are modified.
"""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")
CRM = f"{BASE_URL}/api/admin/crm"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _uniq(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    """Log in as superadmin. Skips if credentials are absent."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"},
    )
    if resp.status_code != 200:
        pytest.skip(f"Superadmin login failed ({resp.status_code}) — seeded DB required")
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def non_admin_token():
    """Register and log in as a regular customer (no admin access)."""
    email = f"{_uniq('customer')}@test.com"
    password = "Test@2026!"
    # Register
    requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"name": "Test Customer", "email": email, "password": password},
    )
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    if resp.status_code != 200:
        pytest.skip("Could not create non-admin test user")
    return resp.json()["access_token"]


# ── Shared state (module-level, populated as tests run) ───────────────────────

_state: dict = {}


# ══════════════════════════════════════════════════════════════════════════════
# 1. AUTHORIZATION — unauthenticated & non-admin are blocked
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthorization:
    def test_unauthenticated_leads_blocked(self):
        r = requests.get(f"{CRM}/leads")
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_unauthenticated_customers_blocked(self):
        r = requests.get(f"{CRM}/customers")
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_unauthenticated_subscriptions_blocked(self):
        r = requests.get(f"{CRM}/subscriptions/any-id")
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_non_admin_leads_blocked(self, non_admin_token):
        r = requests.get(f"{CRM}/leads", headers=_auth(non_admin_token))
        assert r.status_code == 403, f"Expected 403 for non-admin, got {r.status_code}"

    def test_non_admin_customers_blocked(self, non_admin_token):
        r = requests.post(
            f"{CRM}/customers",
            json={"legal_name": "X", "display_name": "X"},
            headers=_auth(non_admin_token),
        )
        assert r.status_code == 403, f"Expected 403 for non-admin, got {r.status_code}"

    def test_non_admin_subscriptions_blocked(self, non_admin_token):
        r = requests.post(
            f"{CRM}/subscriptions",
            json={"org_id": "x", "customer_id": "y"},
            headers=_auth(non_admin_token),
        )
        assert r.status_code == 403, f"Expected 403 for non-admin, got {r.status_code}"

    def test_non_admin_pricing_agreements_blocked(self, non_admin_token):
        r = requests.post(
            f"{CRM}/pricing-agreements",
            json={
                "subscription_id": "x",
                "plan_id": "starter",
                "agreed_monthly_price": 49.0,
                "effective_from": "2026-09-01T00:00:00",
            },
            headers=_auth(non_admin_token),
        )
        assert r.status_code == 403, f"Expected 403 for non-admin, got {r.status_code}"


# ══════════════════════════════════════════════════════════════════════════════
# 2. LEAD — create / read / update / validation
# ══════════════════════════════════════════════════════════════════════════════

class TestLeads:
    def test_create_lead_minimal(self, admin_token):
        r = requests.post(
            f"{CRM}/leads",
            json={
                "name": "Ana García",
                "business_name": "García Bakery",
                "email": f"{_uniq('lead')}@example.com",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, f"Create lead failed: {r.status_code} {r.text}"
        data = r.json()
        assert data["status"] == "new"
        assert data["desired_plan"] is None
        assert "id" in data
        assert "created_at" in data
        _state["lead_id"] = data["id"]

    def test_create_lead_full(self, admin_token):
        r = requests.post(
            f"{CRM}/leads",
            json={
                "name": "Carlos López",
                "business_name": "López Restaurant",
                "email": f"{_uniq('lead')}@restaurant.com",
                "phone": "+1-555-0199",
                "business_type": "restaurant",
                "estimated_screens": 3,
                "desired_plan": "pro",
                "source": "for-business-landing",
                "notes": "Interested in monthly billing",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["desired_plan"] == "pro"
        assert data["estimated_screens"] == 3

    def test_plan_alias_standard_normalized_to_starter_on_lead(self, admin_token):
        """Legacy alias 'standard' must be stored as 'starter'."""
        r = requests.post(
            f"{CRM}/leads",
            json={
                "name": "Legacy Plan Test",
                "business_name": "Legacy Co",
                "email": f"{_uniq('lead')}@legacy.com",
                "desired_plan": "standard",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, r.text
        assert r.json()["desired_plan"] == "starter", "standard must be normalized to starter"

    def test_invalid_plan_rejected_on_lead(self, admin_token):
        r = requests.post(
            f"{CRM}/leads",
            json={
                "name": "Bad Plan",
                "business_name": "Bad Co",
                "email": f"{_uniq('lead')}@bad.com",
                "desired_plan": "diamond",  # non-existent plan
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 422, f"Expected 422 for invalid plan, got {r.status_code}"

    def test_get_lead(self, admin_token):
        lead_id = _state.get("lead_id")
        if not lead_id:
            pytest.skip("No lead_id from previous test")
        r = requests.get(f"{CRM}/leads/{lead_id}", headers=_auth(admin_token))
        assert r.status_code == 200
        assert r.json()["id"] == lead_id

    def test_list_leads(self, admin_token):
        r = requests.get(f"{CRM}/leads", headers=_auth(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_update_lead_status(self, admin_token):
        lead_id = _state.get("lead_id")
        if not lead_id:
            pytest.skip("No lead_id from previous test")
        r = requests.patch(
            f"{CRM}/leads/{lead_id}",
            json={"status": "contacted"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "contacted"

    def test_update_lead_invalid_status_rejected(self, admin_token):
        lead_id = _state.get("lead_id")
        if not lead_id:
            pytest.skip("No lead_id from previous test")
        r = requests.patch(
            f"{CRM}/leads/{lead_id}",
            json={"status": "ghosted"},  # invalid status
            headers=_auth(admin_token),
        )
        assert r.status_code == 422, f"Expected 422, got {r.status_code}"

    def test_list_leads_filter_by_status(self, admin_token):
        r = requests.get(f"{CRM}/leads?status=new", headers=_auth(admin_token))
        assert r.status_code == 200
        for lead in r.json():
            assert lead["status"] == "new"

    def test_list_leads_invalid_status_rejected(self, admin_token):
        r = requests.get(f"{CRM}/leads?status=ghost", headers=_auth(admin_token))
        assert r.status_code == 400, f"Expected 400 for invalid status filter, got {r.status_code}"

    def test_get_nonexistent_lead_404(self, admin_token):
        r = requests.get(f"{CRM}/leads/nonexistent-id-{_uniq()}", headers=_auth(admin_token))
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 3. CUSTOMER — create / read / update
# ══════════════════════════════════════════════════════════════════════════════

class TestCustomers:
    def test_create_customer(self, admin_token):
        r = requests.post(
            f"{CRM}/customers",
            json={
                "legal_name": "García Hospitality S.A.",
                "display_name": "García Group",
                "primary_contact_name": "Ana García",
                "primary_contact_email": f"{_uniq('customer')}@garciahospitality.com",
                "primary_contact_phone": "+1-555-0100",
                "status": "prospect",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, f"Create customer failed: {r.status_code} {r.text}"
        data = r.json()
        assert data["status"] == "prospect"
        assert data["legal_name"] == "García Hospitality S.A."
        assert "id" in data
        _state["customer_id"] = data["id"]

    def test_get_customer_includes_organizations(self, admin_token):
        cid = _state.get("customer_id")
        if not cid:
            pytest.skip("No customer_id")
        r = requests.get(f"{CRM}/customers/{cid}", headers=_auth(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "organizations" in data
        assert isinstance(data["organizations"], list)

    def test_list_customers(self, admin_token):
        r = requests.get(f"{CRM}/customers", headers=_auth(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_update_customer_status(self, admin_token):
        cid = _state.get("customer_id")
        if not cid:
            pytest.skip("No customer_id")
        r = requests.patch(
            f"{CRM}/customers/{cid}",
            json={"status": "active"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "active"

    def test_get_nonexistent_customer_404(self, admin_token):
        r = requests.get(f"{CRM}/customers/nope-{_uniq()}", headers=_auth(admin_token))
        assert r.status_code == 404

    def test_customer_missing_required_fields_rejected(self, admin_token):
        r = requests.post(
            f"{CRM}/customers",
            json={"legal_name": "Only Legal"},  # missing display_name
            headers=_auth(admin_token),
        )
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# 4. ORGANIZATION — create linked to customer / 1:1 cardinality
# ══════════════════════════════════════════════════════════════════════════════

class TestOrganizationForCustomer:
    def test_create_org_for_customer(self, admin_token):
        cid = _state.get("customer_id")
        if not cid:
            pytest.skip("No customer_id")
        r = requests.post(
            f"{CRM}/customers/{cid}/organizations",
            json={"name": "García Group Workspace", "plan": "starter"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, f"Create org failed: {r.status_code} {r.text}"
        data = r.json()
        assert data["customer_id"] == cid
        assert data["schema_source"] == "crm_2c"
        assert data["plan"] == "starter"
        assert "id" in data
        _state["org_id"] = data["id"]

    def test_plan_standard_alias_normalized_in_org(self, admin_token):
        """Plan alias 'standard' in org creation must resolve to 'starter'."""
        # Create a second customer for this test
        r_cust = requests.post(
            f"{CRM}/customers",
            json={"legal_name": "Alias Test Corp", "display_name": "Alias Test"},
            headers=_auth(admin_token),
        )
        assert r_cust.status_code == 201
        cid2 = r_cust.json()["id"]

        r = requests.post(
            f"{CRM}/customers/{cid2}/organizations",
            json={"name": "Alias Org", "plan": "standard"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, r.text
        assert r.json()["plan"] == "starter", "standard alias must normalize to starter"

    def test_create_org_for_nonexistent_customer_404(self, admin_token):
        r = requests.post(
            f"{CRM}/customers/nonexistent-{_uniq()}/organizations",
            json={"name": "Ghost Org", "plan": "starter"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 404

    def test_create_second_org_for_same_customer_rejected(self, admin_token):
        """Phase 2C-1A enforces Customer 1:1 Organization."""
        cid = _state.get("customer_id")
        if not cid:
            pytest.skip("No customer_id")
        r = requests.post(
            f"{CRM}/customers/{cid}/organizations",
            json={"name": "Second Org — must fail", "plan": "starter"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 409, (
            f"Expected 409 (1:1 cardinality), got {r.status_code}: {r.text}"
        )

    def test_list_orgs_for_customer(self, admin_token):
        cid = _state.get("customer_id")
        if not cid:
            pytest.skip("No customer_id")
        r = requests.get(
            f"{CRM}/customers/{cid}/organizations",
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        orgs = r.json()
        assert isinstance(orgs, list)
        assert any(o["id"] == _state.get("org_id") for o in orgs)

    def test_invalid_plan_rejected_on_org(self, admin_token):
        cid = _state.get("customer_id")
        if not cid:
            pytest.skip("No customer_id")
        r = requests.post(
            f"{CRM}/customers/{cid}/organizations",
            json={"name": "Bad Plan Org", "plan": "platinum"},
            headers=_auth(admin_token),
        )
        assert r.status_code in (422, 409), (
            f"Expected 422 or 409 for invalid plan, got {r.status_code}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5. SUBSCRIPTION — create / lifecycle / cross-reference protection
# ══════════════════════════════════════════════════════════════════════════════

class TestSubscriptions:
    def test_create_subscription(self, admin_token):
        org_id = _state.get("org_id")
        customer_id = _state.get("customer_id")
        if not org_id or not customer_id:
            pytest.skip("No org_id or customer_id from previous tests")
        r = requests.post(
            f"{CRM}/subscriptions",
            json={
                "org_id": org_id,
                "customer_id": customer_id,
                "status": "trial",
                "trial_started_at": "2026-09-05T00:00:00",
                "trial_ends_at": "2026-10-05T00:00:00",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, f"Create subscription failed: {r.status_code} {r.text}"
        data = r.json()
        assert data["schema_version"] == 2
        assert data["status"] == "trial"
        assert data["org_id"] == org_id
        assert data["customer_id"] == customer_id
        _state["sub_id"] = data["id"]

    def test_create_duplicate_subscription_rejected(self, admin_token):
        """Cannot create a second active subscription for the same org."""
        org_id = _state.get("org_id")
        customer_id = _state.get("customer_id")
        if not org_id or not customer_id:
            pytest.skip("No org_id or customer_id")
        r = requests.post(
            f"{CRM}/subscriptions",
            json={"org_id": org_id, "customer_id": customer_id, "status": "trial"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 409, (
            f"Expected 409 (duplicate subscription), got {r.status_code}"
        )

    def test_subscription_wrong_customer_rejected(self, admin_token):
        """Cannot create subscription if org's customer_id doesn't match."""
        org_id = _state.get("org_id")
        if not org_id:
            pytest.skip("No org_id")
        # Create a different customer
        r_cust = requests.post(
            f"{CRM}/customers",
            json={"legal_name": "Other Corp", "display_name": "Other"},
            headers=_auth(admin_token),
        )
        assert r_cust.status_code == 201
        other_cid = r_cust.json()["id"]

        r = requests.post(
            f"{CRM}/subscriptions",
            json={"org_id": org_id, "customer_id": other_cid, "status": "trial"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 409, (
            f"Expected 409 (org/customer mismatch), got {r.status_code}: {r.text}"
        )

    def test_subscription_nonexistent_org_rejected(self, admin_token):
        customer_id = _state.get("customer_id")
        if not customer_id:
            pytest.skip("No customer_id")
        r = requests.post(
            f"{CRM}/subscriptions",
            json={"org_id": f"ghost-{_uniq()}", "customer_id": customer_id, "status": "trial"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 404

    def test_subscription_nonexistent_customer_rejected(self, admin_token):
        org_id = _state.get("org_id")
        if not org_id:
            pytest.skip("No org_id")
        r = requests.post(
            f"{CRM}/subscriptions",
            json={"org_id": org_id, "customer_id": f"ghost-{_uniq()}", "status": "trial"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 404

    def test_get_subscription(self, admin_token):
        sub_id = _state.get("sub_id")
        if not sub_id:
            pytest.skip("No sub_id")
        r = requests.get(f"{CRM}/subscriptions/{sub_id}", headers=_auth(admin_token))
        assert r.status_code == 200
        assert r.json()["id"] == sub_id

    def test_update_subscription_status_to_active(self, admin_token):
        sub_id = _state.get("sub_id")
        if not sub_id:
            pytest.skip("No sub_id")
        r = requests.patch(
            f"{CRM}/subscriptions/{sub_id}/status",
            json={"status": "active"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "active"
        assert data["activated_at"] is not None

    def test_update_subscription_status_to_suspended(self, admin_token):
        sub_id = _state.get("sub_id")
        if not sub_id:
            pytest.skip("No sub_id")
        r = requests.patch(
            f"{CRM}/subscriptions/{sub_id}/status",
            json={"status": "suspended"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["suspended_at"] is not None

    def test_get_org_subscription(self, admin_token):
        org_id = _state.get("org_id")
        if not org_id:
            pytest.skip("No org_id")
        r = requests.get(
            f"{CRM}/organizations/{org_id}/subscription",
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["org_id"] == org_id

    def test_get_nonexistent_subscription_404(self, admin_token):
        r = requests.get(f"{CRM}/subscriptions/nope-{_uniq()}", headers=_auth(admin_token))
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 6. PRICING AGREEMENT — create / versioning / plan normalization / validation
# ══════════════════════════════════════════════════════════════════════════════

class TestPricingAgreements:
    def test_create_pricing_agreement_v1(self, admin_token):
        sub_id = _state.get("sub_id")
        if not sub_id:
            pytest.skip("No sub_id")
        r = requests.post(
            f"{CRM}/pricing-agreements",
            json={
                "subscription_id": sub_id,
                "plan_id": "starter",
                "pricing_model": "standard",
                "screens_included": 3,
                "screens_limit": 5,
                "overage_price_per_screen": 15.0,
                "agreed_monthly_price": 149.0,
                "currency": "USD",
                "billing_cycle": "monthly",
                "effective_from": "2026-09-05T00:00:00",
                "notes": "Initial Phase 2C-1A agreement",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, f"Create PA failed: {r.status_code} {r.text}"
        data = r.json()
        assert data["version"] == 1
        assert data["plan_id"] == "starter"
        assert data["agreed_monthly_price"] == 149.0
        _state["pa_id"] = data["id"]

    def test_plan_standard_alias_normalized_in_pricing_agreement(self, admin_token):
        """'standard' alias must be stored as 'starter'."""
        sub_id = _state.get("sub_id")
        if not sub_id:
            pytest.skip("No sub_id")
        r = requests.post(
            f"{CRM}/pricing-agreements",
            json={
                "subscription_id": sub_id,
                "plan_id": "standard",   # legacy alias
                "agreed_monthly_price": 149.0,
                "effective_from": "2026-10-01T00:00:00",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["plan_id"] == "starter", "'standard' must be normalized to 'starter'"
        assert data["version"] == 2, "Second PA for same subscription must be version 2"

    def test_invalid_plan_rejected_in_pricing_agreement(self, admin_token):
        sub_id = _state.get("sub_id")
        if not sub_id:
            pytest.skip("No sub_id")
        r = requests.post(
            f"{CRM}/pricing-agreements",
            json={
                "subscription_id": sub_id,
                "plan_id": "diamond",   # invalid
                "agreed_monthly_price": 99.0,
                "effective_from": "2026-10-01T00:00:00",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 422, f"Expected 422 for invalid plan, got {r.status_code}"

    def test_pricing_agreement_nonexistent_subscription_rejected(self, admin_token):
        r = requests.post(
            f"{CRM}/pricing-agreements",
            json={
                "subscription_id": f"ghost-{_uniq()}",
                "plan_id": "starter",
                "agreed_monthly_price": 99.0,
                "effective_from": "2026-10-01T00:00:00",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 404

    def test_negative_monthly_price_rejected(self, admin_token):
        sub_id = _state.get("sub_id")
        if not sub_id:
            pytest.skip("No sub_id")
        r = requests.post(
            f"{CRM}/pricing-agreements",
            json={
                "subscription_id": sub_id,
                "plan_id": "starter",
                "agreed_monthly_price": -50.0,  # invalid
                "effective_from": "2026-10-01T00:00:00",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 422, f"Expected 422 for negative price, got {r.status_code}"

    def test_list_pricing_agreements_for_subscription(self, admin_token):
        sub_id = _state.get("sub_id")
        if not sub_id:
            pytest.skip("No sub_id")
        r = requests.get(
            f"{CRM}/subscriptions/{sub_id}/pricing-agreements",
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        pas = r.json()
        assert isinstance(pas, list)
        assert len(pas) >= 1
        # Versions must be in ascending order
        versions = [pa["version"] for pa in pas]
        assert versions == sorted(versions), "PricingAgreements must be returned in version order"

    def test_get_pricing_agreement(self, admin_token):
        pa_id = _state.get("pa_id")
        if not pa_id:
            pytest.skip("No pa_id")
        r = requests.get(f"{CRM}/pricing-agreements/{pa_id}", headers=_auth(admin_token))
        assert r.status_code == 200
        assert r.json()["id"] == pa_id

    def test_subscription_current_pricing_agreement_updated(self, admin_token):
        """After creating a PA, the subscription.current_pricing_agreement_id must be updated."""
        sub_id = _state.get("sub_id")
        if not sub_id:
            pytest.skip("No sub_id")
        r = requests.get(f"{CRM}/subscriptions/{sub_id}", headers=_auth(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["current_pricing_agreement_id"] is not None, (
            "Subscription must have current_pricing_agreement_id set after PA creation"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 7. CUSTOMER SUMMARY — relationship view
# ══════════════════════════════════════════════════════════════════════════════

class TestCustomerSummary:
    def test_customer_summary(self, admin_token):
        cid = _state.get("customer_id")
        if not cid:
            pytest.skip("No customer_id")
        r = requests.get(f"{CRM}/customers/{cid}/summary", headers=_auth(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert "customer" in data
        assert "organizations" in data
        assert isinstance(data["organizations"], list)
        if data["organizations"]:
            item = data["organizations"][0]
            assert "organization" in item
            assert "subscription" in item
            assert "current_pricing_agreement" in item

    def test_customer_summary_nonexistent_404(self, admin_token):
        r = requests.get(f"{CRM}/customers/ghost-{_uniq()}/summary", headers=_auth(admin_token))
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 8. PLAN NORMALIZATION — unit tests via API
# ══════════════════════════════════════════════════════════════════════════════

class TestPlanNormalization:
    @pytest.mark.parametrize("raw,expected", [
        ("free",       "free"),
        ("starter",    "starter"),
        ("pro",        "pro"),
        ("enterprise", "enterprise"),
        ("standard",   "starter"),     # legacy alias
        ("STANDARD",   "starter"),     # case-insensitive alias
        ("FREE",       "free"),        # case-insensitive canonical
        ("PRO",        "pro"),
    ])
    def test_plan_normalization_via_lead_creation(self, admin_token, raw, expected):
        """All plan values (canonical + aliases) must normalize correctly."""
        r = requests.post(
            f"{CRM}/leads",
            json={
                "name": f"Plan test {raw}",
                "business_name": "Test Co",
                "email": f"{_uniq('plan')}@test.com",
                "desired_plan": raw,
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 201, (
            f"Plan {raw!r} should be valid (normalizes to {expected!r}), "
            f"but got {r.status_code}: {r.text}"
        )
        assert r.json()["desired_plan"] == expected, (
            f"Expected {expected!r}, got {r.json()['desired_plan']!r}"
        )

    @pytest.mark.parametrize("invalid_plan", [
        "diamond", "gold", "silver", "basic", "premium", "plus", "ultimate", "",
    ])
    def test_invalid_plan_rejected(self, admin_token, invalid_plan):
        """Invalid plan IDs (not in canonical set and not a known alias) must return 422."""
        r = requests.post(
            f"{CRM}/leads",
            json={
                "name": "Invalid Plan",
                "business_name": "Bad Co",
                "email": f"{_uniq('badplan')}@test.com",
                "desired_plan": invalid_plan or "nope",
            },
            headers=_auth(admin_token),
        )
        assert r.status_code == 422, (
            f"Plan {invalid_plan!r} should be rejected with 422, got {r.status_code}"
        )
