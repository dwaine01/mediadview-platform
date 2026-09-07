# Sprint 1 del Player — Entrega y checklist de prueba física

APK: **v3.3.0 (versionCode 18)** · Backend: MediaView FastAPI · Fecha: junio 2026

## 1. Qué cambié

**Backend (`/app/backend`)**
- `device_security.py` (nuevo): emisión y verificación de `device_token` (solo se guarda
  el hash SHA-256), máquina de estados canónica (17 estados), umbrales de conectividad
  (heartbeat 30 s · ONLINE < 90 s · STALE < 5 min · OFFLINE > 5 min) y normalización del
  progreso de sincronización.
- `server.py`:
  - `POST /api/devices/register` devuelve `device_token` + `heartbeat_interval_seconds`
    (también en el camino idempotente: el registro es el punto de enrolamiento y rota el token).
  - `POST /api/devices/{id}/heartbeat`, `GET /api/devices/{id}/playlist` y
    `POST /api/devices/{id}/log` ahora exigen el token (`X-Device-Token` o `Bearer`).
  - El heartbeat acepta y guarda `player_state` (validado contra la lista, lo inválido se ignora)
    y `sync_progress` (archivos y bytes reales; se limpia al pasar a PLAYING/READY).
  - **Nuevo** `GET /api/events/screen/{screen_id}` (SSE): eventos `hello` / `version` / `gone`,
    keepalive cada 20 s y cierre a los 10 min. Es el canal que el player ya llamaba y **no existía**.
- `workspace_routes.py`: `GET /api/workspace/now-playing` devuelve `connectivity`,
  `player_state`, `app_version` y `sync_progress` (solo si tiene menos de 3 min: nada de
  porcentajes pegados).

**Player Android (`/app/android-player`)**
- `PlayerStateMachine.kt` (nuevo): enum `PlayerState`, `SyncProgress` y estado observable
  thread-safe; impide combinaciones imposibles (sin progreso si no se está sincronizando).
- `DeviceIdentity.kt`: guarda/lee `device_token` (sobrevive reinicios).
- `PlayerApi.kt`: envía `X-Device-Token` en GET y POST.
- `DeviceRegistrar.kt` y `PairingActivity.kt`: persisten el token del registro antes de
  cualquier otra llamada; transiciones UNPAIRED → PAIRED.
- `PlayerRepository.kt`: progreso REAL por archivo y por bytes (`size` del manifiesto),
  estados SYNCING → DOWNLOADING → VALIDATING → READY/WAITING_FOR_ASSIGNMENT, y DEGRADED
  cuando se sigue con el último contenido bueno.
- `MainActivity.kt` y `HeartbeatWorker.kt`: reportan `player_state` y `sync_progress` en cada
  heartbeat; estados PLAYING / OFFLINE_PLAYING_CACHE / DEGRADED / ERROR / RESTARTING.
- `PlaybackController.kt`: `hasContent()` para distinguir DEGRADED de ERROR.
- `build.gradle.kts`: 3.2.0 (17) → **3.3.0 (18)**.

**Panel (`/app/frontend`)**
- `LiveScreens.tsx`: badge EN VIVO / SIN SEÑAL / OFFLINE según `connectivity`, etiqueta del
  estado en español, versión del APK y barra "Sincronizando 62 % · 3 de 8" con datos reales.

## 2. Qué reutilicé (no se reescribió)
Pairing de 6 dígitos e idempotencia por `client_uuid`, BootReceiver/BootWorker y rol HOME,
descargas con `.tmp` + verificación SHA/tamaño y swap atómico, caché Room, auto-update del APK,
diagnósticos existentes y los endpoints de dispositivo ya probados.

## 3. Pruebas reales ejecutadas (automatizadas, backend + panel)
`backend/tests/test_player_sprint1.py` — **5/5 pasan**:
1. El token se emite, es obligatorio, funciona por `X-Device-Token` y por `Bearer`, y al
   re-registrar rota (el token viejo pasa a 401). `playlist` y `log` también quedan protegidos.
2. Compatibilidad: un player ya instalado sin token sigue funcionando (modo gracia), se le
   adopta el primer token que presente y desde ese momento es obligatorio.
