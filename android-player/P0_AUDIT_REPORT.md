# MediaView Player P0 — Auditoría y corrección

## Alcance

Auditoría sin rewrite del flujo real:

`Dashboard → Playlist editor → Publish → FastAPI/MongoDB → SSE/polling → Room/cache → Renderer Android`

## Flujo actual trazado

1. El portal guarda `items` mixtos en `/api/playlists/{id}`.
2. Publicar asigna `screen_ids`, horario y prioridad; incrementa `playlist_version`.
3. FastAPI emite `playlist.updated` por SSE; polling cada 15 segundos permanece como respaldo.
4. El player solicita `/api/devices/{device_id}/playlist`.
5. `PlayerRepository` descarga todos los assets a temporales, verifica bytes/SHA-256 y solo
   entonces reemplaza el manifiesto Room en una transacción.
6. `PlaybackController` reproduce la playlist local y heartbeat informa estado al backend.

## WORKING

- Pairing nativo e idempotente; device/screen existentes se preservan.
- Playlist canónica y URLs absolutas.
- Descarga offline, temporales, SHA-256, Room y última playlist válida.
- SSE con reconexión + polling fallback.
- Heartbeat y comandos remotos.
- ExoPlayer para video, Coil para imágenes y WebView aislado para menús/widgets.

## BROKEN — causas encontradas

### 1. Diagnostics visibles

**Causa:** la variante `diagnostic` iniciaba `diagnosticsView` en `VISIBLE`; tecla `I` y cinco
pulsaciones de MENU abrían datos técnicos sin autenticar.

**Corrección:** overlay siempre oculto; acceso por PIN/configuración o activation code;
comandos admin `show_diagnostics`/`hide_diagnostics`; auto-cierre a los cinco minutos.

### 2. “Cargando contenido” y flash entre items

**Causa:** cada transición llamaba `clearSurface()`, liberaba ExoPlayer/WebView, borraba el
frame activo y mostraba `statusView` antes de preparar el siguiente item.

**Corrección:** sesiones `activeSession` + `pendingSession`; el siguiente item se prepara con
alpha 0 mientras el anterior permanece visible; el switch sucede después de decode/primer
frame/page commit con crossfade de 220 ms. Los errores conservan el frame activo y saltan.

### 3. Fotos/videos pequeños

**Causa:** imágenes usaban `FIT_CENTER` y PlayerView conservaba resize FIT.

**Corrección:** `display_mode` end-to-end con `COVER` predeterminado, `CONTAIN` y `STRETCH`;
imágenes usan `CENTER_CROP/FIT_CENTER/FIT_XY`; videos usan `ZOOM/FIT/FILL`.

## MISSING corregido en P0

- Display mode persistente en Room con migración 1→2 no destructiva.
- Selector de fit por item en Playlists web.
- Heartbeat ampliado: ids, playlist/media actual, red, storage, resolución, orientación y sync.
- Diagnostics pairing/player protegidos.
- Player objetivo `3.2.0` (`versionCode 17`).

## RISKY / BLOCKED

- No se compila Android dentro del contenedor; Codemagic/GitHub Actions son la autoridad.
- La ausencia intencional de contenido deja superficie negra; no se muestra mensaje técnico.
- Menús HTML siguen dependiendo de WebView, pero pairing, imágenes y video no.
- La firma debe coincidir con la instalada en el TV para upgrade in-place.
- Solo un TV físico puede confirmar HDMI/overscan/OEM, transición visual y recuperación WAN.

## Estado

### COMPLETED

- Auditoría del flujo.
- Correcciones de diagnostics, loading y fullscreen.
- Contratos backend/portal/heartbeat.
- Doble buffer y migración Room implementados.

### TESTED

- 17 contratos backend relevantes aprobados.
- Ruff y ESLint aprobados.
- Búsqueda estática confirma ausencia de mensajes públicos de carga/error.

### IN PROGRESS

- Revisión estática Kotlin independiente.
- Build CI v3.2.0 y publicación de APK.

### BLOCKED

- Aceptación visual y offline en Android TV físico hasta instalar el artifact CI.
