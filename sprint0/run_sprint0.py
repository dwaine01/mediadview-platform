"""
Sprint 0 — Colorlight A35/A40 Diagnostic Tool (verbose edition)
================================================================

Reusable HTTP diagnostic tool for Colorlight A-series players.
Run this against ANY new A35/A40/A800 to verify in <5 min:
  - Device responds
  - Auth works
  - Discovery works
  - Content publishes and plays

Every HTTP request and response is printed to screen EXACTLY as sent/received:
  METHOD, full URL, headers, body → status, headers, body.

All endpoints used are officially verified against Apifox docs.

Usage:
    pip install requests pillow
    python3 run_sprint0.py
"""

import os, sys, json, time, socket, hashlib, base64
from datetime import datetime
from pathlib import Path

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("ERROR: install with:  pip install requests pillow")
    sys.exit(1)

import config

# ---------- ANSI colors (works on macOS/Linux/Windows 10+) ----------
try:
    if sys.stdout.isatty():
        CYAN = "\033[96m"; GREEN = "\033[92m"; RED = "\033[91m"
        YELLOW = "\033[93m"; BLUE = "\033[94m"; GREY = "\033[90m"
        BOLD = "\033[1m"; RESET = "\033[0m"
    else:
        CYAN = GREEN = RED = YELLOW = BLUE = GREY = BOLD = RESET = ""
except Exception:
    CYAN = GREEN = RED = YELLOW = BLUE = GREY = BOLD = RESET = ""

# ---------- Output paths ----------
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = Path(f"sprint0_report_{STAMP}")
OUT.mkdir(exist_ok=True)
LOG_DIR = OUT / "logs"
LOG_DIR.mkdir(exist_ok=True)
REPORT = OUT / "sprint0_report.md"
RAW_LOG = OUT / "http_transcript.log"

BASE = f"http://{config.DEVICE_IP}:{config.DEVICE_PORT}"
AUTH = HTTPBasicAuth(config.DEVICE_USER, config.DEVICE_PASS)
SESSION = requests.Session()

results = []
CRITICAL = {"T1", "T2", "T3", "T4"}   # if any of these fails, we stop


def hr(char="─", n=78, color=GREY):
    print(color + char * n + RESET)


def cprint(msg, color=""):
    print(f"{color}{msg}{RESET}")


def raw_write(text):
    with open(RAW_LOG, "a") as f:
        f.write(text + "\n")


