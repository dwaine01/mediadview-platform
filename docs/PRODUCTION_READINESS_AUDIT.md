# MediaDView — Plan Final de Cierre y Salida a Producción

**Documento**: `docs/PRODUCTION_READINESS_AUDIT.md`
**Fecha**: Agosto 2026 · post-aprobación C4
**Autor**: Main Agent
**Estado del proyecto**: Núcleo financiero aprobado (Fases 1–4 + Sprint 1 A/B/C0/C1/C2/C3/C4)
**Objetivo del documento**: Auditar TODOS los módulos, identificar
lo pendiente para salir a producción y presentar un plan de despliegue
externo profesional. **NO se ejecuta despliegue en este documento**.

---

## ⚙️ Corrección importante sobre el stack

MediaDView es una **plataforma web SaaS** (FastAPI + Vanilla JS SPA + MongoDB + Redis).
**NO es una app Expo/mobile.** No hay builds iOS/Android para el panel.

El único componente Android es el **reproductor Colorlight A40** y cualquier
APK de player, tratados como componentes SEPARADOS del panel web
(mismos endpoints públicos, distribución aparte).

**Despliegue objetivo**:
- Backend + Frontend (SPA): **Render** (Docker o Web Service)
- Base de datos: **MongoDB Atlas** (cluster gestionado)
- Cache/queue: **Redis** gestionado (Upstash o Render Redis)
- Assets/media: **Cloudflare R2** (ya integrado)
- CDN/WAF/DNS: **Cloudflare** frente al dominio
- Repo: **GitHub** con CI/CD hacia Render
- Dominio: **mediadview.com** (Cloudflare como registrar o DNS)
- Monitoreo: Sentry (ya integrado) + logs de Render + Cloudflare Analytics
- Correo transaccional: por definir (Resend o Postmark recomendado)

---

## 📊 Auditoría por módulo (22 áreas solicitadas)

Leyenda:
- ✅ Completado y verificado
- 🟡 Parcial / requiere ajuste antes de producción
- 🔴 Incompleto / bloqueante
- ⚪ Fuera de scope actual / Sprint 2+

### 1. 🟢 Clientes corporativos (CRM)
**Estado**: 🟡 Parcial
- Backend: colección `clients` + endpoints en `finance.py` (registro CRM heredado de fase 4)
- Frontend: tab de CRM en `/finance` legacy
- Guest checkout crea perfil "invitado" sin ligarlo automáticamente al CRM
**Pendiente para producción**:
- Unificar guest → cliente cuando repite compras (por email)
- UI dedicada para gestión de clientes corporativos (razón social, RNC, dirección fiscal)
- Endpoint `GET /api/admin/clients/{id}/history` con órdenes, facturas, refunds, ledger
**Puede quedar para Sprint 2**: Roles internos por cliente (multi-user por empresa), portal de cliente self-service
**Effort**: 2-3 días

### 2. 🟢 Contratos
**Estado**: 🟡 Parcial
- `finance.py` gestiona contratos LED Rental Agreement (heredado)
- PDF renderer con 22 cláusulas funciona
**Pendiente para producción**:
- Firma electrónica (integrar DocuSign u OpenSign) — opcional pero recomendado
- Vinculación contract ↔ orden/factura del nuevo módulo (actualmente desconectados)
**Puede quedar para Sprint 2**: Firma electrónica, plantillas por país/moneda
**Effort**: 1 día para vinculación; +3 días si se agrega firma digital

### 3. 🟢 Pantallas y dispositivos
**Estado**: 🟡 Parcial
- Modelo `screens` con location/pricing existe
- CRUD admin funcional
- Vinculación con dispositivos Colorlight A40 (`paired_device_id`)
**Pendiente para producción** (bloqueante):
- **D-02**: Campo `operating_hours_per_day` por pantalla
- Zonas horarias por pantalla (`timezone` field para agenda correcta)
- Estados de conexión en tiempo real (last_heartbeat, is_online)
- Foto de referencia + specs técnicas (resolución, pixel pitch, brillo)
**Effort**: 1 día

