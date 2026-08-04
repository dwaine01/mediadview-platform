# Sprint 0 — MediaView × Colorlight A35 Proof of Concept

**Objective**: Prove that MediaView can drive a Colorlight A35 using ONLY the official
Local HTTP API and Device Discovery Protocol documented at
https://colorlight-doc.apifox.cn/. Nothing else. No custom APK. No ColorlightCloud.

**Contract**: If any test reveals an assumption from previous architecture documents
was wrong, STOP, document it, and update the architecture before continuing.

---

## Phase 1 — Endpoints used by Sprint 0

Every endpoint below is documented in the official Colorlight docs. Nothing invented.

| # | Purpose | Method + Path | Docs URL | Test that uses it |
|---|---|---|---|---|
| 1 | Discover A35 on LAN | UDP broadcast `{"netType":1,"mType":71}` → port `9041/UDP` | doc-7054095 | Test 3 |
| 2 | Get device info (model, firmware, serial) | `GET /api/system/info` | api-145138569 | Test 1 |
| 3 | Verify LAN encryption status | `GET /api/system/encryption/lan` | api-145138599 | Test 2 |
| 4 | Publish JSON program + assets, autoplay=1 | `POST /api/program/{name}.vsn` (form-data) | api-145138684, doc-8105869 | Test 5, 6 |
| 5 | List programs on device | `GET /api/program/list` | api-179910235 | Test 7 |
| 6 | Get current playing status | `GET /api/program/play/status` | api-285091083 | Test 7, 8 |
| 7 | Get thumbnail of current program | `GET /api/program/thumbnail` | api-193165866 | Test 7 |
| 8 | Get device screenshot | `GET /api/system/screenshot` | api-145138572 | Test 7 |
| 9 | Get C-Cloud config (current cloud target) | `GET /api/cloud/ccloud/account` | api-180616402 | Test 4 |
| 10 | Set C-Cloud config (point at our server) | `POST /api/cloud/ccloud/account` | api-180616704 | Test 4 |
| 11 | Set HTTP polling interval | `POST /api/cloud/ccloud/pollinterval` | api-180612906 | Test 4 |
| 12 | Get boardconfig (device capabilities) | `GET /api/system/boardconfig` | api-145138607 | Test 1 |

**Auth**: HTTP Basic — user `admin`, password from `test_credentials.md`
(`Jesusmifielamigo8@` or default `Console@123`).

**Program format**: JSON `.vsn` — compatible with ALL firmware versions (docs §4.1).

**Filename spec**: `Playlist{id}_{md5_of_file}_{size_bytes}.vsn` for the .vsn descriptor,
`F_{md5}_{size}.{ext}` for each asset (docs §8.1). Device validates md5 + size.

---

## Phase 2 — Test environment

**Prerequisite**: A laptop on the SAME LAN as the A35, with Python 3.8+.

### Setup (Josue's laptop, one-time)
```
# Clone Sprint 0 files onto your laptop:
git pull   # if repo is already cloned locally
# OR just download the /app/sprint0/ folder from Emergent

cd sprint0/
pip install requests
```

### Configure device IP & credentials
Edit `config.py`:
```python
DEVICE_IP = "192.168.42.129"          # your A35's LAN IP
DEVICE_USER = "admin"
DEVICE_PASS = "Jesusmifielamigo8@"    # or Console@123 for default
MEDIAVIEW_URL = "https://panel.mediadview.com"  # for test 4
```

### Run all tests + generate report
```
python3 run_sprint0.py
```
Output: `sprint0_report_YYYYMMDD_HHMM.md` with PASS/FAIL per test + evidence.

---

## Phase 3 — The 9 tests

| # | Test | PASS criteria | FAIL criteria |
|---|---|---|---|
| 1 | Read device info | HTTP 200, JSON has `model`, `vername`, `serialno` | 401 / timeout / missing fields |
| 2 | Verify auth | HTTP 200 on protected endpoint using Basic auth | 401 with correct password |
| 3 | Discovery via UDP :9041 | Device responds within 5s with `serial` + `modelName` | No response after 3 broadcasts |
| 4 | Point device to MediaView server | Cloud config updated; device begins heartbeat to us | Endpoint returns error / no heartbeat within 5 min |
| 5 | Publish full-screen image (autoplay=1) | HTTP 200 + image visible on LED within 30s | Non-200 / image never appears |
| 6 | Publish full-screen video (autoplay=1, ~5MB mp4) | HTTP 200 + video plays on LED within 90s | Non-200 / video not playing |
| 7 | Verify playback via `/play/status` + screenshot | `playing.name` matches uploaded name; screenshot shows content | Wrong content / offline |
| 8 | Measure latency: publish → LED | Latency < 30s image / < 90s video | Latency > 5 min |
| 9 | Document all requests/responses | Every HTTP call captured in `sprint0_report.md` | Missing data |

**Sprint 0 PASSES if tests 1-9 all pass.**
**Sprint 0 FAILS if ANY test fails. Stop. Update architecture. Restart.**

---

## Phase 4 — Deliverables (what you send back)

After running `run_sprint0.py`, you deliver:

1. `sprint0_report_YYYYMMDD_HHMM.md` — auto-generated markdown with pass/fail per test
2. `sprint0_logs/` folder — full request/response dump per test
3. **2 photos of the LED with your phone**:
   - Photo A: LED showing the red test image from Test 5
   - Photo B: LED showing the test video from Test 6
4. **1 screenshot from the A35**: from Test 7 (`/api/system/screenshot`)
5. Latency measurements (Test 8) in the report

Send me all 5 items → I evaluate → declare Sprint 0 PASS or FAIL → we plan Sprint 1.

---

## Phase 5 — What to do if a test fails

Every failure = potential architecture assumption error. Follow this protocol:

1. **STOP.** Do not proceed to next test.
2. Copy the exact request + response + error from the log.
3. Send it to me with the message: *"Sprint 0 Test N failed. Assumption to re-evaluate: [describe]"*.
4. I re-read the specific docs section, identify the wrong assumption, propose fix.
5. Only then do you retry.

**Never patch a failure without re-reading the docs.**
