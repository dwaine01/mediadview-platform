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

### 2026-06 — Claude (script) + Maxx (ejecución y verificación) — Fix: subida pública por token con soporte real de multipart
- Rama: `trunk`, base `9f0ddd4` (`production` sin tocar, sigue en `622da1a`).
- Archivos: `backend/public_api_routes.py` (+62/−1, un solo archivo).
- Qué cambió: `POST /api/public/playlists/{token}/media` declaraba el body como
  `data: MediaUpload`, lo que obliga a FastAPI a parsear **siempre** el cuerpo como JSON. Un POST
  `multipart/form-data` (un `<form>` clásico o una integración que no puede base64-encodear en
  cliente) reventaba con un **500 `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff`**.
  Ahora un helper nuevo, `_parse_media_upload(request)`, acepta **los dos** contratos: el JSON
  con base64 de siempre (intacto, es lo que manda `backend/web/public-playlist.html`) y
  multipart real (campo `file` + `width`/`height` opcionales), normalizando ambos al mismo
  `MediaUpload` que espera el resto del pipeline. Cualquier otro content-type → **415 limpio**.
  Cierra el «Hallazgo anotado» de la Fase 2B-8 (ex 2C-1).
- Alcance: **sólo** el endpoint público/invitado. NO se toca `/media/upload` autenticado
  (`media_routes.py`, que ya tiene su propio chunked-upload) ni `public-playlist.html`.
- ⚠️ Dos cambios de comportamiento declarados por Claude y verificados por mí:
  1. El chequeo de permiso corre ahora **antes** de leer el body: un link con
     `allow_upload=false` responde **403 siempre**, incluso con un body inválido (antes podía
     devolver 422 porque FastAPI validaba primero). Probado en vivo con multipart, con JSON roto
     y con un content-type raro: **403 en los tres casos**.
  2. `/docs` pierde el schema autogenerado de este endpoint (el body ya no es un parámetro
     pydantic). No afecta a ningún cliente real.
- Verificación:
  1. Los 4 anchors del patch matchearon `count()==1`. `py_compile` OK.
     `flake8 --select=F,E9`: 0 findings. `ruff check backend`: **All checks passed**.
  2. `test_route_inventory.py` en verde con el snapshot **sin regenerar** (md5 `698364b3…`).
  3. Suite completa: **los mismos 42 fallos de la línea base** (491 passed, 35 skipped).
  4. **9 casos probados en vivo** contra una playlist pública de prueba (`allow_upload=true`,
     `require_approval=false`):
     - multipart con un JPEG real (bytes `\xff\xd8\xff`, el caso exacto que antes daba 500) →
       **200 «Content published»**;
     - multipart con `width`/`height` → 200;
     - multipart sin campo `file` → 400; `width=abc` → 400;
     - JSON+base64 (contrato viejo) → 200, sin cambios;
     - JSON roto → 400; JSON sin `data` → 422; `text/plain` → 415; token inexistente → 404.
  5. **Integridad del archivo verificada**: el medio subido por multipart quedó con `size` 677 =
     677 del original y **sha256 idéntico** (`88555ba8…`), y PIL midió 64×48 correcto → el
     base64 intermedio no corrompe nada. Se subió a R2 igual que cualquier otro medio.
  6. La playlist y los 3 medios de prueba quedaron borrados.
- Riesgo para el otro agente: ninguno; `backend/web/public-playlist.html` sin tocar.
- Estado: **CERRADA** — en `trunk` y `main`.


### 2026-06 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-11: `/auth/*` legacy v1 → **FASE 2B CERRADA**
- Rama: `trunk`, base `b5c6238` (`production` sin tocar).
- Archivos: `backend/auth_routes.py` (nuevo, 180 líneas), `backend/server.py`
  (**2243 → 2140 líneas**; acumulado 7106 → 2140, **−69,9 %**).
- Qué se movió: las **4 rutas** legacy v1 (`register`, `login`, `get_me`, `update_profile`) +
  `verify_password` + los 3 modelos (`RegisterRequest`, `LoginRequest`, `ProfileUpdate`).
  `/api/auth/*` **v2 (`auth_v2.py`) no se toca**.
- 🔐 **Paso previo obligatorio cumplido**: antes de tocar `/auth/*` se consultó al
  `integration_expert` (regla propia). Los riesgos que señaló y cómo quedaron cubiertos:
  - *Identidad del limiter*: verificado en runtime que `auth_routes._rl is rate_limit.limiter`
    y `auth_routes._LIMITS is rate_limit.LIMITS` → **el mismo objeto**, no una segunda
    instancia con contadores propios.
  - *Orden de decoradores*: `@router.post(...)` sigue **encima** de `@_rl.limit(...)`
    (verificado por inspección del código generado).
  - *`Request`/`Response` explícitos*: se conservan tal cual en las firmas.
  - *`hash_password`*: **se queda en `server.py`** por el `from server import hash_password`
    local de `finance.py` y `superadmin_routes.py` — comprobado que ambos módulos siguen
    importándolo sin error tras la extracción.
  - *Doble registro / prefijo duplicado*: la tabla de rutas de la app es **idéntica** (ver
    abajo), 0 rutas nuevas y 0 duplicadas.
  - *Imports locales de `auth_v2`* (`audit`, `_ip`, `is_locked_out`, `record_attempt`): sin
    tocar, siguen dentro de `register()`/`login()`.
  - *bcrypt / secreto JWT*: sin cambios de dependencia ni de `.env`.
- Limpieza cosmética empaquetada: el import muerto de `_rl`/`_LIMITS` y el de `_audit` en
  `server.py` (ambos quedaron sin un solo uso tras mover `register`/`login`, comprobado con
  regex de palabra completa antes de borrarlos). `_install_rl` (instalación del limiter) no se
  toca.