### 4. 🟡 Campañas
**Estado**: 🟡 Parcial
- Colección `campaigns` heredada de Fase 1
- Nueva versión via `orders` con state machine robusto
- **Duplicación**: los dos modelos coexisten. Órdenes = flujo nuevo; campañas = legacy
**Decisión requerida**: consolidar en `orders` (recomendado) o mantener ambos
**Pendiente para producción**:
- Documentar cuál modelo usa producción
- Script de migración `campaigns → orders` si se consolida
**Effort**: 2-3 días si se consolida

### 5. 🟢 Playlists
**Estado**: 🟡 Básico
- `menu-editor.html` permite composición
- Colorlight scheduler envía playlist al A40
**Pendiente para producción**:
- Multi-media por orden (hoy 1 media por orden; el nuevo flujo debería aceptar N)
- Rotación programada por franjas horarias
- Preview del playlist final desde admin
**Puede quedar para Sprint 2**: Split-screen, zonas
**Effort**: 3-5 días

### 6. 🟢 Programación de contenido
**Estado**: ✅ Completo para MVP
- `colorlight_scheduler.py` empuja playlist al player
- `slot_reservations` con TTL Redis + Mongo garantiza no double-booking
- Order state machine transita scheduled → playing → completed
**Pendiente para producción**: Worker que actualice `status = playing` cuando el player confirma reproducción real (hoy es best-effort)
**Effort**: 1 día

### 7. 🟢 QR por pantalla
**Estado**: 🟡 Parcial
- Página pública `/screen/{id}` = `screen-public.html` funciona con guest checkout
- Pendiente: generación e impresión de QR físico
**Pendiente para producción**:
- Endpoint `GET /api/screens/{id}/qr.png` (uso: `qrcode` lib Python)
- PDF imprimible con QR + info de pantalla + branding
**Effort**: 4 h

### 8. 🔴 Portal de clientes
**Estado**: 🔴 Incompleto
- Guest checkout con magic-link para VER una orden (`order-view.html`) — sí
- Portal completo con historial, facturas descargables, cambiar métodos de pago — **NO existe**
**Decisión requerida**: ¿Portal completo antes de producción, o guest-only con magic-links para MVP?
**Recomendación**: MVP con magic-links (ya funcional). Portal completo → Sprint 2
**Puede quedar para Sprint 2**: SÍ
**Effort si se hace ahora**: 5-7 días

### 9. 🟡 Notificaciones y correos
**Estado**: 🔴 Incompleto (crítico)
- Colección `notifications` recibe eventos (order.approved, refund.executed, invoice.issued)
- **NO hay worker que envíe correos reales**
- Templates HTML no existen
- WhatsApp Business API en backlog (Fase 3+)
**Bloqueante para producción**:
- Integrar proveedor SMTP (**Resend recomendado** por simplicidad y precio)
- Templates: magic-link de checkout, factura emitida, orden aprobada/rechazada, cambios solicitados, refund ejecutado, credit note
- Worker ARQ que consuma `notifications` y despache
- Emergent-managed Resend está disponible sin API key adicional
**Effort**: 2-3 días
**Cuenta externa**: Resend.com (o Postmark)

### 10. 🟢 Administración de usuarios y permisos
**Estado**: ✅ Completo
- RBAC granular con 20+ permisos en `permissions.py`
- Roles: superadmin / admin / finance / sales / content_reviewer / operations / read_only / client
- Auth v2 (HttpOnly cookies + JWT + lockout + Fernet + refresh tokens)
- Seed automático de superadmin + admin en dev, protegido en prod (requiere env)
**Pendiente para producción**:
- UI de gestión de usuarios (crear/editar/desactivar) — hay endpoints, falta pantalla
- MFA/2FA (opcional pero recomendado para admin/finance)
**Effort**: 1 día para UI; +3 días para MFA
**Puede quedar para Sprint 2**: MFA

