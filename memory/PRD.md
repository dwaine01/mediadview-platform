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
