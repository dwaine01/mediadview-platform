# MediaView / MediAd View — PRD

SaaS de digital signage. Backend FastAPI + MongoDB Atlas, frontend Vanilla HTML/CSS/JS, Android Player nativo Kotlin, CI/CD Codemagic, deploy Render.

## Objetivos de la sesión
- Estabilizar el código de emparejamiento del Player Android (bug crítico reportado por usuario).
- Fix visual: fuente grande que corta el código de 6 chars, orientación bloqueada a landscape.

## Bug arreglado en esta sesión (P0)
### Emparejamiento inestable + "código ya usado"
- **Root cause 1 (backend)**: `POST /api/devices/register` creaba SIEMPRE un registro nuevo con código nuevo → cada relanzamiento/rotación del Player generaba un código distinto y dejaba pendientes acumulados.
- **Root cause 2 (Android)**: `PairingActivity` hacía polling contra `/api/devices/{LOCAL_UUID}/check` en vez del `device_id` que devuelve el servidor → el polling nunca encontraba el registro → nunca detectaba activación.

### Fix
- Backend: `/devices/register` ahora es **idempotente por `client_uuid`**. Devuelve el mismo `device_id` + `activation_code` en llamadas repetidas. `/devices/{id}/check` acepta ambos: server device_id y client_uuid.
- Android `PairingActivity.kt`: persiste el server device_id en SharedPreferences (`mediaview_pairing`), usa ESE id para el polling. Envía `client_uuid` en el payload. Muestra el código cacheado al inicio para que no parpadee.
- Fuente del código: 84sp → 56sp (una sola línea).
- Manifest: quitado `screenOrientation="landscape"` de PairingActivity (soporta vertical).
- Versión: 2.4.1 (versionCode 7).

## Estado
- APK compilando en Codemagic tras push a main (commit `0d2ad2d`).
- Backend redeployando en Render.

## Tareas backlog
- P1: Colorlight API Sprint 1–5 (esperando pruebas físicas usuario en A35/A40).
- P2: Cloudflare R2 para media persistente.
- P2: Stripe LIVE cutover.
- P2: D-04 (consolidado multi-moneda), D-05 (magic numbers presign worker).
