"""
Sprint 0 — Quick smoke test.
Just verifies you can reach the A35 and read basic device info.
Use this FIRST to confirm connectivity before running the full Sprint 0.

Usage:
    python3 quick_smoke_test.py
"""

import sys
try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("Install requests:  pip install requests")
    sys.exit(1)

import config

url = f"http://{config.DEVICE_IP}:{config.DEVICE_PORT}/api/system/info"
print(f"→ GET {url}")
print(f"   Auth: {config.DEVICE_USER} / {'*' * len(config.DEVICE_PASS)}")

try:
    r = requests.get(url, auth=HTTPBasicAuth(config.DEVICE_USER, config.DEVICE_PASS),
                     timeout=15)
    print(f"← HTTP {r.status_code}")
    print("─" * 60)
    try:
        import json
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text[:1000])
    print("─" * 60)
    if r.status_code == 200:
        print("\n✅ Smoke test PASSED. You can now run:  python3 run_sprint0.py")
    elif r.status_code == 401:
        print("\n❌ Auth failed. Try password 'Console@123' in config.py, or reset the device.")
    else:
        print(f"\n❌ Unexpected HTTP {r.status_code}. Check the device is powered on and reachable.")
except requests.exceptions.ConnectionError:
    print(f"\n❌ Cannot reach {config.DEVICE_IP}. Verify:")
    print(f"   - The A35 is powered on")
    print(f"   - Your laptop is on the same LAN as the A35")
    print(f"   - The IP {config.DEVICE_IP} is correct (ping it to confirm)")
except requests.exceptions.Timeout:
    print(f"\n❌ Timeout. Device is unreachable or slow. Check network.")
except Exception as e:
    print(f"\n❌ Exception: {e}")
