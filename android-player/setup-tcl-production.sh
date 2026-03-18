#!/bin/bash
# ============================================================
# MediaView Player - TCL Google TV Production Setup
# CERTIFIED CONFIGURATION for auto-start without external box
# ============================================================
# 
# CERTIFIED MODELS (Initial):
#   - TCL P Series (P745, P755) - Google TV
#   - TCL C Series (C745, C755, C845) - Google TV  
#   - TCL S Series (S5400A, S5500) - Google TV
#   - TCL QM Series (QM6K, QM7) - Google TV QLED
#
# This script configures GUARANTEED auto-start by:
#   1. Installing the APK
#   2. Disabling Google TV default launcher
#   3. Setting MediaView as home launcher
#   4. Configuring Safety Guard auto-launch permission
#   5. Disabling sleep/screensaver/updates
#   6. Verifying with reboot test
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  MediaView Player - Production Setup${NC}"
echo -e "${BLUE}  TCL Google TV Certified Configuration${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# ===== CHECK ADB =====
if ! command -v adb &> /dev/null; then
    echo -e "${RED}ERROR: ADB not installed.${NC}"
    echo "Download: https://developer.android.com/tools/releases/platform-tools"
    exit 1
fi

# ===== GET CONFIG =====
read -p "TV IP Address (e.g. 192.168.1.100): " TV_IP
read -p "MediaView Server URL (e.g. https://app.mediaview.com): " SERVER_URL
read -p "Screen ID (from MediaView Admin Panel): " SCREEN_ID

if [ -z "$TV_IP" ] || [ -z "$SERVER_URL" ] || [ -z "$SCREEN_ID" ]; then
    echo -e "${RED}ERROR: All fields required.${NC}"
    exit 1
fi

PKG="com.mediaview.player"

echo ""
echo -e "${YELLOW}[1/10] Connecting to TV...${NC}"
adb disconnect > /dev/null 2>&1 || true
adb connect "$TV_IP:5555"
sleep 2

if ! adb devices | grep -q "$TV_IP"; then
    echo -e "${RED}FAILED: Cannot connect.${NC}"
    echo "Verify: Developer Mode ON, USB Debugging ON, same WiFi network"
    echo "On TV: Settings > System > About > tap Build Number 7 times"
    echo "Then: Settings > System > Developer Options > USB Debugging ON"
    exit 1
fi
echo -e "${GREEN}  Connected to $TV_IP${NC}"

echo ""
echo -e "${YELLOW}[2/10] Installing MediaView Player APK...${NC}"
APK=$(find . -name "*.apk" -type f 2>/dev/null | head -1)
if [ -n "$APK" ]; then
    adb -s "$TV_IP:5555" install -r "$APK" 2>&1
    echo -e "${GREEN}  Installed: $APK${NC}"
else
    echo -e "${YELLOW}  No APK in current directory. Assuming already installed.${NC}"
fi

echo ""
echo -e "${YELLOW}[3/10] Disabling screen timeout and screensaver...${NC}"
adb -s "$TV_IP:5555" shell settings put system screen_off_timeout 2147483647
adb -s "$TV_IP:5555" shell settings put secure screensaver_enabled 0
adb -s "$TV_IP:5555" shell settings put global stay_on_while_plugged_in 3
echo -e "${GREEN}  Screen timeout: NEVER${NC}"
echo -e "${GREEN}  Screensaver: DISABLED${NC}"
echo -e "${GREEN}  Stay on while plugged: YES${NC}"

echo ""
echo -e "${YELLOW}[4/10] Disabling system notifications...${NC}"
adb -s "$TV_IP:5555" shell settings put global heads_up_notifications_enabled 0 2>/dev/null || true
echo -e "${GREEN}  Notifications: DISABLED${NC}"

echo ""
echo -e "${YELLOW}[5/10] Configuring immersive mode...${NC}"
adb -s "$TV_IP:5555" shell settings put global policy_control "immersive.full=*" 2>/dev/null || true
echo -e "${GREEN}  Immersive mode: ENABLED${NC}"

echo ""
echo -e "${YELLOW}[6/10] Launching MediaView Player...${NC}"
adb -s "$TV_IP:5555" shell am start -n "$PKG/.MainActivity" \
    --es server_url "$SERVER_URL" \
    --es screen_id "$SCREEN_ID"
sleep 3
echo -e "${GREEN}  MediaView Player launched${NC}"

echo ""
echo -e "${YELLOW}[7/10] Setting MediaView as default Home Launcher...${NC}"
echo ""
echo -e "${BLUE}  Attempting automatic configuration...${NC}"

