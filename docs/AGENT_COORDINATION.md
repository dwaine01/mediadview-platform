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

### 2026-09-08 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-4: /playlists/* fuera de server.py
- Fusionada a `trunk`/`main`. `production` sin tocar.
- `backend/playlists_routes.py` (nuevo, 318 líneas): 12 rutas owner/share/moderación + 4 modelos
  + 4 helpers anidados + 1 de módulo. `_public_token_hash` pasó a `media_utils.py` (96 líneas)
  porque `_public_playlist` sigue en `server.py` y también la usa.
  `server.py`: **5004 → 4762 líneas** (acumulado 7106 → 4762, −33 %).
- ⚠️ **Quité del script el `re.sub(r"\n{4,}", "\n\n\n", server_out)`** que Claude añadió como
  limpieza cosmética: ese regex actúa sobre TODO el archivo, incluidos los literales multilínea
  de HTML/JS embebido, así que podía cambiar bytes de respuestas HTTP de forma invisible. Las
  líneas en blanco de más son inocuas; los bytes de una respuesta no.
- Verificación AST: **21/21 elementos idénticos** al original de `25f061b`.
  `import server` sin excepciones (este cambio tocaba 3 archivos a la vez).
- Suite completa: **493 passed, 35 skipped, 7 failed, 7 errors** — mismo conjunto de fallos que
  2B-3, nombre por nombre. Cero regresiones.
- Estado: CERRADA.

### 2026-09-08 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-3: /screens/* fuera de server.py
- Fusionada a `trunk`/`main`. `production` sin tocar.
- `backend/screens_routes.py` (nuevo, 481 líneas): las 13 rutas (8 `/screens/*` + 5
  `/admin/screens*`) y sus 7 modelos, en `create_screens_routes(...)` con 10 dependencias
  threadeadas. `server.py`: **5363 → 5004 líneas** (acumulado 7106 → 5004, −30 %).
- Alcance acordado antes de escribir el script: fuera `/admin/rbac/screens-by-type`,
  `/public/screens*`, `/customer/screens*` y `/playlists/{id}/available-screens`.
- `screen_orientation` **no** se threadeó: Claude verificó que ninguno de sus 7 usos cae en las
  13 rutas movidas (son de campañas, marketplace y player). Tenía razón y mi sugerencia de
  pasarla por defensa habría metido un parámetro muerto. Viajará con la fase que la use.
- Claude encontró con `flake8 F821` **8 dependencias compartidas** que ni él ni yo habíamos
  visto al acordar el alcance: `CampaignSchedule`, `calculate_campaign_price`,
  `_get_unique_public_screen_code`, `get_unique_location_code`, `gen_pairing_code`,
  `gen_pairing_secret`, `gen_activation_code` y `_is_platform_admin`.
- Verificación AST: **20/20 elementos idénticos** al original de `73af1d8`.
- Orden de registro resuelto contra `app.routes`: `/api/screens/cities` → `get_cities`,
  `/api/screens/self-service/mine` → `customer_list_my_screens`, `/api/screens/abc123` →
  `get_screen`. No se invirtieron con la paramétrica.
- Cadena de orientación revalidada: `test_orientation_chain_iter34` +
  `test_marketplace_orientation_iter33` + `test_p1_saas_customer` → **39 passed**.
- Suite completa: **493 passed, 35 skipped, 7 failed, 7 errors**; `diff` contra 2B-2 **vacío**.
- Estado: CERRADA.

### 2026-09-08 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-2: /media/* fuera de server.py
- Rama de trabajo local → fusionada a `trunk`/`main`. `production` sin tocar.
- `backend/media_routes.py` (nuevo, 622 líneas) con los 13 handlers de `/media/*` en
  `create_media_routes(MEDIA_DIR, gen_id, serialize_doc)`, que devuelve
  `(router, upload_media)` porque `public_playlist_media` sigue llamando a `upload_media(...)`
  como función Python directa. `MediaUpload`, `PLAYABLE_STATUSES` y
  `MEDIA_METADATA_PROJECTION` pasaron a `media_utils.py` (87 líneas) para no crear import
  circular. `server.py`: **5853 → 5363 líneas** (−490; acumulado desde el inicio: 7106 → 5363).
