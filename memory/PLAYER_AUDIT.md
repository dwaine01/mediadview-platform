# MediaView Player — Auditoría técnica (antes de implementar)

Fecha: junio 2026 · Auditor: agente E1 · Objetivo: convertir el reproductor en un
player de digital signage profesional y desatendido, SIN reescribir lo que ya funciona.

## 1. Qué existe hoy (3 aplicaciones distintas, no una)

| Pieza | Tecnología | Dónde | Para qué |
|---|---|---|---|
| App de gestión | Expo / React Native 0.81 + expo-router | `/app/frontend` | La que descargan las personas (iOS + Android + Web) para manejar el software |
| Reproductor de TV | **Android nativo Kotlin** v3.2.0 (versionCode 17), ExoPlayer + Coil + Room + WorkManager, 24 archivos / ~2.850 líneas | `/app/android-player` | El APK que se instala en la TV / caja Android |
| Canal Roku | BrightScript (manifest + components + source) | `/app/roku-channel` | Reproductor para Roku (iniciado, sin auditar en profundidad) |
| Backend | FastAPI + MongoDB | `/app/backend` | Pairing, contenido, heartbeat, update de APK |
| CI de APK | `codemagic.yaml` (assemble release + diagnostic) | raíz | Compila el APK; **no se compila dentro de este entorno** |

Conclusión importante: el reproductor **no** es la app Expo. Son dos binarios con
ciclos de vida separados. La app Expo se publica a App Store / Play Store para
gestionar; el APK del player se instala en la TV.

## 2. Lo que YA FUNCIONA (no rehacer)

1. **Pairing de 6 dígitos idempotente** — `POST /api/devices/register` devuelve el
   mismo `device_id` y código para el mismo `client_uuid` (sobrevive relanzamientos y reinicios).
   UI nativa en `PairingActivity.kt` (600 líneas).
2. **Identidad persistente** — `DeviceIdentity.kt` guarda device_id / screen_id localmente;
   el pairing sobrevive reinicios.
3. **Auto-arranque** — `BOOT_COMPLETED`, `QUICKBOOT_POWERON`, `REBOOT`,
   `MY_PACKAGE_REPLACED` (prioridad 1000) + `BootWorker` + categoría `HOME`
   (puede ser launcher por defecto) + solicitud de `ROLE_HOME` (`KioskSetup.kt`).
4. **Pantalla completa tipo kiosco (parcial)** — `lockTaskMode="if_whitelisted"`,
   `keepScreenOn`, `singleTask`, tema sin barra, leanback launcher para Android TV.
5. **Heartbeat con telemetría real** — `HeartbeatWorker.kt` + heartbeat desde
   `MainActivity` → `POST /api/devices/{id}/heartbeat`: uptime, almacenamiento libre,
   memoria, IP, versión de app, resolución, orientación, último sync, playlist e ítem
   actual, último error. El backend guarda `last_heartbeat` + `diagnostics.*`.
6. **Descargas con integridad y cambio atómico** — `.tmp` + verificación SHA/tamaño
   (`FileIntegrity.kt`), swap atómico, la playlist anterior sigue si la nueva falla.
7. **Caché offline** — Room (`PlayerDatabase.kt`) guarda la última playlist válida;
   sin internet sigue reproduciendo.
8. **Auto-update de APK** — `GET /api/devices/{id}/update-check` + `AutoUpdater.kt` +
   FileProvider + `GET /apk` (descarga directa). Requiere `REQUEST_INSTALL_PACKAGES`.
9. **Comandos básicos** — el backend deja `pending_command` y el heartbeat lo entrega:
   `reload`, `clear_cache`, `restart`, `show/hide_diagnostics`.
10. **Panel** — “En vivo ahora”, diagnósticos por dispositivo, versión de playlist
    (`GET /api/player/{screen_id}/version`).

## 3. PARCIAL / con deuda (arreglos concretos)

| # | Hallazgo | Impacto | Clasificación |
|---|---|---|---|
| P-1 | **SSE inexistente**: el player abre `GET /api/events/screen/{id}` (`PlayerEventStream.kt`) y ese endpoint **no existe** en el backend → falla siempre y cae al polling de 15 s | Cambios de contenido tardan hasta 15 s; conexiones fallidas constantes | Backend |
| P-2 | **Sin máquina de estados formal**: los estados son implícitos (`PlayerDiagnostics`); el backend solo recibe `status: online` | El panel no puede mostrar SYNCING / VALIDATING / DEGRADED reales | Player + Backend |
| P-3 | **Progreso de descarga no se reporta**: es real en el dispositivo, pero no viaja al servidor | El panel no puede mostrar “Sincronizando 62 %” | Player + Backend |
| P-4 | **Comandos sin contrato**: un solo `pending_command`, sin ID, sin ACK, sin estado ni registro | “Enviado” se confunde con “ejecutado” | Player + Backend |
| P-5 | **Sin historial de heartbeat** (solo `last_heartbeat`) | No se puede calcular uptime 24 h / 7 d / 30 d ni “activo desde” de forma honesta | Backend |
| P-6 | **Watchdog limitado**: hay recuperación de renderer y reintentos, pero no hay servicio en primer plano / watchdog externo ni límites y registro de recuperaciones | Congelamientos raros pueden quedar sin recuperar | Player (+ Device Owner para lo fuerte) |
| P-7 | **Seguridad: `/api/devices/*` sin autenticación** — el `device_id` es el único secreto; cualquiera que lo conozca puede enviar telemetría o pedir contenido | Suplantación de dispositivo y fuga de contenido entre clientes | Backend + Player (P0) |
| P-8 | **Sin flujo “Reemplazar reproductor”** ni control de límite de pantallas por suscripción al emparejar | Un reemplazo puede consumir una pantalla del plan | Backend + Panel |
| P-9 | **Log de actividad del dispositivo**: existe `POST /api/devices/{id}/log` pero sin UI ni retención | No hay línea de tiempo auditable por pantalla | Backend + Panel |

