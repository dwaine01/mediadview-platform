"""
Backend regression tests for commit 7ea9159:
  (1) Bilingual EN/ES site infrastructure (i18n.js served + <script> tags in HTML)
  (2) Josue Tejada portrait full-photo fix on /about (mobile portrait)

Runs against production https://mediadview.com when reachable, else falls
back to http://localhost:8001 with Host: mediadview.com header.
All endpoints are public / unauthenticated.
"""
import pytest
import requests

PROD = "https://mediadview.com"
LOCAL = "http://localhost:8001"


def _choose_base():
    try:
        r = requests.get(f"{PROD}/api/web/i18n.js", timeout=8)
        if r.status_code == 200 and "MV_I18N" in r.text:
            return PROD, {}
    except Exception:
        pass
    return LOCAL, {"Host": "mediadview.com"}


BASE, HEADERS = _choose_base()


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update(HEADERS)
    return sess


# ── i18n script itself ────────────────────────────────────────────────────
class TestI18nScript:
    def test_i18n_script_200(self, s):
        r = s.get(f"{BASE}/api/web/i18n.js", timeout=10)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        assert len(r.text) > 500

    def test_i18n_script_has_required_keys(self, s):
        body = s.get(f"{BASE}/api/web/i18n.js", timeout=10).text
        # required identifiers
        for token in ["MV_I18N", "landing.card.title", "en:", "es:", "lang-toggle", "mv_lang"]:
            assert token in body, f"Missing token '{token}' in i18n.js"

    def test_i18n_script_has_both_translations(self, s):
        body = s.get(f"{BASE}/api/web/i18n.js", timeout=10).text
        # EN string
        assert "Publish your own ad" in body
        # ES string
        assert "Publica tu anuncio t\u00fa mismo" in body
        # Toggle button labels
        assert '"lang.toggle": "ES"' in body
        assert '"lang.toggle": "EN"' in body

    def test_i18n_script_has_localstorage_persistence(self, s):
        body = s.get(f"{BASE}/api/web/i18n.js", timeout=10).text
        assert "localStorage" in body
        assert "mv_lang" in body


# ── HTML pages include the script ─────────────────────────────────────────
class TestHtmlIncludesI18n:
    def test_landing_html_ok(self, s):
        r = s.get(f"{BASE}/", timeout=10)
        # landing may be served at "/" via web routes
        assert r.status_code in (200, 301, 302)
        if r.status_code in (301, 302):
            r = s.get(f"{BASE}{r.headers.get('Location', '/')}", timeout=10)
            assert r.status_code == 200

    def test_landing_has_i18n_script_tag(self, s):
        # Try direct landing.html path first
        r = s.get(f"{BASE}/", timeout=10)
        html = r.text
        assert '/api/web/i18n.js' in html, "landing missing i18n.js script tag"

    def test_landing_has_data_i18n_attrs(self, s):
        html = s.get(f"{BASE}/", timeout=10).text
        for attr in ['data-i18n="landing.card.title"',
                     'data-i18n="nav.publish"',
                     'data-i18n="nav.dashboard"']:
            assert attr in html, f"landing missing attribute: {attr}"

    def test_landing_has_lang_toggle_button(self, s):
        html = s.get(f"{BASE}/", timeout=10).text
        assert 'id="lang-toggle"' in html

    def test_about_html_200(self, s):
        r = s.get(f"{BASE}/about", timeout=10)
        assert r.status_code == 200

    def test_about_has_i18n_script_tag(self, s):
        html = s.get(f"{BASE}/about", timeout=10).text
        assert '/api/web/i18n.js' in html, "about missing i18n.js script tag"

    def test_about_has_lang_toggle_button(self, s):
        html = s.get(f"{BASE}/about", timeout=10).text
        assert 'id="lang-toggle"' in html

    def test_about_has_ceo_photo_img_tag(self, s):
        """New fix: background-image replaced with <img class='ceo-photo-img'>."""
        html = s.get(f"{BASE}/about", timeout=10).text
        assert 'class="ceo-photo-img"' in html, "ceo-photo-img class not found"
        assert 'src="/api/web/ceo-photo.png"' in html or "ceo-photo.png" in html
        assert 'alt="Josue Tejada"' in html

    def test_about_mobile_object_fit_contain_rule_present(self, s):
        """CSS media query for mobile portrait must apply object-fit:contain."""
        html = s.get(f"{BASE}/about", timeout=10).text
        # Both must appear in the same file (inline <style>)
        assert "@media(max-width:768px)" in html or "@media (max-width:768px)" in html
        assert "object-fit:contain" in html.replace(" ", "")


# ── ceo-photo.png asset served ────────────────────────────────────────────
class TestCeoPhotoAsset:
    def test_ceo_photo_200(self, s):
        r = s.get(f"{BASE}/api/web/ceo-photo.png", timeout=15)
        assert r.status_code == 200
        # PNG magic bytes
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n", "Not a valid PNG"
        assert len(r.content) > 5000, "PNG suspiciously small"

    def test_ceo_photo_content_type(self, s):
        r = s.head(f"{BASE}/api/web/ceo-photo.png", timeout=10)
        ct = r.headers.get("content-type", "").lower()
        assert "image" in ct
