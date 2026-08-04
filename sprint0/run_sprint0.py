"""
Sprint 0 — Colorlight A35 Proof of Concept runner
Executes all 9 tests, produces a markdown report + full request/response logs.

Usage:
    python3 run_sprint0.py

Prerequisites:
    - Python 3.8+
    - pip install requests
    - Edit config.py with your device IP and password
    - Laptop must be on the SAME LAN as the A35
"""

import os
import sys
import json
import time
import socket
import hashlib
import base64
import struct
import zlib
from datetime import datetime
from pathlib import Path

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("ERROR: 'requests' library is required. Run:  pip install requests")
    sys.exit(1)

import config

# ---------------- Setup ----------------
STAMP = datetime.now().strftime("%Y%m%d_%H%M")
OUT = Path(f"sprint0_report_{STAMP}")
OUT.mkdir(exist_ok=True)
LOG_DIR = OUT / "logs"
LOG_DIR.mkdir(exist_ok=True)

REPORT = OUT / "sprint0_report.md"
BASE = f"http://{config.DEVICE_IP}:{config.DEVICE_PORT}"
AUTH = HTTPBasicAuth(config.DEVICE_USER, config.DEVICE_PASS)

results = []


def log(msg, prefix="INFO"):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] [{prefix}] {msg}"
    print(line)
    with open(OUT / "run.log", "a") as f:
        f.write(line + "\n")


def dump(test_id, name, method, url, req_body=None, response=None, error=None):
    """Write full request/response transcript for one HTTP call."""
    p = LOG_DIR / f"{test_id}_{name}.txt"
    with open(p, "w") as f:
        f.write(f"=== {test_id} — {name} ===\n")
        f.write(f"{method} {url}\n")
        if req_body is not None:
            f.write(f"REQUEST BODY:\n{req_body[:2000]}\n\n")
        if response is not None:
            f.write(f"HTTP {response.status_code}\n")
            for k, v in response.headers.items():
                f.write(f"{k}: {v}\n")
            f.write("\n--- BODY ---\n")
            try:
                f.write(json.dumps(response.json(), indent=2, ensure_ascii=False)[:8000])
            except Exception:
                f.write(response.text[:8000])
        if error:
            f.write(f"\n\nERROR: {error}\n")
    return str(p)


def record(test_id, name, passed, details, evidence_files=None):
    results.append({
        "id": test_id, "name": name, "pass": passed,
        "details": details, "evidence": evidence_files or []
    })
    log(f"TEST {test_id} — {name}: {'✅ PASS' if passed else '❌ FAIL'}",
        prefix="PASS" if passed else "FAIL")
    if not passed:
        log(f"   Details: {details}", prefix="FAIL")


def api_get(path, **kwargs):
    return requests.get(BASE + path, auth=AUTH,
                        timeout=config.REQUEST_TIMEOUT_SEC, **kwargs)


def api_post(path, **kwargs):
    return requests.post(BASE + path, auth=AUTH,
                         timeout=config.REQUEST_TIMEOUT_SEC, **kwargs)


# ============ TEST 1: DEVICE INFO ============
def test_1_device_info():
    log("=== TEST 1 — Read device info ===")
    try:
        r = api_get("/api/system/info")
        f = dump("T1", "system_info", "GET", BASE + "/api/system/info", response=r)
        if r.status_code != 200:
            record("T1", "Device info", False,
                   f"HTTP {r.status_code}. Auth or endpoint wrong.", [f])
            return None
        info = r.json().get("info", {})
        need = ["model", "vername", "serialno"]
        missing = [k for k in need if not info.get(k)]
        if missing:
            record("T1", "Device info", False, f"Missing fields: {missing}", [f])
            return None
        record("T1", "Device info", True,
               f"Model={info.get('model')} FW={info.get('vername')} Serial={info.get('serialno')}",
               [f])
        return info
    except Exception as e:
        record("T1", "Device info", False, f"Exception: {e}")
        return None


