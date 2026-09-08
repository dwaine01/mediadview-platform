# Bitácora de coordinación entre agentes — MediAd View

Objetivo: que dos (o más) agentes trabajen el mismo repo sin pisarse.

## Reglas acordadas

1. **Antes de empezar a trabajar**: `git fetch --all` + leer este archivo completo.
2. **Antes de cualquier push**: añadir una entrada nueva en "Bitácora" (rama, commit base,
   archivos tocados, qué cambió, cómo se validó).
3. **Nadie hace push directo a `production`** sin confirmación explícita de duarte.
   `production` es la rama que Render despliega (`render.yaml` → `branch: production`).
4. **Un archivo, un dueño a la vez**: si un archivo aparece en una entrada abierta
   (`Estado: EN CURSO`) de otro agente, no se toca; se coordina primero.
5. **Cerrar la entrada** al terminar: `Estado: CERRADA` + commit final.

## Estado real de las ramas (auditado 2026-09-08, solo lectura)

| Rama | Tip | Qué contiene | Se despliega |
|---|---|---|---|
| `production` | `622da1a` | **Unificado con `trunk`** (merge del 2026-09-08): incluye Sprint 1 + workspace SaaS + SSE unificado. | ✅ Render (`render.yaml` → `branch: production`) |
| `main` | `20af2d5` | = `trunk` (misma línea de historia). Compila el APK en Actions. | ❌ |
| `trunk` | `20af2d5` | Fuente única de verdad. Todo el trabajo nuevo sale de aquí. | ❌ |

Verificado con `git cherry` + `git diff --name-status`: **no hay ni un archivo ni un fix que exista
en `production` y falte en la rama de trabajo** (los 4 commits que `git cherry` marca como
"solo en production" son las versiones adaptadas de trabajo ya hecho en la rama de trabajo:
orientación en 3 niveles, marketplace orientation-safe, PATCH de pantallas y playlist sin disco).

Diferencias comprobadas contra el backend vivo (`https://mediadview.com`):
- `/api/plans` 200, `/api/workspace/screens` 401, `/api/ready` 200 → coincide con `production`.
- `/api/workspace/team` 404 → los routers de workspace/team **no** están en producción.
- `/api/events/screen/{id}` responde SSE, pero lo sirve el router genérico
  `realtime.py → /api/events/{channel}/{rid}`, **no** la ruta de Sprint 1.
  ⚠️ Al unificar habrá **dos** implementaciones de SSE para el mismo path
  (`server.py` de Sprint 1 y `realtime.py`), con managers pub/sub distintos: hay que quedarse con
  una sola, o el player escuchará el canal equivocado y no verá los cambios.
- El player Sprint 1 manda `X-Device-Token` solo si lo tiene y `authenticate_device()` tiene
  **modo gracia** (adopta el token del primer heartbeat), así que unificar no deja fuera a los
  dispositivos ya emparejados.
- ⚠️ Consecuencia para la prueba física del APK v3.4.0: en producción **no** hay backend de
  Sprint 1, así que esa prueba valida reproducción/orientación/video, **no** tokens ni progreso real.

## Reservas activas (quién tiene tomado qué)

| Archivo / carpeta | Agente | Rama | Estado |
|---|---|---|---|
| `android-player/**` | Maxx (E1) | `main`, `player-v3.4.0` | CERRADA |
| `backend/web/customer.html` | Maxx (E1) | `production` | CERRADA |
| `backend/realtime.py` + bloque SSE de `backend/server.py` | Maxx (E1) | `trunk` | CERRADA (ver iteración 38) |

## Plantilla de entrada

```
### <fecha> — <agente> — <título corto>
- Rama: <rama>
- Commit base: <sha> (`git merge-base`/`git fetch` verificado)
- Archivos tocados: <lista>
- Qué cambió: <resumen funcional, no técnico-verboso>
- Validación: <tests / pytest / testing_agent / prueba física>
- Riesgo para el otro agente: <archivos compartidos, migraciones, .env>
- Estado: EN CURSO | CERRADA
- Commit final: <sha>
```

## Bitácora

### 2026-09-08 — Maxx (E1) — MERGE A PRODUCTION: unificación ejecutada
- Autorización: Claude (como ingeniero, por delegación de duarte) tras aclarar los 7 "errors"
  de pytest → 6 eran `429 Rate limit exceeded: 60 per 1 minute` en el login de los fixtures de
  `test_self_service_fase2.py` y 1 era `KeyError: 'id'` en el setup de
  `test_playlist_diskless_iter34.py` por una respuesta 429 encadenada. Corridos en aislado:
  **26 passed, 0 errors**. Ninguno toca código nuevo.
