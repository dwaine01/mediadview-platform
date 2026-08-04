# Sprint 0 — configuration
# Edit these values before running run_sprint0.py

# The Colorlight A35 to test against (must be reachable on the LAN from this laptop)
DEVICE_IP = "192.168.42.129"
DEVICE_USER = "admin"
DEVICE_PASS = "Jesusmifielamigo8@"   # try "Console@123" if this fails with 401

# MediaView server URL that the device will be pointed at in Test 4
# NOTE: for Test 4 to fully validate, our cloud-side endpoints must be live at this URL.
MEDIAVIEW_URL = "https://panel.mediadview.com"

# Optional overrides
DEVICE_PORT = 80          # docs: port 80 from LAN, 8989 from inside device
UDP_DISCOVERY_PORT = 9041 # docs: doc-7054095 §5
REQUEST_TIMEOUT_SEC = 20
POLL_STATUS_INTERVAL_SEC = 2
POLL_STATUS_MAX_SEC = 180