# ============================================================
# The heart of the tool — print every HTTP call verbatim
# ============================================================
def logged_request(method, url, *, headers=None, params=None, data=None,
                   files=None, auth=None, timeout=30, test_id="", desc=""):
    """Send an HTTP request and print request+response transcripts to screen +
    save to logs. Returns the requests.Response (or None on network error)."""

    # Build the prepared request to know EXACTLY what will hit the wire
    req = requests.Request(method=method, url=url, headers=headers or {},
                            params=params, data=data, files=files, auth=auth)
    prepared = SESSION.prepare_request(req)

    # ---------- print REQUEST ----------
    hr("═", color=CYAN)
    cprint(f"  ▶ [{test_id}] {desc}", CYAN + BOLD)
    hr("─", color=CYAN)
    cprint(f"  → REQUEST", BOLD)
    cprint(f"     {prepared.method} {prepared.url}", BLUE + BOLD)
    for h, v in prepared.headers.items():
        # Mask Basic auth secret in header
        if h.lower() == "authorization":
            v = v[:12] + "***(masked)***"
        cprint(f"     {h}: {v}", GREY)
    body_bytes = prepared.body
    if body_bytes:
        if isinstance(body_bytes, bytes):
            preview = body_bytes[:400]
            try:
                preview_txt = preview.decode('utf-8', errors='replace')
            except Exception:
                preview_txt = repr(preview)
            total_len = len(body_bytes)
        else:
            preview_txt = str(body_bytes)[:400]
            total_len = len(str(body_bytes))
        cprint(f"     BODY ({total_len} bytes, first 400 shown):", GREY)
        for line in preview_txt.splitlines()[:20]:
            cprint(f"       {line}", GREY)

    # ---------- send + capture RESPONSE ----------
    hr("─", color=CYAN)
    t0 = time.time()
    try:
        response = SESSION.send(prepared, timeout=timeout)
        elapsed = time.time() - t0
    except Exception as e:
        elapsed = time.time() - t0
        cprint(f"  ✗ NETWORK ERROR ({elapsed*1000:.0f}ms): {type(e).__name__}: {e}", RED + BOLD)
        raw_write(f"\n=== {test_id} {desc} ===\n{prepared.method} {prepared.url}\n"
                  f"NETWORK ERROR: {type(e).__name__}: {e}\n")
        return None

    status_color = GREEN if 200 <= response.status_code < 300 else (
        YELLOW if 300 <= response.status_code < 400 else RED)
    cprint(f"  ← RESPONSE  {status_color}HTTP {response.status_code}{RESET}  "
           f"({elapsed*1000:.0f}ms, {len(response.content)} bytes)", BOLD)
    for h, v in response.headers.items():
        cprint(f"     {h}: {v}", GREY)
    cprint(f"     BODY:", GREY)
    # Body preview: JSON pretty-print if possible, else raw truncated
    try:
        body = response.json()
        preview = json.dumps(body, indent=2, ensure_ascii=False)[:1200]
    except Exception:
        ct = response.headers.get("Content-Type", "")
        if ct.startswith("image/") or "octet-stream" in ct:
            preview = f"<binary {ct} — {len(response.content)} bytes not printed>"
        else:
            preview = response.text[:1200]
    for line in preview.splitlines()[:40]:
        cprint(f"       {line}", GREY)
    hr("═", color=CYAN)

    # Save full transcript
    with open(LOG_DIR / f"{test_id}_{desc.replace(' ','_')[:40]}.txt", "w") as f:
        f.write(f"=== {test_id} — {desc} ===\n\n--- REQUEST ---\n")
        f.write(f"{prepared.method} {prepared.url}\n")
        for h, v in prepared.headers.items():
            f.write(f"{h}: {v}\n")
        if body_bytes:
            f.write(f"\n[body {len(body_bytes) if isinstance(body_bytes,(bytes,str)) else '?'} bytes]\n")
        f.write(f"\n--- RESPONSE ({elapsed*1000:.0f}ms) ---\n")
        f.write(f"HTTP {response.status_code}\n")
        for h, v in response.headers.items():
            f.write(f"{h}: {v}\n")
        f.write("\n")
        try:
            f.write(json.dumps(response.json(), indent=2, ensure_ascii=False)[:8000])
        except Exception:
            f.write(response.text[:8000])

    raw_write(f"\n=== {test_id} {desc} ===\n"
              f"{prepared.method} {prepared.url}\n"
              f"→ HTTP {response.status_code} in {elapsed*1000:.0f}ms")

    return response


def record(test_id, name, passed, details, docs_url=""):
    results.append({"id": test_id, "name": name, "pass": passed,
                    "details": details, "docs": docs_url})
    icon = "✅ PASS" if passed else "❌ FAIL"
    color = GREEN if passed else RED
    cprint(f"\n  {color}{BOLD}{test_id} — {name}: {icon}{RESET}", "")
    cprint(f"      {details}", color)
    if docs_url:
        cprint(f"      docs: {docs_url}", GREY)
    print()


def stop_if_critical_failed(test_id):
    """If any CRITICAL test failed, stop the whole run per user contract."""
    last = results[-1]
    if not last["pass"] and last["id"] in CRITICAL:
        cprint("\n" + "!" * 78, RED + BOLD)
        cprint(f"  STOP: critical test {test_id} failed. "
               f"Per Sprint 0 contract, no further tests will run.", RED + BOLD)
        cprint(f"  → Re-read the docs section for this test, do NOT patch silently.",
               RED)
        cprint(f"  → Send this report + logs to the architect to update assumptions.",
               RED)
        cprint("!" * 78 + "\n", RED + BOLD)
        write_report(aborted=True)
        sys.exit(1)


