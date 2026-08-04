"""
Sprint 0 — Colorlight A35 Proof of Concept (verified-only edition)
Every endpoint used here has been verified against the official Apifox docs.
Any inferred endpoint was REMOVED per contract.

Endpoints used:
  - UDP :9041 broadcast (doc-7054095)
  - GET /api/info.json    (api-145138569)
  - POST /api/program/{name}.vsn?autoplay=1  (doc-8105869 §5 + api-145138684)

Usage:
    pip install requests pillow
    python3 run_sprint0.py

Prerequisites:
  - Laptop on same LAN as A35
  - Edit config.py with device IP and password
"""

import os, sys, json, time, socket, hashlib, base64
from datetime import datetime
from pathlib import Path

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("Install:  pip install requests pillow")
    sys.exit(1)

import config

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


def dump(test_id, name, method, url, response=None, error=None, extra=None):
    p = LOG_DIR / f"{test_id}_{name}.txt"
    with open(p, "w") as f:
        f.write(f"=== {test_id} — {name} ===\n{method} {url}\n\n")
        if extra:
            f.write(f"NOTE: {extra}\n\n")
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


def record(test_id, name, passed, details, evidence=None):
    results.append({"id": test_id, "name": name, "pass": passed,
                    "details": details, "evidence": evidence or []})
    log(f"{test_id} — {name}: {'✅ PASS' if passed else '❌ FAIL'}",
        prefix="PASS" if passed else "FAIL")
    if not passed:
        log(f"   → {details}", prefix="FAIL")


# ============ T1: DEVICE INFO — verified endpoint /api/info.json ============
def test_1_device_info():
    log("=== T1 — GET /api/info.json (docs: api-145138569) ===")
    url = f"{BASE}/api/info.json"
    try:
        r = requests.get(url, auth=AUTH, timeout=config.REQUEST_TIMEOUT_SEC)
        f = dump("T1", "info_json", "GET", url, response=r)
        if r.status_code != 200:
            record("T1", "GET /api/info.json", False,
                   f"HTTP {r.status_code}", [f])
            return None
        info = r.json().get("info", {})
        need = ["model", "vername", "serialno"]
        missing = [k for k in need if not info.get(k)]
        if missing:
            record("T1", "GET /api/info.json", False,
                   f"Response missing fields: {missing}", [f])
            return None
        record("T1", "GET /api/info.json", True,
               f"Model={info.get('model')} FW={info.get('vername')} "
               f"Serial={info.get('serialno')} "
               f"force_encryption={info.get('force_encryption')}", [f])
        return info
    except Exception as e:
        record("T1", "GET /api/info.json", False, f"Exception: {e}")
        return None


# ============ T2: BASIC AUTH ============
def test_2_auth():
    log("=== T2 — HTTP Basic Auth (docs: doc-7054166 §6) ===")
    url = f"{BASE}/api/info.json"
    try:
        # Wrong password
        r_wrong = requests.get(url, auth=HTTPBasicAuth("admin", "wrong-XYZ-9999"),
                               timeout=10)
        f1 = dump("T2", "auth_wrong", "GET", url, response=r_wrong,
                  extra="Wrong password should return 401 if LAN encryption is ON")
        # Correct password
        r_ok = requests.get(url, auth=AUTH, timeout=10)
        f2 = dump("T2", "auth_ok", "GET", url, response=r_ok,
                  extra="Correct password should return 200")

        if r_wrong.status_code == 401 and r_ok.status_code == 200:
            record("T2", "HTTP Basic Auth", True,
                   "Wrong→401, Correct→200. Auth works as documented (LAN encryption ON).",
                   [f1, f2])
            return True
        if r_wrong.status_code == 200 and r_ok.status_code == 200:
            record("T2", "HTTP Basic Auth", True,
                   "Both requests returned 200. LAN encryption is DISABLED (still valid).",
                   [f1, f2])
            return True
        record("T2", "HTTP Basic Auth", False,
               f"Unexpected: wrong={r_wrong.status_code}, correct={r_ok.status_code}",
               [f1, f2])
        return False
    except Exception as e:
        record("T2", "HTTP Basic Auth", False, f"Exception: {e}")
        return False


