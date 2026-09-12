# MediaView — PRD técnico y estado

## Objetivo

Una sola plataforma comercial de Digital Signage con infraestructura compartida
(usuarios, organizaciones, locations, screens, devices, media, playlists, billing y
player), pero tres operaciones estrictamente separadas por backend RBAC:

1. **SELF_SERVICE** — cliente administra únicamente sus pantallas y paga suscripción por unidad.
2. **PUBLIC_ADVERTISING** — MediaView crea/administra la pantalla; anunciantes compran slots.
3. **MEDIAVIEW_MANAGED** — MediaView opera todo; cliente opcional `MANAGED_VIEWER` solo lectura.

## Decisiones confirmadas

- La pantalla productiva **Columbus** migrará a `PUBLIC_ADVERTISING`.
- P0 Player se completa y prueba antes del dominio de tres modelos.
- Diagnostics oculto por defecto; acceso por PIN/activation code y comando remoto admin.
- Billing P1: modelos/ledger primero y Stripe en modo prueba antes de cobro real.
- No rewrite, no endpoints/collections duplicados, no ruptura de pairing/auth existentes.

## Arquitectura

- FastAPI + MongoDB; API bajo `/api`.
- Panel HTML/CSS/JavaScript servido por FastAPI.
- Android Kotlin: pairing nativo, ExoPlayer, Coil, WebView aislado para menús, Room/cache.
- SSE por pantalla + polling 15 s fallback.
- Android se compila únicamente en GitHub Actions/Codemagic.

## Implementado previamente

- Pairing nativo, identidad persistente, Room, SHA-256, descarga offline, watchdog,
  heartbeat, boot recovery, SSE/polling y playlist canónica.
- Playlists mixtas (menús/fotos/videos), duración, horario, prioridad, publicación directa,
  estado de entrega, QR/share y aportes públicos aprobables.
- Sesión web access-token en memoria + refresh HttpOnly y 401 consistente.
- CI sin commits automáticos de APK/logs en `main`; artifacts Android externos.

## P0 Player — implementado

- Auditoría completa en `android-player/P0_AUDIT_REPORT.md`.
- Eliminado cualquier texto público “Cargando contenido”, red/error/status técnico.
- Doble buffer `activeSession/pendingSession`: A permanece visible mientras B decodifica,
  obtiene primer frame o page commit; crossfade 220 ms y fallback al frame anterior.
- `display_mode`: `cover` predeterminado, `contain`, `stretch`; backend, Room y portal.
- Room migration 1→2 no destructiva; pairing/cache existentes preservados.
- Diagnostics siempre oculto; PIN/activation code, comandos `show_diagnostics` /
  `hide_diagnostics`, auto-cierre 5 min. Pairing admin menu también protegido.
- Heartbeat ampliado y parcial seguro: no borra diagnóstico anterior con `None`.
- Player objetivo: **v3.2.0**, `versionCode 17`.
- `/apk` preparado para GitHub Release estable sin binario en `main`.

## Verificación P0

- QA independiente Iteración 14: backend/UI **100%**, sin issues críticos o menores.
- 17 contratos backend P0 aprobados; retest heartbeat adicional 11/11.
- Ruff y ESLint relevantes aprobados.
- Flujo móvil real: menú creado después de abrir editor → Refresh → agregar →
  `contain` → guardar → API persiste; datos temporales eliminados.
- Revisión estática Kotlin consistente; compilación Android local prohibida por diseño.

## P0 pendiente / bloqueado

- Guardar/fusionar checkpoint P0, ejecutar CI y descargar artifact v3.2.0.
- Prueba física TV: image/video/menu/image sin loading, flash negro ni debug; COVER;
  WAN offline; actualización atómica; PIN diagnostics.
- Configurar `MEDIAVIEW_DIAGNOSTICS_PIN` como secreto CI si se desea PIN distinto al activation code.

## P1 — Fase 1: RBAC + Tenant Isolation ✅ COMPLETADO

### Implementado y testeado (100% — Acceptance Tests A-H PASS):

- **rbac.py**: Matriz de 7 roles (SUPER_ADMIN, MEDIAVIEW_ADMIN, SUPPORT, SELF_SERVICE_OWNER, SELF_SERVICE_MANAGER, MANAGED_VIEWER, ADVERTISER). Funciones `assert_permission`, `assert_tenant`, `assert_can_manage_screen`, `get_effective_role`.
- **require_admin / require_superadmin**: Migrados a RBAC. Mapeo automático de roles legacy via `ROLE_MIGRATION_MAP`.
- **_is_platform_admin**: Migrado a RBAC.
- **Tenant isolation**: DELETE /admin/screens, PUT /admin/screens, PUT /admin/screens/{id}/advertising — todos llaman `assert_can_manage_screen` que verifica organización.
- **Nuevos endpoints self-service**: POST /screens/self-service (crear), PUT /screens/self-service/{id} (actualizar con tenant isolation), GET /screens/self-service/mine.
- **MANAGED_VIEWER bloqueado**: _can_publish_playlist rechaza MANAGED_VIEWER explícitamente.
- **Seed test users**: POST /admin/rbac/seed-test-users crea 6 usuarios RBAC + 4 screens test.
- **operation_type** validado en create/update screens (SELF_SERVICE/PUBLIC_ADVERTISING/MEDIAVIEW_MANAGED).

### Resultados acceptance tests:
- TEST A (SUPER_ADMIN → SELF_SERVICE): ✅ 200
- TEST B (SUPER_ADMIN → PUBLIC_ADVERTISING): ✅ 200
- TEST C (SUPER_ADMIN → MEDIAVIEW_MANAGED): ✅ 200
- TEST D (SELF_SERVICE_OWNER → propio org): ✅ 200
- TEST E (SELF_SERVICE_OWNER → otro org): ✅ 403
- TEST F (ADVERTISER → admin screens): ✅ 403
- TEST G (MANAGED_VIEWER → publish): ✅ 403
- TEST H (MEDIAVIEW_ADMIN → Public/Managed): ✅ 200

## P1 — Fase 2: Self-Service Portal (PENDIENTE)

- Organización, locations, y billing por pantalla (`SELF_SERVICE_SUBSCRIPTION`).

## P1 — Fase 3: Public Advertising (PENDIENTE)

- `/advertise/{screen_code}` landing pages, Advertiser dashboard, Ad Approval Workflow.

## P1 — Fase 4: MediaView Managed (PENDIENTE)

- `MANAGED_VIEWER` portal View-Only.

## P2 — billing y operación comercial

- `SELF_SERVICE_SUBSCRIPTION`, `PUBLIC_AD_PURCHASE`, `MANAGED_SERVICE`.
- Ledger/modelos primero; Stripe test para checkout y lifecycle publicitario.
- Estados campaña: draft, payment pending, paid, review, approved, scheduled, active,
  completed, rejected, cancelled, refunded.
- Telemetría/fleet, player health, revenue, audit logs y soak 24–72 h.

## Integraciones pendientes

- Stripe está desactivado mientras no se inicie P2.
- R2 no configurado; uploads mantienen fallback existente hasta migración explícita.

---

## Rediseño Premium UI/UX (junio 2026)

Reporte completo en `/app/design_guidelines.md`.

- Paleta oficial: cian `#06b6d4` / `#0891b2` / `#0e7490`, navy `#0f172a` / `#020c1b`,
  superficies `#ffffff` / `#f8fafc` / `#f1f5f9`. Prohibidos: morados y amarillos de ScreenCloud.
- 24 assets premium propios generados con Gemini Nano Banana
  (`backend/scripts/gen_premium_assets.py`, re-ejecutable) en `backend/web/assets/*.webp`
  (+ variantes `-sm.webp` para grids). PNG originales borrados: 15 MB -> 2.6 MB.
- `web/landing.html`: hero con marco de TV y rotación de 6 industrias, banda de entorno real,
  4 pasos de producto, showcase de 13 industrias filtrable, galería de 8 entornos,
  importación de menú, edición móvil, 12 plantillas filtrables, calculadora de precios
  alimentada por `GET /api/plans` (sin precios hardcodeados).