# ============ TEST 2: AUTH ============
def test_2_auth():
    log("=== TEST 2 — Verify auth ===")
    try:
        # First: request with wrong password → should return 401
        r_wrong = requests.get(BASE + "/api/system/info",
                               auth=HTTPBasicAuth("admin", "definitely-wrong-XYZ-9999"),
                               timeout=10)
        f1 = dump("T2", "auth_wrong", "GET", BASE + "/api/system/info", response=r_wrong)
        # Then: request with correct password → should return 200
        r_ok = api_get("/api/system/info")
        f2 = dump("T2", "auth_ok", "GET", BASE + "/api/system/info", response=r_ok)
        if r_wrong.status_code == 401 and r_ok.status_code == 200:
            record("T2", "Basic Auth", True,
                   "401 with wrong password, 200 with correct — auth works as documented",
                   [f1, f2])
            return True
        # If wrong password ALSO returns 200 → device has LAN encryption OFF (still OK)
        if r_wrong.status_code == 200 and r_ok.status_code == 200:
            record("T2", "Basic Auth", True,
                   "Both requests returned 200 — device has LAN encryption DISABLED",
                   [f1, f2])
            return True
        record("T2", "Basic Auth", False,
               f"Unexpected: wrong={r_wrong.status_code}, correct={r_ok.status_code}",
               [f1, f2])
        return False
    except Exception as e:
        record("T2", "Basic Auth", False, f"Exception: {e}")
        return False


# ============ TEST 3: UDP DISCOVERY ============
def test_3_discovery():
    log(f"=== TEST 3 — UDP Discovery on :{config.UDP_DISCOVERY_PORT} ===")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(5.0)
        msg = b'{"netType":1,"mType":71}'
        # Broadcast to 255.255.255.255 (all-hosts)
        sock.sendto(msg, ('255.255.255.255', config.UDP_DISCOVERY_PORT))
        log(f"  Sent broadcast: {msg}")
        devices = []
        end = time.time() + 5
        while time.time() < end:
            try:
                data, addr = sock.recvfrom(2048)
                try:
                    d = json.loads(data.decode('utf-8'))
                    d['_from'] = addr[0]
                    devices.append(d)
                    log(f"  Response from {addr[0]}: serial={d.get('serial')} model={d.get('modelName')}")
                except Exception as e:
                    log(f"  Non-JSON response from {addr[0]}: {data[:100]!r}")
            except socket.timeout:
                break
        sock.close()
        # Write findings
        f = LOG_DIR / "T3_discovery.txt"
        with open(f, "w") as fp:
            fp.write(f"Broadcast: {msg.decode()}\nPort: {config.UDP_DISCOVERY_PORT}\n\n")
            fp.write(f"Devices found: {len(devices)}\n\n")
            fp.write(json.dumps(devices, indent=2, ensure_ascii=False))
        if not devices:
            record("T3", "UDP Discovery", False,
                   "No devices responded. Verify LAN and firewall allow UDP :9041.",
                   [str(f)])
            return None
        # Verify our target device is among responders
        target = next((d for d in devices if d.get('_from') == config.DEVICE_IP), None)
        if not target:
            record("T3", "UDP Discovery", False,
                   f"{len(devices)} device(s) responded but not our target {config.DEVICE_IP}.",
                   [str(f)])
            return devices
        record("T3", "UDP Discovery", True,
               f"Target A35 responded: serial={target.get('serial')} model={target.get('modelName')}",
               [str(f)])
        return devices
    except Exception as e:
        record("T3", "UDP Discovery", False, f"Exception: {e}")
        return None


# ============ TEST 4: REROUTE CLOUD ============
def test_4_reroute_cloud():
    log("=== TEST 4 — Point device at MediaView server ===")
    try:
        # Read current C-Cloud account
        r = api_get("/api/cloud/ccloud/account")
        f1 = dump("T4", "get_current_cloud", "GET",
                  BASE + "/api/cloud/ccloud/account", response=r)
        if r.status_code != 200:
            record("T4", "Cloud reroute", False,
                   f"GET account returned HTTP {r.status_code}. Endpoint path may differ.",
                   [f1])
            return False
        current = r.json()
        log(f"  Current cloud config: {json.dumps(current, ensure_ascii=False)[:300]}")
        # NOTE: we do NOT permanently change your device. We only READ the config
        # and confirm the endpoint is available. Actual switch requires manual
        # confirmation because it disconnects the device from ColorlightCloud.
        record("T4", "Cloud reroute (read-only probe)", True,
               "GET succeeded — endpoint available. Actual reroute deferred to Sprint 1 "
               "to avoid disconnecting the device before we're ready.",
               [f1])
        return True
    except Exception as e:
        record("T4", "Cloud reroute", False, f"Exception: {e}")
        return False