- Verificación:
  1. Los asserts del script pasaron a la primera; round-trip byte a byte de las 4 rutas OK.
  2. `verify_relocation.py` con snapshot del `server.py` previo: **8/8 idénticas byte a byte**
     (no apareció el defecto de docstring multilínea porque aquí todos son de una línea).
  3. `py_compile` OK. `flake8 --select=F,E9` en `auth_routes.py`: **0 avisos, archivo 100 %
     limpio**. `server.py`: 0 F821/E999. `ruff check backend`: **All checks passed**.
  4. **Tabla de rutas de la app idéntica**: 489 entradas antes y después, `diff` vacío.
     `api_router` en `server.py` **27 → 23 (−4)**, +4 en `auth_routes.py`.
  5. `test_route_inventory.py` en verde con el snapshot **sin regenerar** (md5 `698364b3…`).
  6. Suite completa: **los mismos 42 fallos de la línea base** (491 passed, 35 skipped).
  7. **Superficie de auth probada en vivo end-to-end** (más a fondo de lo habitual, por ser
     auth): registro 200 con token válido y `rbac_role: SELF_SERVICE_OWNER` (o sea el import de
     `Role` quedó bien) → registro duplicado 400 genérico sin filtrar existencia → login 200 →
     `/auth/me` 200 con el usuario correcto → `/auth/me` sin token 401 → `PUT /auth/profile`
     200 y `/auth/me` reflejando nombre/teléfono/idioma nuevos → 5 claves malas = 401 y a la
     **6.ª el lockout de `auth_v2` responde 429** «Too many attempts. Try again in 15 minutes»
     (incluso con la clave correcta, tal como antes) → **rate limit de slowapi verificado
     aparte**: 20 registros duplicados dan 400 y del 20.º en adelante **429**, o sea el
     contador compartido funciona. El usuario de prueba y los `login_attempts` quedaron
     borrados.
- 🏁 **Fase 2B CERRADA**: no queda ninguna ruta de lógica de negocio en `server.py`. Sólo las
  ~20+2 páginas estáticas/SPA que se decidió dejar ahí para siempre.
- Riesgo para el otro agente: ninguno en `android-player/**` ni en `backend/web/**`.
- Estado: **CERRADA** — en `trunk` y `main`.


### 2026-06 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-10: `/payments*`, `/widgets/*`, `/certification/*`
- Rama: `trunk`, base `b964413` (`production` sin tocar).
- Archivos: `backend/payments_routes.py` (nuevo, 102 líneas), `backend/widgets_routes.py`
  (nuevo, 251), `backend/certification_routes.py` (nuevo, 78), `backend/server.py`
  (**2501 → 2243 líneas**; acumulado 7106 → 2243, **−68,4 %**),
  `backend/public_api_routes.py` (4 líneas de docstring resangradas, cosmético).
- Qué se movió: las **7 rutas** del paquete «varios» — 3 `/payments*`
  (`create_payment`/`list_payments`/`get_payment` + modelo `PaymentCreate`), 2
  `/widgets/{id}/render|weather` (+ `_safe_iframe`, `_safe_css_color`, `_safe_js_str`,
  `_safe_yt_id`, `_weather_cache`, `_WEATHER_CACHE_TTL_S`) y 2 `/certification/*`
  (+ modelo `CertificationResult`). Un factory por dominio, **tres archivos separados**, no un
  cajón de sastre. Se threadean `gen_id`, `gen_invoice`, `serialize_doc` y `_esc` (siguen en
  `server.py` porque los comparte código que no se mueve). `widgets_routes.py` usa su propio
  `logging.getLogger(__name__)` en lugar de recibir el `logger` de `server.py`.
- 📌 **Cambio de alcance (decisión de Claude)**: las 2 `/screen*` (`serve_screen_public`,
  `serve_screen_public_legacy`) **NO se extraen**: son `FileResponse(WEB_DIR/....html)` de una
  línea, estructuralmente idénticas a las ~20 páginas estáticas/SPA que ya se decidió (tres
  veces) dejar en `server.py` para siempre. Reclasificadas a ese bucket.
- Limpieza cosmética empaquetada en el mismo script (riesgo cero, no toca CI):
  `typing.List` muerto en `server.py` desde 2B-9 → fuera; `import json` muerto con esta fase
  (su único llamador, `_safe_js_str`, se mudó) → fuera; y las 4 líneas de docstring mal
  resangradas de `public_api_routes.py` (defecto de `reindent()`, líneas 89-90 y 99-100).
- Verificación:
  1. Los 13 asserts de sanidad del script pasaron; round-trip byte a byte de las 7 rutas OK.
  2. `verify_relocation.py` con snapshot del `server.py` previo: **12/13 idénticas byte a
     byte**. La única distinta, `widget_weather_proxy`, con diff unificado que muestra
     exactamente los 2 fixes documentados (3 líneas de docstring resangradas + 1 línea en
     blanco entre `import time` e `import httpx`) y nada más.
  3. `py_compile` OK en los 5 archivos. `flake8 --select=F`: **0 F821/E999** en los 3 nuevos;
     en `server.py` sólo los F401/F811/F841 preexistentes. `ruff check backend`:
     **All checks passed**.
  4. Conteo de rutas por AST: `api_router` en `server.py` **34 → 27 (−7)**, +7 en los 3
     archivos nuevos (3+2+2).
  5. `test_route_inventory.py` en verde con el snapshot **sin regenerar** (md5 `698364b3…`,
     idéntico al de 2B-9).
  6. Suite completa: **22 failed + 20 errors = los mismos 42 fallos de la línea base**, 0
     regresiones (491 passed, 35 skipped).
  7. Prueba en vivo tras reiniciar el backend: `/api/widgets/{id}/render` y
     `/api/widgets/{id}/weather` → 404 de dominio con id inexistente,
     `/api/certification/results` → 200, `/api/payments` sin token → 401, `/api/health` → 200.
- Riesgo para el otro agente: ninguno en `android-player/**` ni en `backend/web/**`.
- Estado: **CERRADA** — en `trunk` y `main`.


### 2026-06 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-9: `/customer/*`
- Rama: `trunk` (commit `f103359`), base `92127f7`. `production` sin tocar.
- Archivos: `backend/customer_routes.py` (nuevo, 254 líneas), `backend/server.py`
  (**2659 → 2501 líneas**; acumulado 7106 → 2501, **−64,8 %**).
- Qué se movió: las **6 rutas** `/customer/*` + `PUBLIC_DISCOUNT_SCALE`,
  `_customer_screen_view`, `_apply_discount` y los 4 modelos (`QuoteItem`/`QuoteRequest`,
  `CartItem`/`CustomerOrderSubmit`). `gen_id` se threadea. Se borró el re-import de
  `_public_screen_view` que la fase anterior había dejado en `server.py` sólo para
  `_customer_screen_view`. **`server.py` queda sin lógica de `/customer/*`.**
- 📌 **Corrección de numeración (decisión de Claude + duarte)**: la fase que aplicamos como
  «2C-1» (`public_api_routes.py`) se **renombra 2B-8**. «Fase 2C» queda reservada
  exclusivamente para la reorganización de carpetas `backend/domains/<dominio>/`.