- Verificación AST: **20/20 elementos movidos idénticos** al original de `7905252`
  (rutas y helpers anidados comparados tras desindentar los 4 espacios del factory; modelos y
  `_sha256_of_file` sin desindentar).
- Orden de registro, que aquí sí es crítico: el test de sombreado de 2B-1 confirma que
  `GET /api/media/serve` lo sigue resolviendo `serve_r2_media` y `GET /api/media/{id}`
  lo resuelve `get_media` — no se invirtieron.
- Probado con R2 **activado** (40 passed: chunks, miniaturas, wizard, iter29, fase4) y con R2
  **desactivado** (40 passed: inventario, chunks, wizard, marketplace, fase4). Los dos caminos.
- Añadí a `media_routes.py` la cabecera `# ruff: noqa` de `server.py`, igual que en 2B-1.
- Suite completa: **493 passed, 35 skipped, 7 failed, 7 errors** y el `diff` del conjunto de
  fallos contra 2B-1 es **vacío: cero regresiones**.
- Estado: CERRADA.

### 2026-09-08 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-1: /menus/* fuera de server.py
- Rama: `refactor/fase2b1-menus` → fusionada a `trunk`/`main`. `production` sin tocar.
- `backend/menus_routes.py` (nuevo, 1100 líneas) con los 15 handlers de `/menus/*` en
  `create_menus_routes(gen_id, serialize_doc, _is_platform_admin, _can_view_playlist,
  _bump_playlist_screens, _esc)` + `_safe_src` y `_notify_menu_change`.
  `server.py`: **6873 → 5853 líneas** (−1020).
- Verificación de relocalización pura, con AST: las **17 funciones movidas son idénticas** a las
  de `bafd87a` (`ast.get_source_segment` comparado tras desindentar los 4 espacios del factory;
  `_safe_src` idéntico sin desindentar porque queda a nivel de módulo).
- Orden de registro comprobado: el router de menús queda en la línea 5440, `api_router` en 5581 y
  el catch-all del SPA en 5844. Además **ninguna ruta de `api_router` empieza por un parámetro**
  (`@api_router.get("/{...")` → 0 resultados), así que nada puede sombrear `/menus/*`.
  En vivo: `GET /api/menus` → 401 (auth intacta) y `GET /api/menus/{id}/render` → 200, 13 KB.
- ⚠️ **Hueco encontrado en la red de seguridad**: el snapshot está ordenado por path, así que
  **no detecta cambios de orden de registro** — justo el fallo que rompería `/media/serve` (si
  `/media/{media_id}` se registrara antes) o `/apk` (si cayera detrás del catch-all del SPA).
  Añadí `test_shadowing_sensitive_paths_resolve_to_the_right_handler`, que resuelve 9 rutas
  reales contra `app.routes` y exige el handler concreto (`serve_r2_media`, `sse_endpoint`,
  `render_menu`, `apk_short_url`, `_marketplace`, `expo_spa_catchall`, …).
- Añadida a `menus_routes.py` la misma cabecera `# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001`
  que ya tenía `server.py`: sin ella el estilo original del código movido rompía el lint.
- Resultados: `py_compile` limpio, `flake8 --select=F821` → **0**, `ruff` limpio,
  inventario de rutas **2 passed**, suite completa **492 passed, 35 skipped, 7 failed, 7 errors**
  — `diff` del conjunto de fallos contra la corrida de 2A: **idéntico, cero regresiones**.
- Sobre la indentación del f-string de `render_menu` que avisó Claude: el HTML sale con 4 espacios
  extra por línea dentro de los 3 bloques multilínea. Ningún test compara líneas exactas
  (`test_menu_theme_colors_persist_and_render` falla por el 404 de borrador de la regla H3, el
  mismo motivo preexistente que ya estaba en 2A). Para las próximas extracciones sugiero mover
  los bloques HTML/JS grandes a constantes a nivel de módulo, así el cuerpo de la respuesta
  queda byte-idéntico.