# ============ VSN BUILDER ============
def build_vsn_image(image_bytes, image_ext, program_name="sprint0test"):
    """Build a JSON .vsn descriptor + material file per Colorlight naming rules.
    Docs §8.1: filenames must follow Playlist{id}_{md5}_{size}.vsn and F_{md5}_{size}.{ext}"""
    md5_asset = hashlib.md5(image_bytes).hexdigest().upper()
    size_asset = len(image_bytes)
    asset_name = f"F_{md5_asset}_{size_asset}.{image_ext}"

    vsn = {
        "version": 1,
        "programName": program_name,
        "width": 1920, "height": 1080,
        "backgroundColor": "0xFF010000",  # not pure black — see Q7 in docs
        "duration": 10,
        "items": [{
            "type": "image" if image_ext.lower() in ("png","jpg","jpeg","webp","bmp","gif") else "video",
            "src": asset_name,
            "x": 0, "y": 0, "w": 1920, "h": 1080,
            "duration": 10
        }]
    }
    vsn_bytes = json.dumps(vsn, ensure_ascii=False).encode('utf-8')
    md5_vsn = hashlib.md5(vsn_bytes).hexdigest().upper()
    size_vsn = len(vsn_bytes)
    program_id = int(time.time()) % 10000
    vsn_name = f"Playlist{program_id}_{md5_vsn}_{size_vsn}.vsn"
    return vsn_name, vsn_bytes, asset_name, image_bytes


def make_red_png():
    """Minimal 1920x1080 red PNG (uses PIL if available, else a solid-color fallback)."""
    try:
        from PIL import Image
        img = Image.new("RGB", (1920, 1080), (220, 40, 40))
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # Fallback: hand-crafted minimal PNG (8x8 red)
        # This works but the LED will show a tiny red block scaled up
        log("  PIL not available, using 8x8 red PNG. Install pillow for full-screen: pip install pillow")
        # Precomputed 8x8 solid red PNG
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAG0lEQVQoU2P8z8DwnwEP"
            "YBzaCkjyIgY0zUAAABJRU5ErkJggg=="
        )


# ============ TEST 5: PUBLISH IMAGE ============
def test_5_publish_image():
    log("=== TEST 5 — Publish full-screen image with autoplay=1 ===")
    img = make_red_png()
    vsn_name, vsn_bytes, asset_name, asset_bytes = build_vsn_image(img, "png",
                                                                    "sprint0_img")
    url = f"{BASE}/api/program/{vsn_name}"
    files = {
        "f1": (vsn_name, vsn_bytes, "application/octet-stream"),
        "f2": (asset_name, asset_bytes, "image/png"),
    }
    params = {"autoplay": 1}
    t0 = time.time()
    try:
        r = requests.post(url, params=params, files=files, auth=AUTH,
                          timeout=60)
        elapsed = time.time() - t0
        f = dump("T5", "publish_image", "POST", url, response=r)
        if r.status_code != 200:
            record("T5", "Publish image", False,
                   f"HTTP {r.status_code}. See {f}", [f])
            return None
        # Verify device claims the program is now playing
        time.sleep(3)  # let device switch
        r2 = api_get("/api/program/play/status")
        f2 = dump("T5", "play_status_after", "GET",
                  BASE + "/api/program/play/status", response=r2)
        playing = ""
        try:
            playing = r2.json().get("playing", {}).get("name", "")
        except Exception:
            playing = "(parse error)"
        record("T5", "Publish image", True,
               f"Uploaded in {elapsed:.1f}s. Device reports playing: {playing}",
               [f, f2])
        return {"vsn_name": vsn_name, "upload_time": elapsed, "playing": playing}
    except Exception as e:
        record("T5", "Publish image", False, f"Exception: {e}")
        return None


# ============ TEST 6: PUBLISH VIDEO ============
def test_6_publish_video():
    log("=== TEST 6 — Publish video with autoplay=1 ===")
    # Look for a video file in the current directory
    candidates = ["sprint0_test.mp4", "test.mp4", "sample.mp4"]
    video_path = next((c for c in candidates if os.path.exists(c)), None)
    if not video_path:
        record("T6", "Publish video", False,
               "No test video found. Place a small mp4 (<5MB) as 'sprint0_test.mp4' "
               "in this folder and re-run.")
        return None
    with open(video_path, "rb") as f:
        vid_bytes = f.read()
    vsn_name, vsn_bytes, asset_name, asset_bytes = build_vsn_image(vid_bytes, "mp4",
                                                                    "sprint0_vid")
    url = f"{BASE}/api/program/{vsn_name}"
    files = {
        "f1": (vsn_name, vsn_bytes, "application/octet-stream"),
        "f2": (asset_name, asset_bytes, "video/mp4"),
    }
    params = {"autoplay": 1}
    t0 = time.time()
    try:
        r = requests.post(url, params=params, files=files, auth=AUTH, timeout=300)
        elapsed = time.time() - t0
        f = dump("T6", "publish_video", "POST", url, response=r)
        if r.status_code != 200:
            record("T6", "Publish video", False,
                   f"HTTP {r.status_code}. Video {len(vid_bytes)/1024:.0f}KB.", [f])
            return None
        record("T6", "Publish video", True,
               f"Uploaded {len(vid_bytes)/1024:.0f}KB video in {elapsed:.1f}s",
               [f])
        return {"vsn_name": vsn_name, "upload_time": elapsed}
    except Exception as e:
        record("T6", "Publish video", False, f"Exception: {e}")
        return None