- Verificación:
  1. Rangos re-derivados por AST: los 12 segmentos coinciden exacto, y el bloque del import
     muerto tiene el contenido esperado antes de borrarlo.
  2. **10/12 idénticas byte a byte.** Las 2 restantes con diff unificado: `customer_quote` = 2
     líneas de continuación de docstring resangradas, `customer_order_from_cart` = 1. Nada más.
     `PUBLIC_DISCOUNT_SCALE` comparada línea a línea.
  3. `flake8`: 0 F821/E999; pyflakes completo sin avisos en el nuevo.
     **`ruff check backend`: All checks passed.**
  4. Walk de rutas antes/después: **43 = 43**, 0 faltantes, 0 nuevas.
  5. `test_route_inventory.py` en verde con el snapshot **sin regenerar** (md5 `698364b3…`).
  6. Suite completa: **mismo conjunto exacto de 42 fallos** que la línea base, 0 regresiones.
  7. **Las 6 rutas probadas en vivo con datos reales**, no sólo 404s: catálogo (200), detalle
     (200), 404 de dominio con id inexistente, escala de descuentos (1:0, 3:0.10, 6:0.20,
     12:0.30), un quote de 2 anuncios × 3 meses que devolvió **300 → 270 con 10 %** (o sea
     `_apply_discount` y `PUBLIC_DISCOUNT_SCALE` quedaron bien movidos), y la orden de punta a
     punta: `POST orders/from-cart` creó la orden con su id por el `gen_id` threadeado y su
     referencia `CUST-…`, y `GET orders/mine` la listó. La orden de sonda quedó borrada.
     Sin token: 401.
- ⚠️ **Un aviso nuevo que NO arreglé** (respetando el pedido de Claude de no improvisar):
  `typing.List` queda sin uso en `server.py` después de esta fase — los F401 pasan de 26 a 27.
  `ruff check backend` sigue en verde (F401 está en la lista de deuda de `ruff.toml`), así que
  **no rompe CI**. Es un renglón de un `from typing import ...` compartido; lo deja para que
  Claude decida si lo saca en la próxima fase.
- 📌 **Defecto del helper `reindent()` confirmado**: efectivamente nunca resangra las líneas de
  continuación de un docstring multilínea, y está visible sin corregir en
  `public_api_routes.py` (líneas 89-90 y 99-100). Es cosmético (Python no exige sangría en las
  líneas de continuación de un string). En esta fase se corrigió a mano; para el archivo ya
  fusionado queda como posible arreglo cosmético suelto, no bloqueante.
- Estado: **CERRADA** — en `trunk` y `main`.

### 2026-06 — Claude (script) + Maxx (ejecución y verificación) — Fase 2C-1: `/public/*`
- Rama: `trunk` (commit `c8e4766`), base `3408a6b`. `production` sin tocar.
- Archivos: `backend/public_api_routes.py` (nuevo, 179 líneas), `backend/server.py`
  (**2755 → 2659 líneas**; acumulado 7106 → 2659, **−62,6 %**), `backend/media_utils.py`
  (141 líneas, recibe `_public_screen_view`).
- Qué se movió: las **8 rutas** `/public/*` (3 del catálogo público de pantallas + las 5 del
  share-link de playlist) + `_public_playlist`. `_public_screen_view` pasa a `media_utils.py`
  porque `_customer_screen_view` sigue en `server.py` hasta la fase `/customer/*`.
  `_bump_playlist_screens` se **threadea** (ya estaba threadeada en `menus` y `playlists`, se
  pasa por referencia: por eso un grep con paréntesis no la encuentra). Se borró el import
  muerto de `_public_token_hash`. Cierra el alcance que la 2B-4 había diferido.
- **Decisión de nombre**: `public_api_routes.py`, separado de `public_pages_routes.py` (Fase 1).
  No se fusionan: el primero son endpoints JSON + 1 shell HTML en `api_router` con prefijo
  `/api`, y el QR de `public_playlist_qr` genera la URL `"/api/public/playlist"` hardcodeada; el
  segundo sirve páginas HTML en el objeto `app` sin prefijo. Fusionarlos cambiaría URLs reales.
- Verificación:
  1. Rangos re-derivados por AST: los 10 segmentos coinciden exacto, y el contenido de la línea
     del import muerto es el esperado.
  2. **8/10 idénticas byte a byte** tal cual. Las 2 con cambio mecánico, con diff unificado:
     `public_playlist_qr` = **1 sola línea en blanco** agregada entre `io` y `qrcode`;
     `serve_public_playlist_editor` = **1 sola línea**, `WEB_DIR` → `web_dir`. Nada más.
  3. `flake8`: 0 F821/E999; pyflakes completo sin avisos. **`ruff check backend`: All checks
     passed.**
  4. Walk de rutas antes/después: **51 = 51**, 0 faltantes, 0 nuevas.
  5. `test_route_inventory.py` en verde con el snapshot **sin regenerar** (md5 `698364b3…`).
  6. Suite completa: **mismo conjunto exacto de 42 fallos** que la línea base, 0 regresiones.
  7. **Flujo completo en vivo**: catálogo público sin auth (lista, por id, 404 por código
     inexistente), shell HTML en 200, y el share-link de punta a punta — se generó un token real
     por `/playlists/{id}/share`, se leyó la playlist pública, el QR devolvió un **PNG de 969
     bytes**, y el upload de invitado devolvió **200 encolando el ítem para aprobación**, lo que
     ejercita el callable threadeado `upload_media`, `serialize_doc` y
     `normalize_playlist_items`. Se limpiaron el token, el ítem pendiente y el media de sonda.
