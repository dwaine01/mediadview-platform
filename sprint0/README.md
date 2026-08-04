# Sprint 0 — MediaView × Colorlight A35 (verified-only edition)

**Contract**: every endpoint below has been verified against its individual page on
the official Colorlight Apifox documentation. **Zero inferred endpoints.**

**Scope reduced**: 6 tests instead of 9. Any endpoint whose exact URL path could not
be confirmed from the docs was REMOVED, per your explicit instruction:
*"fewer tests with 100% verified APIs than more tests based on assumptions"*.

---

## ✅ Officially verified endpoints in Sprint 0

### 1) Device Discovery — UDP broadcast
- **Protocol**: UDP
- **Target**: `<broadcast>:9041`
- **Auth**: none (LAN protocol)
- **Request body** (exact, from docs):
  ```json
  {"netType": 1, "mType": 71}
  ```
- **Response body** (exact, from docs):
  ```json
  {
    "imgVersion": "6.1.3",
    "isNewBrightness": 1,
    "modelName": "a200",
    "password": "-",
    "serial": "CLCA20111457",
    "terminateName": "Terminal1457",
    "errorCode": 0,
    "mType": 72,
    "netType": 1,
    "deviceType": 0
  }
  ```
- **Docs URL**: https://colorlight-doc.apifox.cn/doc-7054095
- **Docs section**: §5, §7.1, §8.1

### 2) Get Device Info
- **Method**: `GET`
- **Path**: `/api/info.json`
- **Auth**: HTTP Basic (`Authorization: Basic base64(user:pass)`)
- **Request**: no body
- **Response example** (exact, from docs):
  ```json
  {
    "info": {
      "vername": "1.71.3",
      "fw": "A600.1713.240124.1910",
      "serialno": "CLCA8A123457",
      "model": "a800",
      "up": 1493809,
      "force_encryption": true,
      "mem": {"total": 4021211136, "free": 2926379008},
      "storage": {"total": 24950689792, "free": 24781905920},
      "playing": {"name": "", "path": "", "source": "STOP"}
    }
  }
  ```
- **Docs URL**: https://colorlight-doc.apifox.cn/api-145138569
- **Notes**: cURL example on the docs page uses your device IP `http://192.168.42.129`

### 3) HTTP Basic Auth (all local API calls)
- **Header**: `Authorization: Basic <base64(user:pass)>`
- **Default user**: `admin`
- **Default password**: `Console@123` (or whatever is currently set on your device)
- **Docs URL**: https://colorlight-doc.apifox.cn/doc-7054166 §6

### 4) Publish Program (image / video) with autoplay
- **Method**: `POST`
- **Path**: `/api/program/{program_name}.vsn`
- **Auth**: HTTP Basic
- **Content-Type**: `multipart/form-data`
- **Query param**: `autoplay=1` (per docs Q4 — value 0 = do not auto-play, 1 = play immediately)
- **File naming rule** (mandatory, docs §8.1):
  - `.vsn` file: `Playlist{id}_{md5}_{size_bytes}.vsn`
  - Asset files: `F_{md5}_{size_bytes}.{ext}` (e.g. `F_82B07E1F..._6446377.mp4`)
- **Form field names**: `f1`, `f2`, `f3`, ... (docs §5.3: "keys should be f\* form")
- **`.vsn` content**: JSON per docs §4.1 (compatible with ALL firmware versions)
- **Docs URL**: https://colorlight-doc.apifox.cn/doc-8105869 (§5) + https://colorlight-doc.apifox.cn/api-145138684

### JSON program-descriptor field spec
- **Docs URL**: https://colorlight-doc.apifox.cn/doc-7054971
- **Docs URL** (XML alternative, firmware ≥ 1.70.2 only): https://colorlight-doc.apifox.cn/doc-7054987

---

## 🗑 Removed from Sprint 0 (NOT officially verified paths — deferred)

| Original test | API ID (functionality confirmed) | Reason removed |
|---|---|---|
| GET screenshot | api-145138572 | Exact URL path not verified. Deferred to Sprint 0.5 after crawling docs page |
| GET play status | api-285091083 | Same — path not verified |
| GET program list | api-179910235 | Same |
| GET boardconfig | api-145138607 | Same |
| GET/POST C-Cloud account | api-180616402 / api-180616704 | Same — also destructive, defer |
| POST HTTP poll interval | api-180612906 | Same |
| GET LAN encryption status | api-145138599 | Same |
| GET program thumbnail | api-193165866 | Same |

**Functionality of each of these IS documented in the official docs.** Only the exact URL PATH remains unverified. Sprint 0.5 will crawl each individual page and add them back after verification.

---

## 🎯 Sprint 0 test list — reduced but 100% verified

| # | Test | Endpoint used | PASS criteria |
|---|---|---|---|
| T1 | Read device info | `GET /api/info.json` | HTTP 200, JSON has `info.model`, `info.vername`, `info.serialno` |
| T2 | Verify Basic Auth | `GET /api/info.json` with wrong password | 401 with wrong, 200 with correct (or 200/200 if LAN encryption OFF) |
| T3 | UDP Discovery | UDP `:9041` with `{"netType":1,"mType":71}` | Device responds within 5s with matching `serial` |
| T4 | Publish full-screen image | `POST /api/program/Playlist{id}_{md5}_{size}.vsn?autoplay=1` | HTTP 200 + image appears on LED |
| T5 | Publish full-screen video | Same endpoint, video asset | HTTP 200 + video appears on LED |
| T6 | Documentation & photos | Log + phone photos | Full request/response saved + photo of LED |

Sprint 0 PASSES if T1–T6 all pass.

---

## ▶ Execution

Every HTTP request and response is printed on screen exactly as sent/received
(colored for readability). Critical failures (T1–T4) stop the run immediately
per contract — no silent patching.

```bash
cd sprint0/
pip install requests pillow
python3 quick_smoke_test.py    # confirms connectivity + verified endpoint path
python3 run_sprint0.py         # runs T1..T6, produces markdown report + logs
```

Deliverables (send back to architect):
- `sprint0_report_YYYYMMDD_HHMM/sprint0_report.md`
- `sprint0_report_YYYYMMDD_HHMM/logs/*.txt` (full request/response transcripts)
- Photo A: LED showing red test image
- Photo B: LED playing test video (if `sprint0_test.mp4` provided)
