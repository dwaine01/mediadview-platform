"""
Sprint 0 — Quick smoke test (verified-only edition)
Uses officially documented endpoint: GET /api/info.json (docs: api-145138569)
"""
import sys
try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("pip install requests"); sys.exit(1)

import config

url = f"http://{config.DEVICE_IP}:{config.DEVICE_PORT}/api/info.json"
print(f"→ GET {url}")
print(f"   Docs: https://colorlight-doc.apifox.cn/api-145138569")
print(f"   Auth: {config.DEVICE_USER} / {'*'*len(config.DEVICE_PASS)}")
print()

try:
    r = requests.get(url, auth=HTTPBasicAuth(config.DEVICE_USER, config.DEVICE_PASS), timeout=15)
    print(f"← HTTP {r.status_code}")
    print("─" * 60)
    try:
        import json
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text[:1000])
    print("─" * 60)
    if r.status_code == 200:
        print("\n✅ Smoke test PASSED. Run:  python3 run_sprint0.py")
    elif r.status_code == 401:
        print("\n❌ Auth failed. Try 'Console@123' in config.py, or reset device password.")
    else:
        print(f"\n❌ Unexpected HTTP {r.status_code}.")
except requests.exceptions.ConnectionError:
    print(f"\n❌ Cannot reach {config.DEVICE_IP}. Ping it, verify LAN + power.")
except Exception as e:
    print(f"\n❌ {e}")