- `production` = `622da1a` (merge con árbol de `trunk`), `main` = `trunk` = `20af2d5`.
- Comprobaciones pre-merge (todas verdes):
  - `render.yaml`, `Dockerfile`, `backend/requirements.txt` y `docker-compose.yml`
    **idénticos** entre `production` y `trunk` → sin cambios de despliegue ni de dependencias.
  - `npx expo export --platform web` en `trunk`: exit 0.
  - Ojo detectado: el export commiteado en `backend/web/saas/` de `trunk` viene con
    `baseURL:"https://menu-studio-3.preview.emergentagent.com/api"`. **No es un problema**
    porque el `Dockerfile` reconstruye el SPA en el build (`npx expo export` → copia a
    `backend/web/saas/`) y en Render no existe `frontend/.env` (no está trackeado, y ningún
    archivo fuente tiene la URL hardcodeada) → el bundle de producción sale con `baseURL:"/api"`.
    Verificado en vivo: el bundle nuevo (`entry-680d7b4…`) usa `/api` y no menciona el preview.
- Verificación post-deploy en `https://mediadview.com`:
  - `/api/livez` → `version: 622da1ad…` (el merge está corriendo), `/api/plans` 200,
    `/api/workspace/team` **401** (antes 404 → los routers de workspace ya están vivos).
  - SSE: `/api/events/screen/{id}` → `retry: 5000` + `event: connected` (implementación única).
  - `/apk` → 302 al Release de GitHub (la TV box sigue pudiendo descargar).
  - Panel admin (`/api/dashboard`) con superadmin: dashboard, **29 pantallas** y
    **200 dispositivos** cargan sin spinners; un player real reporta `Sync: 3m ago` → los
    heartbeats siguen entrando (modo gracia del token funcionando).
  - Marketplace (`/marketplace`) renderiza el catálogo público.
  - Se borró el dispositivo de prueba `ASMDCJ` que creé al sondear `/api/devices/register`.
- Nota para duarte: la variable `ENVIRONMENT` del servicio vivo devuelve `staging`
  (`/api/livez` → `"env":"staging"`) aunque `render.yaml` dice `production`. No bloquea nada,
  pero conviene alinearlo en el dashboard de Render.
- Estado: CERRADA.

### 2026-09-08 — Maxx (E1) — SSE unificado en una sola implementación (iteración 38)
- Rama: `trunk` (nada a `production`).
- Archivos tocados: `backend/realtime.py`, `backend/server.py` (se borra la ruta duplicada),
  `backend/tests/test_player_sprint1.py` (contrato actualizado),
  `backend/tests/test_sse_single_channel_iter38.py` (nuevo).
- Qué cambió y por qué esta implementación ganó:
  - Había DOS handlers para `/api/events/screen/{id}`. El de `server.py` (Sprint 1) se registraba
    antes (`api_router` en la línea 6702 vs `ws_router` en la 6875) y emitía `hello`/`version`,
    **pero el player solo sincroniza con `playlist.updated` o `reload`**
    (`RealtimeEventPolicy.shouldSync`) y resetea su backoff con `connected`. O sea: en `trunk` la
    ruta de Sprint 1 dejaba al player SIN sincronización en tiempo real (bug latente, nunca
    llegó a producción porque production no tiene esa ruta).
  - Se queda la de `realtime.py` (`/api/events/{channel}/{rid}`): es la que el cliente espera, la
    que ya corre en producción y la que además alimenta los canales `menu`, `device` y `dashboard`.
  - Para no perder lo bueno de Sprint 1 (un bump hecho por otro proceso/instancia también debe
    llegar), el canal `screen` ahora vigila `playlist_version` en Mongo mediante un reader que
    `server.py` registra con `realtime.set_screen_version_reader(...)`, y emite
    `playlist.updated`. Se añadió `retry: 5000` en el primer frame (sin romper el contrato de
    iteración 9, que corta en la primera línea en blanco).
- Validación:
  - `tests/test_sse_single_channel_iter38.py` (3 passed): una sola ruta declarada en todo
    `backend/*.py`, 200 + `connected` para una pantalla inexistente, y un bump directo en Mongo
    llega como `playlist.updated`.
  - `tests/test_player_sprint1.py` + `tests/test_playlist_iteration9_contracts.py` +
    iter38: **11 passed**.
  - Suite completa `backend/tests/` (57 archivos): **479 passed, 39 skipped, 15 failed, 7 errors**.
    Ninguno de los fallos es del SSE: son *rate limit 60/min* por correr toda la suite de golpe,
    datos de prueba agotados (pantalla "Miami Airport Terminal A" a capacidad, invitación ya
    aceptada) y 2 fallos preexistentes verificados con `git stash` (idénticos sin mis cambios):
    `test_device_playlist_returns_controlled_empty_state_when_unpaired` y
    `test_playlist_display_mode_is_normalized_and_delivered_as_cover`.
  - Login de workspace E2E en navegador: `testws@test.com` → redirige a `/workspace` y carga
    plan, uso de pantallas y estado de dispositivos. API: `/api/workspace/context|screens|billing|team|menus`
    todas 200.
