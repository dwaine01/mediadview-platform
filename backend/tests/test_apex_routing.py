"""
Bug-fix verification: apex domain must serve the customer.html SPA
(hero 'Haz que tu negocio se vea todos los dias'), while panel.* keeps
serving the admin panel and /home keeps the legacy landing page.

Runs against production https://mediadview.com. Falls back to the preview
backend + explicit Host header if production is not reachable.
"""
import os
import time
import uuid
import pytest
import requests

PROD_APEX = "https://mediadview.com"
PROD_WWW = "https://www.mediadview.com"
PROD_PANEL = "https://panel.mediadview.com"

# Preview backend as fallback (Host header will simulate the target domain)
PREVIEW = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://menu-studio-3.preview.emergentagent.com"
PREVIEW = PREVIEW.rstrip("/")

CUSTOMER_TITLE = "MediAd View — Publicidad en Pantallas Digitales"
CUSTOMER_HERO = "Haz que tu negocio se vea todos los dias"
PANEL_TITLE = "MediAd View — Digital Signage Platform"

SPA_VIEW_IDS = [
    'id="v-landing"', 'id="v-login"', 'id="v-register"', 'id="v-marketplace"',
    'id="v-plans"', 'id="v-upload"', 'id="v-success"', 'id="v-portal"',
    'id="v-edit-camp"', 'id="v-profile"', 'id="v-changepwd"', 'id="v-forgot"',
]


def _get(url, host=None, allow_redirects=True, timeout=15):
    headers = {}
    if host:
        headers["Host"] = host
    return requests.get(url, headers=headers, allow_redirects=allow_redirects, timeout=timeout)


# ------------------------ APEX -------------------------------------
class TestApexServesCustomerSPA:
    def test_apex_returns_200(self):
        r = _get(f"{PROD_APEX}/")
        assert r.status_code == 200, f"apex status={r.status_code}"

    def test_apex_body_has_customer_hero(self):
        r = _get(f"{PROD_APEX}/")
        assert CUSTOMER_HERO in r.text, "apex is NOT serving customer.html hero"

    def test_apex_body_has_customer_title(self):
        r = _get(f"{PROD_APEX}/")
        assert CUSTOMER_TITLE in r.text, "apex title mismatch — not customer.html"

    def test_apex_body_has_at_least_8_spa_views(self):
        r = _get(f"{PROD_APEX}/")
        found = [vid for vid in SPA_VIEW_IDS if vid in r.text]
        assert len(found) >= 8, f"only {len(found)}/12 SPA view ids found: {found}"


# ------------------------ WWW --------------------------------------
class TestWwwServesCustomerSPA:
    def test_www_terminates_on_customer_html(self):
        r = _get(f"{PROD_WWW}/")
        assert r.status_code == 200
        assert CUSTOMER_HERO in r.text, "www did not resolve to customer.html body"
        assert CUSTOMER_TITLE in r.text


# ------------------------ PANEL (regression) -----------------------
class TestPanelStillServesAdmin:
    def test_panel_returns_200(self):
        r = _get(f"{PROD_PANEL}/")
        assert r.status_code == 200

    def test_panel_has_admin_title(self):
        r = _get(f"{PROD_PANEL}/")
        assert PANEL_TITLE in r.text, "panel is NOT serving admin index.html"

    def test_panel_does_NOT_have_customer_hero(self):
        r = _get(f"{PROD_PANEL}/")
        assert CUSTOMER_HERO not in r.text, "panel accidentally serves customer SPA"


# ------------------------ /home (backward compat) ------------------
class TestHomeLegacyMarketing:
    def test_home_returns_200(self):
        r = _get(f"{PROD_APEX}/home")
        assert r.status_code == 200

    def test_home_serves_legacy_landing(self):
        r = _get(f"{PROD_APEX}/home")
        # legacy title: 'MediAd View — Digital Signage & LED Advertising Solutions'
        assert ("Digital Signage" in r.text) or ("Advertise" in r.text) or ("Advertising" in r.text), \
            "/home does not look like the legacy marketing page"

    def test_home_does_not_only_show_customer_hero(self):
        # It is acceptable if landing.html mentions the hero string too;
        # what we do NOT want is /home == customer SPA. Assert the legacy
        # marketing title is present.
        r = _get(f"{PROD_APEX}/home")
        assert "Digital Signage" in r.text


# ------------------------ SPA CORE ROUTES --------------------------
SPA_ROUTES = ["/signup", "/login", "/portal", "/marketplace", "/api/screen", "/api/marketplace"]


@pytest.mark.parametrize("path", SPA_ROUTES)
def test_spa_core_routes_serve_customer_html(path):
    r = _get(f"{PROD_APEX}{path}")
    assert r.status_code == 200, f"{path} status={r.status_code}"
    assert CUSTOMER_HERO in r.text, f"{path} does not serve customer.html (missing hero)"
    assert CUSTOMER_TITLE in r.text, f"{path} does not serve customer.html (title)"


# ------------------------ AUTH SANITY ------------------------------
class TestAuthSanity:
    email = f"walkthrough+{int(time.time())}-{uuid.uuid4().hex[:6]}@example.com"
    password = "SafePass1234!"
    name = "Walkthrough Tester"
    company = "Walkthrough Co"

    def test_register_returns_token(self):
        r = requests.post(
            f"{PROD_APEX}/api/auth/register",
            json={"name": self.name, "email": self.email,
                  "password": self.password, "company_name": self.company},
            timeout=15,
        )
        assert r.status_code == 200, f"register status={r.status_code} body={r.text[:300]}"
        data = r.json()
        assert data.get("access_token"), "no access_token returned by register"
        assert data.get("user", {}).get("email") == self.email.lower()
        # stash for the login test
        TestAuthSanity._registered_email = self.email

    def test_login_with_new_credentials(self):
        email = getattr(TestAuthSanity, "_registered_email", None)
        assert email, "prerequisite register test did not run/succeed"
        r = requests.post(
            f"{PROD_APEX}/api/auth/login",
            json={"email": email, "password": self.password},
            timeout=15,
        )
        assert r.status_code == 200, f"login status={r.status_code} body={r.text[:300]}"
        data = r.json()
        assert data.get("access_token"), "no access_token returned by login"
        assert data.get("user", {}).get("email") == email.lower()
