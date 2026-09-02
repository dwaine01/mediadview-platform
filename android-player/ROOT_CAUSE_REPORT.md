# MediaView Player — Root Cause Report

## Scope

Static audit of the Android player, the WebView activation page, and the existing
player/device API contracts before the native-player refactor.

## Confirmed causes of the post-pairing black screen

1. **The Web player hid its controlled fallback before media became playable.**
   `web_player()` called `sf(false)` as soon as a non-empty playlist arrived.
   Image/video HTTP, decode, renderer, or autoplay failures then left `#ml` black;
   error handlers only advanced to the next item and never restored a visible
   error state. This directly converts any content failure into a black screen.

2. **The two playlist contracts used different scheduling rules.**
   `/api/player/{screen_id}/playlist` accepted open-ended schedules, while
   `/api/devices/{device_id}/playlist` used Mongo `$lte/$gte` filters that reject
   `null` or missing dates. The normal code-pairing flow uses the device endpoint,
   so a valid campaign could become an empty playlist immediately after pairing.

3. **The player media endpoint only handled legacy local files.**
   `/api/player/media/{media_id}` ignored the existing R2-aware storage adapter.
   R2-backed media therefore returned 404. Legacy files missing from ephemeral
   server disk produced the same result. Combined with cause 1, this is a
   deterministic black-screen path.

4. **Pairing identity was fragmented across three stores.**
   Web `localStorage`, `mediaview_identity`, and `mediaview_player` could disagree.
   The normal WebView registration omitted `client_uuid`, so it bypassed backend
   idempotency. The v2.5 migration also cleared Web storage and `screen_id`, forcing
   re-pairing and creating orphan device records.

## Additional production blockers

- The WebView cache was RAM-only blob storage and was cleared on launch; there was
  no durable offline playback.
- Native heartbeat and auto-update were never enabled for devices paired through
  the WebView flow.
- WorkManager was configured with a 5-minute periodic interval although Android's
  supported minimum is 15 minutes.
- SSL errors were accepted with `handler.proceed()`, and WebView renderer death was
  not handled.
- Boot receivers repeatedly attempted background Activity launches, behavior that
  modern Android versions may block unless the app is the managed/default HOME app.
- The app claimed Media3/native playback but contained no Media3 dependency.

## Correction strategy

- One native identity store and one native pairing flow.
- One canonical backend playlist builder, preserving both public endpoint shapes.
- Native Media3 video, native image rendering, isolated WebView only for HTML/widget
  content.
- Room manifest plus atomic `.tmp` downloads, SHA-256/size validation, and retention
  of the last known-good playlist.
- Never hide the status surface until the renderer reports the first usable frame.
- Network callback + bounded retry, renderer watchdog, heartbeat, boot recovery,
  remote diagnostics, and storage cleanup.
- Diagnostic build first; production build keeps the diagnostic screen hidden and
  accessible only through the installer key sequence.

## API compatibility decision

No existing path or required response field is removed. The device playlist keeps
its current contract and receives additive `playlist_version` and `media_url`
fields. The screen playlist receives additive `download_url`, `size`, and
`checksum` fields. Both endpoints now call the same eligibility builder so their
behavior cannot diverge again.

## Release limitation that cannot be hidden in software

Stock Android may block background Activity launches and silent APK installation.
Guaranteed unattended boot/update requires the player to be the default HOME app
or the device to be provisioned as Device Owner / manufacturer-managed kiosk. The
onn installation flow must select MediAd View as HOME. Silent APK installation
still requires Device Owner/OEM privileges; this limitation will not be hidden.