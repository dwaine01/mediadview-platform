#!/bin/bash
# ============================================================
# MediaView Player - TV Setup Script
# Run this from a PC connected to the same network as the TV
# ============================================================

echo "============================================"
echo "  MediaView Player - TV Setup"
echo "============================================"
echo ""

# Check if ADB is installed
if ! command -v adb &> /dev/null; then
    echo "ERROR: ADB is not installed."
    echo "Install it from: https://developer.android.com/tools/releases/platform-tools"
    exit 1
fi

# Get parameters
read -p "TV IP Address (e.g. 192.168.1.100): " TV_IP
read -p "MediaView Server URL (e.g. https://your-server.com): " SERVER_URL
read -p "Screen ID (from admin panel): " SCREEN_ID

if [ -z "$TV_IP" ] || [ -z "$SERVER_URL" ] || [ -z "$SCREEN_ID" ]; then
    echo "ERROR: All fields are required."
    exit 1
fi

echo ""
echo "Connecting to TV at $TV_IP..."
adb connect "$TV_IP:5555"

echo ""
echo "Checking connection..."
DEVICE_COUNT=$(adb devices | grep -c "device$")
if [ "$DEVICE_COUNT" -lt 1 ]; then
    echo "ERROR: Could not connect to TV."
    echo "Make sure:"
    echo "  1. TV is on and connected to WiFi"
    echo "  2. Developer Mode is enabled"
    echo "  3. USB Debugging is ON"
    echo "  4. You accepted the 'Allow USB debugging' popup on TV"
    exit 1
fi
echo "Connected successfully!"

# Check if APK exists
APK_PATH="./app/build/outputs/apk/release/app-release.apk"
if [ ! -f "$APK_PATH" ]; then
    APK_PATH="./mediaview-player.apk"
fi
if [ ! -f "$APK_PATH" ]; then
    echo ""
    read -p "Path to MediaView Player APK: " APK_PATH
fi

if [ -f "$APK_PATH" ]; then
    echo ""
    echo "Installing MediaView Player..."
    adb install -r "$APK_PATH"
else
    echo ""
    echo "WARNING: APK not found. Skipping installation."
    echo "If already installed, continuing with configuration..."
fi

echo ""
echo "Configuring TV for digital signage..."

# Disable screen timeout
adb shell settings put system screen_off_timeout 2147483647
echo "  [OK] Screen timeout disabled"

# Disable screensaver
adb shell settings put secure screensaver_enabled 0
echo "  [OK] Screensaver disabled"

echo ""
echo "Launching MediaView Player..."
adb shell am start -n com.mediaview.player/.MainActivity \
    --es server_url "$SERVER_URL" \
    --es screen_id "$SCREEN_ID"

echo ""
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "  TV IP:      $TV_IP"
echo "  Server:     $SERVER_URL"
echo "  Screen ID:  $SCREEN_ID"
echo ""
echo "  The TV should now be showing MediaView Player."
echo "  Press 'i' on the remote to see diagnostics."
echo ""
echo "  To update later:"
echo "  adb connect $TV_IP:5555"
echo "  adb install -r new-version.apk"
echo ""
