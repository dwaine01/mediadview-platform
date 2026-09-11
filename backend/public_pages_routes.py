"""Public, unauthenticated apex-domain pages: landing/marketing pages, the
customer SPA entry points (signup/login/portal/marketplace), and the short
TV-sideloading URLs for the Android player APK.

Extracted from server.py (Phase 1 of the modularization plan — see
docs/AGENT_COORDINATION.md). This is a pure relocation: every route keeps its
exact path, method, and response, registered on the main `app` (not
`api_router`) exactly as before, via `app.include_router(...)` with no
prefix. No behavior change.

Dependency note: `customer_spa_build()` is also used by server.py's
`/api/app-build` endpoint — import it from here instead of redefining it.
"""

import hashlib
import os
import re
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse


def customer_spa_build(web_dir: str) -> str:
    """Short fingerprint of customer.html, used to bust phone caches."""
    path = os.path.join(web_dir, 'customer.html')
    try:
        stat = os.stat(path)
        return hashlib.sha256(f"{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest()[:8]
    except OSError:
        return "dev"


def _latest_player_apk(web_dir: str) -> str:
    """Pick the highest-versioned mediaview-player-*.apk in web/. Falls back
    to the unversioned mediaview-player.apk if no versioned APK is found."""
    try:
        candidates = []
        for f in os.listdir(web_dir):
            if f.startswith("mediaview-player-v") and f.endswith(".apk"):
                candidates.append(f)
        if candidates:
            # semver-like sort on the numeric parts inside "v<X.Y.Z>"
            def _key(name: str):
                m = re.search(r"v(\d+)\.(\d+)\.(\d+)", name)
                return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
            candidates.sort(key=_key, reverse=True)
            return candidates[0]
    except Exception:
        pass
    return "mediaview-player.apk"


def _player_release_url() -> str:
    override = os.getenv("PLAYER_APK_RELEASE_URL", "").strip()
    if override:
        return override
    repository = os.getenv("PLAYER_RELEASE_REPOSITORY", "dwaine01/mediadview-platform").strip()
    tag = os.getenv("PLAYER_RELEASE_TAG", "player-latest").strip()
    asset = os.getenv("PLAYER_RELEASE_ASSET", "mediaview-player.apk").strip()
    return f"https://github.com/{repository}/releases/download/{tag}/{asset}"


def _serve_player_apk() -> RedirectResponse:
    """Keep the TV-friendly URL stable while APK binaries live in Releases."""
    return RedirectResponse(
        url=_player_release_url(),
        status_code=302,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def create_public_pages_router(web_dir: str) -> APIRouter:
    """Build the router of public apex-domain pages. `web_dir` must be the
    same WEB_DIR used by server.py (str(ROOT_DIR / 'web'))."""
    router = APIRouter()

    @router.get("/", include_in_schema=False)
    async def root(request: Request):
        host = (request.headers.get("host") or "").lower()
        if host.startswith("panel."):
            return FileResponse(os.path.join(web_dir, 'index.html'), media_type='text/html')
        return FileResponse(os.path.join(web_dir, 'landing.html'), media_type='text/html')

    @router.get("/home", include_in_schema=False)
    async def home_marketing():
        return FileResponse(os.path.join(web_dir, 'landing.html'), media_type='text/html')

    @router.get("/about", include_in_schema=False)
    async def about():
        return FileResponse(os.path.join(web_dir, 'about.html'), media_type='text/html')

    @router.get("/for-business", include_in_schema=False)
    async def for_business():
        return FileResponse(os.path.join(web_dir, 'for-business.html'), media_type='text/html')

    @router.get("/api/for-business", include_in_schema=False)
    async def for_business_api():
        return FileResponse(os.path.join(web_dir, 'for-business.html'), media_type='text/html')

    @router.get("/restaurants", include_in_schema=False)
    async def restaurants_landing():
        return FileResponse(os.path.join(web_dir, 'restaurants.html'), media_type='text/html')

    @router.get("/api/restaurants", include_in_schema=False)
    async def restaurants_api():
        return FileResponse(os.path.join(web_dir, 'restaurants.html'), media_type='text/html')

    @router.get("/sign-permit-information", include_in_schema=False)
    async def sign_permit_form_page():
        return FileResponse(os.path.join(web_dir, 'sign-permit.html'), media_type='text/html')

    @router.get("/signup", include_in_schema=False)
    async def _signup():
        return FileResponse(os.path.join(web_dir, 'customer.html'), media_type='text/html',
                            headers={'Cache-Control': 'no-store, must-revalidate'})

    @router.get("/login", include_in_schema=False)
    async def _login():
        return FileResponse(os.path.join(web_dir, 'customer.html'), media_type='text/html',
                            headers={'Cache-Control': 'no-store, must-revalidate'})

    @router.get("/portal", include_in_schema=False)
    async def _portal():
        return FileResponse(os.path.join(web_dir, 'customer.html'), media_type='text/html',
                            headers={'Cache-Control': 'no-store, must-revalidate'})

    @router.get("/marketplace", include_in_schema=False)
    async def _marketplace(v: Optional[str] = None):
        build = customer_spa_build(web_dir)
        if v != build:
            return RedirectResponse(f"/marketplace?v={build}", status_code=302)
        return FileResponse(os.path.join(web_dir, 'customer.html'), media_type='text/html',
                            headers={'Cache-Control': 'no-store, must-revalidate'})

    @router.get("/apk", include_in_schema=False)
    async def apk_short_url():
        """Short URL for sideloading via TV Downloader app."""
        return _serve_player_apk()

    @router.get("/apk.apk", include_in_schema=False)
    async def apk_dot_apk():
        """URL ending in .apk — some Downloader versions require the extension
        to correctly detect the file as an installable Android package."""
        return _serve_player_apk()

    @router.get("/mediaview.apk", include_in_schema=False)
    async def mediaview_apk():
        """Branded direct-download URL: mediadview.com/mediaview.apk"""
        return _serve_player_apk()

    @router.get("/download.apk", include_in_schema=False)
    async def download_dot_apk():
        """Alias — some users type /download.apk instead of /apk."""
        return _serve_player_apk()

    return router