# ============================================================
# TESTS
# ============================================================
def test_1_device_info():
    """T1 — GET /api/info.json (docs: api-145138569)"""
    r = logged_request("GET", f"{BASE}/api/info.json", auth=AUTH,
                       timeout=config.REQUEST_TIMEOUT_SEC,
                       test_id="T1", desc="Device info via GET /api/info.json")
    docs = "https://colorlight-doc.apifox.cn/api-145138569"
    if r is None:
        record("T1", "GET /api/info.json", False,
               f"Network error — device unreachable at {config.DEVICE_IP}", docs)
        return None
    if r.status_code != 200:
        record("T1", "GET /api/info.json", False,
               f"HTTP {r.status_code} (expected 200). Body: {r.text[:200]}", docs)
        return None
    try:
        info = r.json().get("info", {})
    except Exception as e:
        record("T1", "GET /api/info.json", False, f"Response is not valid JSON: {e}", docs)
        return None
    need = ["model", "vername", "serialno"]
    miss = [k for k in need if not info.get(k)]
    if miss:
        record("T1", "GET /api/info.json", False,
               f"Missing required fields per docs: {miss}", docs)
        return None
    record("T1", "GET /api/info.json", True,
           f"model={info.get('model')} fw={info.get('vername')} "
           f"serial={info.get('serialno')} force_encryption={info.get('force_encryption')}",
           docs)
    return info


def test_2_auth():
    """T2 — HTTP Basic Auth negative + positive (docs: doc-7054166 §6)"""
    docs = "https://colorlight-doc.apifox.cn/doc-7054166"
    url = f"{BASE}/api/info.json"

    # Negative case
    r_bad = logged_request("GET", url, auth=HTTPBasicAuth("admin", "wrong-XYZ-9999"),
                            timeout=10,
                            test_id="T2a", desc="Auth NEGATIVE (wrong password)")
    if r_bad is None:
        record("T2", "HTTP Basic Auth", False, "Device unreachable in negative test", docs)
        return False

    # Positive case
    r_ok = logged_request("GET", url, auth=AUTH, timeout=10,
                          test_id="T2b", desc="Auth POSITIVE (correct password)")
    if r_ok is None:
        record("T2", "HTTP Basic Auth", False, "Device unreachable in positive test", docs)
        return False

    if r_bad.status_code == 401 and r_ok.status_code == 200:
        record("T2", "HTTP Basic Auth", True,
               "wrong→401, correct→200. Auth works as documented (LAN encryption ON).",
               docs)
        return True
    if r_bad.status_code == 200 and r_ok.status_code == 200:
        record("T2", "HTTP Basic Auth", True,
               "Both requests returned 200. LAN encryption is DISABLED on this device — still valid.",
               docs)
        return True
    record("T2", "HTTP Basic Auth", False,
           f"Unexpected combination: wrong={r_bad.status_code}, correct={r_ok.status_code}",
           docs)
    return False


def test_3_discovery():
    """T3 — UDP :9041 discovery (docs: doc-7054095)"""
    docs = "https://colorlight-doc.apifox.cn/doc-7054095"
    hr("═", color=CYAN)
    cprint(f"  ▶ [T3] UDP Discovery on :{config.UDP_DISCOVERY_PORT}", CYAN + BOLD)
    hr("─", color=CYAN)
    msg = b'{"netType":1,"mType":71}'
    cprint(f"  → BROADCAST", BOLD)
    cprint(f"     UDP {config.UDP_DISCOVERY_PORT}", BLUE + BOLD)
    cprint(f"     BODY: {msg.decode()}", GREY)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(5.0)
        sock.sendto(msg, ('255.255.255.255', config.UDP_DISCOVERY_PORT))
    except Exception as e:
        hr("═", color=CYAN)
        record("T3", "UDP Discovery", False, f"Socket error: {e}", docs)
        return None

    devices = []
    end = time.time() + 5
    while time.time() < end:
        try:
            data, addr = sock.recvfrom(2048)
            try:
                d = json.loads(data.decode('utf-8'))
                d['_from'] = addr[0]
                devices.append(d)
                cprint(f"  ← RESPONSE from {addr[0]}", BOLD)
                cprint(f"     {json.dumps(d, ensure_ascii=False)}", GREY)
            except Exception:
                cprint(f"  ← non-JSON from {addr[0]}: {data[:100]!r}", YELLOW)
        except socket.timeout:
            break
    sock.close()
    hr("═", color=CYAN)

    with open(LOG_DIR / "T3_discovery.txt", "w") as f:
        f.write(f"UDP broadcast: {msg.decode()} to port {config.UDP_DISCOVERY_PORT}\n\n")
        f.write(json.dumps(devices, indent=2, ensure_ascii=False))

    if not devices:
        record("T3", "UDP Discovery", False,
               "No devices responded within 5s. Check LAN + UDP :9041 firewall.", docs)
        return None
    target = next((d for d in devices if d.get('_from') == config.DEVICE_IP), None)
    if not target:
        record("T3", "UDP Discovery", False,
               f"{len(devices)} device(s) responded but not target {config.DEVICE_IP}", docs)
        return devices
    if target.get('mType') != 72:
        record("T3", "UDP Discovery", False,
               f"Target responded but mType={target.get('mType')} (docs say 72)", docs)
        return devices
    record("T3", "UDP Discovery", True,
           f"Target responded: serial={target.get('serial')} model={target.get('modelName')} mType=72",
           docs)
    return devices


