# Fase 2 Self-Service Portal — Backend tests
# Tests: Organizations, Locations, Subscriptions, Team/Invites, Admin, Tenant Isolation, RBAC
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://menu-studio-3.preview.emergentagent.com")

# ── Credentials ─────────────────────────────────────────────────────────────
SUPER_ADMIN = {"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"}
MW_ADMIN    = {"email": "rbac.mwadmin@test.com",     "password": "RbacTest#2026"}
SSO_ORGA    = {"email": "rbac.ssowner.orga@test.com","password": "RbacTest#2026"}
SSO_ORGB    = {"email": "rbac.ssowner.orgb@test.com","password": "RbacTest#2026"}
ADVERTISER  = {"email": "rbac.advertiser@test.com",  "password": "RbacTest#2026"}


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s

def _login(session, creds):
    r = session.post(f"{BASE_URL}/api/auth/login", json=creds)
    assert r.status_code == 200, f"Login failed for {creds['email']}: {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"No token in login response: {r.json()}"
    return token

@pytest.fixture(scope="session")
def token_sso_orga(session):
    return _login(session, SSO_ORGA)

@pytest.fixture(scope="session")
def token_sso_orgb(session):
    return _login(session, SSO_ORGB)

@pytest.fixture(scope="session")
def token_admin(session):
    return _login(session, MW_ADMIN)

@pytest.fixture(scope="session")
def token_superadmin(session):
    return _login(session, SUPER_ADMIN)

@pytest.fixture(scope="session")
def token_advertiser(session):
    return _login(session, ADVERTISER)

def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
#  ORGANIZATIONS
# ══════════════════════════════════════════════════════════════════════════════
class TestOrganizations:
    """Organization CRUD and login response fields"""

    def test_login_response_has_rbac_role_and_org_id(self, session, token_sso_orga):
        """Login response debe incluir rbac_role y organization_id (dentro del objeto 'user')"""
        r = session.post(f"{BASE_URL}/api/auth/login", json=SSO_ORGA)
        assert r.status_code == 200
        data = r.json()
        user = data.get("user", {})
        assert "rbac_role" in user, f"rbac_role missing from login response user object: {list(user.keys())}"
        assert "organization_id" in user, f"organization_id missing from login response user object: {list(user.keys())}"
        assert user["rbac_role"] == "SELF_SERVICE_OWNER", f"Expected SELF_SERVICE_OWNER, got {user['rbac_role']}"
        print(f"PASS: login user includes rbac_role={user['rbac_role']} org_id={user['organization_id']}")

    def test_get_my_org(self, session, token_sso_orga):
        """GET /api/organizations/mine → org con stats"""
        r = session.get(f"{BASE_URL}/api/organizations/mine", headers=auth_headers(token_sso_orga))
        assert r.status_code == 200
        data = r.json()
        # Could be {"org": None} or a full org object
        # When org doesn't exist: {"org": None, "message": "..."}
        # When org exists: the org object directly (with "id" key)
        if "message" in data and not data.get("id"):
            pytest.skip("SSO Org A has no organization yet")
        assert "id" in data, f"No 'id' in org response: {list(data.keys())}"
        assert "stats" in data, f"No 'stats' in org response: {list(data.keys())}"
        stats = data["stats"]
        assert "locations" in stats
        assert "screens" in stats
        assert "members" in stats
        assert "active_subscriptions" in stats
        print(f"PASS: org '{data.get('name')}' stats={stats}")

    def test_create_org_already_exists_409(self, session, token_sso_orga):
        """SSO Org A ya tiene org → debe retornar 409"""
        r = session.post(f"{BASE_URL}/api/organizations",
                         json={"name": "Duplicate Org Test"},
                         headers=auth_headers(token_sso_orga))
        assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
        print(f"PASS: 409 cuando usuario ya tiene org: {r.json().get('detail')}")

    def test_update_org(self, session, token_sso_orga):
        """PUT /api/organizations/{id} → actualizar nombre y billing_email"""
        # Get org id first
        r = session.get(f"{BASE_URL}/api/organizations/mine", headers=auth_headers(token_sso_orga))
        assert r.status_code == 200
        org = r.json()
        if not org.get("id"):
            pytest.skip("No org found")
        org_id = org["id"]
        r2 = session.put(f"{BASE_URL}/api/organizations/{org_id}",
                         json={"billing_email": "billing-test@acme.com"},
                         headers=auth_headers(token_sso_orga))
        assert r2.status_code == 200, f"Update org failed: {r2.text}"
        updated = r2.json()
        assert updated.get("billing_email") == "billing-test@acme.com"
        print(f"PASS: org updated billing_email={updated['billing_email']}")


