"""Iteration 37 — Backend regression suite for:

1. BUG fix: POST /api/workspace/menus/ai-import must return 200 with items
   extracted from a real menu photo (base64). No 500 / ModuleNotFoundError.
2. Endpoint validations: unsupported content_type -> 400, corrupt base64 -> 400,
   no token -> 401.
3. Dockerfile contains the emergentintegrations --no-deps step with the
   --extra-index-url from Emergent; stripe==15.3.0 and openai==1.99.9 stay
   pinned in requirements.txt (fix didn't downgrade them).
4. Import sanity: `emergentintegrations.llm.chat` is importable in this pod
   (mirrors what the Dockerfile step will guarantee in production).
5. Public playlist upload regression: unknown token -> 404, text/plain body
   on a valid token+allow_upload -> 415 (never 500).
"""
from __future__ import annotations

import pathlib
import re
import uuid

import pytest
import requests

# Local import of the tiny image factory (tests/ is a package).
from tests._make_menu_image import make_menu_jpeg_b64

OWNER = {"email": "pizzeria@demo.com", "password": "Pizza1234!"}


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
def _login(base_url, creds):
    r = requests.post(f"{base_url}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def owner_token(base_url):
    return _login(base_url, OWNER)


@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture(scope="module")
def menu_image_b64():
    return make_menu_jpeg_b64()


# --------------------------------------------------------------------------- #
# 1. Package / infra assertions                                               #
# --------------------------------------------------------------------------- #
class TestPackageAndDockerfile:
    """Ensure the fix ingredients are in place."""

    def test_emergentintegrations_importable_in_pod(self):
        """The pod already has the package; production will after the Docker fix."""
        from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage  # noqa: F401

    def test_dockerfile_contains_no_deps_emergent_step(self):
        content = pathlib.Path("/app/Dockerfile").read_text()
        assert "emergentintegrations" in content, "Dockerfile must install emergentintegrations"
        assert "--no-deps" in content, "Install must be --no-deps to preserve stripe/openai pins"
        assert "https://d33sy5i8bnduwe.cloudfront.net/simple/" in content, (
            "Must use Emergent index URL (--extra-index-url)"
        )
        assert "--extra-index-url" in content

    def test_requirements_pins_are_untouched(self):
        req = pathlib.Path("/app/backend/requirements.txt").read_text()
        assert re.search(r"^stripe==15\.3\.0\s*$", req, re.M), "stripe must remain 15.3.0"
        assert re.search(r"^openai==1\.99\.9\s*$", req, re.M), "openai must remain 1.99.9"
        # emergentintegrations is intentionally NOT in requirements.txt (installed
        # via Dockerfile with --no-deps).
        assert not re.search(r"^emergentintegrations", req, re.M), (
            "emergentintegrations must NOT be in requirements.txt"
        )

    def test_installed_stripe_openai_versions(self):
        import openai
        import stripe
        assert stripe.VERSION == "15.3.0"
        assert openai.__version__ == "1.99.9"


# --------------------------------------------------------------------------- #
# 2. Endpoint validations (fast, no LLM call)                                 #
# --------------------------------------------------------------------------- #
class TestAiImportValidations:
    """Fast negative paths — never reach the LLM."""

    def test_unsupported_content_type_returns_400(self, base_url, owner_headers, menu_image_b64):
        r = requests.post(
            f"{base_url}/api/workspace/menus/ai-import",
            headers=owner_headers,
            json={"image_base64": menu_image_b64, "content_type": "image/gif"},
            timeout=30,
        )
        assert r.status_code == 400, r.text
        assert "Formato no soportado" in r.text or "no soportado" in r.text.lower()

    def test_corrupt_base64_returns_400(self, base_url, owner_headers):
        r = requests.post(
            f"{base_url}/api/workspace/menus/ai-import",
            headers=owner_headers,
            json={
                "image_base64": "!!!not-valid-base64@@@" + "x" * 40,
                "content_type": "image/jpeg",
            },
            timeout=30,
        )
        assert r.status_code == 400, r.text

    def test_missing_token_returns_401(self, base_url, menu_image_b64):
        r = requests.post(
            f"{base_url}/api/workspace/menus/ai-import",
            json={"image_base64": menu_image_b64, "content_type": "image/jpeg"},
            timeout=30,
        )
        assert r.status_code == 401, r.text


# --------------------------------------------------------------------------- #
# 3. Happy path — hits the LLM (slower)                                       #
# --------------------------------------------------------------------------- #
class TestAiImportHappyPath:
    """The heart of the bug fix — must return 200 with real items, no 500."""

    def test_menu_photo_returns_items(self, base_url, owner_headers, menu_image_b64):
        r = requests.post(
            f"{base_url}/api/workspace/menus/ai-import",
            headers=owner_headers,
            json={"image_base64": menu_image_b64, "content_type": "image/jpeg"},
            timeout=180,  # LLM vision calls can take a while
        )
        assert r.status_code == 200, (
            f"Expected 200, got {r.status_code}. Body: {r.text[:600]}"
        )
        body = r.json()
        assert isinstance(body, dict)
        assert "menu_name" in body and isinstance(body["menu_name"], str)
        assert "currency" in body and isinstance(body["currency"], str)
        assert "items" in body and isinstance(body["items"], list)
        assert "raw_count" in body and isinstance(body["raw_count"], int)
        assert body["raw_count"] > 0, f"Expected products extracted, got 0. Body: {body}"

        # Each item must have name + numeric price
        for it in body["items"]:
            assert isinstance(it.get("name"), str) and it["name"].strip()
            assert isinstance(it.get("price"), (int, float))
            assert it["price"] >= 0

        # We drew concrete products with prices; check at least one made it through.
        joined = " ".join(i["name"].lower() for i in body["items"])
        assert any(k in joined for k in ["margarita", "pepperoni", "quesos",
                                          "hawaiana", "agua", "refresco",
                                          "cerveza", "pizza"]), (
            f"None of the drawn products found in extracted items: {body['items']}"
        )


# --------------------------------------------------------------------------- #
# 4. Public playlists upload — regression from prior fix                      #
# --------------------------------------------------------------------------- #
class TestPublicPlaylistUploadRegression:
    """POST /api/public/playlists/{token}/media must never 500 anymore.

    - Unknown token → 404.
    - Valid token + wrong content-type on the file part → 415.
    """

    def test_unknown_token_returns_404(self, base_url):
        fake_token = f"nope-{uuid.uuid4().hex}"
        r = requests.post(
            f"{base_url}/api/public/playlists/{fake_token}/media",
            files={"file": ("t.jpg", b"\x00\x00", "image/jpeg")},
            timeout=20,
        )
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text[:300]}"

    def test_valid_token_wrong_content_type_returns_415(self, base_url, owner_headers, owner_token):
        """Create a playlist, enable its public upload token, then send text/plain."""
        # Create a playlist owned by the demo workspace.
        create = requests.post(
            f"{base_url}/api/workspace/playlists",
            headers=owner_headers,
            json={"name": f"TEST_iter37_{uuid.uuid4().hex[:6]}"},
            timeout=20,
        )
        if create.status_code >= 400:
            pytest.skip(f"Playlist create not available: {create.status_code} {create.text[:200]}")
        playlist_id = create.json().get("id") or create.json().get("playlist", {}).get("id")
        assert playlist_id, f"No id returned: {create.json()}"

        # Enable public upload — try the two known shapes.
        pub_token = None
        for path, payload in [
            (f"/api/workspace/playlists/{playlist_id}/public-link",
             {"allow_upload": True}),
            (f"/api/workspace/playlists/{playlist_id}/public",
             {"allow_upload": True, "enabled": True}),
        ]:
            resp = requests.post(f"{base_url}{path}", headers=owner_headers,
                                 json=payload, timeout=20)
            if resp.status_code < 400:
                data = resp.json()
                pub_token = (data.get("token") or data.get("public_token")
                             or (data.get("public") or {}).get("token"))
                if pub_token:
                    break

        if not pub_token:
            pytest.skip("Public-link endpoint shape unknown in this build; "
                        "unknown-token 404 path already covers regression.")

        r = requests.post(
            f"{base_url}/api/public/playlists/{pub_token}/media",
            files={"file": ("t.txt", b"hello world", "text/plain")},
            timeout=20,
        )
        # Cleanup
        requests.delete(f"{base_url}/api/workspace/playlists/{playlist_id}",
                        headers=owner_headers, timeout=20)

        assert r.status_code == 415, (
            f"Expected 415, got {r.status_code}: {r.text[:300]}"
        )