- `web/i18n.js`: +180 claves; landing 100% bilingüe ES/EN con el toggle existente.
- `app/workspace/*`: migrado de oscuro/índigo a claro cian/navy
  (`frontend/scripts/relight_workspace.py`) y copy a español
  (`frontend/scripts/translate_workspace.py`). Dashboard reconstruido con uso de pantallas,
  estado de dispositivos, lista de pantallas y acciones rápidas.
- `workspace_routes.py` → `GET /api/workspace/context` ahora devuelve
  `stats.devices_online` y `stats.devices_offline` (heartbeat < 2 min).
- Planes localizados a español en Mongo (`backend/scripts/localize_plans_es.py`).
- Animaciones: scroll reveal + crossfade con `IntersectionObserver`, sin librerías nuevas,
  respetando `prefers-reduced-motion`.

### Pendiente / decisiones del dueño
1. `web/saas/` (export estático de Expo que sirve `/pricing` y `/workspace/*` en producción)
   está desactualizado — hay que regenerarlo antes del deploy.
2. En producción `/login` y `/signup` sirven el legacy `customer.html` (anunciantes),
   no las páginas Expo del SaaS. Decidir destino antes de tocar.
3. Producir los 4 videos de producto (storyboard en `design_guidelines.md`, sección 7).

## Iteración 28 — Precio anual, logos de clientes y export de producción

**Precio anual (sin hardcode)**
- Cada plan tiene `annual_free_months` en Mongo (2 para los pagos, 0 para Free) y
  `annual_price = monthly_price * (12 - annual_free_months)`.
  Script: `backend/scripts/set_annual_pricing.py [free_months]`.
- `PUT /api/admin/plans/{plan_id}` recalcula `annual_price` automáticamente al cambiar
  `monthly_price` o `annual_free_months`, salvo que el admin mande un `annual_price` explícito.
- `/pricing` tiene toggle Mensual/Anual: muestra el equivalente por mes, el total anual
  y el ahorro. Los meses gratis se leen de la API, nunca están escritos en el código.
- La calculadora del landing (`#pt-annual`) muestra la línea anual con la misma regla.

**Ciclo de facturación real**
- `POST /api/auth/customer-signup` acepta `billing_cycle` (`monthly` | `annual`, default monthly,
  valor inválido → 400). Guarda el ciclo en `subscriptions` y en `pricing_agreements`,
  y pone `current_period_end` a 365 días si es anual.
- `billing_status` queda en `pending`: **no se simula ningún cobro** (Stripe no está integrado).

**Logos de clientes (administrable, sin testimonios inventados)**
- `backend/client_logos_routes.py`:
  `GET /api/client-logos` (público) · `GET|POST|PATCH|DELETE /api/admin/client-logos` (admin).
  Los archivos se guardan en `backend/web/clients/` y se sirven en `/api/web/clients/<archivo>`.
  Validación: png/jpg/jpeg/webp/svg, máximo 2 MB.
- Panel de administración: `backend/web/admin-clients.html`, ruta `GET /api/admin/clients-view`.
- La sección se muestra en `/pricing` y en `landing.html` (id `clients`) y queda **oculta
  cuando no hay logos activos**. No hay testimonios ficticios en ninguna parte.

**Rutas de auth separadas (decisión de seguridad)**
- Las páginas SaaS pasaron de `/login` y `/signup` a **`/account/login`** y **`/account/signup`**
  (archivos movidos de `app/(auth)/` a `app/account/`).
- `/login`, `/signup`, `/portal` y `/marketplace` siguen sirviendo el SPA legacy de
  anunciantes (`customer.html`) — sin cambios, sin romper ese flujo.
- Encabezado navy unificado en `/pricing`, `/account/login` y `/account/signup`.

**Export de producción regenerado**
- `npx expo export --platform web` → copiado a `backend/web/saas/` (7.7 MB).
- Diff de rutas verificado: idénticas a la versión anterior salvo
  `login.html`/`signup.html` → `account/login.html`/`account/signup.html`.
- Verificado: `/`, `/pricing`, `/account/login`, `/account/signup`, `/workspace`,
  `/login` y `/marketplace` responden 200 en el backend.

**Pruebas**: `backend/tests/test_mediaview_iter28_premium.py` — 24/24 en verde.
Flujo E2E verificado en navegador: pricing → signup → login → workspace.

## Panel de administración aclarado (junio 2026)

- El shell del panel (`web/styles.css`, `web/design-system.css`, `web/index.html`) ya era claro,
  pero muchos bloques que se construyen en JS (`web/app.js`) seguían con superficies oscuras,
  texto casi invisible sobre blanco y el acento índigo viejo.
- Script: `backend/scripts/relight_admin_panel.py` (idempotente, solo literales de color).
  Mapea: `#0f172a`/`#020617` (fondos) → `#f1f5f9`/`#e2e8f0`; `#1e293b` (bordes) → `#e2e8f0`;
  `color:#e2e8f0`/`#334155`/`#94a3b8` → texto legible; índigo `#6366f1`/`#818cf8`/`#4338ca`
  y cian neón `#22d3ee` → cian de marca `#0891b2`/`#0e7490`; `#34d399`→`#059669`,
  `#f87171`→`#dc2626`, `#fbbf24`→`#d97706`. Los scrims de los modales siguen oscuros a propósito.
- Extras: el placeholder de la campaña sin media ahora dice "Sin vista previa" en gris claro,
  y el botón "View Plans & Create Account" del login pasó de índigo casi ilegible a cian claro
  y apunta directo a `/pricing`.
- Verificado en navegador con superadmin: pestañas Screens, Pending, Users, LED Cloud
  y Managed Clients — todas claras y legibles. Cero colores prohibidos en
  `app.js`, `index.html`, `styles.css` y `design-system.css`.
- No requiere regenerar el export de Expo: estos archivos los sirve FastAPI directamente.

## Marca del cliente (logo propio) — junio 2026

- `organizations.logo_url` guarda el logo del negocio del cliente.
- Helpers en `backend/org_branding_routes.py` (`save_org_logo` / `delete_org_logo`):
  valida png/jpg/jpeg/webp/svg, máximo 2 MB, escribe en `backend/web/orgs/`
  y expone la URL pública `/api/web/orgs/<archivo>`.
- Endpoints en `workspace_routes.py`:
  `POST /api/workspace/logo` (subir/reemplazar) y `DELETE /api/workspace/logo` (quitar),
  ambos detrás del gate `require_workspace_user`.
- `POST /api/auth/customer-signup` acepta `logo_filename` + `logo_base64` opcionales,
  así el dueño puede subir su logo mientras crea la cuenta.
- Frontend:
  - `src/components/LogoPicker.tsx` — selector reutilizable con `expo-image-picker`,
    permisos pedidos solo al tocar, y botón "Abrir Ajustes" si el permiso quedó bloqueado.
  - `/account/signup` — campo opcional "LOGO DE TU NEGOCIO".
  - `/workspace/settings` — tarjeta "Tu Marca" para subir, cambiar o quitar el logo.
  - `app/workspace/_layout.tsx` — el logo y el nombre del negocio reemplazan la marca "MV"
    en la esquina del panel (escritorio y móvil).
- Demo: `backend/scripts/seed_demo_pizzeria.py` crea "Pizzería Don Luis" (Starter, 3 pantallas,
  menú de 8 productos publicado) y tiene logo cargado.

## Responsive del registro

- `/account/signup` dejó de usar `Dimensions.get('window')` (valor congelado) y ahora usa
  `useWindowDimensions()`, así reacciona al tamaño real de la ventana.
- En escritorio (>900 px) muestra dos columnas: formulario a la izquierda (máx 560 px) y un
  panel de valor a la derecha con los 4 beneficios y una vista del menú digital.
  En móvil se apila en una sola columna.

## Iteración 29 — Registro pulido, estados vacíos accionables y Equipo (RBAC de cliente)

### Arreglos de UI (P0)
- `/account/signup` en escritorio: formulario en tarjeta blanca (maxWidth 580, sombra suave),
  títulos y espaciados mayores, fondo `#F8FAFC`. `aside` en blanco.
- Se eliminó la "línea negra" al escribir: nuevo `app/+html.tsx` con CSS global
  (`outline: none` en inputs/botones) + `outlineStyle: 'none'` en los estilos de input.
- Teléfono con formato automático `555-123-4567` (`formatPhone` en signup.tsx).

