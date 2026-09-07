"""Iteración 32 — producto agotado, promo instantánea y reporte semanal."""
import os
import re

import requests

BASE = os.environ.get("MV_BASE", "http://localhost:8001")
OWNER = ("pizzeria@demo.com", "Pizza1234!")
OTHER = ("testws@test.com", "Test1234!")


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_sold_out_item_disappears_from_the_render():
    h = _login(*OWNER)
    menu = requests.get(f"{BASE}/api/workspace/menus", headers=h, timeout=30).json()[0]
    item = menu["items"][0]

    page = requests.get(f"{BASE}/api/menus/{menu['id']}/render", headers=h, timeout=30)
    assert page.status_code == 200
    assert item["name"] in page.text

    off = requests.put(f"{BASE}/api/workspace/menus/{menu['id']}/items/{item['id']}",
                       headers=h, timeout=30, json={"available": False})
    assert off.status_code == 200, off.text

    hidden = requests.get(f"{BASE}/api/menus/{menu['id']}/render", headers=h, timeout=30)
    assert hidden.status_code == 200
    assert item["name"] not in hidden.text, "un producto agotado debe desaparecer del menú"

    feed = requests.get(f"{BASE}/api/workspace/activity?limit=10", headers=h, timeout=30).json()
    assert any(e["action"] == "menu_item.sold_out" for e in feed)

    back = requests.put(f"{BASE}/api/workspace/menus/{menu['id']}/items/{item['id']}",
                        headers=h, timeout=30, json={"available": True})
    assert back.status_code == 200
    restored = requests.get(f"{BASE}/api/menus/{menu['id']}/render", headers=h, timeout=30)
    assert item["name"] in restored.text
    feed = requests.get(f"{BASE}/api/workspace/activity?limit=10", headers=h, timeout=30).json()
    assert any(e["action"] == "menu_item.restored" for e in feed)


def test_instant_promo_takes_over_and_can_be_turned_off():
    h = _login(*OWNER)

    launched = requests.post(f"{BASE}/api/workspace/promos", headers=h, timeout=60, json={
        "kind": "text", "text": "Iter32 promo", "subtitle": "prueba", "duration_minutes": 15,
    })
    assert launched.status_code == 201, launched.text
    promo = launched.json()
    assert promo["screens"] >= 1
    assert 0 < promo["seconds_remaining"] <= 15 * 60

    card = requests.get(f"{BASE}/api/player/media/{promo['media_id']}", timeout=30)
    assert card.status_code == 200 and len(card.content) > 5000
    assert card.headers["content-type"].startswith("image/")

    active = requests.get(f"{BASE}/api/workspace/promos/active", headers=h, timeout=30).json()
    assert any(p["id"] == promo["id"] for p in active)

    # the promo wins over the regular playlist because of its priority
    live = requests.get(f"{BASE}/api/workspace/now-playing", headers=h, timeout=30).json()
    playing = [s["now_playing"] for s in live if s["now_playing"]]
    assert playing, "debe haber algo al aire"
    assert all(p["playlist_name"] == promo["name"] for p in playing)

    # validations
    assert requests.post(f"{BASE}/api/workspace/promos", headers=h, timeout=30,
                         json={"kind": "text", "text": " "}).status_code == 400
    assert requests.post(f"{BASE}/api/workspace/promos", headers=h, timeout=30,
                         json={"kind": "image"}).status_code == 400
    assert requests.post(f"{BASE}/api/workspace/promos", headers=h, timeout=30,
                         json={"kind": "image", "media_id": "nope"}).status_code == 404
    assert requests.post(f"{BASE}/api/workspace/promos", headers=h, timeout=30,
                         json={"kind": "text", "text": "x y", "duration_minutes": 7}).status_code == 400
    assert requests.post(f"{BASE}/api/workspace/promos", timeout=30,
                         json={"kind": "text", "text": "sin token"}).status_code in (401, 403)

    # another org cannot stop my promo
    other = _login(*OTHER)
    assert requests.delete(f"{BASE}/api/workspace/promos/{promo['id']}", headers=other,
                           timeout=30).status_code == 404

    stopped = requests.delete(f"{BASE}/api/workspace/promos/{promo['id']}", headers=h, timeout=30)
    assert stopped.status_code == 200
    assert requests.get(f"{BASE}/api/workspace/promos/active", headers=h, timeout=30).json() == []


def test_weekly_report_shape_and_isolation():
    h = _login(*OWNER)
    report = requests.get(f"{BASE}/api/workspace/reports/weekly", headers=h, timeout=30)
    assert report.status_code == 200, report.text
    body = report.json()

    assert body["period"]["is_current_week"] is True
    assert re.match(r"^\d{2}/\d{2} – \d{2}/\d{2}/\d{4}$", body["period"]["label"])
    assert set(body["totals"]) == {"plays", "minutes_on_air", "screens", "screens_offline", "changes"}
    assert body["totals"]["screens"] >= 1
    assert isinstance(body["top_content"], list)
    assert isinstance(body["screens"], list) and len(body["screens"]) == body["totals"]["screens"]
    assert all({"screen_name", "plays", "silent_days", "is_online"} <= set(row) for row in body["screens"])
    # the promo launched above was logged this week
    assert body["totals"]["changes"] >= 1

    previous = requests.get(f"{BASE}/api/workspace/reports/weekly?weeks_ago=1", headers=h, timeout=30)
    assert previous.status_code == 200
    assert previous.json()["period"]["is_current_week"] is False
    assert previous.json()["period"]["label"] != body["period"]["label"]

    other = _login(*OTHER)
    theirs = requests.get(f"{BASE}/api/workspace/reports/weekly", headers=other, timeout=30).json()
    mine = {row["screen_id"] for row in body["screens"]}
    assert mine.isdisjoint({row["screen_id"] for row in theirs["screens"]})

    assert requests.get(f"{BASE}/api/workspace/reports/weekly", timeout=30).status_code in (401, 403)