## 4. FALTA por completo

- **Screenshot bajo demanda** y **Live View** real (no hay MediaProjection en el APK ni endpoint).
- **Manifest versionado explícito** (deseado vs aplicado) — hoy se usa versión de playlist.
- **Alertas** (pantalla caída, almacenamiento bajo, app desactualizada, error de sync).
- **Matriz de compatibilidad por hardware** y checklist de provisión de fábrica.
- **HDMI / CEC** (encender/apagar TV, estado de HDMI).
- **Reboot remoto del dispositivo.**
- **Métricas de uptime** históricas y **proof of play** consolidado.

## 5. Clasificación honesta de capacidades (lo que Android permite)

| Capacidad | Clasificación | Nota |
|---|---|---|
| Auto-arranque tras encendido | **APK** (mejor con launcher por defecto) | Ya implementado; algunos OEM lo bloquean si no es HOME |
| Kiosco real (sin salir a Android) | **DEVICE OWNER** | Con APK normal solo es “fullscreen + volver a abrir” |
| Reiniciar la app | **APK** | Ya soportado |
| Reiniciar el dispositivo | **DEVICE OWNER / root** | No prometible con APK normal |
| Update silencioso del APK | **DEVICE OWNER** (o system app) | Hoy: update con diálogo de instalación (APK) |
| Screenshot desatendido | **DEVICE OWNER / system app / root** | MediaProjection en APK normal pide consentimiento en pantalla cada sesión |
| Live View de baja latencia | **DEVICE OWNER + infraestructura** | Coste alto de CPU/banda; evaluar en V2 |
| Estado de HDMI / CEC | **OEM / firmware** | Depende del fabricante |
| Watchdog fuerte | **DEVICE OWNER / OEM** | Con APK: servicio en primer plano + WorkManager |
| Heartbeat, estados, progreso, comandos, diagnóstico, alertas | **BACKEND + APK** | Todo esto sí es 100 % alcanzable ahora |

### Sobre iPhone / iPad / Apple TV
- **Gestionar el software**: sí, la app Expo sale para **iOS y Android** (se publica con el
  botón Publish → builds). Ahí caben pairing, promo, menús, reportes, live view, comandos.
- **Reproducir en la TV**: iOS/tvOS **no** permite señalización desatendida sin MDM
  (sin auto-arranque tras corte de luz, sin kiosco, sin update silencioso). Para TV la vía
  profesional es: **Android APK** (lo que ya tenemos), **Roku** (canal ya iniciado) o el
  navegador de la Smart TV con `/player/{screen}/web`. No voy a prometer un player iOS
  desatendido porque Apple no lo permite.

### Límite de este entorno
El APK se compila en CI (`codemagic.yaml`), **no aquí**. Yo puedo escribir el código Kotlin,
el backend y el panel, y probar backend + panel de forma automatizada; la validación en
hardware real (encendido, corte de luz, 24 h de soak) la tienes que ejecutar tú con el APK
compilado. Eso lo reportaré siempre como “pendiente de prueba en dispositivo real”.

## 6. Secuencia V1 recomendada (por fiabilidad, no por vistosidad)

**Sprint 1 — Cimientos honestos (P0)**
1. `device_token` emitido en el pairing y exigido en `/api/devices/*` (cierra P-7, compatible hacia atrás).
2. Máquina de estados formal en el player (BOOTING…PLAYING…DEGRADED) y `state` normalizado en el heartbeat (P-2).
3. Progreso de sync real reportado al backend con anti-flood (P-3).
4. Arreglar el canal de eventos: implementar `GET /api/events/screen/{id}` (SSE) o quitar la llamada muerta (P-1).

**Sprint 2 — Control y trazabilidad**
5. Cola de comandos con ID, estado (QUEUED/RECEIVED/RUNNING/SUCCESS/FAILED/EXPIRED) y ACK del player (P-4).
6. Línea de tiempo por pantalla con retención/TTL + UI en el Workspace (P-9).
7. Acciones en el detalle de pantalla: Sincronizar ahora, Recargar contenido, Reiniciar app (con permisos por rol).

**Sprint 3 — Fiabilidad visible**
8. Historial agregado de heartbeat → uptime 24 h/7 d/30 d, “activo desde”, última conexión (P-5).
9. Alertas: pantalla caída, almacenamiento bajo, app desactualizada, fallo de sync (con cooldown).
10. Device Center para MediaView con filtros y paginación (sin N+1).

**Sprint 4 — Recuperación y soporte remoto**
11. Watchdog reforzado (servicio en primer plano, límites y registro de recuperaciones) (P-6).
12. Screenshot bajo demanda con la limitación de MediaProjection documentada + paquete de diagnóstico acotado.
13. Flujo “Reemplazar reproductor” y control del límite de pantallas del plan (P-8).

**Sprint 5 — Flota y hardware**
14. Matriz de compatibilidad por hardware + checklist de provisión de fábrica (Device Owner por QR/ADB).
15. Proof of play consolidado y evaluación real de Live View.

## 7. Riesgos
- Cambiar la autenticación de dispositivos puede dejar fuera a los players ya instalados
  → se implementa con periodo de gracia (token opcional primero, obligatorio después).
- SSE con muchos dispositivos consume conexiones: definir umbrales (heartbeat 30 s,
  online < 90 s, stale < 5 min, offline > 5 min) y medir antes de subir frecuencias.
- Nada de screenshots “LIVE” falsos: siempre con marca de tiempo real.