# ══════════════════════════════════════════════════════════════════════════════
#  LOCATIONS
# ══════════════════════════════════════════════════════════════════════════════
class TestLocations:
    """Location CRUD and tenant isolation"""

    # module-level state
    created_loc_id = None

    def test_create_location(self, session, token_sso_orga):
        """POST /api/locations → crear ubicación"""
        payload = {
            "name": "TEST_Location Fase2",
            "address": "123 Main St",
            "city": "Miami",
            "state": "FL",
            "country": "US",
            "zip": "33101",
            "timezone": "America/New_York",
        }
        r = session.post(f"{BASE_URL}/api/locations", json=payload, headers=auth_headers(token_sso_orga))
        assert r.status_code == 200, f"Create location failed: {r.text}"
        data = r.json()
        assert data.get("id"), "No id in location response"
        assert data.get("name") == "TEST_Location Fase2"
        assert data.get("screen_count") == 0
        TestLocations.created_loc_id = data["id"]
        print(f"PASS: location created id={data['id']} city={data['city']}")

    def test_list_locations(self, session, token_sso_orga):
        """GET /api/locations → listar ubicaciones de mi org"""
        r = session.get(f"{BASE_URL}/api/locations", headers=auth_headers(token_sso_orga))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"PASS: listed {len(data)} locations")

    def test_update_location(self, session, token_sso_orga):
        """PUT /api/locations/{id} → actualizar nombre"""
        if not TestLocations.created_loc_id:
            pytest.skip("No location to update")
        r = session.put(f"{BASE_URL}/api/locations/{TestLocations.created_loc_id}",
                        json={"name": "TEST_Location Updated"},
                        headers=auth_headers(token_sso_orga))
        assert r.status_code == 200, f"Update location failed: {r.text}"
        assert r.json().get("name") == "TEST_Location Updated"
        print(f"PASS: location updated")

    def test_delete_location_with_no_screens_ok(self, session, token_sso_orga):
        """DELETE /api/locations/{id} sin screens vinculadas → OK"""
        if not TestLocations.created_loc_id:
            pytest.skip("No location to delete")
        r = session.delete(f"{BASE_URL}/api/locations/{TestLocations.created_loc_id}",
                           headers=auth_headers(token_sso_orga))
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert r.json().get("success") is True
        TestLocations.created_loc_id = None
        print(f"PASS: location deleted successfully")

    def test_delete_location_with_screen_linked_409(self, session, token_sso_orga):
        """DELETE /api/locations/{id} con screen vinculada → 409"""
        # Create a fresh location to link to a screen
        r = session.post(f"{BASE_URL}/api/locations",
                         json={"name": "TEST_Loc For Delete Test", "address": "99 St", "city": "NY", "country": "US"},
                         headers=auth_headers(token_sso_orga))
        assert r.status_code == 200
        loc_id = r.json()["id"]

        # Get a screen from Org A
        rs = session.get(f"{BASE_URL}/api/screens/self-service/mine", headers=auth_headers(token_sso_orga))
        if rs.status_code != 200 or not rs.json():
            # cleanup loc and skip
            session.delete(f"{BASE_URL}/api/locations/{loc_id}", headers=auth_headers(token_sso_orga))
            pytest.skip("No screens in Org A to link")

        screens = rs.json()
        if isinstance(screens, dict) and "screens" in screens:
            screens = screens["screens"]
        if not screens:
            session.delete(f"{BASE_URL}/api/locations/{loc_id}", headers=auth_headers(token_sso_orga))
            pytest.skip("No screens in Org A")
        screen_id = screens[0]["id"]

        # Link screen to location
        rl = session.put(f"{BASE_URL}/api/screens/self-service/{screen_id}/link-location",
                         json={"location_id": loc_id},
                         headers=auth_headers(token_sso_orga))
        if rl.status_code != 200:
            session.delete(f"{BASE_URL}/api/locations/{loc_id}", headers=auth_headers(token_sso_orga))
            pytest.skip(f"Could not link screen: {rl.text}")

        # Now try to delete location — should get 409
        rd = session.delete(f"{BASE_URL}/api/locations/{loc_id}", headers=auth_headers(token_sso_orga))
        assert rd.status_code == 409, f"Expected 409, got {rd.status_code}: {rd.text}"
        print(f"PASS: 409 when deleting location with linked screen")

        # Cleanup: unlink screen then delete
        session.put(f"{BASE_URL}/api/screens/self-service/{screen_id}/link-location",
                    json={"location_id": None}, headers=auth_headers(token_sso_orga))
        session.delete(f"{BASE_URL}/api/locations/{loc_id}", headers=auth_headers(token_sso_orga))

    def test_tenant_isolation_orga_cannot_read_orgb_locations(self, session, token_sso_orga, token_sso_orgb):
        """Org A NO puede leer/crear en Org B (tenant isolation)"""
        # Create location as Org B
        rb = session.post(f"{BASE_URL}/api/locations",
                          json={"name": "TEST_OrgB Secret Location", "address": "1 Org B St", "city": "Chicago", "country": "US"},
                          headers=auth_headers(token_sso_orgb))
        assert rb.status_code == 200, f"Failed to create OrgB location: {rb.text}"
        orgb_loc_id = rb.json()["id"]

        # Org A tries to update OrgB's location → should get 403
        ra = session.put(f"{BASE_URL}/api/locations/{orgb_loc_id}",
                         json={"name": "Org A Hacked!"},
                         headers=auth_headers(token_sso_orga))
        assert ra.status_code == 403, f"Expected 403 for tenant isolation, got {ra.status_code}: {ra.text}"
        print(f"PASS: Org A cannot modify Org B location (403)")

        # Cleanup: OrgB deletes its location
        session.delete(f"{BASE_URL}/api/locations/{orgb_loc_id}", headers=auth_headers(token_sso_orgb))