3. Estado y progreso llegan al panel: `DOWNLOADING`, 43 % calculado de 62/145 MB reales,
   un estado inválido no contamina, y al pasar a `PLAYING` el progreso se limpia.
4. El canal SSE existe: `text/event-stream`, evento `hello` con versión, 404 si la pantalla no existe.
5. Umbrales de conectividad ONLINE/STALE/OFFLINE/NEVER.

Regresión: 21 pruebas de las iteraciones 30-32 siguen pasando.

## 4. Lo que funciona con un APK normal (sin Device Owner)
Auto-arranque tras encendido, fullscreen, pairing, token propio, heartbeat con estado real,
progreso real, caché offline, cambio atómico de contenido, auto-update con diálogo de
instalación, reinicio de la propia app.

## 5. Lo que queda limitado por Device Owner / OEM
- Kiosco total (bloquear salida a Android): requiere Device Owner (lock task).
- Reiniciar el equipo: Device Owner o root.
- Update silencioso del APK: Device Owner o app de sistema.
- Screenshot desatendido: Device Owner / app de sistema (MediaProjection pide consentimiento).
- HDMI / CEC: firmware del fabricante.

## 6. Deuda encontrada durante el sprint (para sprints siguientes)
- Los comandos remotos siguen sin ID ni confirmación (Sprint 2).
- No hay historial de heartbeat, así que el uptime 24 h/7 d/30 d todavía no es calculable (Sprint 3).
- El player abre SSE pero **no reconecta con backoff explícito**: revisar en Sprint 2 junto con los comandos.
- `POST /api/devices/{id}/log` no tiene retención/TTL ni UI (Sprint 2).
- Los endpoints `/api/devices/*` restantes (`check`, `update-check`) aún no exigen token;
  se hará al cerrar el modo gracia (necesitamos que la flota instalada actualice primero).

## 7. Checklist para TU prueba en el equipo Android real

Antes: compila en Codemagic (workflow de release; el APK sale como artefacto) e instala el
APK 3.3.0 en la caja/TV. Anota modelo y versión de Android.

| # | Paso | Resultado esperado |
|---|---|---|
| 1 | Instalar el APK y abrirlo | Arranca sin pantalla azul/negra; branding MediaView |
| 2 | Ver la pantalla de emparejamiento | Código de 6 dígitos grande y legible a 3 m |
| 3 | En el panel: Pantallas → Agregar pantalla → escribir el código | El player confirma en segundos y muestra "conectada" |
| 4 | Mirar el Panel → "En vivo ahora" | Badge **EN VIVO**, etiqueta de estado (Emparejada / Sin contenido) y **v3.3.0** |
| 5 | Publicar una playlist con 3-4 fotos | La barra muestra **Sincronizando N %** con archivos reales, no salta a 100 |
| 6 | Esperar a que termine | Estado pasa a **Reproduciendo** y la barra desaparece |
| 7 | Cambiar de contenido (publicar otra playlist) | El contenido viejo sigue en pantalla hasta que el nuevo está listo; el cambio es en ~2 s por el canal de eventos |
| 8 | Desconectar el internet del equipo | Sigue reproduciendo; estado pasa a **Sin internet · usando caché** |
| 9 | Esperar 2 min con internet caído | Panel muestra **SIN SEÑAL** y luego **OFFLINE** (más de 5 min) |
| 10 | Reconectar internet | Vuelve solo a EN VIVO y sincroniza sin tocar nada |
| 11 | Apagar el equipo de golpe (cortar corriente) y encenderlo | Arranca MediaView solo, **sin volver a pedir el código**, y reproduce el último contenido bueno |
| 12 | Cerrar la app desde Android (si el equipo lo permite) | Vuelve a abrirse (o queda como launcher si lo configuraste) |
| 13 | Revisar en el panel el estado durante todo el proceso | Nunca aparece EN VIVO si el equipo está apagado, ni un porcentaje que no avance |

Reporta modelo, versión de Android, fecha y qué pasos fallaron. **Sprint 1 no se marca como
validado en hardware hasta que completes esta tabla.**
