"""Stable direct-download contract for Android TV sideloading."""

from fastapi.testclient import TestClient

from server import app


def test_all_tv_friendly_aliases_share_the_stable_release(monkeypatch):
    release_url = (
        "https://github.com/dwaine01/mediadview-platform/"
        "releases/download/player-latest/mediaview-player.apk"
    )
    monkeypatch.setenv("PLAYER_APK_RELEASE_URL", release_url)
    with TestClient(app) as client:
        for path in ("/apk", "/apk.apk", "/mediaview.apk", "/download.apk"):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 302
            assert response.headers["location"] == release_url
            assert response.headers["cache-control"] == "no-store"