# ══════════════════════════════════════════════════════════════════════════════
#  SUBSCRIPTIONS
# ══════════════════════════════════════════════════════════════════════════════
class TestSubscriptions:
    """Subscription lifecycle: plans, create, list, cancel"""

    created_sub_id = None

    def test_list_plans_public(self, session):
        """GET /api/subscriptions/plans → público, sin auth"""
        r = session.get(f"{BASE_URL}/api/subscriptions/plans")
        assert r.status_code == 200, f"Plans endpoint failed: {r.text}"
        data = r.json()
        assert "starter" in data
        assert "pro" in data
        assert "enterprise" in data
        assert data["starter"]["price_monthly"] == 29.00
        print(f"PASS: plans returned: {list(data.keys())}")

    def _get_or_create_screen(self, session, token):
        """Get existing screen or create one for subscription tests."""
        rs = session.get(f"{BASE_URL}/api/screens/self-service/mine", headers=auth_headers(token))
        if rs.status_code == 200:
            screens = rs.json()
            if isinstance(screens, dict) and "screens" in screens:
                screens = screens["screens"]
            if screens:
                return screens[0]["id"]
        # Create a new screen
        r = session.post(f"{BASE_URL}/api/screens/self-service",
                         json={"name": "TEST_Fase2 Sub Screen",
                               "location": {"address": "1 Test St", "city": "Miami", "state": "FL", "country": "US", "zip": "33101"}},
                         headers=auth_headers(token))
        assert r.status_code == 200, f"Could not create screen: {r.text}"
        return r.json()["id"]

    def test_create_subscription(self, session, token_sso_orga):
        """POST /api/subscriptions → crear sub para una screen"""
        # Get or create a screen with the correct org UUID
        screen_id = self._get_or_create_screen(session, token_sso_orga)

        # Check if screen already has active subscription
        rsubs = session.get(f"{BASE_URL}/api/subscriptions", headers=auth_headers(token_sso_orga))
        if rsubs.status_code == 200:
            existing_subs = rsubs.json()
            existing_screen_ids = [s.get("screen_id") for s in existing_subs
                                   if s.get("status") in ("trialing", "active", "suspended")]
            if screen_id in existing_screen_ids:
                # Cancel existing first or use different screen
                for s in existing_subs:
                    if s.get("screen_id") == screen_id and s.get("status") in ("trialing", "active"):
                        session.post(f"{BASE_URL}/api/subscriptions/{s['id']}/cancel",
                                     headers=auth_headers(token_sso_orga))
                        break

        r = session.post(f"{BASE_URL}/api/subscriptions",
                         json={"screen_id": screen_id, "plan": "starter", "billing_cycle": "monthly"},
                         headers=auth_headers(token_sso_orga))
        assert r.status_code == 200, f"Create sub failed: {r.text}"
        data = r.json()
        assert data.get("id")
        assert data.get("plan") == "starter"
        assert data.get("billing_cycle") == "monthly"
        assert data.get("status") == "trialing"
        assert data.get("price") == 29.00
        assert data.get("plan_info"), "plan_info missing"
        TestSubscriptions.created_sub_id = data["id"]
        print(f"PASS: subscription created id={data['id']} status={data['status']}")

    def test_list_subscriptions(self, session, token_sso_orga):
        """GET /api/subscriptions → listar subs de mi org"""
        r = session.get(f"{BASE_URL}/api/subscriptions", headers=auth_headers(token_sso_orga))
        assert r.status_code == 200, f"List subs failed: {r.text}"
        data = r.json()
        assert isinstance(data, list)
        print(f"PASS: listed {len(data)} subscriptions")

    def test_cancel_subscription(self, session, token_sso_orga):
        """POST /api/subscriptions/{id}/cancel"""
        if not TestSubscriptions.created_sub_id:
            pytest.skip("No subscription to cancel")
        r = session.post(f"{BASE_URL}/api/subscriptions/{TestSubscriptions.created_sub_id}/cancel",
                         headers=auth_headers(token_sso_orga))
        assert r.status_code == 200, f"Cancel sub failed: {r.text}"
        data = r.json()
        assert data.get("status") == "cancelled"
        assert data.get("cancelled_at") is not None
        print(f"PASS: subscription cancelled at {data['cancelled_at']}")

    def test_cancel_already_cancelled_400(self, session, token_sso_orga):
        """POST cancel again → 400"""
        if not TestSubscriptions.created_sub_id:
            pytest.skip("No sub id")
        r = session.post(f"{BASE_URL}/api/subscriptions/{TestSubscriptions.created_sub_id}/cancel",
                         headers=auth_headers(token_sso_orga))
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        print(f"PASS: 400 on double-cancel")

    def test_duplicate_subscription_409(self, session, token_sso_orga):
        """POST /api/subscriptions con screen que ya tiene sub activa → 409"""
        screen_id = self._get_or_create_screen(session, token_sso_orga)

        # Create a new sub
        r1 = session.post(f"{BASE_URL}/api/subscriptions",
                          json={"screen_id": screen_id, "plan": "starter", "billing_cycle": "monthly"},
                          headers=auth_headers(token_sso_orga))
        if r1.status_code == 409:
            # Already has active sub → correct behavior
            print("PASS: 409 duplicate subscription (existing active)")
            return
        assert r1.status_code == 200, f"First sub creation failed: {r1.text}"
        new_sub_id = r1.json()["id"]

        # Try creating another
        r2 = session.post(f"{BASE_URL}/api/subscriptions",
                          json={"screen_id": screen_id, "plan": "pro", "billing_cycle": "monthly"},
                          headers=auth_headers(token_sso_orga))
        assert r2.status_code == 409, f"Expected 409 duplicate sub, got {r2.status_code}: {r2.text}"
        print(f"PASS: 409 on duplicate subscription")

        # Cleanup
        session.post(f"{BASE_URL}/api/subscriptions/{new_sub_id}/cancel", headers=auth_headers(token_sso_orga))


