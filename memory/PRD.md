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