- Estado: CERRADA.

### 2026-09-08 — Claude (código) + Maxx (verificación) — Fase 2A: red de seguridad y helpers compartidos
- Rama: `refactor/fase2a-deps` → fusionada a `trunk`/`main`. `production` sin tocar.
- Archivos nuevos: `backend/database.py` (dueño del cliente Mongo, evita el import circular),
  `backend/deps.py` (`get_current_user`, `require_admin`, `require_superadmin`),
  `backend/media_utils.py` (`media_orientation`, `_media_has_inline_bytes`,
  `bump_playlist_version`), `backend/tests/test_route_inventory.py` +
  `backend/tests/route_inventory_snapshot.json`.
  `server.py`: **6923 → 6873 líneas**.
- Verificación de que es relocalización pura, hecha con AST y no a ojo: los 6 helpers tienen el
  **cuerpo idénticamente igual** al de `server.py` (`ast.dump` del body sin docstring) y los
  docstrings son byte a byte iguales. Correcciones al texto que llegó por chat: el guion largo
  de `"Session revoked — please login again"`, el `logging...warning` del fallback de
  `JWT_SECRET` y el docstring completo de `_media_has_inline_bytes`.
- ⚠️ **No regeneré el snapshot después del cambio** (Claude lo pedía en el paso final). El
  snapshot se generó ANTES de tocar `server.py` y el test pasa DESPUÉS sin regenerarlo: eso es
  lo que demuestra que no hubo deriva de rutas. Regenerarlo al final habría convertido la red
  de seguridad en un sello de goma.
- Hallazgo del inventario, antes de mover nada: **5 rutas están registradas dos veces**, así que
  la segunda registración es código muerto (FastAPI resuelve la primera):
  `GET /api/health` (la inline de `server.py` gana y por eso `/api/health` no devuelve el formato
  de `health.py` con `env`/`version`), y las 4 de finanzas
  (`contracts/{id}/pdf`, `contracts/{id}/sign`, `deposits/{id}/pdf`, `invoices/{id}/pdf`).
  No las toco: no es relocalización, es limpieza con posible cambio de comportamiento.
  **Queda para fase 3**, decidiendo primero cuál de las dos implementaciones de finanzas es la buena.
- Resultados: `py_compile` limpio en los 5 archivos, `ruff` limpio, inventario de rutas
  **492 rutas, 1 passed**, y suite completa **492 passed, 35 skipped, 7 failed, 7 errors** —
  exactamente el mismo conjunto de fallos que la corrida de la fase 1, nombre por nombre
  (4 preexistentes de player/playlist, 1 de contenido en `landing.html`, 1 de datos en
  `test_rbac_fase1` y el resto veneno de 429). **Cero fallos nuevos.**
- SSE revalidado tras mover `bump_playlist_version`: `test_sse_single_channel_iter38` +
  `test_player_sprint1` + `test_fase4_backend` → 38 passed.
- Estado: CERRADA.

### 2026-09-08 — Maxx (E1) — R2 fusionado a trunk (aprobado por Claude)
- `trunk`/`main` = `b8f4a8f`: merge `22afda0` de `feat/r2-storage` + tests conscientes del entorno.
  `production` sigue en `622da1a`.
- Inerte hasta que duarte ponga las variables en Render: `R2_ENABLED` solo es True con
  `R2_ENDPOINT` + `R2_ACCESS_KEY_ID` + `R2_SECRET_ACCESS_KEY` + `R2_BUCKET_NAME`.
- Hallazgo al probar con R2 activo: tres tests asumían "R2 sin configurar" y se rompían en
  cuanto el bucket existe — justo lo que iba a pasar en staging al poner las variables:
  `test_upload_image_falls_back_to_legacy`, `test_presign_returns_503_when_r2_unset` y
  `test_readiness_ok_in_dev` (esperaba `driver == "local"`). Ahora los tres leen `R2_ENABLED`
  del mismo módulo que el backend y exigen `r2`/200/`driver=r2` cuando está configurado.
  `/api/media/presign` además exige `duration_seconds` para video (regla de negocio existente).