# ══════════════════════════════════════════════════════════════════════════════
#  TEAM INVITES
# ══════════════════════════════════════════════════════════════════════════════
class TestTeamInvites:
    """Invite lifecycle: create, get public info, accept"""

    created_invite_token = None
    created_invite_id = None

    def test_create_invite(self, session, token_sso_orga):
        """POST /api/organizations/{org_id}/invites → crear invite link"""
        # Get org_id
        r = session.get(f"{BASE_URL}/api/organizations/mine", headers=auth_headers(token_sso_orga))
        assert r.status_code == 200
        org = r.json()
        if not org.get("id"):
            pytest.skip("No org found")
        org_id = org["id"]

        # Invite a new TEST_ email
        invite_email = "TEST_invite_fase2@example.com"
        ri = session.post(f"{BASE_URL}/api/organizations/{org_id}/invites",
                          json={"email": invite_email, "role": "SELF_SERVICE_MANAGER"},
                          headers=auth_headers(token_sso_orga))
        assert ri.status_code == 200, f"Create invite failed: {ri.text}"
        data = ri.json()
        assert data.get("token"), "No token in invite response"
        assert data.get("invite_url"), "No invite_url in response"
        assert data.get("status") == "pending"
        TestTeamInvites.created_invite_token = data["token"]
        TestTeamInvites.created_invite_id = data["id"]
        print(f"PASS: invite created token={data['token'][:8]}... url={data['invite_url']}")

    def test_get_invite_info_public(self, session):
        """GET /api/invites/{token} → público, sin auth"""
        if not TestTeamInvites.created_invite_token:
            pytest.skip("No invite token")
        r = session.get(f"{BASE_URL}/api/invites/{TestTeamInvites.created_invite_token}")
        assert r.status_code == 200, f"Get invite info failed: {r.text}"
        data = r.json()
        assert data.get("email") == "TEST_invite_fase2@example.com"
        assert data.get("role") == "SELF_SERVICE_MANAGER"
        assert "org_name" in data
        assert "has_account" in data
        # Note: on re-runs has_account may be True (user already created)
        assert isinstance(data["has_account"], bool)
        print(f"PASS: invite info org_name='{data['org_name']}' has_account={data['has_account']}")

    def test_accept_invite_new_user(self, session):
        """POST /api/invites/{token}/accept → aceptar invite (nuevo usuario)"""
        if not TestTeamInvites.created_invite_token:
            pytest.skip("No invite token")
        r = session.post(f"{BASE_URL}/api/invites/{TestTeamInvites.created_invite_token}/accept",
                         json={"name": "TEST Invited User", "password": "TestPass#2026"})
        assert r.status_code == 200, f"Accept invite failed: {r.text}"
        data = r.json()
        assert data.get("success") is True
        assert "org_name" in data
        print(f"PASS: invite accepted, joined '{data['org_name']}'")

    def test_accept_invite_again_410(self, session):
        """POST accept same token again → 410 (already used)"""
        if not TestTeamInvites.created_invite_token:
            pytest.skip("No invite token")
        r = session.post(f"{BASE_URL}/api/invites/{TestTeamInvites.created_invite_token}/accept",
                         json={"name": "Again", "password": "TestPass#2026"})
        assert r.status_code == 410, f"Expected 410 on re-use, got {r.status_code}: {r.text}"
        print(f"PASS: 410 on re-accepting invite")

    def test_invalid_invite_token_404(self, session):
        """GET invite with invalid token → 404"""
        r = session.get(f"{BASE_URL}/api/invites/totally-invalid-token-xyz999")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
        print(f"PASS: 404 for invalid invite token")


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN
# ══════════════════════════════════════════════════════════════════════════════
class TestAdmin:
    """Admin endpoints: organizations, subscriptions revenue"""

    def test_admin_list_organizations(self, session, token_admin):
        """GET /api/admin/organizations → listar todas las orgs (requiere admin)"""
        r = session.get(f"{BASE_URL}/api/admin/organizations", headers=auth_headers(token_admin))
        assert r.status_code == 200, f"Admin list orgs failed: {r.text}"
        data = r.json()
        assert isinstance(data, list)
        if data:
            assert "id" in data[0]
            assert "screen_count" in data[0]
            assert "member_count" in data[0]
        print(f"PASS: admin listed {len(data)} organizations")

    def test_admin_revenue_summary(self, session, token_admin):
        """GET /api/admin/subscriptions/revenue → revenue summary"""
        r = session.get(f"{BASE_URL}/api/admin/subscriptions/revenue", headers=auth_headers(token_admin))
        assert r.status_code == 200, f"Revenue endpoint failed: {r.text}"
        data = r.json()
        assert "mrr" in data
        assert "arr" in data
        assert "total" in data
        assert "by_status" in data
        assert "by_plan" in data
        print(f"PASS: revenue MRR={data['mrr']} ARR={data['arr']} total={data['total']}")

    def test_advertiser_cannot_access_admin_403(self, session, token_advertiser):
        """ADVERTISER cannot access /api/admin/organizations → 403"""
        r = session.get(f"{BASE_URL}/api/admin/organizations", headers=auth_headers(token_advertiser))
        assert r.status_code in (401, 403), f"Expected 403, got {r.status_code}: {r.text}"
        print(f"PASS: advertiser blocked from admin org list (status={r.status_code})")

    def test_sso_owner_cannot_access_admin_403(self, session, token_sso_orga):
        """SELF_SERVICE_OWNER cannot access admin endpoints → 403"""
        r = session.get(f"{BASE_URL}/api/admin/organizations", headers=auth_headers(token_sso_orga))
        assert r.status_code in (401, 403), f"Expected 403 for SSO owner, got {r.status_code}: {r.text}"
        print(f"PASS: SSO owner blocked from admin org list (status={r.status_code})")