### Estados vacíos con acción (P1)
- Componente compartido `src/components/EmptyState.tsx` (icono, copy, CTA primario y secundario).
- Horarios → "Crear Playlist" (abre el constructor con `/workspace/playlists?new=1`).
- Contenido → "Subir Contenido" (expo-image-picker → `POST /api/media/upload` en base64, hasta 10 fotos).
- Playlists → "Crear Playlist" / "Subir contenido primero".
- `src/components/AppDialog.tsx`: diálogos propios porque `Alert.alert` es no-op en react-native-web.

### Playlists del workspace (backend nuevo, en workspace_routes.py)
- `POST /api/workspace/playlists` (valida que cada `ref_id` sea media/menú del propio org)
- `GET  /api/workspace/playlists` (ahora incluye borradores del org, no solo publicadas)
- `POST /api/workspace/playlists/{id}/publish` (screen_ids vacío = todas las pantallas del org)
- `DELETE /api/workspace/playlists/{id}`

### Equipo / RBAC de cliente (P1)
- Nuevo rol `Role.SELF_SERVICE_STAFF` en rbac.py (+ permiso `team.manage` solo para owner).
- Roles visibles al cliente: Administrador (SELF_SERVICE_OWNER), Gerente (SELF_SERVICE_MANAGER),
  Empleado (SELF_SERVICE_STAFF).
- Nuevo `backend/workspace_team_routes.py`: `GET/POST /api/workspace/team`,
  `PATCH|DELETE /api/workspace/team/{id}`, `POST /api/workspace/team/{id}/reset-password`,
  `POST /api/workspace/change-password`.
- Contraseña temporal creada por el dueño → `must_change_password: true`; `/api/workspace/*`
  responde **428** hasta que el miembro crea su contraseña en `/account/change-password`.
- Restricciones: empleado no puede facturación, pantallas, logo ni equipo; gerente sí pantallas
  pero no facturación/equipo. La barra lateral oculta "Equipo" y "Facturación" a no-dueños.
- Cambio de rol / desactivación incrementan `session_epoch` (invalidan sesiones activas).

### Pruebas
- `backend/tests/test_workspace_playlists_iter29.py`, `test_workspace_team_iter29.py`,
  `test_iter29_extra_coverage.py` — 9/9 pasan. Frontend validado por el testing agent.
- Export estático regenerado a `backend/web/saas` (incluye `/account/change-password`).

### Pendiente
- P2: Importar menú con IA desde una foto (Emergent LLM Key).
- P2: Stripe real para facturación anual.
- Menor: no existe `DELETE /api/workspace/screens/{id}`.

## Iteración 30 — Menú con IA, edición de playlists y registro de actividad

### Importar Menú con IA (foto → productos)
- `backend/menu_ai_routes.py`: `POST /api/workspace/menus/ai-import`
  (emergentintegrations · OpenAI `gpt-5.4` visión · EMERGENT_LLM_KEY).
  Acepta JPG/PNG/WebP hasta 10 MB en base64; devuelve `{menu_name, currency, items[], raw_count}`
  y **no escribe en la base**: es una vista previa editable.
- `app/workspace/menu-import.tsx`: foto → "Leyendo tu menú…" → lista editable de nombre/precio →
  "Crear Menú con N productos" (usa el `POST /api/workspace/menus` existente, `source: ai_photo`)
  y salta al editor del menú. La tarjeta "Importar con IA" reemplaza el placeholder "Pronto" en menus.tsx.
- Reglas de imagen documentadas en `/app/image_testing.md`.

### Editar Playlists (orden y duración)
- `PATCH /api/workspace/playlists/{id}` (renombrar, reordenar, cambiar duración, quitar/agregar items).
  Revalida que cada `ref_id` sea del propio org, recalcula `order`, sube `version` y refresca las pantallas.
- `app/workspace/playlist-edit.tsx`: flechas arriba/abajo, segundos por elemento (mínimo 3), quitar,
  "Agregar contenido" desde la biblioteca y total del ciclo. Se abre tocando la tarjeta en /workspace/playlists.

### Registro de Actividad
- Se reutiliza `audit_logs` vía `create_audit_log`. Nuevos eventos con `org_id`:
  menu.created/updated/deleted/published, menu_item.added/updated (con `price_from`→`price_to` y
  `photo_changed`)/deleted, media.uploaded, playlist.created/updated/published/deleted,
  screen.created/connected, org.logo_updated/removed, team.member_created/updated/password_reset/deactivated.
- `GET /api/workspace/activity?limit=` (aislado por organización) + `app/workspace/activity.tsx`
  con textos en español, detalle de cambio de precio y tiempo relativo. Enlace "Actividad" en la barra lateral.

### Pruebas
- `backend/tests/test_workspace_iter30.py` (3) + `test_workspace_iter30_extra.py` del testing agent
  (IA con imagen real, invariante de no-escritura, aislamiento entre organizaciones): 7 pasan, 1 skip esperado.
- Export estático regenerado en `backend/web/saas`.

### Pendiente
- P2: Stripe real para facturación mensual/anual.
- Menor: falta `DELETE /api/workspace/screens/{id}`; sin testIDs en menu-import/playlist-edit.

## Iteración 31 — Pantalla en Vivo, Fotos con IA y Menú por Horario

### Pantalla en Vivo (miniatura de lo que se ve ahora)
- `GET /api/workspace/now-playing`: por cada pantalla del org calcula el elemento en el aire
  (ciclo = suma de duraciones, posición = epoch % ciclo) usando `build_screen_playlist_items`,
  más `is_online` / `last_seen_seconds` desde el último heartbeat de sus dispositivos.
- `src/components/LiveScreens.tsx` + sección "En vivo ahora" en el Panel: tarjetas 16:9 con
  miniatura real (imagen), tarjeta especial para menús, badge EN VIVO/OFFLINE, contador `x/y · Ns`
  con tick local de 1 s y refresco automático cada 15 s.

### Fotos con IA para productos sin imagen
- `POST /api/workspace/menus/{menu_id}/items/{item_id}/ai-photo` en `menu_ai_routes.py`:
  Gemini `gemini-3.1-flash-image-preview` (Nano Banana) vía `send_message_multimodal_response`,
  guarda la imagen como media legacy (disco + base64) y asigna `image_url`/`media_id` al producto.
  Registra `menu_item.ai_photo` en la actividad.
- `menu-edit.tsx`: miniatura por producto, botón "Foto IA" en los que no tienen imagen y banner
  naranja "N productos sin foto" para generarlas en lote.

### Menú por Horario (dayparting)
- `PATCH /api/workspace/playlists/{id}` ahora acepta `schedule` (normalizado con
  `playlist_domain.normalize_schedule`) y `priority` (0..100). El motor `select_winning_playlist`
  ya existía, así que el player cambia de franja solo.
- `GET /api/workspace/schedules` reescrito: por playlist devuelve horario, días, `in_window`,
  `live_now`, prioridad, pantallas y estado.
- `playlist-edit.tsx`: sección "¿Cuándo se muestra?" (Todo el día / Por horario, presets
  Desayuno 06:00-11:00, Comida 11:00-17:00, Cena 17:00-23:00, horas HH:MM, días L-D y prioridad ±).
- `schedules.tsx` reescrito como parrilla de franjas con badges EN VIVO / En franja / Fuera de horario / Borrador.

### Regresión crítica arreglada
- `GET /api/menus/{id}/render` devolvía **500** para los menús del workspace (lista plana de items y
  categorías como texto): ahora se agrupan al formato del renderizador.
- `_safe_src` acepta rutas absolutas del mismo origen (`/api/player/media/...`) y sigue rechazando
  `javascript:`, `vbscript:` y `//host`. Sin esto, las fotos de los productos no se veían en pantalla.

### Pruebas
- `backend/tests/test_workspace_iter31.py` (4) + `test_workspace_iter31_extra.py` del testing agent (5): pasan.
- Frontend verificado por el testing agent, sin bugs abiertos. Export estático regenerado en `backend/web/saas`.

### Pendiente
- P2: Stripe real para facturación mensual/anual.
- Menor: falta `DELETE /api/workspace/screens/{id}`; añadir testIDs en horarios y playlist-edit.

## Iteración 32 — Producto Agotado, Promo Instantánea y Reporte Semanal