- Suite completa con R2 activo: **487 passed, 35 skipped, 8 failed, 10 errors**. Los 5 fallos
  reales son los preexistentes ya documentados; los otros 3 fallos y los 10 errores son el
  veneno de 429 (aislados pasan: `test_267b0ec_ui_bugs` + `test_workspace_playlists_iter29`
  → 17 passed).

### 2026-09-08 — Claude (diff) + Maxx (aplicación) — Fase 1: páginas públicas fuera de server.py
- Rama: `refactor/server-py-fase1` (`93b8320`) → **fusionada a `trunk` y `main`** (fast-forward).
  A `production` NO: espera OK de duarte.
- Archivos: `backend/public_pages_routes.py` (nuevo) y `backend/server.py` (**7068 → 6923 líneas**).
- Qué cambia: las 16 rutas públicas sin auth ni DB (`/`, `/home`, `/about`, `/for-business` +
  alias `/api`, `/restaurants` + alias `/api`, `/sign-permit-information`, `/signup`, `/login`,
  `/portal`, `/marketplace` y los 4 alias de descarga del APK) más sus helpers pasan a un router
  propio, registrado con `app.include_router(create_public_pages_router(WEB_DIR))` en el mismo
  punto donde estaban. `/api/app-build` usa `customer_spa_build(WEB_DIR)`.
  `@api_router.get("/marketplace")` (el alias `/api/marketplace`) se queda en `server.py`.
- Validación (con R2 desactivado en el `.env` del sandbox, para comparar contra `trunk`):
  - Las 16 rutas comprobadas una por una: mismos códigos y mismos destinos. Los 4 alias de APK
    siguen dando 302 al Release; `/marketplace` sin `?v=` redirige con el hash correcto y el
    hash coincide con `/api/app-build`; `/` con `Host: panel.*` sigue sirviendo el panel
    (`app.js` presente) y sin ese Host sirve `landing.html`.
  - Suite completa: **492 passed, 34 skipped, 7 failed, 7 errors**. Ninguno toca rutas públicas:
    4 preexistentes de player/playlist, 1 preexistente de contenido
    (`test_landing_has_data_i18n_attrs` exige `data-i18n="nav.dashboard"`, atributo que **no
    existe** en `landing.html`) y el resto es el veneno de 429 que se va con el parche de `ci.yml`.
  - ⚠️ Aviso para la próxima corrida: con R2 activo en el `.env` aparecen 4 fallos FALSOS
    (`test_iter29_extra_coverage::test_media_upload_is_served_by_player`,
    `test_fase6_infra::test_readiness_ok_in_dev` y los 2 de `TestMedia`) porque esta rama no
    lleva `/api/media/serve`. R2 queda **desactivado** en el `.env` del sandbox hasta que se
    apruebe `feat/r2-storage`.
- Deuda anotada para fase 3: subir el `import public_pages_routes` al bloque de imports
  (hoy está en la línea 6472) y borrar `_latest_player_apk()`, que es código muerto.
- Estado: CERRADA.

### 2026-09-08 — Maxx (E1) — Arnés de CI verde + rama feat/r2-storage
- Ramas: `trunk`/`main` = `b397759` (arnés de pruebas). `feat/r2-storage` = `38bfee2`
  (R2, **pendiente de revisión de Claude + OK de duarte**, no fusionada).
- 🔴 **BLOQUEO: no puedo pushear `.github/workflows/ci.yml`.** El token de este entorno no
  tiene scope `workflow`: GitHub responde
  `refusing to allow a Personal Access Token to create or update workflow`.
  El cambio de `ci.yml` está listo y probado en local pero **duarte tiene que pegarlo desde la
  web de GitHub** (o darme un token con scope `workflow`). Son dos cosas:
  1. En el `env:` del job *Backend tests*, junto a `REDIS_URL: ""`, añadir:
     `RATE_LIMIT_DISABLED: "1"` y `LOCKOUT_WINDOW_MIN: "0"`.
  2. Un paso nuevo antes de *pytest (if any)* que siembra `testws@test.com` / `Test1234!` y
     `pizzeria@demo.com` / `Pizza1234!` vía `POST /api/auth/customer-signup` (acepta 201 y
     también 400/409 para poder re-ejecutar el job).
  Sin esos dos cambios el job *Backend tests* seguirá rojo aunque el código esté bien.
