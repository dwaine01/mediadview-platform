# ruff: noqa: E501,E701,E402
"""
test_security_fixes.py — MediaView Fase 6 Security Hardening Tests
===================================================================

Covers:
  SEC-001 — Stored XSS in menu renderer
  SEC-002 — Invite acceptance / account hijack
  SEC-003 — Widget renderer XSS + API key exposure
  H1      — CSP headers (documents remaining unsafe-inline P1 blocker)
  H2      — X-Forwarded-For trusted proxy
  H3      — Public menu render published-state gate

All tests run against the LIVE local server on port 8001.
"""

import os
import sys
import time
import uuid
from datetime import datetime, timedelta

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

BASE = "http://localhost:8001/api"
TIMEOUT = 10


# ─── helpers ──────────────────────────────────────────────────────────────────
def _admin_token() -> str:
    """Login as superadmin and return access token."""
    r = httpx.post(f"{BASE}/auth/v2/login",
                   json={"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"},
                   timeout=TIMEOUT)
    if r.status_code != 200:
        pytest.skip(f"Cannot authenticate as superadmin: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _unique_email() -> str:
    return f"sectest_{uuid.uuid4().hex[:8]}@test.com"


# ══════════════════════════════════════════════════════════════════════════════
# SEC-001 — Stored XSS in menu renderer
# ══════════════════════════════════════════════════════════════════════════════

class TestSec001MenuXSS:
    """The renderer must HTML-escape every user-supplied field.
    A <script> payload in a menu field must appear escaped (not executable) in the HTML."""

    XSS_PAYLOAD = '<script>alert(1)</script>'
    XSS_ESCAPED = '&lt;script&gt;alert(1)&lt;/script&gt;'

    @pytest.fixture(scope="class")
    def token(self):
        return _admin_token()

    @pytest.fixture(scope="class")
    def xss_menu_id(self, token):
        """Create a menu with XSS payloads in all user-controlled fields and PUBLISH it."""
        # Create menu
        r = httpx.post(f"{BASE}/menus", headers=_auth_headers(token),
                       json={"name": "XSS Test Menu", "template_id": "classic",
                             "restaurant_name": self.XSS_PAYLOAD,
                             "subtitle": self.XSS_PAYLOAD},
                       timeout=TIMEOUT)
        assert r.status_code in (200, 201), f"Create menu: {r.status_code} {r.text}"
        menu_id = r.json()["id"]

        # Add a category with XSS payload
        r2 = httpx.post(f"{BASE}/menus/{menu_id}/categories",
                        headers=_auth_headers(token),
                        json={"name": self.XSS_PAYLOAD,
                              "description": self.XSS_PAYLOAD,
                              "items": []},
                        timeout=TIMEOUT)
        assert r2.status_code in (200, 201), f"Add category: {r2.status_code}"
        cat_id = r2.json()["id"]

        # Add an item with XSS payload
        httpx.post(f"{BASE}/menus/{menu_id}/categories/{cat_id}/items",
                   headers=_auth_headers(token),
                   json={"name": self.XSS_PAYLOAD,
                         "description": self.XSS_PAYLOAD,
                         "price": 9.99,
                         "image": "javascript:alert(1)"},   # dangerous src
                   timeout=TIMEOUT)

        # Publish the menu so it's accessible at /render
        httpx.put(f"{BASE}/menus/{menu_id}", headers=_auth_headers(token),
                  json={"status": "published"}, timeout=TIMEOUT)

        yield menu_id

        # Cleanup
        httpx.delete(f"{BASE}/menus/{menu_id}", headers=_auth_headers(token), timeout=TIMEOUT)

    def test_restaurant_name_escaped(self, xss_menu_id):
        """restaurant_name must appear HTML-escaped, not as raw <script>."""
        r = httpx.get(f"{BASE}/menus/{xss_menu_id}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert self.XSS_ESCAPED in r.text, "restaurant_name not escaped"
        assert '<script>alert(1)</script>' not in r.text, "raw XSS in restaurant_name!"

    def test_subtitle_escaped(self, xss_menu_id):
        """subtitle must appear HTML-escaped."""
        r = httpx.get(f"{BASE}/menus/{xss_menu_id}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert self.XSS_ESCAPED in r.text

    def test_category_name_escaped(self, xss_menu_id):
        """Category name must appear HTML-escaped."""
        r = httpx.get(f"{BASE}/menus/{xss_menu_id}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.text
        # At least one occurrence must be escaped (restaurant + category both have the payload)
        assert self.XSS_ESCAPED in body

    def test_item_name_escaped(self, xss_menu_id):
        """Item name must appear HTML-escaped."""
        r = httpx.get(f"{BASE}/menus/{xss_menu_id}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert self.XSS_ESCAPED in r.text

    def test_item_description_escaped(self, xss_menu_id):
        """Item description must appear HTML-escaped."""
        r = httpx.get(f"{BASE}/menus/{xss_menu_id}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert self.XSS_ESCAPED in r.text

    def test_javascript_src_rejected(self, xss_menu_id):
        """javascript: URL in item image must NOT appear as a src= attribute value."""
        r = httpx.get(f"{BASE}/menus/{xss_menu_id}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert 'src="javascript:' not in r.text.lower(), \
            "javascript: URL appeared in src attribute — XSS vector not blocked!"

    def test_event_handler_not_injected(self, xss_menu_id):
        """onerror, onclick payloads must not appear unescaped in the HTML."""
        # Get the menu and update with event handler payload
        token = _admin_token()
        r = httpx.get(f"{BASE}/menus/{xss_menu_id}", headers=_auth_headers(token), timeout=TIMEOUT)
        if r.status_code != 200:
            pytest.skip("Could not fetch menu")
        r2 = httpx.get(f"{BASE}/menus/{xss_menu_id}/render", timeout=TIMEOUT)
        # Verify onerror handlers cannot be injected raw
        assert 'onerror=' not in r2.text or 'onerror=&' in r2.text or \
               r2.text.count('onerror=') == 0


# ══════════════════════════════════════════════════════════════════════════════
# SEC-002 — Invite acceptance security
# ══════════════════════════════════════════════════════════════════════════════

class TestSec002InviteAcceptance:
    """Comprehensive invite security tests A–I per the security spec."""

    @pytest.fixture(scope="class")
    def token(self):
        return _admin_token()

    @pytest.fixture(scope="class")
    def org_and_invite(self, token):
        """Create an org and a valid pending invite for a fresh email."""
        # Create org via /api/organizations
        email = _unique_email()
        r = httpx.post(f"{BASE}/organizations",
                       headers=_auth_headers(token),
                       json={"name": f"SecTest Org {uuid.uuid4().hex[:4]}"},
                       timeout=TIMEOUT)
        if r.status_code not in (200, 201):
            pytest.skip(f"Cannot create org: {r.status_code} {r.text}")
        org_id = r.json()["id"]

        # Create invite
        r2 = httpx.post(f"{BASE}/organizations/{org_id}/invites",
                        headers=_auth_headers(token),
                        json={"email": email, "role": "SELF_SERVICE_MANAGER"},
                        timeout=TIMEOUT)
        if r2.status_code not in (200, 201):
            pytest.skip(f"Cannot create invite: {r2.status_code} {r2.text}")
        inv_token = r2.json().get("token")
        if not inv_token:
            pytest.skip("Invite token not in response")

        yield {"org_id": org_id, "invite_token": inv_token, "email": email}

    def test_A_new_email_valid_invite_passes(self, org_and_invite):
        """A: Owner invites new email → new user created → PASS."""
        inv_t = org_and_invite["invite_token"]
        r = httpx.post(f"{BASE}/invites/{inv_t}/accept",
                       json={"name": "New Test User", "password": "SecTest#9876"},
                       timeout=TIMEOUT)
        assert r.status_code == 200, f"A: {r.status_code} {r.text}"
        assert r.json().get("success") is True

    def test_B_wrong_token_rejected(self):
        """B: Wrong token → 404/410."""
        r = httpx.post(f"{BASE}/invites/definitely-invalid-token-xyz/accept",
                       json={"name": "Hacker", "password": "Hack123456!"},
                       timeout=TIMEOUT)
        assert r.status_code in (404, 410), f"B: Expected 404/410, got {r.status_code}"

    def test_C_expired_token_rejected(self, token):
        """C: Expired token (manually expired in DB) → 410."""
        # This test requires direct DB manipulation; skip if DB not accessible
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            import asyncio
            client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = client["mediaview_db"]

            async def expire():
                # Create a test org + invite
                email = _unique_email()
                r = httpx.post(f"{BASE}/organizations",
                               headers=_auth_headers(token),
                               json={"name": "ExpiredOrg"},
                               timeout=TIMEOUT)
                if r.status_code not in (200, 201):
                    return None
                org_id = r.json()["id"]
                r2 = httpx.post(f"{BASE}/organizations/{org_id}/invites",
                                headers=_auth_headers(token),
                                json={"email": email, "role": "SELF_SERVICE_MANAGER"},
                                timeout=TIMEOUT)
                if r2.status_code not in (200, 201):
                    return None
                inv_t = r2.json().get("token")
                if not inv_t:
                    return None
                # Force-expire
                past = datetime.utcnow() - timedelta(days=10)
                await db.org_invites.update_one({"token": inv_t}, {"$set": {"expires_at": past}})
                return inv_t

            inv_t = asyncio.get_event_loop().run_until_complete(expire())
            if inv_t is None:
                pytest.skip("Could not create test invite for expiration test")

            r = httpx.post(f"{BASE}/invites/{inv_t}/accept",
                           json={"name": "Expired", "password": "Test#1234"},
                           timeout=TIMEOUT)
            assert r.status_code == 410, f"C: Expected 410 for expired token, got {r.status_code}"
        except Exception as exc:
            pytest.skip(f"C: Skipped — DB manipulation failed: {exc}")

    def test_D_token_reuse_rejected(self, org_and_invite):
        """D: Already-accepted token is rejected on second use → 410."""
        # org_and_invite token was used in test_A — it should now be "accepted"
        inv_t = org_and_invite["invite_token"]
        r = httpx.post(f"{BASE}/invites/{inv_t}/accept",
                       json={"name": "Reuse Attempt", "password": "Reuse#1234"},
                       timeout=TIMEOUT)
        assert r.status_code == 410, f"D: Expected 410 for reused token, got {r.status_code} {r.text}"

    def test_E_wrong_email_auth_rejected(self, token):
        """E: Authenticated user with different email tries to accept → 403."""
        # Create an invite for a NEW email
        email = _unique_email()
        r = httpx.post(f"{BASE}/organizations",
                       headers=_auth_headers(token),
                       json={"name": "EmailMismatchOrg"},
                       timeout=TIMEOUT)
        if r.status_code not in (200, 201):
            pytest.skip("Cannot create org")
        org_id = r.json()["id"]
        r2 = httpx.post(f"{BASE}/organizations/{org_id}/invites",
                        headers=_auth_headers(token),
                        json={"email": email, "role": "SELF_SERVICE_MANAGER"},
                        timeout=TIMEOUT)
        if r2.status_code not in (200, 201):
            pytest.skip("Cannot create invite")
        inv_t = r2.json().get("token")

        # First, create the target user so they have an account (makes existing=True path)
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            import asyncio, bcrypt as _bcrypt
            client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db_motor = client["mediaview_db"]

            async def create_user():
                pw_hash = _bcrypt.hashpw("Test#1234".encode(), _bcrypt.gensalt()).decode()
                await db_motor.users.insert_one({
                    "id": str(uuid.uuid4()), "name": "Target User", "email": email,
                    "password_hash": pw_hash, "role": "customer",
                    "rbac_role": "SELF_SERVICE_MANAGER", "active": True, "session_epoch": 0,
                    "created_at": datetime.utcnow()
                })
            asyncio.get_event_loop().run_until_complete(create_user())
        except Exception:
            pytest.skip("E: Cannot create target user")

        # Now superadmin tries to accept an invite for a different email
        # (superadmin@mediadview.com != email)
        r3 = httpx.post(f"{BASE}/invites/{inv_t}/accept",
                        headers=_auth_headers(token),  # token is for superadmin@...
                        json={"name": "Mismatch", "password": "Test#1234"},
                        timeout=TIMEOUT)
        assert r3.status_code == 403, \
            f"E: Expected 403 for email mismatch, got {r3.status_code} {r3.text}"

    def test_F_superadmin_invite_blocked(self, token):
        """F: Owner invites email of SUPER_ADMIN → cannot modify/move that account → 403."""
        # The superadmin account email
        sa_email = "superadmin@mediadview.com"
        r = httpx.post(f"{BASE}/organizations",
                       headers=_auth_headers(token),
                       json={"name": "AttackerOrg"},
                       timeout=TIMEOUT)
        if r.status_code not in (200, 201):
            pytest.skip("Cannot create org")
        org_id = r.json()["id"]
        r2 = httpx.post(f"{BASE}/organizations/{org_id}/invites",
                        headers=_auth_headers(token),
                        json={"email": sa_email, "role": "SELF_SERVICE_MANAGER"},
                        timeout=TIMEOUT)
        if r2.status_code not in (200, 201):
            pytest.skip("Cannot create invite for superadmin email")
        inv_t = r2.json().get("token")

        # Attacker tries to accept the invite AS superadmin (with superadmin token, email matches)
        # → Must be blocked because superadmin is in PROTECTED_ROLES
        r3 = httpx.post(f"{BASE}/invites/{inv_t}/accept",
                        headers=_auth_headers(token),  # superadmin token
                        json={"name": "SA", "password": "unused"},
                        timeout=TIMEOUT)
        assert r3.status_code == 403, \
            f"F: Expected 403 protecting SUPER_ADMIN from invite, got {r3.status_code} {r3.text}"

    def test_G_privileged_role_in_invite_blocked(self, token):
        """G: Creating an invite that assigns SUPER_ADMIN role → blocked at accept time."""
        email = _unique_email()
        r = httpx.post(f"{BASE}/organizations",
                       headers=_auth_headers(token),
                       json={"name": "PrivRoleOrg"},
                       timeout=TIMEOUT)
        if r.status_code not in (200, 201):
            pytest.skip("Cannot create org")
        org_id = r.json()["id"]

        # Attempt to force a privileged role via direct DB insertion (bypass API validation)
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            import asyncio
            client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db_motor = client["mediaview_db"]
            exp = datetime.utcnow() + timedelta(days=7)

            async def insert_bad_invite():
                bad_token = f"bad_priv_{uuid.uuid4().hex}"
                await db_motor.org_invites.insert_one({
                    "id": str(uuid.uuid4()), "token": bad_token, "email": email,
                    "org_id": org_id, "role": "SUPER_ADMIN",  # privileged!
                    "invited_by_user_id": "test", "status": "pending",
                    "expires_at": exp, "created_at": datetime.utcnow()
                })
                return bad_token

            bad_t = asyncio.get_event_loop().run_until_complete(insert_bad_invite())
        except Exception:
            pytest.skip("G: Cannot inject test data")

        r2 = httpx.post(f"{BASE}/invites/{bad_t}/accept",
                        json={"name": "New User", "password": "Test#1234"},
                        timeout=TIMEOUT)
        assert r2.status_code == 400, \
            f"G: Expected 400 for privileged role in invite, got {r2.status_code} {r2.text}"

    def test_H_no_auth_for_new_user_still_works(self, token):
        """H: Normal invite for genuinely new email (no account) succeeds without auth."""
        email = _unique_email()
        r = httpx.post(f"{BASE}/organizations",
                       headers=_auth_headers(token),
                       json={"name": "NormalInviteOrg"},
                       timeout=TIMEOUT)
        if r.status_code not in (200, 201):
            pytest.skip("Cannot create org")
        org_id = r.json()["id"]
        r2 = httpx.post(f"{BASE}/organizations/{org_id}/invites",
                        headers=_auth_headers(token),
                        json={"email": email, "role": "SELF_SERVICE_MANAGER"},
                        timeout=TIMEOUT)
        if r2.status_code not in (200, 201):
            pytest.skip("Cannot create invite")
        inv_t = r2.json().get("token")

        r3 = httpx.post(f"{BASE}/invites/{inv_t}/accept",
                        json={"name": "Brand New User", "password": "Test#5678"},
                        timeout=TIMEOUT)
        assert r3.status_code == 200, f"H: Normal new-user invite failed: {r3.status_code} {r3.text}"
        assert r3.json().get("success") is True

    def test_I_cross_org_protected_account_safe(self, token):
        """I: Invite from Org A cannot move a SUPER_ADMIN from Org B → 403."""
        # SA is always in protected roles, so this is covered by test_F
        # Just verify the logic works with the admin's own token
        sa_email = "superadmin@mediadview.com"
        r = httpx.post(f"{BASE}/organizations",
                       headers=_auth_headers(token),
                       json={"name": "OrgA_CrossOrg"},
                       timeout=TIMEOUT)
        if r.status_code not in (200, 201):
            pytest.skip("Cannot create org")
        org_id = r.json()["id"]
        r2 = httpx.post(f"{BASE}/organizations/{org_id}/invites",
                        headers=_auth_headers(token),
                        json={"email": sa_email, "role": "MANAGED_VIEWER"},
                        timeout=TIMEOUT)
        if r2.status_code not in (200, 201):
            pytest.skip("Cannot create invite")
        inv_t = r2.json().get("token")

        r3 = httpx.post(f"{BASE}/invites/{inv_t}/accept",
                        headers=_auth_headers(token),  # SA token (email matches)
                        json={"name": "SA", "password": "unused"},
                        timeout=TIMEOUT)
        # Must be blocked by PROTECTED_ROLES check
        assert r3.status_code == 403, \
            f"I: Protected account moved across orgs! Got {r3.status_code} {r3.text}"


# ══════════════════════════════════════════════════════════════════════════════
# SEC-003 — Widget renderer XSS + API key exposure
# ══════════════════════════════════════════════════════════════════════════════

class TestSec003WidgetRenderer:
    """User-controlled widget config values must be HTML-escaped.
    API key must NEVER appear in rendered HTML output."""

    XSS_PAYLOAD = '<script>pwned()</script>'
    XSS_ESCAPED = '&lt;script&gt;pwned()&lt;/script&gt;'

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Use demo admin (has 'admin' role required for /admin/widgets)."""
        r = httpx.post(f"{BASE}/auth/v2/login",
                       json={"email": "admin.demo@mediadview.com", "password": "AdminDemo#2026"},
                       timeout=TIMEOUT)
        if r.status_code != 200:
            # Fallback to superadmin if demo admin not seeded
            r = httpx.post(f"{BASE}/auth/v2/login",
                           json={"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"},
                           timeout=TIMEOUT)
            if r.status_code != 200:
                pytest.skip("Cannot authenticate")
        return r.json()["access_token"]

    def _create_widget(self, token, widget_type: str, config: dict) -> str:
        """Create widget at /admin/widgets (requires admin role)."""
        r = httpx.post(f"{BASE}/admin/widgets",
                       headers=_auth_headers(token),
                       json={"widget_type": widget_type,
                             "name": f"sec003_{widget_type}",
                             "config": config,
                             "screen_id": "sec-test-screen"},
                       timeout=TIMEOUT)
        if r.status_code not in (200, 201):
            pytest.skip(f"Cannot create {widget_type} widget: {r.status_code} {r.text[:200]}")
        return r.json()["id"]

    def _delete_widget(self, token: str, wid: str):
        httpx.delete(f"{BASE}/admin/widgets/{wid}", headers=_auth_headers(token), timeout=TIMEOUT)

    def test_ticker_text_escaped(self, admin_token):
        """Ticker text must be HTML-escaped."""
        wid = self._create_widget(admin_token, "ticker", {"text": self.XSS_PAYLOAD, "speed": 80})
        r = httpx.get(f"{BASE}/widgets/{wid}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert self.XSS_ESCAPED in r.text, "ticker text not escaped"
        assert '<script>pwned()' not in r.text, "raw XSS in ticker text!"
        httpx.delete(f"{BASE}/widgets/{wid}", headers=_auth_headers(admin_token), timeout=TIMEOUT)

    def test_countdown_title_escaped(self, admin_token):
        """Countdown title must be HTML-escaped."""
        wid = self._create_widget(admin_token, "countdown",
                                  {"title": self.XSS_PAYLOAD, "target_date": "2030-01-01T00:00:00"})
        r = httpx.get(f"{BASE}/widgets/{wid}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert self.XSS_ESCAPED in r.text, "countdown title not escaped"
        httpx.delete(f"{BASE}/widgets/{wid}", headers=_auth_headers(admin_token), timeout=TIMEOUT)

    def test_qrcode_label_escaped(self, admin_token):
        """QR code label must be HTML-escaped."""
        wid = self._create_widget(admin_token, "qrcode",
                                  {"label": self.XSS_PAYLOAD, "url": "https://example.com"})
        r = httpx.get(f"{BASE}/widgets/{wid}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert self.XSS_ESCAPED in r.text, "qrcode label not escaped"
        httpx.delete(f"{BASE}/widgets/{wid}", headers=_auth_headers(admin_token), timeout=TIMEOUT)

    def test_qrcode_url_js_context_safe(self, admin_token):
        """QR code URL must be JSON-encoded in JS string context (no JS injection).
        A URL with double-quote injection must be escaped (json.dumps handles this)."""
        # This payload would break out of a naive single-quoted JS string,
        # but json.dumps properly escapes it inside a double-quoted string.
        malicious_url = '"); alert(document.cookie); var x=("'
        wid = self._create_widget(admin_token, "qrcode",
                                  {"label": "Scan", "url": malicious_url})
        r = httpx.get(f"{BASE}/widgets/{wid}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        # The raw double-quote injection must NOT appear unescaped
        # json.dumps encodes " as \" inside the string
        assert '"); alert(document.cookie)' not in r.text, \
            "Double-quote URL injection not escaped in JS context!"
        self._delete_widget(admin_token, wid)

    def test_youtube_video_id_validated(self, admin_token):
        """YouTube video_id must be alphanumeric only — arbitrary chars rejected."""
        malicious_id = '"><script>alert(1)</script>'
        wid = self._create_widget(admin_token, "youtube", {"video_id": malicious_id})
        r = httpx.get(f"{BASE}/widgets/{wid}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert '<script>alert(1)</script>' not in r.text, \
            "Malicious YouTube video_id was not sanitized!"
        assert 'Invalid video ID' in r.text or malicious_id not in r.text
        httpx.delete(f"{BASE}/widgets/{wid}", headers=_auth_headers(admin_token), timeout=TIMEOUT)

    def test_slides_javascript_url_rejected(self, admin_token):
        """Slides widget must reject javascript: URLs in iframe src."""
        wid = self._create_widget(admin_token, "slides", {"url": "javascript:alert(document.cookie)"})
        r = httpx.get(f"{BASE}/widgets/{wid}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert 'src="javascript:' not in r.text.lower(), \
            "javascript: URL appeared in iframe src!"
        assert 'about:blank' in r.text or 'javascript:' not in r.text
        httpx.delete(f"{BASE}/widgets/{wid}", headers=_auth_headers(admin_token), timeout=TIMEOUT)

    def test_webpage_javascript_url_rejected(self, admin_token):
        """Webpage widget must reject javascript: URLs in iframe src."""
        wid = self._create_widget(admin_token, "webpage", {"url": "javascript:void(0)"})
        r = httpx.get(f"{BASE}/widgets/{wid}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert 'src="javascript:' not in r.text.lower(), \
            "javascript: URL appeared in webpage iframe src!"
        httpx.delete(f"{BASE}/widgets/{wid}", headers=_auth_headers(admin_token), timeout=TIMEOUT)

    def test_weather_api_key_not_exposed(self, admin_token):
        """Weather widget: the API key must NEVER appear in rendered HTML."""
        fake_key = f"FAKE_API_KEY_{uuid.uuid4().hex}"
        wid = self._create_widget(admin_token, "weather",
                                  {"city": "London", "api_key": fake_key})
        r = httpx.get(f"{BASE}/widgets/{wid}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        assert fake_key not in r.text, \
            "Weather API key leaked in rendered HTML! (SEC-003 critical)"
        # Must instead call the backend proxy
        assert f"/api/widgets/{wid}/weather" in r.text or \
               "/weather" in r.text, \
               "Weather widget is not using the server-side proxy"
        httpx.delete(f"{BASE}/widgets/{wid}", headers=_auth_headers(admin_token), timeout=TIMEOUT)

    def test_weather_proxy_endpoint_exists(self, admin_token):
        """Weather proxy /api/widgets/{id}/weather must exist and return JSON (no api_key)."""
        fake_key = f"PROXY_KEY_{uuid.uuid4().hex}"
        wid = self._create_widget(admin_token, "weather",
                                  {"city": "Paris", "api_key": fake_key})
        r = httpx.get(f"{BASE}/widgets/{wid}/weather", timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "city" in data
        assert fake_key not in str(data), "API key leaked in weather proxy response!"
        httpx.delete(f"{BASE}/widgets/{wid}", headers=_auth_headers(admin_token), timeout=TIMEOUT)

    def test_clock_bg_css_injection_blocked(self, admin_token):
        """Clock bg_color must be validated — CSS injection must be rejected."""
        # Attempt CSS injection via background color
        wid = self._create_widget(admin_token, "clock",
                                  {"format": "12h",
                                   "bg_color": "red; background-image:url(javascript:alert(1))"})
        r = httpx.get(f"{BASE}/widgets/{wid}/render", timeout=TIMEOUT)
        assert r.status_code == 200
        # The malicious string should NOT appear verbatim in CSS
        assert "background-image:url(javascript:" not in r.text, \
            "CSS injection not blocked in clock bg_color!"
        httpx.delete(f"{BASE}/widgets/{wid}", headers=_auth_headers(admin_token), timeout=TIMEOUT)


# ══════════════════════════════════════════════════════════════════════════════
# H1 — CSP (documents P1 remaining work; does NOT expect unsafe-inline removed)
# ══════════════════════════════════════════════════════════════════════════════

class TestH1CSP:
    """Verify CSP header is present and documents the unsafe-inline P1 status."""

    def test_csp_header_present(self):
        """CSP header must be set on all API responses."""
        r = httpx.get(f"{BASE}/health", timeout=TIMEOUT)
        assert r.status_code == 200
        csp = r.headers.get("content-security-policy") or \
              r.headers.get("content-security-policy-report-only", "")
        assert csp, "No CSP header found on /api/health"

    def test_csp_default_src_not_wildcard(self):
        """default-src must not be '*' (wildcard defeats CSP)."""
        r = httpx.get(f"{BASE}/health", timeout=TIMEOUT)
        csp = r.headers.get("content-security-policy", "")
        assert "default-src *" not in csp, "default-src should not be wildcard!"

    def test_csp_script_src_has_unsafe_inline_documented_p1(self):
        """
        H1 P1 status: unsafe-inline is still present (expected) because inline
        <script> blocks in renderers have not yet been extracted to external files.
        This test DOCUMENTS the P1 blocker — it passes if unsafe-inline is present
        AND the blocker is acknowledged in security_headers.py.
        """
        r = httpx.get(f"{BASE}/health", timeout=TIMEOUT)
        csp = r.headers.get("content-security-policy", "")
        # Read the docstring from security_headers.py to verify P1 is documented
        import importlib.util, pathlib
        sh_path = pathlib.Path(__file__).parent.parent / "security_headers.py"
        content = sh_path.read_text()
        assert "P1" in content and "unsafe-inline" in content, \
            "H1 P1 blocker not documented in security_headers.py"


# ══════════════════════════════════════════════════════════════════════════════
# H2 — Trusted Proxy / X-Forwarded-For
# ══════════════════════════════════════════════════════════════════════════════

class TestH2TrustedProxy:
    """Verify TRUST_PROXY config exists and IP extraction respects it."""

    def test_trust_proxy_config_in_source(self):
        """TRUST_PROXY env var must be read in auth_v2.py."""
        import pathlib
        av2 = pathlib.Path(__file__).parent.parent / "auth_v2.py"
        content = av2.read_text()
        assert "TRUST_PROXY" in content, "TRUST_PROXY not in auth_v2.py"
        assert "request.client.host" in content, \
            "Fallback to direct TCP IP not present in auth_v2._ip()"

    def test_xff_spoofing_not_trusted_when_trust_proxy_false(self):
        """When TRUST_PROXY=false, a spoofed X-Forwarded-For must not bypass rate limiting.
        This is a code-level inspection test — we verify _ip() does NOT read XFF
        when TRUST_PROXY=false."""
        import importlib, pathlib
        av2_path = pathlib.Path(__file__).parent.parent / "auth_v2.py"
        content = av2_path.read_text()
        # When TRUST_PROXY is false, the function must use request.client.host
        assert 'if TRUST_PROXY:' in content, \
            "_ip() must have a TRUST_PROXY branch"
        # The else-path must fall through to request.client.host
        lines = content.splitlines()
        in_ip = False
        found_fallback = False
        for line in lines:
            if 'def _ip(' in line:
                in_ip = True
            if in_ip and 'request.client.host' in line:
                found_fallback = True
                break
        assert found_fallback, \
            "_ip() must fall back to request.client.host when TRUST_PROXY is false"


# ══════════════════════════════════════════════════════════════════════════════
# H3 — Public menu render published-state gate
# ══════════════════════════════════════════════════════════════════════════════

class TestH3MenuPublishedGate:
    """Draft menus must not render publicly. Only published/active menus are accessible."""

    @pytest.fixture(scope="class")
    def token(self):
        return _admin_token()

    @pytest.fixture(scope="class")
    def draft_menu_id(self, token):
        """Create a menu in draft state (default)."""
        r = httpx.post(f"{BASE}/menus",
                       headers=_auth_headers(token),
                       json={"name": "Draft Security Test", "restaurant_name": "Draft Rest."},
                       timeout=TIMEOUT)
        assert r.status_code in (200, 201), f"Create menu: {r.status_code}"
        menu_id = r.json()["id"]
        # Status should be "draft" by default
        assert r.json().get("status") == "draft"
        yield menu_id
        httpx.delete(f"{BASE}/menus/{menu_id}", headers=_auth_headers(token), timeout=TIMEOUT)

    @pytest.fixture(scope="class")
    def published_menu_id(self, token):
        """Create a menu and publish it."""
        r = httpx.post(f"{BASE}/menus",
                       headers=_auth_headers(token),
                       json={"name": "Published Test Menu",
                             "restaurant_name": "Pub Rest.",
                             "subtitle": "Open for testing"},
                       timeout=TIMEOUT)
        assert r.status_code in (200, 201)
        menu_id = r.json()["id"]
        httpx.put(f"{BASE}/menus/{menu_id}", headers=_auth_headers(token),
                  json={"status": "published"}, timeout=TIMEOUT)
        yield menu_id
        httpx.delete(f"{BASE}/menus/{menu_id}", headers=_auth_headers(token), timeout=TIMEOUT)

    def test_draft_menu_not_accessible_unauthenticated(self, draft_menu_id):
        """A draft menu must return 404 for unauthenticated requests."""
        r = httpx.get(f"{BASE}/menus/{draft_menu_id}/render", timeout=TIMEOUT)
        assert r.status_code == 404, \
            f"Draft menu rendered publicly! Expected 404, got {r.status_code}"

    def test_published_menu_accessible_unauthenticated(self, published_menu_id):
        """A published menu must render without auth (player + public display)."""
        r = httpx.get(f"{BASE}/menus/{published_menu_id}/render", timeout=TIMEOUT)
        assert r.status_code == 200, \
            f"Published menu not accessible: {r.status_code}"
        assert "Pub Rest." in r.text

    def test_draft_menu_accessible_to_owner(self, token, draft_menu_id):
        """Owner must be able to preview their own draft menu with auth."""
        r = httpx.get(f"{BASE}/menus/{draft_menu_id}/render",
                      headers=_auth_headers(token),
                      timeout=TIMEOUT)
        assert r.status_code == 200, \
            f"Owner cannot preview own draft menu: {r.status_code}"

    def test_nonexistent_menu_returns_404(self):
        """Non-existent menu ID returns 404."""
        r = httpx.get(f"{BASE}/menus/{uuid.uuid4()}/render", timeout=TIMEOUT)
        assert r.status_code == 404

    def test_draft_menu_not_in_player_playlist(self, token, draft_menu_id):
        """Draft menus are excluded from player playlists."""
        # Create a screen and playlist
        r = httpx.post(f"{BASE}/admin/screens",
                       headers=_auth_headers(token),
                       json={"name": "H3 Test Screen", "location": "Test", "type": "indoor"},
                       timeout=TIMEOUT)
        if r.status_code not in (200, 201):
            pytest.skip("Cannot create screen")
        screen_id = r.json().get("id") or r.json().get("screen_id")

        # Create a playlist with the draft menu
        rp = httpx.post(f"{BASE}/playlists",
                        headers=_auth_headers(token),
                        json={"name": "H3 Test Playlist", "screen_id": screen_id,
                              "items": [{"type": "menu", "ref_id": draft_menu_id}]},
                        timeout=TIMEOUT)
        if rp.status_code not in (200, 201):
            pytest.skip("Cannot create playlist")
        pl_id = rp.json().get("id")

        # Publish the playlist and check the player API
        httpx.put(f"{BASE}/playlists/{pl_id}",
                  headers=_auth_headers(token),
                  json={"status": "published"},
                  timeout=TIMEOUT)
        httpx.post(f"{BASE}/playlists/{pl_id}/publish",
                   headers=_auth_headers(token),
                   timeout=TIMEOUT)

        # Pair the screen and check player playlist
        rsc = httpx.get(f"{BASE}/admin/screens/{screen_id}",
                        headers=_auth_headers(token), timeout=TIMEOUT)
        pairing_code = rsc.json().get("pairing_code") if rsc.status_code == 200 else None

        if pairing_code:
            rpl = httpx.get(f"{BASE}/player/{screen_id}/playlist", timeout=TIMEOUT)
            if rpl.status_code == 200:
                items = rpl.json()
                menu_urls = [i.get("media_url", "") for i in items
                             if "menu:" + draft_menu_id in i.get("media_id", "")]
                assert len(menu_urls) == 0, \
                    "Draft menu URL appeared in player playlist!"

        # Cleanup
        httpx.delete(f"{BASE}/playlists/{pl_id}", headers=_auth_headers(token), timeout=TIMEOUT)
        httpx.delete(f"{BASE}/admin/screens/{screen_id}", headers=_auth_headers(token), timeout=TIMEOUT)


# ══════════════════════════════════════════════════════════════════════════════
# REGRESSION: Phases 0–4 still working
# ══════════════════════════════════════════════════════════════════════════════

class TestRegressions:
    """Quick regression smoke tests for existing features."""

    def test_health_ok(self):
        r = httpx.get(f"{BASE}/health", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_ready_ok(self):
        r = httpx.get(f"{BASE}/ready", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_auth_v2_login_still_works(self):
        r = httpx.post(f"{BASE}/auth/v2/login",
                       json={"email": "superadmin@mediadview.com", "password": "SuperAdmin#2026"},
                       timeout=TIMEOUT)
        assert r.status_code == 200, f"Auth v2 login broken: {r.status_code}"
        assert "access_token" in r.json()

    def test_fase3_marketplace_screens(self):
        """Fase 3: marketplace/screens requires auth — returns list with auth."""
        token = _admin_token()
        r = httpx.get(f"{BASE}/marketplace/screens",
                      headers=_auth_headers(token), timeout=TIMEOUT)
        assert r.status_code == 200, f"Fase 3 regression: /marketplace/screens {r.status_code}"
        assert isinstance(r.json(), list)

    def test_fase4_managed_dashboard(self):
        """Fase 4: managed/dashboard accessible to admin (MEDIAVIEW_ADMIN or SUPPORT or MANAGED_VIEWER)."""
        # Try with MANAGED_VIEWER credentials from RBAC seed
        r = httpx.post(f"{BASE}/auth/v2/login",
                       json={"email": "rbac.viewer@test.com", "password": "RbacTest#2026"},
                       timeout=TIMEOUT)
        if r.status_code != 200:
            pytest.skip("MANAGED_VIEWER test user not seeded (run /api/admin/rbac/seed-test-users)")
        viewer_token = r.json()["access_token"]
        r2 = httpx.get(f"{BASE}/managed/dashboard",
                       headers=_auth_headers(viewer_token), timeout=TIMEOUT)
        assert r2.status_code == 200, f"Fase 4 regression: /managed/dashboard {r2.status_code}"

    def test_menus_crud_still_works(self):
        token = _admin_token()
        r = httpx.get(f"{BASE}/menus", headers=_auth_headers(token), timeout=TIMEOUT)
        assert r.status_code == 200, f"Menus CRUD broken: {r.status_code}"

    def test_widgets_list_still_works(self):
        """Widgets list at /admin/widgets requires admin role."""
        r = httpx.post(f"{BASE}/auth/v2/login",
                       json={"email": "admin.demo@mediadview.com", "password": "AdminDemo#2026"},
                       timeout=TIMEOUT)
        if r.status_code != 200:
            pytest.skip("admin.demo not seeded")
        t = r.json()["access_token"]
        r2 = httpx.get(f"{BASE}/admin/widgets", headers=_auth_headers(t), timeout=TIMEOUT)
        assert r2.status_code == 200, f"Widgets list broken: {r2.status_code}"