### Producto Agotado (desaparece al instante)
- `PUT /api/workspace/menus/{id}/items/{item_id}` con `available:false`: el renderizador
  (`GET /api/menus/{id}/render`) ahora **omite** los productos no disponibles, se audita
  `menu_item.sold_out` / `menu_item.restored` y se sube la versión de todas las pantallas que
  muestran ese menú para que refresquen enseguida.
- `menu-edit.tsx`: chip "Marcar agotado" en cada producto → tarjeta ámbar, nombre tachado y
  "AGOTADO · toca para reponer".

### Promo Instantánea
- `backend/promo_routes.py`: `POST /api/workspace/promos`, `GET /api/workspace/promos/active`,
  `DELETE /api/workspace/promos/{id}`. Una promo es una playlist con `is_promo`, prioridad 90 y
  `expires_at` opcional, así que gana sobre el contenido normal y al vencer todo vuelve solo
  (`_build_owned_playlist_items` filtra las expiradas).
  - `kind: "text"` genera una tarjeta 1920x1080 con Pillow en navy + cian y la guarda como media.
  - `kind: "image"` usa una foto de la biblioteca del negocio.
  - Duraciones permitidas: 15, 60, 240, 480 minutos o `null` (hasta apagarla).
- `app/workspace/promo.tsx`: pestañas Mensaje/Foto, vista previa en vivo, chips de duración,
  botón "Lanzar a N pantallas", tarjeta "PROMO EN EL AIRE" con botón de apagado.
  Banner de promo activa y acceso rápido "Lanzar Promo" en el Panel. Nav: "Promo".

### Reporte Semanal (solo en el panel, por decisión del usuario)
- `backend/workspace_reports_routes.py`: `GET /api/workspace/reports/weekly?weeks_ago=`
  (semana lunes-domingo) con datos reales de `play_logs`, `audit_logs` y heartbeats:
  totales, lo más mostrado, pantallas caídas (última señal y días sin reproducir),
  cambios del equipo por tipo, precios que cambiaron (de → a, quién) y ranking de personas.
- `app/workspace/reports.tsx` con selector de semana. Nav: "Reportes".

### Pruebas
- `backend/tests/test_workspace_iter32.py` (3) + `test_workspace_iter32_extra.py` del testing agent
  (versionado de pantallas, expiración de promo forzada, price_changes, promo con foto): 18 pasan.
- Frontend validado por el testing agent sin bugs. Export estático regenerado en `backend/web/saas`.

### Pendiente / deuda menor
- P2: Stripe real para facturación mensual/anual.
- `expo-av` sigue declarado en package.json aunque no se usa (candidato a eliminar).
- Warnings de consola: `shadow*` y `style.resizeMode` deprecados en RN Web.
- Falta `DELETE /api/workspace/screens/{id}`.

## Player Sprint 1 — Identidad, estados reales, progreso real y canal de eventos

Auditoría previa completa en `/app/memory/PLAYER_AUDIT.md`; entrega y checklist de prueba
física en `/app/memory/PLAYER_SPRINT1_REPORT.md`.

Contexto: el reproductor de TV es un **APK nativo Android/Kotlin** (`/app/android-player`,
ahora v3.3.0 / versionCode 18) que se compila en Codemagic, no la app Expo. La app Expo es
la de gestión (iOS + Android + Web). iOS/tvOS no sirve como reproductor desatendido (Apple).

1. **Seguridad de dispositivo** — `backend/device_security.py`: `device_token` emitido en
   `POST /api/devices/register` (se guarda solo el hash), exigido en heartbeat, playlist y log
   por `X-Device-Token` o `Bearer`. Modo gracia para la flota ya instalada (se adopta el primer
   token presentado). El registro rota el token porque es el punto de enrolamiento.
2. **Máquina de estados** — 17 estados canónicos compartidos: `PlayerStateMachine.kt` en el
   player y validación en el backend (`normalize_player_state`); el heartbeat reporta
   `player_state` y el panel lo muestra en español. Umbrales: heartbeat 30 s, ONLINE < 90 s,
   STALE < 5 min, OFFLINE > 5 min (`connectivity_from_heartbeat`).
3. **Progreso real de sincronización** — el player suma bytes/archivos reales del manifiesto
   (`PlayerRepository.sync`) y los envía en el heartbeat; el backend los normaliza y el panel
   dibuja "Sincronizando 62 % · 3 de 8". Se descarta si tiene más de 3 min o si el estado ya
   es PLAYING/READY (no hay porcentajes pegados).
4. **Canal de eventos** — `GET /api/events/screen/{screen_id}` (SSE) implementado: eventos
   `hello`/`version`/`gone`, keepalive 20 s, cierre a los 10 min. El player ya llamaba a esa
   ruta y no existía, así que los cambios de contenido dependían del polling de 15 s.
5. **Honestidad en el panel** — si el reproductor no está en línea, ya NO se muestra lo que
   "debería" verse como si fuera real: aparece "Sin señal del reproductor" y el ítem se anuncia
   como "Programado: …".

Pruebas: `backend/tests/test_player_sprint1.py` 5/5 + 21 de regresión (iteraciones 30-32).
Pendiente de validación en hardware real por el dueño (checklist de 13 pasos en el reporte).

### Deuda abierta (Sprints 2-5, en ese orden)
- Sprint 2: cola de comandos con ID/ACK/estado, línea de tiempo por pantalla con TTL,
  acciones en el panel, reconexión SSE con backoff explícito.
- Sprint 3: historial de heartbeat → uptime 24 h/7 d/30 d, alertas, Device Center.
- Sprint 4: watchdog reforzado, screenshot bajo demanda, diagnóstico, "Reemplazar reproductor".
- Sprint 5: matriz de hardware, provisión de fábrica (Device Owner), Live View.
- `check` y `update-check` seguirán sin token hasta cerrar el modo gracia.

## Iteración 33 — Panel perf + Marketplace orientación (2026-06 / sesión fork)
- **Fix P0 panel lento (producción)**: `/api/admin/campaigns` 5.47 MB→8.6 KB, `/api/screens` 610 KB→20 KB,
  `/api/admin/devices` paginado (`?limit=`, `?status=`). Causa: `advertising.photo_base64` incrustado en listados
  + lista de dispositivos sin paginar (498 "pending" fantasma). Commit `8534eef`, desplegado a `production`.
- **Marketplace (clientes QR, mediadview.com/marketplace)**:
  - Preview con la forma real de la pantalla antes de publicar (`orientationPreview` en customer.html);
    archivo con orientación incorrecta se bloquea y NO consume cambios.
  - Máximo **2 reemplazos de creativo** por publicación (`media_changes_used`), nuevo endpoint
    `PUT /api/campaigns/{id}/media`. Pantalla y fechas no cambian.
  - Eliminar publicación pagada → `status=archived`, sale de la pantalla al instante, libera slot, **sin reembolso**
    (historial de pagos intacto). `DELETE /api/campaigns/{id}`.
  - `POST /api/campaigns` y el swap rechazan (422) archivos con orientación distinta a la pantalla.
  - `/media/upload` guarda `width`/`height`/`orientation` (PIL para imagen, medida del navegador para video).
- **Player (requiere build nuevo, v3.3.1 / versionCode 19)**:
  - `/api/devices/{id}/playlist` y `/api/player/{screen}/playlist` publican `orientation`;
    `MainActivity.applyOrientation` fija la TV a esa orientación (cacheada en prefs para arranque offline).
  - `PlaybackController.applyRotationFill` escala el contenido rotado 90/270 para cubrir la pantalla
    (arregla las barras negras arriba/abajo reportadas en la TV).