# ══════════════════════════════════════════════════════════════════════════════
#  TENANT ISOLATION
# ══════════════════════════════════════════════════════════════════════════════
class TestTenantIsolation:
    """Org B cannot list/create in Org A and vice versa"""

    def test_orgb_cannot_list_orga_locations(self, session, token_sso_orga, token_sso_orgb):
        """Org B solo ve sus propias locations (no las de Org A)"""
        # Create a location as Org A
        ra = session.post(f"{BASE_URL}/api/locations",
                          json={"name": "TEST_OrgA Exclusive Loc", "address": "1 A St", "city": "Miami", "country": "US"},
                          headers=auth_headers(token_sso_orga))
        assert ra.status_code == 200
        orga_loc_id = ra.json()["id"]

        # Org B lists its locations → should NOT see Org A's location
        rb = session.get(f"{BASE_URL}/api/locations", headers=auth_headers(token_sso_orgb))
        assert rb.status_code == 200
        orgb_locs = rb.json()
        orgb_loc_ids = [l["id"] for l in orgb_locs]
        assert orga_loc_id not in orgb_loc_ids, "Tenant isolation violated: Org B sees Org A's location!"
        print(f"PASS: Org B cannot see Org A locations")

        # Cleanup
        session.delete(f"{BASE_URL}/api/locations/{orga_loc_id}", headers=auth_headers(token_sso_orga))

    def test_orgb_cannot_subscribe_to_orga_screen(self, session, token_sso_orga, token_sso_orgb):
        """Org B cannot subscribe to Org A's screen → 403"""
        # Create a screen as Org A
        rs = session.post(f"{BASE_URL}/api/screens/self-service",
                          json={"name": "TEST_OrgA screen for isolation test",
                                "location": {"address": "1 A St", "city": "Miami", "state": "FL", "country": "US", "zip": "33101"}},
                          headers=auth_headers(token_sso_orga))
        assert rs.status_code == 200
        screen_id = rs.json()["id"]

        r = session.post(f"{BASE_URL}/api/subscriptions",
                         json={"screen_id": screen_id, "plan": "starter", "billing_cycle": "monthly"},
                         headers=auth_headers(token_sso_orgb))
        assert r.status_code in (403, 400), f"Expected 403/400 for cross-org subscription, got {r.status_code}: {r.text}"
        print(f"PASS: Org B cannot subscribe to Org A screen (status={r.status_code})")