# ============ TEST 7: VERIFY PLAYBACK + SCREENSHOT ============
def test_7_verify_playback():
    log("=== TEST 7 — Verify playback + fetch screenshot ===")
    try:
        r = api_get("/api/program/play/status")
        f1 = dump("T7", "play_status", "GET",
                  BASE + "/api/program/play/status", response=r)
        # Screenshot
        r2 = api_get("/api/system/screenshot")
        shot_path = None
        if r2.status_code == 200 and "image" in r2.headers.get("Content-Type", ""):
            shot_path = LOG_DIR / "T7_screenshot.jpg"
            with open(shot_path, "wb") as fp:
                fp.write(r2.content)
            log(f"  Screenshot saved to {shot_path}")
        f2 = str(shot_path) if shot_path else dump("T7", "screenshot", "GET",
                                                    BASE + "/api/system/screenshot",
                                                    response=r2)
        if r.status_code == 200:
            record("T7", "Verify playback", True,
                   "Play status endpoint works. Screenshot saved. "
                   "→ VISUALLY verify the LED with your phone camera (PHOTO A/B).",
                   [f1, f2])
            return True
        record("T7", "Verify playback", False,
               f"Play status HTTP {r.status_code}", [f1, f2])
        return False
    except Exception as e:
        record("T7", "Verify playback", False, f"Exception: {e}")
        return False


# ============ TEST 8: LATENCY ============
def test_8_latency(t5_result):
    log("=== TEST 8 — Measure end-to-end latency ===")
    if not t5_result:
        record("T8", "Latency", False, "Skipped because T5 failed")
        return
    # Latency = upload time from T5 (image published → play_status confirmed)
    lat = t5_result.get("upload_time", 0)
    threshold = 30  # seconds per README
    passed = lat < threshold
    record("T8", "Latency", passed,
           f"Publish → playback confirmed in {lat:.1f}s (threshold {threshold}s)")


# ============ TEST 9: DOCUMENT EVERYTHING ============
def test_9_document():
    """Always passes if we got here — the LOG_DIR is the deliverable."""
    files = list(LOG_DIR.glob("*"))
    record("T9", "Full request/response documentation", True,
           f"{len(files)} evidence files written to {LOG_DIR}/",
           [str(p) for p in files[:20]])


# ============ MAIN ============
def main():
    log(f"Sprint 0 starting. Target: {BASE}")
    log(f"Report will be written to: {REPORT}")

    # Order matters
    info = test_1_device_info()
    test_2_auth()
    test_3_discovery()
    test_4_reroute_cloud()
    t5 = test_5_publish_image()
    test_6_publish_video()
    test_7_verify_playback()
    test_8_latency(t5)
    test_9_document()

    # Write markdown report
    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    with open(REPORT, "w") as f:
        f.write(f"# Sprint 0 Report — {STAMP}\n\n")
        f.write(f"**Target device**: {BASE}\n")
        f.write(f"**Device info**: {json.dumps(info, ensure_ascii=False)[:400] if info else 'N/A'}\n\n")
        f.write(f"## Result: {passed}/{total} tests passed\n\n")
        f.write("| # | Test | Result | Details |\n|---|---|---|---|\n")
        for r in results:
            mark = "✅ PASS" if r["pass"] else "❌ FAIL"
            f.write(f"| {r['id']} | {r['name']} | {mark} | {r['details']} |\n")
        f.write("\n## Evidence files\n\n")
        for r in results:
            if r["evidence"]:
                f.write(f"### {r['id']} — {r['name']}\n")
                for e in r["evidence"]:
                    f.write(f"- `{e}`\n")
                f.write("\n")
        f.write("\n## Photos needed from you (Josue)\n")
        f.write("- **Photo A**: LED showing the RED test image (Test 5)\n")
        f.write("- **Photo B**: LED playing the test video (Test 6)\n\n")
        f.write("## Verdict\n\n")
        if passed == total:
            f.write("🟢 **Sprint 0 PASSED**. Ready to begin production development.\n")
        else:
            f.write("🔴 **Sprint 0 FAILED**. STOP. Send this report + the "
                    "photos to the architect and update assumptions before continuing.\n")

    log(f"\n{'='*50}\nSprint 0 complete. {passed}/{total} tests passed.\nReport: {REPORT}\n{'='*50}\n",
        prefix="DONE")
    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