# ============ T3: UDP DISCOVERY (docs: doc-7054095) ============
def test_3_discovery():
    log(f"=== T3 — UDP Discovery on :{config.UDP_DISCOVERY_PORT} (docs: doc-7054095) ===")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(5.0)
        msg = b'{"netType":1,"mType":71}'  # exact per docs §7.1
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
                    log(f"  Response from {addr[0]}: serial={d.get('serial')} "
                        f"model={d.get('modelName')} mType={d.get('mType')}")
                except Exception:
                    log(f"  Non-JSON from {addr[0]}: {data[:100]!r}")
            except socket.timeout:
                break
        sock.close()

        p = LOG_DIR / "T3_discovery.txt"
        with open(p, "w") as fp:
            fp.write(f"Broadcast: {msg.decode()} to :{config.UDP_DISCOVERY_PORT}\n\n")
            fp.write(f"Responses: {len(devices)}\n")
            fp.write(json.dumps(devices, indent=2, ensure_ascii=False))

        if not devices:
            record("T3", "UDP Discovery", False,
                   "No devices responded. Check LAN and UDP firewall.", [str(p)])
            return None
        target = next((d for d in devices if d.get('_from') == config.DEVICE_IP), None)
        if not target:
            record("T3", "UDP Discovery", False,
                   f"{len(devices)} device(s) responded but not target {config.DEVICE_IP}",
                   [str(p)])
            return devices
        # Docs §8.1: mType must be 72 in a valid response
        if target.get('mType') != 72:
            record("T3", "UDP Discovery", False,
                   f"Target responded but mType={target.get('mType')} (expected 72)",
                   [str(p)])
            return devices
        record("T3", "UDP Discovery", True,
               f"Target responded: serial={target.get('serial')} "
               f"model={target.get('modelName')} mType=72 ✓ (matches docs)",
               [str(p)])
        return devices
    except Exception as e:
        record("T3", "UDP Discovery", False, f"Exception: {e}")
        return None


# ============ VSN BUILDER (docs: doc-8105869 §8.1 filename spec) ============
def make_red_png_fullscreen():
    """Full-screen 1920x1080 red PNG. Requires pillow (fallback: 8x8 red)."""
    try:
        from PIL import Image
        from io import BytesIO
        img = Image.new("RGB", (1920, 1080), (220, 40, 40))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        log("  pillow not installed — using 8x8 red PNG fallback. Install: pip install pillow")
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAG0lEQVQoU2P8z8DwnwEP"
            "YBzaCkjyIgY0zUAAABJRU5ErkJggg=="
        )


def build_vsn(asset_bytes, asset_ext, program_name):
    """Build .vsn JSON + names per docs §8.1 filename rule.
    Uses JSON format because it works on ALL firmware versions (docs §4.1)."""
    md5_asset = hashlib.md5(asset_bytes).hexdigest().upper()
    size_asset = len(asset_bytes)
    asset_name = f"F_{md5_asset}_{size_asset}.{asset_ext}"

    kind = "video" if asset_ext.lower() == "mp4" else "image"
    vsn = {
        "version": 1,
        "programName": program_name,
        "width": 1920,
        "height": 1080,
        "duration": 10,
        "items": [{
            "type": kind,
            "src": asset_name,
            "x": 0, "y": 0, "w": 1920, "h": 1080,
            "duration": 10
        }]
    }
    vsn_bytes = json.dumps(vsn, ensure_ascii=False).encode('utf-8')
    md5_vsn = hashlib.md5(vsn_bytes).hexdigest().upper()
    size_vsn = len(vsn_bytes)
    pid = int(time.time()) % 10000
    vsn_name = f"Playlist{pid}_{md5_vsn}_{size_vsn}.vsn"
    return vsn_name, vsn_bytes, asset_name, asset_bytes


# ============ T4: PUBLISH IMAGE (docs: doc-8105869 §5 + api-145138684) ============
def test_4_publish_image():
    log("=== T4 — POST /api/program/*.vsn (docs: doc-8105869 §5) — IMAGE ===")
    img = make_red_png_fullscreen()
    vsn_name, vsn_bytes, asset_name, asset_bytes = build_vsn(img, "png", "sprint0_img")
    url = f"{BASE}/api/program/{vsn_name}"
    files = {
        "f1": (vsn_name, vsn_bytes, "application/octet-stream"),
        "f2": (asset_name, asset_bytes, "image/png"),
    }
    params = {"autoplay": 1}
    t0 = time.time()
    try:
        r = requests.post(url, params=params, files=files, auth=AUTH, timeout=120)
        elapsed = time.time() - t0
        f = dump("T4", "publish_image", "POST", url + "?autoplay=1",
                 response=r, extra=f"vsn size={len(vsn_bytes)} asset size={len(asset_bytes)}")
        if r.status_code != 200:
            record("T4", "Publish image (autoplay=1)", False,
                   f"HTTP {r.status_code}. Elapsed {elapsed:.1f}s", [f])
            return None
        record("T4", "Publish image (autoplay=1)", True,
               f"Uploaded in {elapsed:.1f}s. NOW LOOK AT THE LED and take Photo A.",
               [f])
        return {"upload_time": elapsed, "vsn_name": vsn_name}
    except Exception as e:
        record("T4", "Publish image (autoplay=1)", False, f"Exception: {e}")
        return None