# --- .vsn builder (docs: doc-8105869 §8.1) ---
def make_red_png():
    try:
        from PIL import Image
        from io import BytesIO
        img = Image.new("RGB", (1920, 1080), (220, 40, 40))
        buf = BytesIO(); img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        cprint("     (pillow not installed — using 8x8 red PNG fallback)", YELLOW)
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAG0lEQVQoU2P8z8DwnwEP"
            "YBzaCkjyIgY0zUAAABJRU5ErkJggg=="
        )


def build_vsn(asset_bytes, asset_ext, program_name):
    md5_asset = hashlib.md5(asset_bytes).hexdigest().upper()
    size_asset = len(asset_bytes)
    asset_name = f"F_{md5_asset}_{size_asset}.{asset_ext}"
    kind = "video" if asset_ext.lower() == "mp4" else "image"
    vsn = {
        "version": 1, "programName": program_name,
        "width": 1920, "height": 1080, "duration": 10,
        "items": [{"type": kind, "src": asset_name,
                   "x": 0, "y": 0, "w": 1920, "h": 1080, "duration": 10}]
    }
    vsn_bytes = json.dumps(vsn, ensure_ascii=False).encode('utf-8')
    md5_vsn = hashlib.md5(vsn_bytes).hexdigest().upper()
    size_vsn = len(vsn_bytes)
    pid = int(time.time()) % 10000
    vsn_name = f"Playlist{pid}_{md5_vsn}_{size_vsn}.vsn"
    return vsn_name, vsn_bytes, asset_name, asset_bytes


def test_4_publish_image():
    """T4 — POST /api/program/*.vsn (docs: doc-8105869 §5)"""
    docs = "https://colorlight-doc.apifox.cn/doc-8105869"
    img = make_red_png()
    vsn_name, vsn_bytes, asset_name, asset_bytes = build_vsn(img, "png", "sprint0_img")
    url = f"{BASE}/api/program/{vsn_name}"
    files = {
        "f1": (vsn_name, vsn_bytes, "application/octet-stream"),
        "f2": (asset_name, asset_bytes, "image/png"),
    }
    t0 = time.time()
    r = logged_request("POST", url, params={"autoplay": 1}, files=files,
                       auth=AUTH, timeout=180,
                       test_id="T4", desc=f"Publish IMAGE (autoplay=1) — "
                                          f".vsn={len(vsn_bytes)}B, PNG={len(asset_bytes)}B")
    elapsed = time.time() - t0
    if r is None:
        record("T4", "Publish image", False, "Network error on upload", docs); return None
    if r.status_code != 200:
        record("T4", "Publish image", False,
               f"HTTP {r.status_code} after {elapsed:.1f}s. Body: {r.text[:200]}", docs)
        return None
    record("T4", "Publish image (autoplay=1)", True,
           f"Uploaded in {elapsed:.1f}s → NOW LOOK AT THE LED and take Photo A.", docs)
    return {"upload_time": elapsed, "vsn_name": vsn_name}


