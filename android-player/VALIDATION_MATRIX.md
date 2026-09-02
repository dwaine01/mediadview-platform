# MediaView Player v3.2 — Validation Matrix

Production target: `v3.2.0` (`versionCode 17`); diagnostics stay locked until PIN/admin command.

## Automated gates before APK

| Scenario | Automated coverage | Expected result |
|---|---|---|
| Pairing | Backend idempotency test | Same `client_uuid` returns the same device/code |
| Empty playlist | Backend + Kotlin contract tests | Explicit empty list; no public technical message |
| Video | Pending ExoPlayer + first-frame gate | Active item remains visible; COVER default; seamless switch |
| Image | Pending Coil surface + decode gate | Active item remains visible; COVER default; seamless switch |
| HTML/WebView | Kotlin contract classification | Isolated WebView; SSL cancelled; renderer death recovered |
| Network loss | Bounded retry test | Last Room playlist remains active; retry capped at 5 minutes |
| Reconnection | NetworkCallback + retry contract | Immediate sync when connectivity returns |
| Device reboot | Boot action policy test | Boot/package replacement trigger one recovery request |
| Playlist update | SSE + 15 s polling + Room migration tests | Atomic download/switch; polling recovers missed events |
| Corrupt content | SHA/size + atomic swap test | `.tmp` rejected; last known-good file remains untouched |

## Required physical onn Android TV acceptance before production release

1. Fresh install on the onn box shows a stable pairing code and no diagnostic HUD.
2. Pairing transitions to the assigned `screen_id` without relaunch.
3. JPEG/PNG remains visible for its configured duration.
4. H.264/AAC MP4 renders a first frame, loops, and advances.
5. HTML/widget renders; invalid SSL remains blocked without exposing a public error.
6. Disconnect WAN for 10 minutes: cached content continues.
7. Reconnect WAN: playlist change applies; PIN/admin command can inspect last-sync.
8. Power-cycle the onn box: default HOME launches player and cached content starts.
9. Publish a changed playlist: SSE triggers immediate sync and atomic download completes before switching.
10. Serve a truncated/bad file: player rejects it without public status and keeps
    the active frame while preparing another valid item.

## Release gate

The `/apk` direct-download candidate may update for acceptance, but the player
auto-update channel must not be promoted until all ten onn/TV checks pass.
Both variants start with diagnostics hidden. The diagnostic variant only enables
additional collection; viewing still requires PIN/activation code or admin command.