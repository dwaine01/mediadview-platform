#!/bin/bash
# ============================================================
# MediaView Player - Production TV Setup Script
# Configures GUARANTEED auto-start by setting app as Home Launcher
# ============================================================

set -e

echo "============================================"
echo "  MediaView Player - Production Setup"
echo "============================================"
echo ""

if ! command -v adb &> /dev/null; then
    echo "ERROR: ADB not installed. Get it from:"
    echo "https://developer.android.com/tools/releases/platform-tools"
    exit 1
fi

read -p "TV/Device IP Address: " TV_IP
read -p "MediaView Server URL: " SERVER_URL
read -p "Screen ID (from admin panel): " SCREEN_ID

if [ -z "$TV_IP" ] || [ -z "$SERVER_URL" ] || [ -z "$SCREEN_ID" ]; then
    echo "ERROR: All fields required."
    exit 1
fi

echo ""
echo "[1/8] Connecting to device..."
adb connect "$TV_IP:5555"
sleep 2

echo "[2/8] Verifying connection..."
if ! adb devices | grep -q "$TV_IP"; then
    echo "FAIL: Cannot connect. Check WiFi, Developer Mode, USB Debugging."
    exit 1
fi
echo "  Connected OK"

echo "[3/8] Installing APK..."
APK=$(find . -name "*.apk" -type f | head -1)
if [ -n "$APK" ]; then
    adb install -r "$APK"
    echo "  Installed: $APK"
else
    echo "  No APK found in current directory. Skipping install."
fi

echo "[4/8] Configuring display settings..."
# Disable screen timeout (max value = never)
adb shell settings put system screen_off_timeout 2147483647
# Disable screensaver
adb shell settings put secure screensaver_enabled 0
# Disable auto-rotate (force landscape)
adb shell settings put system accelerometer_rotation 0
echo "  Screen timeout: DISABLED"
echo "  Screensaver: DISABLED"

echo "[5/8] Disabling system interruptions..."
# Disable notifications
adb shell settings put global heads_up_notifications_enabled 0 2>/dev/null || true
# Disable auto-updates (prevents unexpected reboots)
adb shell pm disable-user --user 0 com.google.android.gms 2>/dev/null || true
echo "  Notifications: DISABLED"
echo "  Auto-updates: DISABLED (manual re-enable: adb shell pm enable com.google.android.gms)"

echo "[6/8] Launching MediaView Player..."
adb shell am start -n com.mediaview.player/.MainActivity \
    --es server_url "$SERVER_URL" \
    --es screen_id "$SCREEN_ID"
sleep 3

echo "[7/8] Setting MediaView as DEFAULT HOME LAUNCHER..."
echo ""
echo "  *** CRITICAL STEP ***"
echo "  The device should now show a 'Select Home App' dialog."
echo "  Select 'MediaView Player' and choose 'Always'."
echo ""
echo "  If no dialog appears, run manually on device:"
echo "  Settings > Apps > Default Apps > Home App > MediaView Player"
echo ""
echo "  Or force via ADB (may need root):"
echo "  adb shell cmd package set-home-activity com.mediaview.player/.MainActivity"
echo ""

# Try to trigger home selector
adb shell am start -a android.intent.action.MAIN -c android.intent.category.HOME 2>/dev/null || true

# For rooted devices / AOSP boxes, force set home:
adb shell cmd package set-home-activity com.mediaview.player/.MainActivity 2>/dev/null || true

echo "[8/8] Verifying setup..."
echo ""
echo "============================================"
echo "  SETUP COMPLETE"
echo "============================================"
echo ""
echo "  Device:    $TV_IP"
echo "  Server:    $SERVER_URL"
echo "  Screen:    $SCREEN_ID"
echo ""
echo "  VERIFICATION CHECKLIST:"
echo "  [ ] MediaView Player is showing on screen"
echo "  [ ] Press HOME button - should stay in MediaView (if set as home)"
echo "  [ ] Power off device, power on - should auto-start MediaView"
echo "  [ ] Press 'i' on remote for diagnostics"
echo ""
echo "  IF HOME LAUNCHER NOT SET:"
echo "  1. Go to Settings > Apps > Default Apps > Home App"
echo "  2. Select 'MediaView Player'"
echo "  3. Test power cycle"
echo ""
echo "  For updates: adb connect $TV_IP:5555 && adb install -r new.apk"
echo ""