# ============ T5: PUBLISH VIDEO ============
def test_5_publish_video():
    log("=== T5 — POST /api/program/*.vsn (docs: doc-8105869 §5) — VIDEO ===")
    candidates = ["sprint0_test.mp4", "test.mp4", "sample.mp4"]
    video_path = next((c for c in candidates if os.path.exists(c)), None)
    if not video_path:
        record("T5", "Publish video (autoplay=1)", False,
               "No mp4 found. Place 'sprint0_test.mp4' (<5MB) in this folder.")
        return None
    with open(video_path, "rb") as f:
        vid = f.read()
    vsn_name, vsn_bytes, asset_name, asset_bytes = build_vsn(vid, "mp4", "sprint0_vid")
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
        f = dump("T5", "publish_video", "POST", url + "?autoplay=1",
                 response=r, extra=f"video {len(vid)/1024:.0f}KB, vsn {len(vsn_bytes)}B")
        if r.status_code != 200:
            record("T5", "Publish video (autoplay=1)", False,
                   f"HTTP {r.status_code}. Elapsed {elapsed:.1f}s.", [f])
            return None
        record("T5", "Publish video (autoplay=1)", True,
               f"Uploaded {len(vid)/1024:.0f}KB in {elapsed:.1f}s. LOOK AT THE LED, take Photo B.",
               [f])
        return {"upload_time": elapsed}
    except Exception as e:
        record("T5", "Publish video (autoplay=1)", False, f"Exception: {e}")
        return None


# ============ T6: DOCUMENTATION (always PASS if reached) ============
def test_6_documentation():
    files = list(LOG_DIR.glob("*"))
    record("T6", "Full request/response documentation", True,
           f"{len(files)} evidence files written to {LOG_DIR}/",
           [str(p.name) for p in files])


# ============ MAIN ============
def main():
    log(f"Sprint 0 (verified-only) starting — target: {BASE}")

    info = test_1_device_info()
    test_2_auth()
    test_3_discovery()
    test_4_publish_image()
    test_5_publish_video()
    test_6_documentation()

    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    with open(REPORT, "w") as f:
        f.write(f"# Sprint 0 Report — {STAMP}\n\n")
        f.write(f"**Target**: {BASE}\n\n")
        f.write("**Endpoints used (100% verified against official Apifox docs)**:\n")
        f.write("- UDP :9041 broadcast — doc-7054095\n")
        f.write("- GET /api/info.json — api-145138569\n")
        f.write("- POST /api/program/*.vsn — doc-8105869 §5\n")
        f.write("- HTTP Basic Auth — doc-7054166 §6\n\n")
        if info:
            f.write(f"**Device**: model={info.get('model')} fw={info.get('vername')} "
                    f"serial={info.get('serialno')} force_encryption={info.get('force_encryption')}\n\n")
        f.write(f"## Result: {passed}/{total} tests passed\n\n")
        f.write("| # | Test | Result | Details |\n|---|---|---|---|\n")
        for r in results:
            mark = "✅ PASS" if r["pass"] else "❌ FAIL"
            f.write(f"| {r['id']} | {r['name']} | {mark} | {r['details']} |\n")
        f.write("\n## Evidence files\n\n")
        for r in results:
            for e in r["evidence"]:
                f.write(f"- `{e}`\n")
        f.write("\n## Photos required (from you, taken with phone)\n")
        f.write("- **Photo A** — LED showing red test image (after T4)\n")
        f.write("- **Photo B** — LED playing test video (after T5, if mp4 was provided)\n\n")
        f.write("## Verdict\n")
        if passed == total:
            f.write("🟢 **Sprint 0 PASSED** — Ready for Sprint 0.5 (verify remaining endpoints) and Sprint 1.\n")
        else:
            f.write("🔴 **Sprint 0 FAILED** — Send report + logs + photos to architect. Do NOT patch. Re-read docs section for failed test.\n")

    log(f"Sprint 0 complete: {passed}/{total} passed. Report: {REPORT}", prefix="DONE")
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