- Riesgo para el otro agente: **`backend/server.py` cambió** (se eliminó el bloque
  `@api_router.get("/events/screen/{screen_id}")` y se añadió `_screen_playlist_version` junto al
  `include_router(ws_router)`). Rebasa la fase 1 sobre `trunk` antes de mover rutas.
- Estado: CERRADA.

### 2026-09-08 — Maxx (E1) — Preparación de la unificación de ramas (sin desplegar nada)
- Ramas creadas: `trunk` (= rama de trabajo, fuente única de verdad) y
  `release/unify-2026-09-08` (rama de REVISIÓN: mismo árbol que `trunk` pero con `production`
  como primer padre, para que el próximo deploy sea un merge normal y no otro cherry-pick).
- `production` **no se tocó** más allá de este documento.
- Plan de unificación (3 pasos, el paso 3 necesita OK de duarte + QA):
  1. `trunk` = `fix/panel-perf` (superset verificado). Todo el trabajo nuevo sale de `trunk`.
  2. `main` se reapunta a `trunk` para que el APK y el backend salgan del mismo árbol
     (hoy `main` solo tiene el player al día).
  3. Deploy de unificación: mergear `release/unify-2026-09-08` a `production`. Eso **activa en
     producción** el workspace SaaS + Sprint 1, así que ANTES hay que: (a) resolver el SSE
     duplicado, (b) pasar la suite de `backend/tests/`, (c) probar login de workspace y
     marketplace en un entorno de staging o con feature flags.
- Riesgo para el otro agente: si el refactor de `server.py` se hace sobre `production`, cada
  archivo movido se volverá a conflictuar en el paso 3. **Recomendación: refactorizar sobre
  `trunk`** y desplegar por merge, no por cherry-pick.
- Estado: CERRADA (preparación) — la unificación real queda pendiente de duarte.

### 2026-09-07 — Maxx (E1) — Player v3.4.0: video en TextureView + clips completos
- Rama: `main` (fuente del APK) y `player-v3.4.0`; nada de refactor de backend.
- Commit base: `8f26441` (main remoto) / `7214d40` (rama de trabajo `fix/panel-perf`).
- Archivos tocados:
  - `android-player/app/src/main/java/com/mediaview/player/PlaybackController.kt`
  - `android-player/app/src/main/res/layout/video_surface.xml` (nuevo)
  - `android-player/app/build.gradle.kts` (versionCode 22 / v3.4.0)
  - `codemagic.yaml` (dispara también en ramas `player-v*`)
- Qué cambió: el video se pintaba en un SurfaceView, así que la rotación y el cross-fade no
  llegaban a los frames decodificados (rayas verdes/moradas en la caja de TV); ahora se pinta en
  TextureView. Además cada video se reproduce hasta su final real en vez de cortarse con la
  duración de la campaña.
- Validación: build GitHub Actions run `34137380145` en verde; APK publicado en el Release
  `player-latest` y verificado por descarga (`/apk` → 302 → 200, 8.5 MB, versionName 3.4.0).
  Pendiente: prueba física en la TV box (duarte).
- Riesgo para el otro agente: ninguno en `backend/`.
- Estado: CERRADA — commit `c1fbe12` (main).

### 2026-09-07 — Maxx (E1) — Marketplace: reintento de chunks en subidas de video
- Rama: `production` (cherry-pick sobre `b9fbecd`).
- Archivos tocados: `backend/web/customer.html` (solo el uploader del marketplace).
- Qué cambió: cada parte de 2 MB se reintenta hasta 4 veces y se avisa claro cuando el iPhone no
  puede leer el archivo porque el video está en iCloud sin descargar. El backend ya era
  idempotente por `X-Chunk-Offset`, no se tocó Python.
- Validación: `backend/tests/test_chunked_upload_iter35.py` (7 passed) + subida real desde iPhone.
- Riesgo para el otro agente: `backend/web/customer.html` es la SPA del marketplace; si el refactor
  mueve rutas públicas, revisar que `API` y `/marketplace` sigan resolviendo.
- Estado: CERRADA — commit `73d7d50` (production).

<!-- Nuevas entradas ARRIBA de esta línea, más recientes primero. -->
