#!/usr/bin/env python3
"""
============================================================
MediaView → Colorlight A35 Bridge Script
============================================================

PURPOSE:
  This script bridges the gap between MediaView's Player API
  and the Colorlight A35 media player. Since the A35 does NOT
  expose an HTTP API for receiving content, this bridge:

  1. Polls MediaView's Player API for the current playlist
  2. Downloads and caches media files locally
  3. Exports content to a folder structure compatible with
     PlayerMaster USB import or manual publishing

USAGE:
  python3 a35_bridge.py --server http://your-server:8001 --screen-id <SCREEN_ID>

OPTIONS:
  --server       MediaView API server URL (default: http://localhost:8001)
  --screen-id    The screen ID to sync (required)
  --output       Output directory for cached content (default: ./a35_content)
  --interval     Polling interval in seconds (default: 300 = 5 min)
  --once         Run once and exit (no polling loop)

A35 INTEGRATION METHODS:

  Method 1: USB Export (Simplest)
    - Script downloads content to --output folder
    - Copy folder to USB drive
    - Insert USB into A35 for plug-and-play

  Method 2: LAN Shared Folder
    - Script downloads to a network-shared folder
    - PlayerMaster imports from the shared folder
    - Publish to A35 via LAN

  Method 3: HDMI Passthrough (Recommended for automation)
    - Connect a mini-PC/Raspberry Pi to LED controller via HDMI
    - Open the Web Player URL on the mini-PC browser:
      http://your-server:8001/api/player/<screen_id>/web
    - A35 receives the HDMI signal and displays on LED screen
    - Fully automated, no manual intervention needed

============================================================
"""

import argparse
import json
import os
import sys
import time
import hashlib
import base64
from datetime import datetime

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library required. Install: pip install requests")
    sys.exit(1)