- Arnés (ya en `trunk`, código de producción intacto salvo el interruptor gateado):
  - `rate_limit.is_rate_limit_disabled()` solo devuelve True si `ENVIRONMENT == "test"` **y**
    `RATE_LIMIT_DISABLED` está activo → imposible apagar el rate limit de staging/production.
  - `test_fase4_backend` lee `LIMITS.login` y `LOCKOUT_MAX_FAIL` de la misma fuente que el
    backend en vez del `5` hardcodeado (en dev el login permite 60/min, así que el guardia que
    salta primero es el bloqueo por fuerza bruta, y el test lo dice explícitamente).
  - Fixtures idempotentes: invite con correo único por corrida y limpieza de las campañas
    `TEST_` que dejaban "Miami Airport Terminal A" a capacidad máxima.
  - Resultados locales: `test_fase4_backend` 20 passed, `test_self_service_fase2` 27 passed,
    `test_fase3_advertising` 12 passed, `test_phase2c_1a` 77 passed.
- Estado: CERRADA salvo el bloqueo de `ci.yml` (acción de duarte).

### 2026-09-08 — Maxx (E1) — R2 (fase 2): videos a Cloudflare R2 · EN REVISIÓN
- Rama: `feat/r2-storage` (`38bfee2`), partiendo de `trunk`. **No fusionada.**
- Credenciales R2 recibidas de duarte y verificadas contra el bucket `mediaview-media`
  (put/get/list/delete OK). Están solo en `backend/.env` local (no trackeado) — **faltan en
  Render**: `R2_ACCOUNT_ID`, `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
  `R2_BUCKET_NAME`, `R2_REGION=auto` en el env group `mediadview-secrets`.
- Qué cambia:
  - `complete_chunked_upload` (la ruta de los videos) sube el archivo ensamblado a R2 en
    streaming; sin R2 configurado sigue el camino de disco de siempre.
  - Nuevo `GET /api/media/serve?key=...` que hace streaming desde R2 mientras el bucket no
    tenga dominio público. Declarado ANTES de `/media/{media_id}` (esa ruta se lo comía y
    devolvía "Media not found"), y solo sirve claves registradas en `db.media`.
  - **Fallback pedido por Claude**: si el objeto no está en R2 todavía, se sirve la copia
    local/base64 en vez de 404. Verificado a mano con un media de `r2_key` inexistente +
    copia en disco → 200 con los bytes correctos.
- Tests (reales, en el sandbox, con R2 activo):
  - chunks + miniaturas: `test_chunked_upload_iter35` + `test_admin_video_thumbnail_iter36`
    → **12 passed, 1 skipped**. Los videos quedan en Mongo con `storage: "r2"` y se
    recuperan byte a byte desde el bucket.
  - media/playlist/orientación: `test_media_upload_wizard_flow`, `test_playlist_diskless_iter34`,
    `test_playlist_iteration9_contracts`, `test_orientation_chain_iter34`,
    `test_marketplace_orientation_iter33` → **24 passed, 1 skipped**.
  - player/playlists: **18 passed, 4 failed**. Los 4 son PREEXISTENTES: los mismos 4 fallan
    con `git stash` de mis cambios (`test_playlist_professional_platform` ×2,
    `test_p0_player_diagnostics_playlist_contract`, `test_player_backend_contracts_2026`).
- Pendiente antes de fusionar: revisión de Claude (diff/tree), OK de duarte, variables en
  Render y `python -m scripts.migrate_media_to_r2 --dry-run` contra la base de producción
  (yo no tengo el MONGO_URL de producción).
- Estado: EN CURSO (esperando revisión).

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
    `baseURL:"https://sprint1-signage.preview.emergentagent.com/api"`. **No es un problema**
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
