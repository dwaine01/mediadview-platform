# MediaView / MediAd View — PRD técnico

## Problema

El APK Android TV se emparejaba pero podía quedar en pantalla negra. El objetivo es
un player de digital signage 24/7, offline-first y recuperable, comparable en
robustez operativa con OptiSigns, ScreenCloud o Yodeck.

## Arquitectura

- **Backend:** FastAPI + MongoDB; contratos públicos `/api/devices/*` y
  `/api/player/*` preservados.
- **Panel:** HTML/CSS/JS servido por FastAPI.
- **Player Android:** Kotlin, Media3/ExoPlayer para video, Coil para imágenes,
  WebView aislado para HTML/widgets, Room para manifiesto persistente.
- **Entrega Android:** Codemagic; el contenedor local no compila Android.

## Causas raíz confirmadas

1. El player web ocultaba el fallback antes de confirmar imagen/frame/video; un
   404 o fallo de decoder quedaba como superficie negra.
2. Las playlists por `screen_id` y `device_id` aplicaban reglas de fechas distintas;
   el endpoint de dispositivo descartaba campañas abiertas con fechas nulas.
3. `/api/player/media/{id}` no utilizaba la capa de almacenamiento R2 y fallaba para
   objetos cloud o archivos legacy ausentes.
4. Pairing e identidad estaban fragmentados entre Web localStorage y dos archivos
   SharedPreferences; una migración borraba el vínculo.

Detalle y correcciones: `/app/android-player/ROOT_CAUSE_REPORT.md`.

## Implementado

- Pairing nativo idempotente y una identidad canónica persistente.
- Playlist canónica compartida, checksums SHA-256, versión y URLs compatibles.
- Render nativo por tipo, estado visible hasta `first frame`/decode/commit visual.
- Room + descargas `.tmp`, validación de integridad, reemplazo con respaldo y
  conservación de la última playlist válida.
- Red: NetworkCallback, polling 15 s, backoff acotado y recuperación inmediata.
- Watchdog de playback, timeout de preparación, cuarentena temporal de corruptos,
  recuperación de crash y heartbeat en foreground/fallback WorkManager.
- BootReceiver único y flujo para configurar la app como HOME.
- SSL inválido bloqueado; HTTP y muerte del renderer WebView quedan visibles.
- HUD diagnóstico con URL, screen_id, pairing, HTTP, WebView/player error, red y
  última sincronización. `release` lo compila desactivado.
- CI separada: primero pruebas Kotlin, luego `assembleDiagnostic`; no reemplaza el
  alias APK de producción.
- Matriz de pruebas: `/app/android-player/VALIDATION_MATRIX.md`.

## Verificación actual

- Backend/contratos: **22 passed, 1 skipped**, ruff y py_compile correctos.
- Revisión estática Android/CI: sin bloqueador conocido tras añadir `org.json` a
  tests JVM.
- R2 real, decoders y boot no pueden verificarse en este contenedor.

## Prioridades

### P0 — actual

- Ejecutar Codemagic mediante **Save to Github** y confirmar que pruebas Kotlin +
  `assembleDiagnostic` terminan verdes.
- Instalar `mediaview-player-v3.0.0-diagnostic.apk` en el onn Android TV conectado al televisor.
- Completar los 10 checks físicos y reportar el HUD ante cualquier fallo.

### P1 — después de validar A40

- Corregir cualquier incompatibilidad específica del firmware/codec del onn detectada.
- Cambiar CI a `assembleRelease`, conservar `DIAGNOSTICS_ENABLED=false` y publicar
  el APK final sin sobrescribirlo antes de la aceptación.
- Prueba soak 24–72 horas con cortes de WAN y cambios de playlist.

### P2 — flota administrada

- Aprovisionamiento Device Owner/OEM para autoarranque e instalación silenciosa
  garantizados en Android moderno.
- Métricas remotas de decoder, almacenamiento, caché y recuperación por dispositivo.
- Validación end-to-end de Cloudflare R2 con objeto real.

### Backlog ajeno al player

- Stripe LIVE, D-04 multi-moneda, D-05 presign worker y mejoras de borrado en cascada.