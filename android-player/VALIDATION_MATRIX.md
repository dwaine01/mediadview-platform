# MediaView Player v3 — Validation Matrix

## Automated gates before APK

| Scenario | Automated coverage | Expected result |
|---|---|---|
| Pairing | Backend idempotency test | Same `client_uuid` returns the same device/code |
| Empty playlist | Backend + Kotlin contract tests | Explicit empty list; controlled status remains visible |
| Video | Kotlin contract classification + Media3 build | Routed to Media3; status hides only after first frame |
| Image | Kotlin contract classification + Coil build | Routed to Coil; status hides only after decode success |
| HTML/WebView | Kotlin contract classification | Isolated WebView; SSL cancelled; renderer death recovered |
| Network loss | Bounded retry test | Last Room playlist remains active; retry capped at 5 minutes |
| Reconnection | NetworkCallback + retry contract | Immediate sync when connectivity returns |
| Device reboot | Boot action policy test | Boot/package replacement trigger one recovery request |
| Playlist update | Signature + backend version tests | Changed duration/hash/order replaces manifest atomically |
| Corrupt content | SHA/size + atomic swap test | `.tmp` rejected; last known-good file remains untouched |

## Required physical onn Android TV acceptance before production release

1. Fresh install on the onn box shows a stable pairing code and diagnostic HUD.
2. Pairing transitions to the assigned `screen_id` without relaunch.
3. JPEG/PNG remains visible for its configured duration.
4. H.264/AAC MP4 renders a first frame, loops, and advances.
5. HTML/widget renders; invalid SSL remains blocked with a visible error.
6. Disconnect WAN for 10 minutes: cached content continues.
7. Reconnect WAN: HUD updates HTTP/last-sync and applies playlist change.
8. Power-cycle the onn box: default HOME launches player and cached content starts.
9. Publish a changed playlist: atomic download completes before switching.
10. Serve a truncated/bad file: player rejects it, shows controlled status, and
    advances or keeps the last valid playlist.

## Release gate

The production alias must not be overwritten until all ten onn/TV checks pass.
The `release` variant has `DIAGNOSTICS_ENABLED=false`; the `diagnostic` variant
shows URL, `screen_id`, pairing, HTTP, WebView/player errors, network, and sync time.