- 📌 **Hallazgo anotado (comportamiento preexistente, NO de esta fase)**:
  `POST /api/public/playlists/{token}/media` espera **JSON con base64** (`MediaUpload`), no
  multipart. Si se le manda `multipart/form-data` devuelve **500** con
  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff` al intentar parsear el cuerpo como
  JSON, en vez de un 415/422. Debería ser un 4xx limpio. Lo confirmé leyendo la firma del
  handler (idéntica byte a byte al original). Fuera del alcance del refactor; candidato a fix
  aparte si alguna vez un cliente sube desde un formulario HTML clásico.
  ✅ **RESUELTO** en el fix del 2026-06 (ver la entrada «Subida pública por token: soporte real
  de multipart» al principio de esta bitácora): el endpoint ahora acepta multipart de verdad.
- Estado: **CERRADA** — en `trunk` y `main`.

### 2026-06 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-7: `/campaigns/*` de cliente
- Rama: `trunk` (commit `0451b5f`), base `803ea6d`. `production` sin tocar.
- Archivos: `backend/campaigns_routes.py` (nuevo, 289 líneas), `backend/server.py`
  (**2956 → 2755 líneas**; acumulado 7106 → 2755, **−61,2 %**).
- Qué se movió: las **6 rutas** `/campaigns/*` de cliente que quedaron pendientes a propósito en
  la 2B-6b + `MAX_MEDIA_CHANGES`, `CampaignMediaReplace`, `CampaignCreate` y `CampaignUpdate`.
  **`server.py` queda sin lógica de negocio de campañas.**
- `CampaignSchedule`, `calculate_campaign_price` y `screen_orientation` se **threadean** porque
  las sigue usando código que no se movió. Esta es la fase que `screens_routes.py` había anotado
  en su propio docstring como «la que debería threadear `screen_orientation`».
- **Novedad del patrón**: `CampaignCreate` y `CampaignUpdate` no pueden ser modelos de nivel de
  módulo porque su campo `schedule` es del tipo threadeado `CampaignSchedule`, así que quedan
  definidos **dentro del factory**, con la misma verificación round-trip byte a byte que se le
  aplica al cuerpo de una ruta. Primera vez que el patrón se usa sobre una definición de clase.
- Verificación:
  1. Rangos re-derivados por AST: los 9 segmentos coinciden exacto.
  2. **9/9 idénticas byte a byte**, incluidas las dos clases anidadas dentro del factory
     (`verify_relocation.py` camina el AST completo, así que las encuentra igual).
     `MAX_MEDIA_CHANGES` comparada línea a línea. Ninguna quedó definida de más en `server.py`.
  3. `flake8`: 0 F821/E999; pyflakes completo sin avisos en el nuevo.
     **`ruff check backend`: All checks passed.**
  4. Walk de rutas antes/después: **57 = 57**, 0 faltantes, 0 nuevas.
  5. `test_route_inventory.py` en verde con el snapshot **sin regenerar** (md5 `698364b3…`).
  6. Suite completa: **mismo conjunto exacto de 42 fallos** que la línea base, 0 regresiones.
  7. **CRUD completo en vivo** con la cuenta de cliente `pizzeria@demo.com`: se creó una campaña
     real (ejercitando el modelo anidado, el `normalise_schedule` y el `pricing` calculado por
     `calculate_campaign_price`), se leyó el detalle, se actualizó, se probó el reemplazo de media
     (400 de dominio) y se borró. Además 422 correctos con `schedule` ausente o mal tipado — la
     prueba de que el modelo anidado quedó bien cableado. La campaña de sonda quedó borrada.
- Cosmético: los avisos `E3/W3` en `server.py` bajan de 114 a 110; el archivo nuevo sale con 0.
- Estado: **CERRADA** — en `trunk` y `main`.

### 2026-06 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-6c: superadmin, RBAC y customer-orders → **FASE 2B-6 CERRADA**
- Rama: `trunk` (commit `af58bef`), base `325fdab`. `production` sin tocar.
- Archivos: `backend/superadmin_routes.py` (nuevo, 422 líneas), `backend/server.py`
  (**3260 → 2956 líneas**; acumulado 7106 → 2956, **−58,4 %**).
- Qué se movió: las **14 rutas** del PR 3 de 3 (superadmin admins CRUD + overview, RBAC
  info/migrate/screens-by-type/seed-test-users, customer-orders vista/detalle/estado) + los
  modelos `CustomerOrderStatusUpdate` y `CreateAdminRequest`.
- **Decisión tomada sobre las 3 `*-view`**: se quedan en `server.py`. Son `FileResponse(WEB_DIR)`
  sin lógica y ya viven en el mismo bloque que el resto de las páginas estáticas, que no se tocó
  en ninguna fase (mismo precedente que `/player-activate`). Moverlas sólo obligaría a threadear
  `WEB_DIR` en otro módulo. Cierra el punto que el doc dejaba abierto.
- `hash_password` sigue definido en `server.py` (lo usan signup y los datos demo). Las dos rutas
  que lo necesitan hacen un `from server import hash_password` **dentro de la función**, el mismo
  patrón que ya usa `finance.py` con ese nombre. `IS_PROD` se recalcula localmente para no
  arriesgar un import circular, igual que `auth_v2.py`.
- Verificación:
  1. Rangos re-derivados por AST: los 16 segmentos coinciden exacto.
  2. **14/16 idénticas byte a byte** automático; `create_admin` y `seed_rbac_test_users`
     comparadas con diff unificado: **3 líneas agregadas y 0 borradas** en cada una, y son
     exactamente las 3 declaradas (comentario + import local + línea en blanco). Ninguna quedó
     definida de más en `server.py`.
  3. `flake8`: 0 F821/E999; pyflakes completo sin avisos en el nuevo.
     **`ruff check backend` con la config del proyecto: All checks passed.**
  4. Walk de rutas antes/después: **71 = 71**, 0 faltantes, 0 nuevas.
  5. `test_route_inventory.py` en verde con el snapshot **sin regenerar** (md5 `698364b3…`).
  6. Suite completa: **mismo conjunto exacto de 42 fallos** que la línea base, 0 regresiones.
  7. Sonda en vivo de las 14 rutas: todas ejecutan su handler. **El import diferido de
     `hash_password` se probó de punta a punta**: se creó un admin real por
     `/superadmin/create-admin`, se hizo login con él (rol `admin`, token válido) y después se lo
     desactivó con `toggle` y se lo borró con `DELETE` — o sea 3 rutas más validadas en positivo,
     no sólo con 404 de dominio. La cuenta de sonda quedó borrada de la base. Las 3 `*-view`
     siguen devolviendo 200.
- Cosmético: los avisos `flake8 --select=E3,W3` en `server.py` **bajan** de 126 a 114. Otra vez
  el delta de E303 que Claude anticipó (+3) no se materializó.
- **Estado de la Fase 2B-6: CERRADA.** Los 3 PRs (`b899732`, `7f2c3de`, `af58bef`) movieron 43 de
  las 46 rutas `/admin|/superadmin`; las 3 que quedan en `server.py` son las `*-view` estáticas,
  por decisión explícita.
- Estado: **CERRADA** — en `trunk` y `main`.

### 2026-06 — Estado de `server.py` tras la Fase 2B-7

- **2755 líneas** (era 7106: **−61,2 %**). Le quedan **51 rutas**. Sin lógica de campañas,
  dispositivos, player, pantallas, playlists, menús, media ni admin.
- Lo que queda, agrupado y con mi recomendación de orden:
  1. **8 `/public/*`** — el bloque más grande y autocontenido: `/public/screens*`,
     `/public/playlists/{token}*` (con QR, media e ítems), `/public/playlist`. Candidato natural
     al próximo PR; ojo que ya existe `public_pages_routes.py` de la Fase 1, así que hay que
     elegir bien el nombre o fusionarlos.
  2. **6 `/customer/*`** — `quote`, `discount-scale`, `orders/mine`, `orders/from-cart`,
     `screens`, `screens/{id}`. Comparten el motor de cotización.
  3. **4 `/auth/*`** — `login`, `register`, `me`, `profile`. ⚠️ Tocar auth exige pasar por el
     `integration_expert` antes de escribir código; no es una relocalización más.
  4. **3 `/payments*`** + 2 `/widgets/{id}/render|weather` + 2 `/certification/*` + 2 `/screen*`
     — bloques chicos, se pueden juntar en un PR de «varios».
  5. **~20 páginas estáticas/SPA de una ruta** (`/landing`, `/about`, `/download`,
     `/marketplace`, `/menu-editor`, `/design-studio`, `/dashboard`, `/player-activate`, las 3
     `*-view`, `/health`, el catch-all `/{full_path:path}`, etc.): **se quedan donde están**, ya
     es decisión tomada tres veces.
- Siguiente hito del plan: **Fase 2C** — mover los módulos a `backend/domains/<dominio>/`.

### 2026-06 — Estado de `server.py` al cerrar la Fase 2B-6
- **2956 líneas** (era 7106 al empezar: **−58,4 %**). Le quedan **57 rutas**, repartidas así:
  8 `/public/*`, 6 `/customer/*`, 6 `/campaigns/*` (cliente), 4 `/auth/*`, 3 `/payments/*`,
  3 `/admin/*-view` (estáticas, por decisión), 2 `/widgets/*`, 2 `/certification/*`,
  2 `/screen*`, y ~20 páginas estáticas/SPA de una sola ruta (`/landing`, `/about`,
  `/download`, `/marketplace`, `/menu-editor`, `/design-studio`, `/dashboard`,
  `/player-activate`, el catch-all `/{full_path:path}`, etc.).
- Candidatos naturales para lo que viene, en orden de tamaño: las 6 `/campaigns/*` de cliente
  (quedaron pendientes a propósito en la 2B-6b), las 8 `/public/*`, las 6 `/customer/*`,
  `/auth/*` + `/payments/*`. El bloque de páginas estáticas conviene dejarlo entero donde está.
- Siguiente hito del plan: **Fase 2C** — mover los módulos a `backend/domains/<dominio>/`.

### 2026-06 — Claude (diagnóstico) + Maxx (fix) — CI: el job de lint fallaba por un desajuste de config de ruff
- Rama: `trunk` (commit `3442566`). `production` sin tocar.
- Causa raíz (diagnóstico de Claude, confirmado): en ruff un `--ignore` por línea de comando
  **reemplaza** el `ignore` del archivo de config en vez de sumarse. Los flags de
  `.github/workflows/ci.yml` (`--select E,F,W,I --ignore E501,E402,F401,F403,F841`) anulaban la
  lista de deuda técnica de `backend/ruff.toml` (`E701`, `E702`, `E741`, `E731`, `F811`, `W293`,
  `W605`), así que CI reportaba código que ya estaba en `production` (`622da1ad`) desde antes de
  la primera fase del refactor. **No lo introdujo el refactor**: cualquier push a `main` que
  tocara `backend/` iba a fallar igual.
- Lo que sí era nuestro: 3 avisos `I001` (bloque de imports sin ordenar) en
  `admin_devices_routes.py`, `admin_campaigns_routes.py` y
  `tests/test_iter36_rename_regression.py`. Corregidos con `ruff check --select I --fix`: sólo se
  movieron líneas de import, mismo set de imports, ningún cuerpo de ruta tocado.
- Nota: el diff real de ruff fue **más chico** que el que Claude anticipó. Como `ruff.toml` no
  declara `known-first-party`, ruff detecta `database`/`deps` como primera parte y deja `fastapi`
  y `pydantic` en el bloque de terceros; no los reordenó como en el diff esperado. El resultado
  igual es 0 `I001`.
- Verificación: `ruff check backend` → **All checks passed** (0 avisos; con el comando viejo daban
  7). 0 F821, `import server` limpio, `test_route_inventory` + `test_iter36_rename_regression`
  en verde (28/28).
- ⚠️ **Pendiente de duarte**: la otra mitad del arreglo es **una línea en
  `.github/workflows/ci.yml`** y **no se puede pushear desde acá** (el token no tiene scope
  `workflow`, GitHub rechaza el push). Instrucciones paso a paso en
  `docs/CI_PATCH_RUFF_CONFIG.md`. Hasta que se aplique, el mail de «Lint (ruff) failed» va a
  seguir llegando aunque el código esté limpio.
- Estado: código CERRADO en `trunk`/`main`; **el workflow queda BLOQUEADO ESPERANDO A DUARTE**.

### 2026-06 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-6b: campañas, widgets, pagos y scheduler
- Rama: `trunk` (commit `7f2c3de`), base `156d92c`. `production` sin tocar.
- Archivos: `backend/admin_campaigns_routes.py` (nuevo, 360 líneas), `backend/server.py`
  (**3526 → 3260 líneas**; acumulado 7106 → 3260, **−54,1 %**), `backend/media_utils.py`
  (122 líneas, recibe `normalise_schedule`).
- Qué se movió: las **12 rutas** del PR 2 de 3 (moderación de campañas, widgets CRUD, vista de
  pagos, monitoreo del Campaign Scheduler) + `WIDGET_TYPES`, `WidgetCreate` y
  `_media_is_available`. `normalise_schedule` va a `media_utils.py` porque la usan tanto
  `admin_repair_campaigns` (se mueve) como `create_campaign`/`update_campaign` (quedan);
  `server.py` conserva el re-import de una línea porque `test_playlist_pipeline` importa
  `server.normalise_schedule`. Se borró el import muerto de `campaign_scheduler`.
- Verificación:
  1. Rangos re-derivados por AST: los 15 segmentos coinciden exacto.
  2. **15/15 idénticas byte a byte** (14 en el archivo nuevo + `normalise_schedule` en
     `media_utils.py`, más `WIDGET_TYPES` comparado línea a línea), y ninguna quedó definida de
     más en `server.py`.
  3. `flake8`: 0 F821/E999 en los tres archivos; pyflakes completo sin avisos en el nuevo. El
     **conjunto de F401 preexistentes de `server.py` queda idéntico (21 = 21)**: la limpieza del
     import de `campaign_scheduler` no dejó ni agregó imports muertos.
  4. Walk de rutas antes/después: **83 = 83**, 0 faltantes, 0 nuevas.
  5. `test_route_inventory.py` en verde con el snapshot **sin regenerar** (md5 `698364b3…`).
  6. Suite completa: **mismo conjunto exacto de 42 fallos** que la línea base, 0 regresiones.
  7. Sonda en vivo de las 12 rutas con token de superadmin: todas ejecutan su handler.
     `/admin/campaigns/repair` devolvió 200 sobre **254 campañas** sin normalizar ni podar nada, y
     el scheduler corrió con 0 transiciones. Las `/campaigns/*` de cliente siguen respondiendo.
- Sobre el aviso de Claude de que los E303 subirían +5: **no ocurrió**. Los avisos
  `flake8 --select=E3,W3` en `server.py` **bajan** de 134 a 126, y el archivo nuevo más
  `media_utils.py` salen con 0. Nada que revisar.
- Riesgo para el otro agente: `server.py` volvió a correrse ~266 líneas. Los rangos de la 2B-6c
  ya están re-derivados contra `7f2c3de` en `docs/FASE2B6_MAPA_RUTAS_ADMIN.md`.
- Estado: **CERRADA** — en `trunk` y `main`.

### 2026-06 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-6a: `/admin/devices/*` y dashboards
- Rama: `trunk` (commit `b899732`), base `5e9c149`. `production` sin tocar.
- Archivos: `backend/admin_devices_routes.py` (nuevo, 412 líneas), `backend/server.py`
  (**3844 → 3526 líneas**; acumulado 7106 → 3526, **−50,4 %**), `backend/verify_relocation.py`
  (nuevo, herramienta de verificación).
- Qué se movió: las **17 rutas** del PR 1 de 3 (devices CRUD/activación/provisioning/power/
  comandos, `player-release` ×2, `playlogs`, `client-errors`, `analytics`) + los modelos
  `DeviceActivate` y `DeviceProvision` (grep-verificado: sin otros usos).
- Verificación:
  1. Rangos re-derivados por AST sobre el `server.py` real: los 19 segmentos coinciden exacto.
  2. Verificación AST independiente: **19/19 idénticas byte a byte**, y ninguna quedó definida de
     más en `server.py`.
  3. `flake8`: 0 F821/E999 en los dos archivos; pyflakes completo sin avisos en el nuevo.
  4. Walk de rutas antes/después: **100 = 100**, 0 faltantes, 0 nuevas, 0 duplicadas.
  5. `test_route_inventory.py` en verde con el snapshot **sin regenerar** (md5 `698364b3…`).
  6. Suite completa: **mismo conjunto exacto de 42 fallos** que la línea base, 0 regresiones.
     `test_iter36_rename_regression`: 26/26.
  7. Sonda en vivo de las 17 rutas con token de superadmin: todas ejecutan su handler (404/422 de
     dominio, ningún 404 de routing) y siguen exigiendo auth (401 sin token).
- Cosmético: los avisos `flake8 --select=E3,W3` en `server.py` **bajan** de 148 a 134; el archivo
  nuevo sale con 0.
- ⚠️ Efecto colateral de la sonda, sólo en el entorno de preview: el `POST /admin/player-release`
  de prueba **sobrescribió el documento de release** que estaba en 2.2.0 / `versionCode` 4 y ahora
  dice 3.4.0 / 22, que es la versión real del APK. Es más correcto que antes y no afecta a
  producción, pero queda anotado.
- Riesgo para el otro agente: `server.py` volvió a correrse ~320 líneas. Los rangos de 2B-6b y
  2B-6c hay que re-derivarlos contra `b899732`.
- Estado: **CERRADA** — en `trunk` y `main`.

### 2026-06 — Claude (reporte) + Maxx (fix) — Colisión de nombre: `create_player_routes` ×2
- Rama: `trunk` (commit `1071a39`). Commit chico y aislado, **no** mezclado con la 2B-6.
- Qué pasaba: `server.py` tenía **dos imports del mismo nombre** a nivel de módulo —
  `from player_routes import create_player_routes` (línea 3401, nueva de la 2B-5) y
  `from colorlight_player import create_player_routes` (línea 3584, vieja, modo Direct
  Player/A40). No rompía por el orden de ejecución (la primera se usa en la 3429, antes de que el
  segundo import la pise), pero era una redefinición real y una trampa para quien tocara el bloque.
- Fix: la factory de `player_routes.py` pasa a llamarse **`create_player_domain_routes`**;
  `colorlight_player.create_player_routes` queda intacta por ser la más vieja y de mayor
  superficie. Se dejó un comentario en el punto de montaje explicando por qué el nombre difiere.
  **Sólo rename**: ninguna ruta, handler ni lógica cambia.
- Validación (testing agent, informe `test_reports/iteration_36.json`): ambas factories siguen
  registradas —las 16 rutas de player/devices y las `/cls/*` + `/wp-json/*` de Direct Player—,
  ciclo completo del dispositivo en 200, `test_route_inventory.py` en verde con el snapshot
  **sin modificar** (md5 idéntico) y la suite completa con el **mismo conjunto exacto de 42
  fallos** de la línea base: 0 regresiones. Se añadió
  `backend/tests/test_iter36_rename_regression.py` (26 tests) para re-verificarlo en el futuro.
- Estado: CERRADA — commit `1071a39`.

### 2026-06 — Corte acordado de la Fase 2B-6 (46 rutas `/admin/*` + `/superadmin/*`)
- Mapa por AST sobre `258bbae`: `docs/FASE2B6_MAPA_RUTAS_ADMIN.md`. Conteo real **46** rutas
  (41 `/admin/*` + 5 `/superadmin/*`), 868 líneas de handlers — el plan decía 51.
- **No hay bloque de finanzas que extraer** de `server.py`: esas rutas ya viven en
  `admin_invoices_routes.py`, `admin_orders_routes.py`, `admin_refunds_routes.py`, `finance.py`
  y `reports_routes.py`. El tercer PR pasa a ser superadmin + RBAC + órdenes + vistas.
- Corte confirmado por Claude y duarte, en este orden:
  1. **2B-6a** `admin_devices_routes.py` — 17 rutas (devices, player-release, playlogs,
     client-errors, analytics). `DeviceProvision` se muda entero con
     `admin_provision_device` (grep-verificado: no lo usa nadie más), sin threadear.
  2. **2B-6b** `admin_campaigns_routes.py` — 12 rutas (campañas, widgets, pagos,
     campaign-scheduler). Los helpers compartidos con las `/campaigns/*` de cliente **se
     threadean**; esas 6 rutas de cliente quedan para un PR aparte, para no agrandar este.
  3. **2B-6c** `superadmin_routes.py` — 17 rutas (superadmin, usuarios, RBAC, customer-orders y
     las 3 `*-view`). Las `*-view` **sí se mueven** aunque sean `FileResponse` puro: están bajo
     el prefijo `/admin/*` que estamos vaciando (a diferencia de `/player-activate`, que no).
- Estado: EN CURSO — Claude está armando el script de la 2B-6a.

### 2026-06 — Maxx — Bug de producción: el panel del cliente crasheaba con pantallas creadas por admin
- Rama: **`fix/workspace-screen-location`** (sale de `eaea594`, o sea de `trunk`; **no** mezclada
  con la 2B-5 a pedido de Claude). Commits `142f27f` + `33bfa70`. Ya en GitHub, **sin mergear**.
- Síntoma: asignar a una organización una pantalla creada por `POST /api/admin/screens` dejaba
  el panel del cliente **completamente en blanco**, con
  `Objects are not valid as a React child (found: object with keys {address, city, state, country, lat, lng})`.
- Causa raíz: `screens.location` es un **string** cuando la pantalla se crea desde el panel del
  cliente (`workspace_routes.py`) y un **objeto estructurado** cuando se crea desde el API de
  admin. `app/workspace/index.tsx` y `app/workspace/screens.tsx` renderizaban `s.location`
  directo dentro de un `<Text>`, y eso tumba todo el árbol de React.
- Fix: `frontend/src/utils/screenLocation.ts` con `formatScreenLocation()` (acepta
  string | objeto | null, devuelve siempre string) usado en los dos listados. Segundo commit:
  el subtítulo se arma con `join(' · ')` porque sin `code` arrancaba con un punto suelto.
- **Afecta a producción**, no solo al entorno de prueba: cualquier pantalla que soporte o un
  admin asigne a una cuenta de cliente rompe el panel de ese cliente.
- Verificado por el **testing agent** (informe `test_reports/iteration_35.json`): panel carga
  completo, la ubicación sale como `Casa de duarte, Miami, US`, las 3 pantallas con `location`
  string siguen igual, las 5 pestañas del panel sin errores de render.
- Encontrado al armar la organización «Pizzería Don Luis» en plan Enterprise para la prueba
  física de la 2B-5 (ver `docs/PRUEBA_FISICA_2B5.md`).
- Estado: **LISTO PARA MERGEAR** a `trunk` cuando Claude/duarte lo autoricen (es independiente
  de la 2B-5; el mismo cambio ya viaja dentro de la rama de la 2B-5 porque el entorno de preview
  lo necesitaba para que duarte pudiera usar el panel durante la prueba).

### 2026-06 — Auditoría de variables de entorno faltantes en producción (Render)
- Pedido de duarte: «que todo funcione, todas las funciones» en producción.
- Sondas **de solo lectura** contra `https://mediadview.com` (sin escribir nada):
  - `POST /api/media/presign` con el superadmin devuelve
    `503 "Direct uploads not available — use /media/upload"` → **`R2_ENABLED` es false en
    producción**, o sea faltan las variables de R2. El storage sigue andando por el fallback
    legacy de disco/base64 (las lecturas de media existente no se rompen).
  - `EMERGENT_LLM_KEY` falta (confirmado por el 503 de «Importar Menú con IA» que reportó
    duarte). `menu_ai_routes.py` lo chequea en las líneas 102 y 173.
- Nombres exactos que lee `backend/storage.py` (¡ojo, no son los del resumen viejo!):
  `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` (esas 4 activan
  `R2_ENABLED`), más `R2_PUBLIC_BASE_URL` y `R2_REGION` (por defecto `auto`).
  `startup_check.py` exige las 5 primeras cuando `STORAGE_DRIVER=r2`.
- Barrido del resto del código buscando el mismo patrón: `EMERGENT_LLM_KEY` es el **único** hueco
  de variable de entorno que rompe una función de cara al cliente. Stripe tiene fail-fast al
  arrancar, `FERNET_KEY`/`REDIS_URL` tienen fallback seguro, y el SMTP se configura por base de
  datos (Ajustes → Email), no por variable de entorno.
- **No tengo visibilidad del panel de Render**: lo de arriba es inferido por sondas HTTP, no leído
  de la configuración.

### 2026-06 — Claude (script) + Maxx (ejecución y verificación) — Fase 2B-5: /player/* + /devices/* fuera de server.py
- Rama: **`refactor/fase2-5-player`**. `trunk`, `main` y `production` **sin tocar**.
- Commit base: `eaea594` (= `de45af4` + el commit automático del entorno; `backend/server.py`
  idéntico a `de45af4`).
- Archivos tocados: `backend/player_routes.py` (nuevo, 1066 líneas), `backend/server.py`
  (**4761 → 3845 líneas**; acumulado 7106 → 3845, **−46 %**), `backend/media_utils.py`
  (96 → 108, recibe `_norm_date`).
- Qué se movió: las **16 rutas del plan** (9 `/player/*` + 7 `/devices/*`) + 5 modelos
  (`DeviceRegister`, `DeviceSyncProgress`, `DeviceHeartbeat`, `DeviceLog`, `DevicePair`) +
  `effective_playlist_schedule_key`. `_norm_date` pasa a `media_utils.py` porque
  `normalise_schedule` sigue en `server.py` y `tests/test_playlist_pipeline.py` importa
  `server._norm_date` (se dejó re-import de una línea).
  **`/player-activate` NO se movió** (decisión de duarte): es `FileResponse` de un HTML estático
  de `WEB_DIR`, pertenece al grupo SPA junto a `/public/playlist`, `/download`, `/screen`,
  `/marketplace`. Las 4 `/admin/devices/*` y `/admin/player-release` quedan para la 2B-6.
- Novedad técnica: el `reindent()` del script usa `tokenize` para **no** tocar las filas
  interiores de un string multilínea. `web_player` es la primera ruta del refactor con un literal
  multilínea real (~67 líneas de HTML/JS), y el reindent ingenuo de las fases 2B-1…2B-4 le habría
  metido 4 espacios *dentro* del valor del string sin que ningún test de forma de ruta lo notara.
- Imports muertos eliminados de `server.py`: el bloque completo `from device_security import (...)`
  (sus 5 nombres se van con las rutas; `connectivity_from_heartbeat` ya tenía 0 usos antes de esta
  fase) y el bloque completo `from storage import (...)` (10 de 11 nombres eran restos de la 2B-2;
  solo `open_media_for_response` se re-importa, en `player_routes.py`).
- Validación (toda ejecutada por Maxx, no solo por el script):
  1. **Rangos de línea re-derivados por AST** sobre el `server.py` real: los 23 segmentos del
     script coinciden exactamente; el único `@api_router` de `/player|/devices` fuera del alcance
     es `serve_player_activate`, como estaba acordado.
  2. **Verificación AST independiente**: **23/23 unidades idénticas byte a byte** al original
     (script propio, no el del extractor; con dedent consciente de strings multilínea).
  3. `flake8 F821/F811/E999`: **0 F821** en los 3 archivos. F811 baja de 9 a 7 (los 2 que
     desaparecen estaban dentro de rutas movidas). `import server` limpio.
  4. `tests/test_route_inventory.py` **en verde sin regenerar el snapshot** (492 rutas).
  5. Suite completa: **465 passed / 22 failed / 35 skipped / 20 errors**, y el `diff` del conjunto
     de IDs que fallan contra la línea base pre-2B-5 (`docs/BASELINE_PYTEST_PRE_2B5.md`) es
     **vacío**: cero regresiones.
  6. **A/B contra el servidor pre-refactor**: se levantó `de45af4` en un worktree en el puerto
     8002 y se comparó respuesta contra respuesta:
     - `/api/player/{id}/web` y `/api/player/{id}/test`: **HTML idéntico byte a byte**
       (12 975 y 9 648 bytes) — la prueba directa de que el HTML/JS embebido no se corrompió.
     - `playlist`, `version`, `schedule`, `status`, `export`, `diagnose`: JSON idéntico
       (normalizando solo las marcas de tiempo).
     - Ciclo de vida completo del dispositivo (`pair` → `register` → `check` → `heartbeat` →
       `update-check` → `log` → `playlist` + `player/{id}/playlist` ya emparejado): **8/8
       idénticas**; la única diferencia es el nombre/ID de la pantalla, porque cada lado usó su
       propia pantalla de prueba.
  7. `/apk` sigue devolviendo 302 y `/api/player-activate` 200.
- ⚠️ **RIESGO ROJO — prueba física**: el plan pedía probar con una **TV box real** antes de
  fusionar. **Decisión de duarte (2026-06)**: la prueba física **deja de ser gate por fase** y pasa
  a ser la **validación final de punta a punta** de todo el refactor, cuando ya esté desplegado y
  funcionando en producción. Motivo práctico: la caja tiene `https://mediadview.com` compilado en
  el APK y el único lugar donde se puede cambiar el servidor es la pantalla de «Manual pairing»,
  que con el control de una TV box común no es accesible durante la reproducción (sólo se escuchan
  MENU/F1 y la tecla I; el mantener-OK-5-segundos existe únicamente en la pantalla de
  emparejamiento). Repuntar la caja exige teclado USB o ADB, y no justificaba frenar el refactor.
  El código de 6 dígitos **no sirve** para cruzar de entorno: ese código vive en la base de datos
  del servidor que lo generó.
- Verificación equivalente que sí se hizo, y que es la razón por la que el merge es seguro: el
  **A/B respuesta contra respuesta contra el servidor pre-refactor** (punto 6) cubre las 16 rutas,
  incluido el HTML del web player byte a byte y el ciclo completo del dispositivo.
- Estado: **CERRADA** — fusionada a `trunk` y `main`.
- Cosmético conocido y aceptado (mismo criterio que en 2B-4): quedan 3 comentarios de sección
  huérfanos en `server.py` y algunos empalmes con más de 2 líneas en blanco. El total de avisos
  `flake8 --select=E3,W3` en `server.py` **baja** de 166 a 148, y `player_routes.py` +
  `media_utils.py` salen con 0. No se pasó ningún regex global sobre el archivo.
- Riesgo para el otro agente: `backend/server.py` y `backend/media_utils.py` cambiaron en esta
  rama. La 2B-6 (`/admin/*`) debe salir de aquí o rebasarse encima, y sus rangos de línea hay que
  re-derivarlos: `server.py` se corrió casi 1000 líneas.
- Estado: **CERRADA** — fusionada a `trunk` y `main` (2026-06). `production` sin tocar.
- Commit final: ver el merge en `trunk`.

### 2026-06 — Pendiente anotado (sin tocar código): `server_url` en la respuesta de `/check`
- Idea: que `GET /api/devices/{device_id}/check` incluya un campo **`server_url`** para poder
  mover una caja —o una flota entera— de servidor **desde el panel, sin tocar el hardware**.
- Por qué es casi gratis: el APK **ya lo soporta**. `PairingActivity` (líneas 461-463) lee
  `server_url` de la respuesta de `/check` y llama a `PlayerApi.setBaseUrl(...)`. Lo único que
  falta es que el backend lo devuelva; hoy la respuesta de `check_device_activation`
  (`player_routes.py`) sólo trae `device_id`, `activation_code`, `status`, `screen_id`,
  `screen_name`, `activated_at` y `screen_resolution`.
- Problema que resuelve: hoy la URL del servidor sólo se puede cambiar a mano en la pantalla de
  «Manual pairing», que con el control de una TV box común no es accesible durante la
  reproducción. Cualquier migración de servidor obliga a teclado USB o ADB por cada equipo.
- Decisión de duarte (2026-06): **anotado como pendiente, no se toca código ahora** y sobre todo
  **no se toca `production`** por esto. Se retoma más adelante.
- Estado: PENDIENTE (no empezado).


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