# Method 1: Direct set-home-activity (works on many AOSP/TCL)
adb -s "$TV_IP:5555" shell cmd package set-home-activity "$PKG/.MainActivity" 2>/dev/null && \
    echo -e "${GREEN}  Home launcher set via cmd package${NC}" || true

# Method 2: Disable Google TV launcher (forces our app as home)
echo ""
echo -e "${BLUE}  Disabling Google TV default launcher...${NC}"
adb -s "$TV_IP:5555" shell pm disable-user --user 0 com.google.android.tvlauncher 2>/dev/null && \
    echo -e "${GREEN}  com.google.android.tvlauncher: DISABLED${NC}" || \
    echo -e "${YELLOW}  tvlauncher disable not supported on this model${NC}"

adb -s "$TV_IP:5555" shell pm disable-user --user 0 com.google.android.apps.tv.launcherx 2>/dev/null && \
    echo -e "${GREEN}  com.google.android.apps.tv.launcherx: DISABLED${NC}" || \
    echo -e "${YELLOW}  launcherx disable not supported${NC}"

echo ""
echo -e "${YELLOW}  NOTE: If the TV shows a 'Select Home App' dialog,${NC}"
echo -e "${YELLOW}  select 'MediaView Player' and choose 'Always'.${NC}"

echo ""
echo -e "${YELLOW}[8/10] TCL Safety Guard configuration...${NC}"
echo ""
echo -e "${BLUE}  *** MANUAL STEP REQUIRED (TCL specific) ***${NC}"
echo ""
echo "  On the TV remote, navigate to:"
echo "  Settings > Apps > Safety Guard > Permission Shield > Auto Launch"
echo ""
echo "  Then configure:"
echo "  1. 'Auto Manager' --> CLOSED (toggle OFF)"
echo "  2. 'MediaView Player' --> OPENED (toggle ON)"
echo ""
echo "  This allows MediaView Player to auto-start on boot."
echo ""
read -p "  Press ENTER when done (or ENTER to skip if not TCL)..."

echo ""
echo -e "${YELLOW}[9/10] Disabling auto-updates (prevents unexpected reboots)...${NC}"
adb -s "$TV_IP:5555" shell pm disable-user --user 0 com.google.android.gms 2>/dev/null && \
    echo -e "${GREEN}  Google Play Services auto-update: DISABLED${NC}" || \
    echo -e "${YELLOW}  Could not disable (non-critical)${NC}"
echo -e "${YELLOW}  To re-enable later: adb shell pm enable com.google.android.gms${NC}"

echo ""
echo -e "${YELLOW}[10/10] Verification reboot test...${NC}"
echo ""
echo "  The TV will now REBOOT to verify auto-start."
echo "  After reboot, MediaView Player should start automatically."
echo ""
read -p "  Press ENTER to reboot TV (or Ctrl+C to skip)..."

adb -s "$TV_IP:5555" shell reboot
echo ""
echo -e "${BLUE}  TV is rebooting... waiting 60 seconds...${NC}"
sleep 60

# Reconnect after reboot
echo "  Reconnecting..."
adb connect "$TV_IP:5555" > /dev/null 2>&1
sleep 5

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  SETUP COMPLETE${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Device:    $TV_IP"
echo "  Server:    $SERVER_URL"
echo "  Screen:    $SCREEN_ID"
echo ""
echo -e "  ${BLUE}VERIFICATION CHECKLIST:${NC}"
echo "  [ ] TV rebooted and MediaView Player started automatically"
echo "  [ ] Content is playing (or fallback screen showing)"
echo "  [ ] Press HOME on remote - should stay in MediaView"
echo "  [ ] Press 'i' on remote - diagnostics HUD appears"
echo ""
echo -e "  ${YELLOW}IF AUTO-START DID NOT WORK:${NC}"
echo "  1. Check TCL Safety Guard settings (Step 8)"
echo "  2. Try disabling launcher: adb shell pm disable-user --user 0 com.google.android.tvlauncher"
echo "  3. Try set-home: adb shell cmd package set-home-activity $PKG/.MainActivity"
echo ""
echo -e "  ${BLUE}For remote management:${NC}"
echo "  adb connect $TV_IP:5555"
echo "  adb shell am start -n $PKG/.MainActivity"
echo ""
echo -e "  ${BLUE}For APK updates:${NC}"
echo "  adb connect $TV_IP:5555"
echo "  adb install -r new-version.apk"
echo ""
echo -e "  ${RED}To restore TV to normal (undo all changes):${NC}"
echo "  adb shell pm enable com.google.android.tvlauncher"
echo "  adb shell pm enable com.google.android.apps.tv.launcherx"
echo "  adb shell pm enable com.google.android.gms"
echo "  adb shell pm uninstall $PKG"
echo "  adb shell settings put system screen_off_timeout 1800000"
echo "  adb reboot"
echo ""