### 11. 🟢 Reproductor Colorlight A40
**Estado**: 🟡 Parcial (funcional en dev)
- `colorlight.py` + `colorlight_player.py` + `a35_bridge.py` en el backend
- Emparejamiento con `pairing_code + pairing_secret`
- Push de playlist funcional
**Pendiente para producción**:
- Pruebas en dispositivo real (blockeante — solo hay tests unitarios)
- Página `apk-install-guide.html` (existe) revisada con instrucciones actualizadas
- Página `player-activate.html` (existe) probada con QR real
- Auto-recovery cuando pierde red (config offline)
**Effort**: 2-3 días de QA en hardware real
**Bloquea producción**: Requiere validación con al menos 1 A40 físico

### 12. 🔴 Cloudflare R2 (almacenamiento de media)
**Estado**: 🔴 Configurado en código, NO en producción
- `storage.py` con integración R2 vía boto3 + presigned URLs
- Fallback base64 en Mongo si R2 no está configurado
- Env vars requeridas: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ACCOUNT_ID`, `R2_PUBLIC_BASE_URL`
- Log actual: `R2 not configured (missing env vars) — uploads will fall back to legacy base64/disk`
**Bloqueante para producción**:
- Crear bucket R2 en Cloudflare + tokens de acceso
- Configurar CORS del bucket para tu dominio
- Configurar CDN pública frente al bucket (`r2-public.mediadview.com` o similar)
- Migrar los base64 en Mongo (si hay) a R2 (script `tools/migrate_media_to_r2.py` — a crear)
**Effort**: 4 h configuración + 1 día migración de datos si hay muchos
**Cuenta externa**: Cloudflare R2 (~$0.015/GB/mes + $0 egress)

### 13. 🔴 Datos de prueba
**Estado**: 🔴 Requiere limpieza antes de producción
- 10 users de dev (incluye demo@mediadview.com, admin.demo@mediadview.com)
- 2 screens de smoke tests (con nombres "(unknown)" - **D-03**)
- 7 orders de smoke tests
- 18 entradas ledger de smoke tests
- 5 credit notes de smoke tests
- 3 campaigns legacy de Fase 1
**Acción requerida**: Script `tools/reset_for_production.py` (a crear) que:
1. Detecta ENVIRONMENT != "dev"
2. Elimina cuentas `demo@*`, `admin.demo@*`, `superadmin@*` (o pide confirmación)
3. Vacía collections: orders, fin_invoices, fin_credit_notes, refunds, fin_ledger, campaigns, notifications, stripe_events, slot_reservations, checkout_sessions
4. RESETEA counters a 0 (`counters` collection)
5. Deja `screens` y `users` (superadmin real) intactos
**Effort**: 4 h script + verificación
**Bloquea producción**: SÍ

### 14. 🟢 Seguridad
**Estado**: ✅ Bueno, con puntos a verificar
- Auth v2: HttpOnly cookies, Fernet cifra tokens, bcrypt hash de passwords
- Rate limiting Redis en `/api/auth/*` y `/api/checkout/*`
- CORS configurado (`CORS_ORIGINS`)
- CSP + HSTS: **NO configurados** (bloqueante)
- Secrets rotation policy: **no documentada** (bloqueante suave)
- Dependency scan: **no automatizado** (recomendado)
**Pendiente para producción**:
- Headers de seguridad: CSP, X-Frame-Options, HSTS via middleware o Cloudflare Transform Rules
- Migrar SECRETS a variables de entorno de Render (**nunca commit al repo**)
- `JWT_SECRET`, `FERNET_KEY`, `ORDER_LINK_SECRET` deben regenerarse para prod
- Documentar rotación semestral de secretos
- Cloudflare WAF con rate limiting en `/api/auth/login`
**Effort**: 1 día headers + docs

### 15. 🟡 Testing completo
**Estado**: 🟡 Backend bien cubierto, frontend manual
- 44 smoke assertions C4, 18 C3, 20+ C2/C1, más `test_fase4_backend.py` (25 endpoints)
- Testing manual del guest checkout
- **NO hay** tests E2E automatizados de la SPA (Playwright)
- `stripe_live_e2e.py` pendiente de ejecutar con keys reales
**Pendiente para producción**:
- Suite Playwright para: login admin, aprobar orden, refund, exportar reporte
- Pipeline CI que corra los smoke tests en cada PR
- E2E Stripe cuando el usuario diga "Stripe listo"
**Effort**: 2-3 días Playwright + 1 día CI
**Puede quedar para Sprint 2**: E2E completo. **Obligatorio pre-prod**: pipeline CI corriendo smoke tests.

### 16. 🔴 MongoDB Atlas (migración)
**Estado**: 🔴 Actualmente Mongo local en contenedor
**Plan**:
1. Crear cluster M10 en Atlas (~$60/mes) — región cercana al usuario final (Miami/DR)
2. Configurar Network Access (IP allowlist con Render egress IPs)
3. Crear DB user con permisos mínimos (readWrite en `mediadview`)
4. Exportar `MONGO_URL` con SRV string a Render
5. Ejecutar `stripe_indexes.py::ensure_stripe_indexes` en el primer arranque (ya hace esto)
6. Configurar backup diario automático de Atlas (incluido en M10+)
7. Test de failover antes de go-live
**Effort**: 1 día + monitoreo primera semana
**Cuenta externa**: MongoDB Atlas (Free M0 para stage, M10 para prod ~$60/mes)

### 17. 🔴 Redis administrado
**Estado**: 🔴 Actualmente Redis local en contenedor
**Recomendado**: **Upstash Redis** (serverless, per-request pricing, ~$0-10/mes bajo tráfico) O Render Redis (~$10/mes fijo)
**Plan**:
1. Crear instancia con TLS obligatorio
2. Exportar `REDIS_URL` con `rediss://` y credenciales
3. Verificar ARQ worker se conecta correctamente (mismo REDIS_URL)
4. Habilitar persistencia AOF si Upstash lo permite
**Effort**: 2 h
**Cuenta externa**: Upstash.com o Render Redis

### 18. 🔴 Render (backend + frontend)
**Estado**: 🔴 No creado
**Plan**:
1. Repo GitHub push
2. Render → New Web Service → Docker/Python
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT --workers 2`
5. Health check path: `/api/health`
6. ARQ worker como Background Worker separado (mismo repo, entrypoint distinto: `python -m arq worker.WorkerSettings`)
7. Configurar TODAS las 60+ env vars (ver checklist abajo)
8. Auto-deploy on `git push main`
**Effort**: 4 h primer setup + ajustes
**Cuenta externa**: Render.com — plan Starter $7/mes por servicio (web + worker = ~$14/mes)

### 19. 🔴 Cloudflare (DNS/WAF/CDN)
**Estado**: 🔴 No configurado
**Plan**:
1. Añadir `mediadview.com` a Cloudflare (cambiar NS del registrar si aplica)
2. DNS: `A/CNAME` → Render app URL, `CNAME r2-public` → R2 public bucket
3. SSL: Full (strict) — Render ya provee cert válido
4. WAF: reglas para bloquear XSS/SQLi comunes + rate limit en `/api/auth/*`
5. Transform Rules: inyectar headers CSP/HSTS/X-Frame-Options
6. Page Rules: cache `/api/web/*` estáticos con 1 h TTL
7. Bot Fight Mode: activado
**Effort**: 4 h
**Cuenta externa**: Cloudflare (Free tier suficiente para arrancar; Pro $20/mes si se necesita WAF avanzado)

### 20. 🔴 GitHub
**Estado**: 🔴 No creado como repo dedicado (código vive en el contenedor Emergent)
**Plan**:
1. Crear repo privado `mediadview/platform`
2. `.gitignore` incluye `.env`, `__pycache__`, `*.pyc`, `media/`, `.venv/`, logs
3. **PROTEGER** archivos `.env` — nunca commit, usar `.env.example` con placeholders
4. Workflow `.github/workflows/ci.yml`: install deps → run smoke tests → auto-deploy a Render staging
5. Branch protection en `main`: require PR review + CI passing
6. Secrets de repo (para CI): `MONGO_URL_TEST`, `REDIS_URL_TEST`
**Effort**: 3 h + configuración de CI
**Cuenta externa**: GitHub (Free para privado con colaboradores limitados)

### 21. 🔴 Dominio mediadview.com
**Estado**: 🔴 Por verificar propiedad y NS
**Plan**:
1. Confirmar registrar actual (si es Cloudflare Registrar, ya está en su ecosistema)
2. Apuntar NS a Cloudflare si no está
3. Sub-dominios sugeridos:
   - `mediadview.com` → landing pública
   - `app.mediadview.com` → panel admin/finance
   - `checkout.mediadview.com` → guest checkout (opcional)
   - `api.mediadview.com` → backend (opcional, o mismo host)
   - `r2.mediadview.com` → CDN público de media
4. Verificación SPF/DKIM/DMARC para el correo de Resend
**Effort**: 2 h

### 22. 🔴 Backups
**Estado**: 🔴 No configurado en producción
- Existe `docs/BACKUP_RECOVERY.md` con plan documentado
**Plan**:
1. MongoDB Atlas: backups diarios (incluidos en M10+), retención 7 días
2. Point-in-Time Recovery habilitado en Atlas
3. Redis: no crítico (cache) — sin backup, con warmup en cold start
4. R2: versionado del bucket habilitado + lifecycle rule (retener 30 días)
5. Ledger append-only: backup separado semanal a bucket R2 diferente (contabilidad legal)
6. Snapshot antes de cada deploy mayor (Atlas manual snapshot)
**Effort**: 2 h configuración
**Costo adicional**: incluido en Atlas M10

### 23. 🔴 Monitoreo
**Estado**: 🟡 Parcial
- `observability.py`: request-id middleware + Sentry integration (opcional via `SENTRY_DSN`)
- Health endpoint `/api/health` y `/api/ready`
- Logs estructurados (stdout)
**Pendiente para producción**:
- Sentry project creado + DSN configurado (Free tier suficiente para arrancar)
- Uptime monitoring externo (**Uptime Kuma self-hosted** o **BetterStack** ~$5/mes)
- Alertas: email/Slack cuando `/api/ready` falle o Sentry vea >10 errores/min
- Cloudflare Analytics + logs 7 días
- Dashboard de métricas negocio (ya existe `/api/admin/reports-view`)
**Effort**: 4 h
**Cuenta externa**: Sentry (Free), BetterStack o Uptime Robot (Free-$5)

---

## 🚦 Resumen ejecutivo por prioridad

### 🔴 OBLIGATORIO antes de producción (bloqueantes)

| # | Ítem | Effort | Depende de |
|---|------|--------|------------|
| P0-01 | Fix D-01/D-02/D-03 (SLA, ocupación, screens unknown) | 4 h | — |
| P0-02 | Script `reset_for_production.py` + ejecutarlo | 4 h | — |
| P0-03 | MongoDB Atlas cluster + migración | 1 día | cuenta Atlas |
| P0-04 | Redis administrado (Upstash) | 2 h | cuenta Upstash |
| P0-05 | Render Web + Worker services | 4 h | GitHub repo |
| P0-06 | GitHub repo privado + CI que corra smoke tests | 4 h | — |
| P0-07 | Cloudflare R2 bucket + CORS + CDN público | 4 h | cuenta CF |
| P0-08 | Cloudflare DNS/WAF/Transform Rules | 4 h | dominio |
| P0-09 | Secrets rotados para prod (JWT/FERNET/ORDER_LINK) | 30 min | — |
| P0-10 | Headers de seguridad (CSP/HSTS/XFO) | 2 h | Cloudflare |
| P0-11 | Correo transaccional (Resend) + templates | 2 días | cuenta Resend |
| P0-12 | Sentry DSN + alertas básicas | 2 h | cuenta Sentry |
| P0-13 | Uptime monitor externo | 1 h | cuenta BetterStack |
| P0-14 | Backup verification (Atlas + R2 versioning) | 1 h | — |
| P0-15 | QA del A40 físico (playback real) | 2 días | 1 A40 disponible |
| P0-16 | Documentar runbook incidentes | 2 h | — |

**Total effort P0**: ~10 días persona (2 semanas calendario con QA en A40)

### 🟡 RECOMENDADO antes de producción (mejora significativa)

| # | Ítem | Effort |
|---|------|--------|
| P1-01 | UI de gestión de usuarios (endpoints existen) | 1 día |
| P1-02 | Vinculación contratos ↔ nuevas órdenes | 1 día |
| P1-03 | Endpoint QR PNG por pantalla + PDF imprimible | 4 h |
| P1-04 | Migrar campaigns → orders (unificar) | 2-3 días |
| P1-05 | Playwright E2E smoke suite (5 flujos críticos) | 2 días |
| P1-06 | Multi-media por orden (hoy solo 1) | 2 días |
| P1-07 | MFA para admin/finance | 3 días |

**Total P1**: ~2 semanas persona

### ⚪ Sprint 2 (aprobado para postponer)

- Stripe Billing / Subscriptions / Setup Intents / ACH / Stripe Tax
- Content validation via magic numbers (anti MIME-spoofing)
- Malware scan (ClamAV) via ARQ worker
- Portal de clientes completo (self-service)
- Firma electrónica de contratos
- WhatsApp Business API
- Split-screen / zonas en playlist
- Consolidado multi-moneda (**D-04**, requiere feed de tasas)
- Push notifications móviles (fuera de scope actual — es web)

---

## 🔑 Cuentas externas a crear (checklist)

| Servicio | Free tier suficiente? | Costo mensual estimado | Uso |
|----------|------------------------|------------------------|-----|
| GitHub | ✅ Free (repo privado) | $0 | Código + CI |
| Render | ⚠️ Requiere Starter | ~$14/mes (2 servicios) | Web + Worker |
| MongoDB Atlas | ⚠️ M0 stage / M10 prod | ~$60/mes (M10) | Base de datos |
| Upstash Redis | ✅ Free hasta 10k req/día | $0-10/mes | Cache/queue |
| Cloudflare | ✅ Free tier suficiente | $0 (o $20 Pro) | DNS/WAF/CDN |
| Cloudflare R2 | ✅ 10 GB/mes gratis | ~$1-5/mes | Storage media |
| Resend | ✅ 3000 correos/mes gratis | $0-20/mes | Email transaccional |
| Sentry | ✅ Free 5k eventos/mes | $0-26/mes | Error tracking |
| BetterStack | ✅ Free plan | $0-10/mes | Uptime monitor |
| Dominio mediadview.com | Ya adquirido | ~$10/año | DNS |
| Stripe | ✅ Free (fees por transacción) | 2.9% + $0.30 por pago | Payments (Fase B post-Stripe listo) |

**Costo mensual estimado producción MVP**: **~$90–120/mes** (todo incluido)
- Escala a ~$200–300/mes con volumen medio (Atlas más grande, Cloudflare Pro, Resend paid)
- Stripe es proporcional al revenue

---

## 🔐 Credenciales a configurar en Render (variables de entorno)

### Obligatorias (bloquean el arranque)
```
MONGO_URL=mongodb+srv://user:pass@cluster.mongodb.net/mediadview?retryWrites=true
DB_NAME=mediadview
REDIS_URL=rediss://:pass@host:6379
JWT_SECRET=<64 chars random>           # rotar cada 6 meses
FERNET_KEY=<Fernet.generate_key()>     # rotar cuidadosamente (cifra tokens)
ORDER_LINK_SECRET=<32 chars random>
ENVIRONMENT=production
PUBLIC_BASE_URL=https://app.mediadview.com
CORS_ORIGINS=https://mediadview.com,https://app.mediadview.com
COOKIE_SECURE=true
COOKIE_DOMAIN=.mediadview.com
COOKIE_SAMESITE=Lax
```

### Cloudflare R2
```
R2_ACCESS_KEY_ID=<from Cloudflare>
R2_SECRET_ACCESS_KEY=<from Cloudflare>
R2_BUCKET=mediadview-prod
R2_ACCOUNT_ID=<from Cloudflare>
R2_PUBLIC_BASE_URL=https://r2.mediadview.com
```

### Correo (Resend)
```
RESEND_API_KEY=re_...
EMAIL_FROM=notifications@mediadview.com
EMAIL_FROM_NAME=MediaDView
```

### Monitoreo
```
SENTRY_DSN=https://...@sentry.io/...
SENTRY_TRACES_RATE=0.1
SENTRY_PROFILES_RATE=0.0
APP_RELEASE=<commit-sha>       # populated automatically by Render
LOG_LEVEL=INFO
```

### Seed en producción (opcional — solo si NO existe superadmin)
```
SEED_SUPERADMIN_EMAIL=owner@mediadview.com
SEED_SUPERADMIN_PASSWORD=<strong password, rotar tras primer login>
# Al primer arranque el sistema crea el usuario y luego IGNORA estos valores
SKIP_SEED=false   # una vez creado, cambiar a true
```

### Stripe (SOLO cuando digas "Stripe listo")
```
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
PAYMENT_PROVIDER=stripe
```

**Total env vars a configurar en Render**: ~35-40

---

## 🧹 Limpieza de datos ANTES del primer arranque en prod

Ejecutar `python -m tools.reset_for_production` (a crear en P0-02):

1. `db.orders.drop()` — órdenes de smoke tests
2. `db.fin_invoices.drop()` — facturas de smoke tests
3. `db.fin_credit_notes.drop()` — notas de crédito de smoke tests
4. `db.refunds.drop()` — refunds de smoke tests
5. `db.fin_ledger.drop()` — ledger de dev (empieza limpio en prod)
6. `db.stripe_events.drop()`
7. `db.slot_reservations.drop()`
8. `db.checkout_sessions.drop()`
9. `db.notifications.drop()`
10. `db.campaigns.drop()` — decidir según decisión #4 arriba
11. `db.counters.drop()` — resetea numeración INV/CN/RFD a 1 en 2026
12. **NO tocar**: `users` (solo elimina demo@/admin.demo@ manualmente), `screens` (revisar y curar)
13. Reindexar (el startup lo hará automáticamente vía `ensure_stripe_indexes`)

Verificación post-limpieza:
```
db.orders.countDocuments({}) === 0
db.fin_ledger.countDocuments({}) === 0
db.counters.countDocuments({}) === 0
db.users.find({email: /demo|test/i}).count() === 0
```

---

## 📅 Orden exacto recomendado para desplegar

**Semana 1 · Preparación (sin usuarios reales aún)**

| Día | Tarea |
|-----|-------|
| L | Crear todas las cuentas externas (GitHub, Render, Atlas, Cloudflare, Upstash, Resend, Sentry, BetterStack) |
| L | Crear repo GitHub `mediadview/platform` (privado) — push del código actual con `.env.example` |
| M | Crear cluster MongoDB Atlas M10 en región Miami · configurar allowlist + user + backup |
| M | Configurar Upstash Redis con TLS |
| M | Crear bucket Cloudflare R2 + tokens + CORS + subdominio público `r2.mediadview.com` |
| Mi | Fix D-01, D-02, D-03 en código (~4 h) + smoke tests re-corrida |
| Mi | Escribir `tools/reset_for_production.py` + probar en Atlas staging |
| J | Deploy en Render staging (`mediadview-staging.onrender.com`) con env vars staging |
| J | Correr TODOS los smoke tests contra staging |
| V | Configurar Cloudflare DNS/WAF/Transform Rules apuntando a Render staging |
| V | Templates Resend + integración worker de notificaciones |

**Semana 2 · QA + Hardening**

| Día | Tarea |
|-----|-------|
| L | QA A40 físico con playlist real desde staging |
| M | Playwright E2E (opcional recomendado — 5 flujos) |
| M | CSP/HSTS/XFO configurados y verificados con securityheaders.com |
| Mi | Uptime monitor + alertas Sentry configuradas |
| Mi | Documentar runbook incidentes en `docs/RUNBOOK.md` |
| J | **Freeze de código** · rotación final de secretos · último smoke |
| J | Ejecutar `reset_for_production.py` en el DB de PROD (vacío) |
| V | **Go-live**: apuntar `app.mediadview.com` a Render production · verificar health |
| V | Crear superadmin real vía SEED_SUPERADMIN_* · rotar password inmediatamente · SKIP_SEED=true |
| V | Monitoreo 24h antes de anunciar |

**Semana 3+ · Post go-live**
- Sprint 2: Stripe integration (cuando el usuario diga "Stripe listo")
- Sprint 2: Ítems P1 diferidos
- Semana 3-4: A40 en producción con clientes piloto

---

## ⚠️ Riesgos identificados

| # | Riesgo | Impacto | Mitigación |
|---|--------|---------|------------|
| R-01 | Rotar `FERNET_KEY` invalidaría todos los tokens activos | Alto | Documentar procedimiento de rotación con doble-key (soportar OLD + NEW por 24h) |
| R-02 | Migración `campaigns → orders` puede perder datos | Medio | Script con dry-run + backup Atlas manual snapshot antes |
| R-03 | Sin tests E2E automatizados, un bug en checkout pasa a prod | Alto | Al menos 1 test Playwright del happy-path del guest checkout (P1-05) |
| R-04 | A40 no probado en dispositivo real | Alto | Bloquear go-live hasta QA en 1 dispositivo con playlist real |
| R-05 | Correos no llegan (SPF/DKIM/DMARC mal configurados) | Alto | Verificar en mail-tester.com antes de anunciar |
| R-06 | Sin monitoreo, no vemos caídas | Alto | BetterStack + Sentry configurados desde día 1 |
| R-07 | R2 sin lifecycle rule = costo creciente | Bajo | Regla de expiración 30 días para versiones antiguas |
| R-08 | Ledger crece indefinidamente | Bajo (largo plazo) | Sharding por año en Sprint 3 cuando >1M entradas |

---

## ✅ Definition of Done — Producción

Un despliegue se considera **listo para anunciarse** cuando:

- [ ] Todos los P0 ejecutados y verificados
- [ ] Health check verde por 24 h continuas
- [ ] Sentry recibe 0 errores no-esperados
- [ ] Un checkout guest completo funciona end-to-end (crear orden → magic-link → pago dev → aprobación admin → factura descargable)
- [ ] Un reembolso completo (single admin) funciona end-to-end en prod
- [ ] Un reembolso con doble aprobación funciona con 2 usuarios distintos
- [ ] Los 24 exports (8 reportes × 3 formatos) descargan correctamente
- [ ] Backup Atlas manual verificado (restore a staging)
- [ ] Uptime monitor reporta 100% por 24 h
- [ ] Runbook publicado y accesible al equipo
- [ ] Superadmin real con MFA (si se implementa) o password fuerte + confirmado
- [ ] Todas las cuentas demo/test/smoke eliminadas
- [ ] SSL A+ en securityheaders.com
- [ ] mail-tester.com score 10/10 para el correo saliente

---

## 📋 Documentos relacionados
- `docs/TECHNICAL_DEBT.md` — deuda registrada (D-01 a D-04)
- `docs/GO_LIVE_CHECKLIST.md` — checklist operativa creada en Sprint 1
- `docs/BACKUP_RECOVERY.md` — plan de recuperación de desastres
- `docs/TESTING_STANDARDS.md` — estándares de test agentes
- `docs/BACKLOG_SPRINT2.md` — features postponidas explícitamente
- `docs/WEBSOCKET_SCALING.md` — plan de escalado WS (post-go-live)
- `docs/FASE5_STRIPE_ARCHITECTURE.md` — arquitectura de pagos (para post-"Stripe listo")

---

## 🎯 Próximo paso propuesto

Cuando estés listo, autorízame para arrancar con la **Semana 1 · Preparación**:
1. Fix de D-01/D-02/D-03 (higiene de reportes)
2. Script `reset_for_production.py`
3. Documento `.env.example` para push a GitHub
4. Documentación del `RUNBOOK.md` inicial

Estos 4 ítems se pueden hacer completos DENTRO del ambiente de desarrollo
actual sin necesidad de que crees ninguna cuenta externa todavía.

Cuando estés listo con las cuentas externas, pasamos al despliegue real.