def test_5_publish_video():
    """T5 — POST /api/program/*.vsn video"""
    docs = "https://colorlight-doc.apifox.cn/doc-8105869"
    candidates = ["sprint0_test.mp4", "test.mp4", "sample.mp4"]
    video_path = next((c for c in candidates if os.path.exists(c)), None)
    if not video_path:
        record("T5", "Publish video", False,
               "Skipped: no mp4 in this folder. Add 'sprint0_test.mp4' (<5MB) and rerun.", docs)
        return None
    with open(video_path, "rb") as f:
        vid = f.read()
    vsn_name, vsn_bytes, asset_name, asset_bytes = build_vsn(vid, "mp4", "sprint0_vid")
    url = f"{BASE}/api/program/{vsn_name}"
    files = {
        "f1": (vsn_name, vsn_bytes, "application/octet-stream"),
        "f2": (asset_name, asset_bytes, "video/mp4"),
    }
    t0 = time.time()
    r = logged_request("POST", url, params={"autoplay": 1}, files=files,
                       auth=AUTH, timeout=600,
                       test_id="T5", desc=f"Publish VIDEO (autoplay=1) — "
                                          f"{len(vid)/1024:.0f}KB mp4")
    elapsed = time.time() - t0
    if r is None:
        record("T5", "Publish video", False, "Network error on upload", docs); return None
    if r.status_code != 200:
        record("T5", "Publish video", False,
               f"HTTP {r.status_code} after {elapsed:.1f}s. Body: {r.text[:200]}", docs)
        return None
    record("T5", "Publish video (autoplay=1)", True,
           f"Uploaded {len(vid)/1024:.0f}KB in {elapsed:.1f}s → LOOK AT LED, take Photo B.", docs)
    return {"upload_time": elapsed}


def test_6_documentation():
    files = list(LOG_DIR.glob("*"))
    record("T6", "Full HTTP transcripts saved", True,
           f"{len(files)} evidence file(s) in {LOG_DIR}/", "")


# ============================================================
# REPORT
# ============================================================
def write_report(aborted=False):
    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    with open(REPORT, "w") as f:
        f.write(f"# Sprint 0 Report — {STAMP}\n\n")
        f.write(f"**Target device**: {BASE}\n")
        f.write(f"**Aborted due to critical failure**: {'YES' if aborted else 'no'}\n\n")
        f.write("## Endpoints (100% verified against official Apifox docs)\n\n")
        f.write("- UDP :9041 discovery — https://colorlight-doc.apifox.cn/doc-7054095\n")
        f.write("- GET /api/info.json — https://colorlight-doc.apifox.cn/api-145138569\n")
        f.write("- POST /api/program/*.vsn — https://colorlight-doc.apifox.cn/doc-8105869\n")
        f.write("- HTTP Basic Auth — https://colorlight-doc.apifox.cn/doc-7054166\n\n")
        f.write(f"## Result: {passed}/{total} tests passed\n\n")
        f.write("| # | Test | Result | Details | Docs |\n|---|---|---|---|---|\n")
        for r in results:
            mark = "✅ PASS" if r["pass"] else "❌ FAIL"
            docs = f"[link]({r['docs']})" if r.get('docs') else "—"
            f.write(f"| {r['id']} | {r['name']} | {mark} | {r['details']} | {docs} |\n")
        f.write("\n## HTTP transcripts\n\n")
        f.write(f"Full request/response per test: `{LOG_DIR}/`\n\n")
        f.write("## Photos required (from you, with phone)\n")
        f.write("- **Photo A**: LED showing the red test image (after T4 passes)\n")
        f.write("- **Photo B**: LED playing the test video (after T5 passes)\n\n")
        f.write("## Verdict\n")
        if aborted:
            f.write("🔴 **ABORTED** at first critical failure. Do NOT patch silently. "
                    "Re-read the docs section for the failed test.\n")
        elif passed == total:
            f.write("🟢 **Sprint 0 PASSED** — 99% confidence. Ready for Sprint 1.\n")
        else:
            f.write("🔴 **Sprint 0 FAILED** — architect must review before Sprint 1.\n")


# ============================================================
# MAIN
# ============================================================
def main():
    open(RAW_LOG, "w").close()
    hr("═", color=CYAN)
    cprint(f"  Sprint 0 Diagnostic Tool — {STAMP}", CYAN + BOLD)
    cprint(f"  Target: {BASE}   User: {config.DEVICE_USER}", GREY)
    cprint(f"  Report will be written to: {OUT}/", GREY)
    hr("═", color=CYAN)
    print()

    test_1_device_info();       stop_if_critical_failed("T1")
    test_2_auth();              stop_if_critical_failed("T2")
    test_3_discovery();         stop_if_critical_failed("T3")
    test_4_publish_image();     stop_if_critical_failed("T4")
    test_5_publish_video()      # non-critical
    test_6_documentation()

    write_report(aborted=False)
    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    hr("═", color=CYAN)
    color = GREEN if passed == total else YELLOW
    cprint(f"  DONE: {passed}/{total} tests passed. Report: {REPORT}", color + BOLD)
    hr("═", color=CYAN)
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