- Tests: `backend/tests/test_marketplace_orientation_iter33.py` (9 passed).
- APK v3.3.0 (Build #13 Codemagic) publicado en Release `player-latest` → `https://mediadview.com/apk`.
  Respaldo del v3.2.0 en el mismo release como `mediaview-player-v3.2.0-backup.apk`.

## Iteración 34 — Auditoría de la cadena de orientación (3 niveles) + perf del player
**Nivel 1 (superadmin panel)**: `editAdminScreen()` no inicializaba `window._editOrient` y `saveScreen()`
  lo leía con fallback 'landscape' → editar cualquier otro campo (precio, dirección) volteaba la pantalla
  a horizontal en silencio. Corregido; badges de lista/detalle aceptan `specs.orientation` y el legado.
**Nivel 2 (workspace SaaS)**: `/workspace/screens` y `/workspace/screens/connect` guardaban la orientación
  en el nivel superior (o no la guardaban) mientras todos los lectores usan `specs.orientation` → las
  pantallas verticales de clientes SaaS siempre se reproducían horizontales. Ahora escriben
  `specs.orientation`; `screen_orientation()` acepta el campo legado; nuevo
  `PATCH /api/workspace/screens/{id}` (renombrar / cambiar orientación, hace bump de playlist_version).
  UI Expo: selector de orientación al conectar + chip por tarjeta para cambiarla.
**Nivel 3 (player)**: los 3 payloads de playlist resuelven la orientación con `screen_orientation()`.
  Tarjeta de dispositivo del panel muestra orientación/resolución/versión reales del TV.
  APK v3.3.3 (build #16): la Activity se queda en landscape nativo (1920x1080) y rota el *content host*
  90° para pantallas verticales — antes `setRequestedOrientation(PORTRAIT)` daba una ventana 608x1080.
**Perf crítico**: `/api/player/{screen}/playlist` tardaba **36 s** en producción porque cada item hacía
  `find_one` completo sobre `media`, cuyos documentos legado llevan el archivo en base64 (`data`).
  Con `MEDIA_METADATA_PROJECTION` bajó a **0.33 s** (también `/export`: 36 s → 0.27 s).
**Hallazgo pendiente (P0 de contenido)**: los 8 campaigns de la pantalla "anuncio publico" están excluidos
  porque sus archivos NO existen en disco (`/app/backend/media/*.jpeg`). El disco de Render es efímero:
  cada deploy borra los medios. Hay soporte de R2 en el código (`scripts/migrate_media_to_r2.py`,
  `storage: r2`) pero sin credenciales en producción → fallback a disco. **Requiere object storage.**
- Tests: `backend/tests/test_orientation_chain_iter34.py` (10 passed).
**Recuperación de contenido (mismo día)**: el playlist descartaba medios cuyo archivo en disco fue borrado
  por el deploy, aunque Mongo conserva el base64 y `/api/player/media/{id}` sí lo sirve. Con
  `_media_has_inline_bytes()` la pantalla "anuncio publico" pasó de **0 → 5 items** en producción
  (verificado; los 3 primeros medios descargan 119-208 KB con HTTP 200).
  Test: `backend/tests/test_playlist_diskless_iter34.py`.

## Iteración 35 — Subida de video por chunks (bug "Load failed")
- Síntoma del usuario: en `mediadview.com/marketplace`, al subir un VIDEO daba "error / Load failed"
  ("Load failed" es el error genérico de fetch en Safari/iOS).
- Causa: el marketplace mandaba el archivo completo en base64 en un solo `POST /api/media/upload`;
  un video de teléfono no cabe en memoria del navegador ni pasa por el proxy.
- Fix: subida por partes de 2 MB —
  `POST /api/media/chunk/init` (valida tipo/tamaño/duración ANTES de mover bytes),
  `POST /api/media/chunk/{id}` (body binario crudo, devuelve `percent`),
  `POST /api/media/chunk/{id}/complete` (verifica tamaño + magic bytes y registra el media).
  El marketplace usa la ruta por chunks para video o cualquier archivo > 3 MB, con barra de progreso.
- Tests: `backend/tests/test_chunked_upload_iter35.py` (7 passed, incluye comparación byte a byte).
- Verificado por testing_agent: 26/26 backend + E2E en navegador (video 4.6 MB sube, progreso 45%,
  botón habilitado, campaña enviada) y sin regresiones de orientación.
- Verificado en PRODUCCIÓN por API: video de 4.6 MB sube en 3 chunks y `/api/player/media/{id}`
  devuelve los 4 615 981 bytes idénticos en 1.8 s.
- Pendiente relacionado: los videos legacy NO guardan copia base64 en Mongo, así que un deploy
  sigue borrando videos del disco (las imágenes ya están cubiertas). R2 sigue siendo el fix definitivo.

## Iteración 37 — Video en el player: rayas de color y clip cortado (APK v3.4.0)
- Síntoma del usuario (video del TV): al reproducirse un video se oía el audio pero la imagen salía
  con rayas/bandas verdes-moradas y tearing; además el video se cortaba antes de terminar.
- Causa 1 (rayas): `PlaybackController.prepareVideo()` creaba `PlayerView(activity)`, que usa
  **SurfaceView** por defecto. Un SurfaceView vive en su propia capa de hardware, así que
  `view.rotation` (orientación de la pantalla) y la animación de `alpha` (cross-fade) NO se aplican
  a los frames decodificados → en cajas Android TV eso pinta basura/rayas.
  Fix: `res/layout/video_surface.xml` con `app:surface_type="texture_view"` e inflado en
  `prepareVideo()`. Un TextureView se compone como una vista normal, así que rotación + fade funcionan.
- Causa 2 (video cortado): `scheduleAdvance()` usaba siempre `item.durationSeconds` (metadato de la
  campaña, normalmente 10 s) también para videos.
  Fix: `scheduleAdvance(item)` — para VIDEO calcula el tiempo real restante (`player.duration`) y si
  aún no se conoce no programa temporizador y espera `STATE_ENDED`.
- Versión: v3.4.0 (versionCode 22). Rama `player-v3.4.0` (Codemagic ahora dispara con `player-v*`).
- No compilable en este entorno (no hay SDK Android): validación = build de Codemagic + prueba física.
- Publicado: APK v3.4.0 (release, build GitHub Actions run 34137380145) en el Release `player-latest` → https://mediadview.com/apk (8.5 MB, verificado 302 + descarga 200).

## Iteración 38 — SSE unificado (una sola implementación de /api/events/screen/{id})
- Había dos handlers: el de Sprint 1 en `server.py` (`hello`/`version`, registrado primero) y el
  genérico de `realtime.py` (`connected`/`playlist.updated`). El player solo sincroniza con
  `playlist.updated`/`reload`, así que la ruta de Sprint 1 lo dejaba sin tiempo real (bug latente).
- Se elimina la ruta de `server.py`. Queda solo `realtime.py`, que ahora además vigila
  `playlist_version` en Mongo (reader registrado por `server.py`) para que un bump hecho por otro
  proceso o instancia también emita `playlist.updated`.
- Tests: `backend/tests/test_sse_single_channel_iter38.py` (3 passed) + Sprint 1 e iteración 9 (11 passed).
  Suite completa: 479 passed / 15 failed (rate limit y datos de prueba; 2 fallos preexistentes verificados con git stash).
- Login de workspace verificado E2E en navegador (testws@test.com → /workspace).

## Unificación de ramas (2026-09-08)
- `production` = `main` = `trunk` = una sola línea de historia. Producción corre `622da1a`
  (merge con árbol de trunk): Sprint 1 + workspace SaaS + SSE unificado ya están en vivo.
- Verificado post-deploy: /api/livez con el sha del merge, /api/workspace/team 401 (antes 404),
  SSE con connected, /apk 302, panel admin con 29 pantallas y 200 dispositivos sin spinners,
  marketplace OK y heartbeats de players reales entrando (modo gracia del device token).
- Pendiente menor: la variable ENVIRONMENT del servicio en Render devuelve "staging".

## Refactor Fase 2B-10 (2026-06) — `/payments*`, `/widgets/*`, `/certification/*`
- 7 rutas fuera de `server.py` en 3 archivos por dominio: `payments_routes.py` (3 rutas +
  `PaymentCreate`), `widgets_routes.py` (2 rutas + `_safe_iframe/_safe_css_color/_safe_js_str/`
  `_safe_yt_id` + cache de clima) y `certification_routes.py` (2 rutas + `CertificationResult`).
- `server.py`: 2501 → 2243 líneas (acumulado 7106 → 2243, −68,4 %). Rutas de `api_router` 34 → 27.
- Decisión de alcance: `/screen` y `/screen/legacy` (FileResponse de una línea) se quedan en
  `server.py` para siempre, junto al resto de páginas estáticas/SPA.
- Limpieza empaquetada: `typing.List` e `import json` muertos en `server.py`; 4 líneas de
  docstring resangradas en `public_api_routes.py`.
- Verificación: 12/13 unidades idénticas byte a byte (`verify_relocation.py`); la única distinta
  (`widget_weather_proxy`) sólo con los 2 fixes cosméticos documentados. `ruff check backend`
  limpio, `flake8` sin F821, `test_route_inventory.py` en verde sin regenerar el snapshot
  (md5 `698364b3…`), suite con los mismos 42 fallos de la línea base (491 passed).
- Commit `b5c6238` en `trunk` y `main`. `production` sin tocar.
- Falta para cerrar la Fase 2B: las 4 rutas `/auth/*` (requieren consultar al integration expert
  antes de tocarlas).

## Refactor Fase 2B-11 (2026-06) — `/auth/*` legacy v1 → FASE 2B CERRADA
- 4 rutas legacy v1 (`register`, `login`, `/auth/me`, `PUT /auth/profile`) + `verify_password`
  + 3 modelos fuera de `server.py` → `auth_routes.py`. `/api/auth/*` v2 (`auth_v2.py`) intacto.
- `server.py`: 2243 → 2140 líneas (acumulado 7106 → 2140, −69,9 %). Rutas `api_router` 27 → 23.
- `hash_password` y `create_token` se quedan en `server.py` (los importa `finance.py` y
  `superadmin_routes.py` con `from server import hash_password` en tiempo de llamada).
- Paso previo obligatorio: consultado el integration expert antes de tocar auth. Verificado que
  el limiter es el MISMO objeto (`auth_routes._rl is rate_limit.limiter`), orden de decoradores
  intacto y tabla de rutas idéntica (489 entradas, diff vacío).
- Verificación: 8/8 unidades idénticas byte a byte, ruff limpio, flake8 sin avisos en el nuevo,
  route inventory sin regenerar snapshot, suite con los mismos 42 fallos base.
- Pruebas en vivo: registro/login/me/profile OK, duplicado 400, sin token 401, lockout de
  auth_v2 a la 6.ª clave mala (429) y rate limit de slowapi a los 20 registros (429).
- FASE 2B CERRADA: en `server.py` sólo quedan las ~20+2 páginas estáticas/SPA, por decisión.
- Siguiente: Fase 2C (mover módulos a `backend/domains/<dominio>/`).

## Fix (2026-06) — Subida pública por token acepta multipart real
- `POST /api/public/playlists/{token}/media` ya no revienta con 500 (`UnicodeDecodeError`) al
  recibir `multipart/form-data`: nuevo helper `_parse_media_upload()` en `public_api_routes.py`
  que acepta el JSON+base64 de siempre Y multipart real (campo `file` + `width`/`height`
  opcionales). Otro content-type → 415 limpio. Cierra el hallazgo abierto desde la Fase 2B-8.
- Alcance: sólo el endpoint público/invitado. `/media/upload` autenticado y
  `backend/web/public-playlist.html` sin tocar (este último sigue mandando JSON).
- Cambio de comportamiento declarado: el chequeo de `allow_upload` corre antes de leer el body,
  así que un link deshabilitado responde 403 siempre (antes podía dar 422 con body inválido).
  `/docs` pierde el schema autogenerado de esta ruta.
- Verificado en vivo (9 casos) + integridad del archivo (sha256 y tamaño idénticos al original,
  64×48 medido por PIL), ruff limpio, route inventory sin regenerar, suite con los 42 fallos base.

## Feature (2026-06) — Desvincular pantalla + `server_url` para repuntar TV boxes
- `DELETE /api/workspace/screens/{screen_id}`: inverso de `/screens/connect`. Borra la pantalla
  de la org y libera los dispositivos vinculados (los deja `pending` con código de activación
  nuevo, sin borrar el registro), y limpia el `screen_id` de playlists y menús. Roles owner y
  manager, scoping por `organization_id`, auditoría `screen.unlinked`.
- Panel del cliente (`frontend/app/workspace/screens.tsx`): chip rojo «Desvincular» por tarjeta
  + modal de confirmación + estado de éxito. Verificado en vivo: 19 → 18 pantallas.
- `GET /api/devices/{device_id}/check` ahora devuelve `server_url` (config
  `app_config.player_server.server_url` → env `PLAYER_SERVER_URL` → `null`), para repuntar una
  TV box a otro backend sin tocarla físicamente. Se gestiona con `POST`/`GET
  /api/admin/player-server` (solo admin, valida el esquema http/https).
  Pendiente: que el player Kotlin lea ese campo.
- Snapshot de rutas regenerado a propósito (492 → 495): 3 rutas nuevas, 0 eliminadas.
- Test nuevo `backend/tests/test_screen_unlink_and_server_url.py` (5 casos, todos en verde).

## Deploy (2026-06) — `trunk` → `production` (`622da1a` → `f8474ee`)
- Autorizado explícitamente por duarte. Tag de respaldo `pre-merge-622da1a` en el remoto para
  rollback. Merge limpio, árbol idéntico a `trunk`.
- Incluye: Fase 2A/2B completa (server.py 7106 → 2140 líneas), fix de subida multipart, los 2
  fixes de R2 en render.yaml (bucket `mediaview-media`, `R2_PUBLIC_BASE_URL` vacío) y las 2
  features nuevas (desvincular pantalla, `server_url` en el check del dispositivo).
- Producción verificada: `/api/livez` 200 con `version f8474ee`, `/api/ready` 200 con mongo,
  storage (driver `r2`), redis y worker en verde; landing y panel 200; rutas nuevas respondiendo
  401/422 sin auth; el bundle del panel reconstruido incluye la feature de desvincular.

## Bug fix (2026-06) — «Importar Menú con IA» daba 500 en producción
- Causa: `ModuleNotFoundError: No module named 'emergentintegrations'`. El paquete no está en
  PyPI público ni en `requirements.txt`, así que la imagen de Docker de producción nunca lo tuvo
  (en el pod de desarrollo viene preinstalado). `EMERGENT_LLM_KEY` ya estaba cargada.
- Fix: paso `RUN` nuevo en el `Dockerfile`:
  `pip install --no-deps emergentintegrations==0.2.0 --extra-index-url <índice de Emergent>`.
  El `--no-deps` es obligatorio: la metadata exige `stripe<15` y degradaría el `stripe==15.3.0`
  de requirements.txt, rompiendo la facturación. Las 6 dependencias reales ya están pineadas.
- Verificado: paso del build simulado en un directorio aislado (importa OK, stripe y openai
  intactos) y el endpoint devolviendo 200 con los 5 productos extraídos de una foto de menú.
- La comprobación final es en producción, tras el próximo deploy (sólo Render construye la imagen).
- Desplegado a production (`f8474ee` → `567b338`): livez 200 con esa versión, ready 200 (mongo,
  storage r2, redis, worker), `ai-import` sin token 401. Falta sólo la confirmación funcional de
  duarte desde el panel de producción.

## Revert (2026-06) — `server_url` fuera del contrato de `/api/devices/{id}/check`
- duarte reportó que tras instalar la APK el equipo «se desconecta» (la TCL vuelve a su propio
  video) y el contenido no llega a la pantalla, y pidió volver al mismo payload de antes.
- Revertido: la clave `server_url` de `/check`, el helper `_player_server_url()` y los endpoints
  `POST`/`GET /api/admin/player-server`. La feature de desvincular pantalla se mantiene.
- Añadido test de contrato (`TestDeviceCheckContract`) que congela las claves de `/check` en sus
  dos estados (6 en `pending`, +`screen_resolution` en `active`), para que ningún cambio futuro
  del payload rompa al player sin avisar.
- Sospechoso principal restante, del lado del player (otro agente): la APK v3.4.0 publicada el
  2026-09-08 incluye el cambio de renderizado de video a TextureView, nunca probado en hardware.
  Rollback inmediato disponible: `mediaview-player-v3.3.2-backup.apk` del mismo release.
- Dispositivo huérfano creado durante el diagnóstico, a borrar:
  `26ba0b65-4106-4101-aae9-404ee4540952` (`client_uuid: probe-diag-0001`).

## Fix de producto (2026-06) — Reconectar un equipo a una pantalla existente
- CAUSA RAÍZ del «no llega contenido a la pantalla» que reportó duarte: `POST
  /workspace/screens/connect` siempre creaba una pantalla NUEVA. Al reinstalar la APK el player
  pierde su almacenamiento, se registra como dispositivo nuevo con código nuevo, y al enlazarlo
  nacía una pantalla vacía mientras el contenido quedaba en la vieja (que pasaba a «offline»).
  El TV mostraba su pantalla de «esperando contenido» porque su playlist tenía 0 ítems.
- Fix: `connect` acepta un `screen_id` opcional y entonces reutiliza esa pantalla (libera el
  dispositivo anterior, engancha el nuevo, `screen.reconnected` en auditoría). Sin `screen_id`,
  comportamiento idéntico al anterior.
- Panel: modal con dos pestañas, «Pantalla nueva» y «Reconectar una existente» (selector de
  pantallas del cliente). Botón «Reconectar Equipo».
- Verificado en local reproduciendo el caso: la playlist del equipo nuevo pasó de 0 a 2 ítems
  reales al reconectarlo a «Mostrador». 4 tests nuevos + suite 518 passed, sin rutas nuevas.

## Feature (2026-06) — Publicar un menú eligiendo las pantallas
- Pedido de duarte: al publicar un menú el panel debe preguntar en qué pantalla, no actualizar
  todas. Ahora «Publicar en Pantallas» abre un selector múltiple con las pantallas del cliente,
  «Seleccionar todas» con contador, las actuales marcadas como «en vivo», y el botón indica en
  cuántas se va a publicar.
- Bug de fondo arreglado en el backend: al publicar en un subconjunto, las pantallas que antes
  mostraban ese menú y ya no están elegidas se limpian (`active_menu_id = None`); antes seguían
  mostrándolo. La respuesta trae `removed_from` y el panel lo informa. Se valida que cada
  `screen_id` sea de la organización (404) y se deduplica; sin `screen_ids` sigue publicando en
  todas (compatibilidad).
- 4 tests nuevos (`backend/tests/test_menu_publish_per_screen.py`), verificado por API y en el panel.

## Fix P0 (2026-06) — El menú publicado no llegaba al TV
- CAUSA RAÍZ: `POST /workspace/menus/{id}/publish` sólo estampaba `screens.active_menu_id`, un
  campo que NINGÚN endpoint del player lee. El TV arma su contenido desde los `playlists`
  publicados que lo apuntan (`_build_owned_playlist_items`), así que publicar un menú no cambiaba
  nada en la pantalla. duarte lo reportó como «elijo la pantalla, mando y no hace el cambio».
- Fix: al publicar, el backend sincroniza un playlist propio del menú (`source_menu_id`) y lo
  publica exactamente en las `screen_ids` elegidas, con `published_at` fresco para ganar el
  desempate de `select_winning_playlist`, y hace `bump_playlist_version` en las pantallas viejas
  y nuevas para que el TV re-baje en su siguiente poll (~15 s).
- `backend/tests/test_iter42_menu_reaches_tv.py` (10 tests) asegura el contrato del player, no el
  interno: `/api/player/{screen}/playlist` tiene que traer `media_id: "menu:<id>"`.

## Feature (2026-06) — Vista previa «como se ve en el TV»
- Botón «Vista previa» en el editor de menú. Abre la misma página que renderiza el TV.
- `/api/menus/{id}/render` sigue gateado a menús publicados (H3); para los borradores el panel
  pide `GET /workspace/menus/{id}/preview`, que firma un token HMAC de 1 hora
  (`sign_menu_preview_token`, mismo patrón que los quotes de checkout). Nunca se mete un bearer
  en la URL.

## Feature (2026-06) — «Mi propio diseño»: el menú del cliente, editable
- Pedido textual de duarte: su menú ya está diseñado en JPG/PNG/PDF y quiere que la IA lo vuelva
  editable «dejando los mismos colores y tipo de letra», cambiando sólo nombres, precios y fotos;
  y que al reemplazar una foto ésta se adapte al tamaño y al contorno que ya existe.
- Flujo: `POST /workspace/menus/{id}/canvas/import` normaliza el archivo a PNG (del PDF toma la
  primera página con pymupdf a 2x), lo guarda como media y le pide el layout a
  `gemini-3.1-pro-preview`, que devuelve `box_2d` en 0-1000 por cada texto y cada foto.
- Tres decisiones que hacen que se vea como el original y no como una copia:
  1. El color que tapa el texto impreso NO se le pregunta a la IA: se muestrea con Pillow del
     anillo de pixeles alrededor de la caja (`_sample_background`). Tiene que ser exacto.
  2. El cuerpo de letra se recupera midiendo el texto ORIGINAL dentro de su caja con las fuentes
     Liberation (métricamente compatibles con Arial y Times New Roman, que es lo que pide el CSS).
     Se guarda en el campo, así retipear un precio no lo reescala.
  3. El render sólo pinta un campo si su texto cambió (`text != original_text`). Un menú sin
     editar sale pixel-idéntico al archivo que subió el cliente.
- Las fotos se recortan al centro con el aspecto del recuadro y se limitan a 2x su tamaño, así
  nada se estira y el `border-radius` detectado se respeta.
- El escenario se posiciona en pixeles del diseño original y se escala con un único
  `transform: scale()`, por lo que el resultado es idéntico en 1080p, 4K y en el celular.
- Panel: `frontend/app/workspace/menu-canvas.tsx` — lienzo con los recuadros encima, arrastrables
  y estirables (PanResponder), zoom 1x/2x/3x con scroll en ambos ejes, y un bottom sheet por
  recuadro para cambiar el texto o reemplazar la foto.
- `backend/tests/test_iter43_menu_canvas.py`: 18 tests (13 marcados `ai`, pegan al modelo real).
- `fonts-liberation` agregado al Dockerfile: sin esas fuentes la medición cae a una estimación.

## Fix P0 (2026-06) — «Cambié el precio, guardé, publiqué y la tele no cambia»
- CAUSA RAÍZ REAL (la de fondo, distinta a la del fix anterior): el player Kotlin decide si
  recargar comparando una firma de la playlist — `media_id:checksum:duration:rotation:display_mode`
  (`PlayerModels.kt:98`). Un menú viaja como una URL, así que editar un precio no cambiaba NADA de
  esa firma y el WebView seguía mostrando el precio viejo para siempre.
- Fix 1: el ítem de menú ahora lleva en `checksum` un sha256 de `menu_id + última edición`. Es un
  campo que ya existía y el player exige 64 hex (`PlayerModels.kt:68`), así que el contrato del
  APK no se toca; `ContentCache` ni siquiera verifica checksums de ítems `widget`. La URL del
  render suma `?v=<ms>` para el caché HTTP del WebView, y el render responde `Cache-Control:
  no-store`.
- Fix 2: el panel sólo subía `playlist_version` cuando se marcaba «agotado». Ahora cualquier
  edición (precio, nombre, alta o baja de producto, rename del menú, foto IA, guardado del diseño
  propio) sube la versión de las pantallas afectadas y además emite el evento realtime
  `menu.updated`, que recarga al instante las pantallas que ya tienen el menú abierto.
- Fix 3 (bug que introdujo la feature anterior): borrar un menú dejaba su playlist publicada.
  Ganaba el desempate por prioridad, no renderizaba nada y la pantalla se iba a NEGRO. Ahora el
  playlist se borra con el menú y, como red de seguridad, `_build_owned_playlist_items` cae al
  siguiente contendiente cuando el ganador no produce ningún ítem. Se limpiaron 118 playlists
  huérfanos de la base de desarrollo.
- `backend/tests/test_iter45_menu_edits_reach_the_tv.py` (13 tests) fija la firma que ve el player,
  los bumps de versión y que borrar un menú no apague la pantalla.

## Feature (2026-06) — «¿Qué está mostrando mi pantalla y por qué?»
- `GET /api/workspace/screens/{id}/now-playing` responde en castellano por qué la pantalla muestra
  lo que muestra: equipo sin enlazar, equipo apagado, sin contenido, o una playlist con más
  prioridad ganándole al menú (las promos son prioridad 90 contra 10 del menú, a propósito).
  Aplica el mismo filtro de vencimiento que el player, así no reporta como ganadora una promo
  vencida que el TV ya ignora.
- El panel lo llama automáticamente después de publicar un menú y muestra el veredicto por
  pantalla en el mismo diálogo de «¡Publicado!». Publicar ya no es un acto de fe.
- `backend/tests/test_iter44_now_playing.py` (8 tests).

## Fix (2026-06) — Subir el diseño propio fallaba en el panel web
- `FileSystem.readAsStringAsync` quedó deprecada en expo-file-system 19 (SDK 54) y tiraba el error
  en pantalla. Ahora en web se lee el `File` del navegador con `FileReader.readAsDataURL` y en
  nativo con la clase `File` nueva del filesystem.

## Fix P0 (2026-06) — 502 al subir el menú diseñado
- Síntoma: «No pudimos procesar tu diseño. Request failed with status code 502» al subir un JPG/PDF
  real desde el panel de producción.
- CAUSA RAÍZ: el servicio corre en plan `starter` de Render (512 MB) con **2 workers de uvicorn**,
  o sea ~250 MB por worker. El handler decodificaba la imagen a tamaño completo: un JPG de cámara
  de 40 megapixeles ocupa 300+ MB en RGB, y el PDF se rasterizaba con un zoom fijo de 2x (un A3 a
  300 dpi daba un pixmap de 100+ megapixeles). El worker moría por OOM y el proxy devolvía 502.
- Fixes, de arriba hacia abajo del pipeline:
  1. El navegador reduce la imagen a 2200 px de lado largo con un canvas antes de subirla. Un JPG
     de 12 MB se convierte en ~800 KB y el JSON deja de pesar 30 MB. Los PDF pasan intactos porque
     no se pueden redibujar en canvas (y suelen ser vectoriales y livianos).
  2. `Image.draft()` le pide al decodificador JPEG la imagen ya reducida, en vez de decodificar
     todo y después achicar.
  3. El zoom del PDF se calcula para caer en el tamaño del escenario (máx. 2x, mín. 1x), nunca 2x
     ciego.
  4. `Image.MAX_IMAGE_PIXELS = 25_000_000`: por encima de eso se responde 413 con un mensaje claro
     en vez de morir.
  5. `_sample_background` pasó de un loop de pixeles en Python puro a numpy — 160 campos tardaban
     segundos de CPU por campo.
- `backend/tests/test_iter46_big_uploads.py` (6 tests) sube un JPEG de 40 MP real y un PDF A3 de
  imprenta y exige que el backend conteste y siga vivo (`/api/livez`).
- Nota de producto: el diseño subido queda guardado en el menú y funciona como la plantilla del
  cliente; no hay (todavía) una biblioteca de plantillas reutilizables entre menús.

## Fix P0 definitivo (2026-06) — el 502 al subir el diseño era un TIMEOUT, no memoria
- Los arreglos de memoria ayudaron pero no eran la causa final: el modelo de visión tarda entre 15
  y 90 segundos y el proxy de adelante corta la conexión mucho antes. Cualquier ajuste dentro de
  una request síncrona iba a seguir fallando de a ratos.
- Fix estructural: `POST /workspace/menus/{id}/canvas/import` ahora **responde 202 en ~1.3 s**.
  Guarda el fondo (que el cliente ya puede ver) y lanza el análisis en un `BackgroundTask`. El
  panel hace polling a `GET /workspace/menus/{id}/canvas` y lee
  `analysis.status` (`analyzing` | `ready` | `failed`) más `analysis.error` textual.
- El fondo pasó de PNG a JPEG q92, y la imagen que se usa para muestrear el color del papel se
  decodifica DESDE ese JPEG: muestrear del original y servir el comprimido dejaba parches que no
  matcheaban.
- Si el worker se reinicia a mitad del análisis, el GET marca `failed` después de 6 minutos en vez
  de dejar el panel girando para siempre.
- `backend/tests/test_iter43_menu_canvas.py::TestTheAnalysisRunsInTheBackground` (4 tests) exige
  que la subida conteste en menos de 10 s y que el fondo ya sea visible antes de que la IA termine.

## Feature (2026-06) — Biblioteca de plantillas del cliente
- Pedido textual: «debe crear la plantilla inmediatamente que la IA reconozca toda la estructura y
  ponerla en una lista de plantillas a usar donde se pueda cambiar la foto del artículo, precio y
  nombre».
- Cuando el análisis termina bien, el backend guarda solo el layout en la colección
  `menu_templates` (`save_canvas_as_template`). Volver a subir el diseño del mismo menú actualiza
  la misma plantilla en vez de duplicarla.
- `GET /workspace/menu-templates`, `POST /workspace/menu-templates/{id}/use`,
  `PUT` (renombrar), `DELETE`. Tope de 60 plantillas por organización.
- DECISIÓN QUE NO SE PUEDE ROMPER: la plantilla y el menú NO comparten documento, y al usar una
  plantilla los recuadros se copian **con ids nuevos**. Si compartieran ids, cambiar un precio en
  un local se metería en todos los menús armados con el mismo diseño. Borrar una plantilla tampoco
  toca los menús ya armados.
- Panel: `frontend/app/workspace/menu-templates.tsx` (lista con preview del diseño, conteo de
  textos y fotos, «Usar esta plantilla», borrar) + botón «Plantillas» en el encabezado de Menús y
  una vía «Desde mi propio diseño» en el modal de crear menú.
- `backend/tests/test_iter47_menu_templates.py` (13 tests). E2E del panel validado por el agente
  de testing (iteration_44.json): la subida responde al instante, el polling detecta `ready` en
  ~9 s y la plantilla aparece sola en la lista. Cero 502.

## Feature (2026-06) — F1 Plantillas profesionales de cartelería (Pizzería), validado E2E
- Pedido: poder elegir plantillas de calidad de agencia por rubro y sólo reemplazar contenido. Se
  acordó validar primero UN rubro (Pizzería, horizontal y vertical) antes de construir los demás.
- Arquitectura: el CATÁLOGO es de MediaView y vive versionado en `backend/seed_templates/*.json`
  (se siembra en cada arranque, idempotente); el DISEÑO es la instancia del cliente (`designs`);
  el render lo hace un único motor (`backend/template_engine`). Una plantilla nueva = un JSON
  nuevo, nunca código nuevo.
- Camino al TV: el diseño viaja dentro de un playlist como `content_type: "widget"` con
  `media_url = /api/designs/{id}/render?v=<ts>` y un `checksum` sha256 que cambia con cada
  edición. El APK Kotlin no se tocó. NO cambiar este contrato.
- Panel: `signage-templates.tsx` (catálogo + filtros + vista previa a pantalla completa),
  `design-edit.tsx` (reemplazar nombre/precio/foto y publicar), `designs.tsx` («Mis diseños»).
  Acceso desde la acción rápida «Plantillas Pro» del dashboard y desde Menús.
- Ajustes de legibilidad pedidos por el usuario (regla de signage): nombres, precios y listas más
  grandes y con más contraste; la descripción se corta a dos renglones para no robarle altura a la
  foto; promo ancha con el precio al costado. Fotos del rubro regeneradas con un único «set
  fotográfico» (mismo ángulo y misma luz) y optimizadas a 1024 px (~200 KB cada una).
- BUGS DE MOTOR QUE NO SE PUEDEN REINTRODUCIR:
  1. `.hero` y `.promo` tenían `position:relative` y por orden de cascada pisaban el
     `position:absolute` de `.blk`: el bloque volvía al flujo y empujaba a los siguientes (la
     promo del tótem vertical terminaba fuera del lienzo). Los bloques ya son absolutos, ninguna
     clase de bloque declara `position`.
  2. `fitText` medía contra `clientWidth`, que incluye el padding, y cortaba el ticker.
  3. `api.ts` tenía DOS claves `nowPlaying` en `workspaceAPI` y la segunda pisaba la primera. La
     de una pantalla puntual ahora se llama `screenNowPlaying`.
- Pruebas: `backend/tests/test_iter_signage_templates.py` (19 tests, incluye el contrato del
  reproductor y el cambio de checksum al editar un precio) + E2E de panel validado por el agente
  de testing (`test_reports/iteration_45.json`).
- Pendiente: subir fotos propias desde el editor (el endpoint ya existe) y el resto de los rubros
  (comida rápida, heladería, mexicano, mariscos, farmacia, ofertas flash).