class A35Bridge:
    def __init__(self, server_url, screen_id, output_dir):
        self.server_url = server_url.rstrip("/")
        self.screen_id = screen_id
        self.output_dir = output_dir
        self.media_dir = os.path.join(output_dir, "media")
        self.cache_file = os.path.join(output_dir, "playlist_cache.json")
        self.last_playlist_hash = None

        os.makedirs(self.media_dir, exist_ok=True)
        print(f"[A35 Bridge] Server: {self.server_url}")
        print(f"[A35 Bridge] Screen: {self.screen_id}")
        print(f"[A35 Bridge] Output: {self.output_dir}")

    def check_server(self):
        """Check server connectivity."""
        try:
            r = requests.get(f"{self.server_url}/api/player/{self.screen_id}/status", timeout=10)
            if r.status_code == 200:
                data = r.json()
                print(f"[A35 Bridge] Connected! Screen: {data.get('screen_name')}")
                print(f"[A35 Bridge] Active campaigns: {data.get('active_campaigns')}")
                print(f"[A35 Bridge] Resolution: {data.get('resolution')}")
                return True
            else:
                print(f"[A35 Bridge] ERROR: Server returned {r.status_code}")
                return False
        except Exception as e:
            print(f"[A35 Bridge] ERROR: Cannot connect to server: {e}")
            return False

    def fetch_playlist(self):
        """Fetch current playlist from MediaView API."""
        try:
            r = requests.get(
                f"{self.server_url}/api/player/{self.screen_id}/playlist",
                timeout=15
            )
            if r.status_code == 200:
                return r.json()
            else:
                print(f"[A35 Bridge] Playlist fetch error: {r.status_code}")
                return None
        except Exception as e:
            print(f"[A35 Bridge] Playlist fetch error: {e}")
            return None

    def download_media(self, media_id, filename):
        """Download a media file and save to local cache."""
        output_path = os.path.join(self.media_dir, filename)

        # Skip if already downloaded
        if os.path.exists(output_path):
            return output_path

        try:
            url = f"{self.server_url}/api/player/media/{media_id}"
            r = requests.get(url, timeout=60, stream=True)
            if r.status_code == 200:
                with open(output_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_kb = os.path.getsize(output_path) / 1024
                print(f"[A35 Bridge] Downloaded: {filename} ({size_kb:.1f} KB)")
                return output_path
            else:
                print(f"[A35 Bridge] Download error for {filename}: {r.status_code}")
                return None
        except Exception as e:
            print(f"[A35 Bridge] Download error for {filename}: {e}")
            return None

    def sync(self):
        """Main sync: fetch playlist → download media → generate export."""
        print(f"\n[A35 Bridge] Syncing at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")

        playlist = self.fetch_playlist()
        if not playlist:
            print("[A35 Bridge] No playlist data")
            return False

        items = playlist.get("items", [])
        playlist_hash = hashlib.md5(json.dumps(items, sort_keys=True).encode()).hexdigest()

        if playlist_hash == self.last_playlist_hash:
            print(f"[A35 Bridge] Playlist unchanged ({len(items)} items)")
            return True

        print(f"[A35 Bridge] Playlist updated! {len(items)} items")
        self.last_playlist_hash = playlist_hash

        # Download all media files
        local_items = []
        for item in items:
            media_id = item.get("media_id")
            filename = item.get("filename", f"{media_id}.bin")
            local_path = self.download_media(media_id, filename)

            if local_path:
                local_items.append({
                    "campaign_id": item.get("campaign_id"),
                    "media_id": media_id,
                    "filename": filename,
                    "local_path": local_path,
                    "content_type": item.get("content_type"),
                    "duration": item.get("duration", 15),
                    "order": len(local_items) + 1
                })

        # Generate playlist manifest
        manifest = {
            "screen_id": self.screen_id,
            "screen_name": playlist.get("screen_name"),
            "synced_at": datetime.now().isoformat(),
            "total_items": len(local_items),
            "loop": True,
            "items": local_items
        }

        # Save manifest
        manifest_path = os.path.join(self.output_dir, "playlist.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"[A35 Bridge] Manifest saved: {manifest_path}")

        # Generate PlayerMaster-compatible file list
        filelist_path = os.path.join(self.output_dir, "filelist.txt")
        with open(filelist_path, "w") as f:
            for item in local_items:
                f.write(f"{item['filename']}\t{item['duration']}s\n")
        print(f"[A35 Bridge] File list saved: {filelist_path}")

        # Clean up old media files not in current playlist
        current_files = set(item["filename"] for item in local_items)
        for existing in os.listdir(self.media_dir):
            if existing not in current_files:
                os.remove(os.path.join(self.media_dir, existing))
                print(f"[A35 Bridge] Cleaned up: {existing}")

        print(f"[A35 Bridge] Sync complete! {len(local_items)} files ready in {self.media_dir}")
        return True

    def run_loop(self, interval):
        """Run continuous sync loop."""
        print(f"[A35 Bridge] Starting sync loop (interval: {interval}s)")
        while True:
            try:
                self.sync()
            except KeyboardInterrupt:
                print("\n[A35 Bridge] Stopped by user")
                break
            except Exception as e:
                print(f"[A35 Bridge] Error: {e}")
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="MediaView → Colorlight A35 Bridge")
    parser.add_argument("--server", default="http://localhost:8001",
                        help="MediaView API server URL")
    parser.add_argument("--screen-id", required=True,
                        help="Screen ID to sync")
    parser.add_argument("--output", default="./a35_content",
                        help="Output directory")
    parser.add_argument("--interval", type=int, default=300,
                        help="Polling interval in seconds")
    parser.add_argument("--once", action="store_true",
                        help="Run once and exit")

    args = parser.parse_args()

    bridge = A35Bridge(args.server, args.screen_id, args.output)

    if not bridge.check_server():
        print("[A35 Bridge] Cannot connect to server. Exiting.")
        sys.exit(1)

    if args.once:
        success = bridge.sync()
        sys.exit(0 if success else 1)
    else:
        bridge.run_loop(args.interval)


if __name__ == "__main__":
    main()
