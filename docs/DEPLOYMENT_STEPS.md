# MediaDView — Deployment Steps (Semana 2 Externa)

> **Guía profesional paso-a-paso** para desplegar MediaDView desde
> `v1.0.0-rc1` a producción. Diseñada para que un operador sin contexto
> previo pueda seguirla sin errores.
>
> **Prerequisitos**: haber leído `docs/RUNBOOK.md` (operaciones) y
> `docs/PRODUCTION_READINESS_AUDIT.md` (arquitectura). Deuda técnica
> aceptada en `docs/TECHNICAL_DEBT.md`.

---

## Índice

1. [Orden estricto de configuración](#1-orden-estricto)
2. [Paso 1 · GitHub (repo + secrets)](#paso-1--github)
3. [Paso 2 · MongoDB Atlas](#paso-2--mongodb-atlas)
4. [Paso 3 · Upstash Redis](#paso-3--upstash-redis)
5. [Paso 4 · Cloudflare (DNS + R2)](#paso-4--cloudflare)
6. [Paso 5 · Resend (correo transaccional)](#paso-5--resend)
7. [Paso 6 · Sentry (observabilidad)](#paso-6--sentry)
8. [Paso 7 · BetterStack (uptime)](#paso-7--betterstack)
9. [Paso 8 · Render (deploy)](#paso-8--render)
10. [Paso 9 · Cloudflare DNS switch a Render](#paso-9--cloudflare-dns)
11. [Paso 10 · Post-deploy checklist de validación](#paso-10--post-deploy)
12. [Procedimiento de rollback](#procedimiento-de-rollback)
13. [Variables de entorno requeridas (resumen)](#variables-de-entorno-requeridas)

---

## 1 · Orden estricto

El orden importa porque cada servicio produce credenciales que el
siguiente necesita:

```
1.  GitHub          → repo + CI corre suites ANTES de tocar prod
2.  MongoDB Atlas   → produce MONGO_URL
3.  Upstash Redis   → produce REDIS_URL (con TLS)
4a. Cloudflare DNS  → verificar dominio; NS apunta a Cloudflare
4b. Cloudflare R2   → produce R2_* env vars
5.  Resend          → produce RESEND_API_KEY / SMTP_*
6.  Sentry          → produce SENTRY_DSN
7.  BetterStack     → configura monitores (usa /api/health de staging)
8.  Render          → recibe TODAS las env vars anteriores y despliega
9.  Cloudflare DNS  → apunta app.mediadview.com al hostname de Render
10. Validación      → checklist manual
```

**NO cambiar este orden.** Si un paso falla, deten-te y resuelve antes de continuar.

---

## Paso 1 · GitHub

### 1.1 Crear repo privado
1. `github.com/new` → nombre `mediadview/platform` (privado).
2. NO inicializar con README (ya tenemos el nuestro).
3. Descripción: "MediaDView SaaS platform — FastAPI + Vanilla JS + Mongo + Redis".

### 1.2 Push del código actual desde el entorno de dev
Desde el entorno donde tienes `/app`:
```
cd /app
git init  # si no lo estaba
git remote add origin git@github.com:mediadview/platform.git
git add .
git status | head -40   # verifica que NO haya .env ni credenciales
git commit -m "chore: initial import of v1.0.0-rc1"
git branch -M main
git push -u origin main
```

### 1.3 Configurar branch protection (Settings ▸ Branches)
- Branch: `main`
- ✅ Require a pull request before merging (1 approval)
- ✅ Require status checks to pass before merging:
  - `lint` · `test` · `e2e` · `validate` · `docker`
- ✅ Require branches to be up to date before merging
- ✅ Do not allow bypassing the above settings

### 1.4 Confirmar que CI corre las 5 suites
- Push cualquier PR → verificar en Actions que aparecen los jobs y todos pasan verdes.
- `lint · Ruff` · `test · smoke suites 4x` · `e2e · Playwright 14 aserciones` · `validate · secret scan` · `docker · build image`.

### 1.5 Crear tag de release candidate
```
git tag -a v1.0.0-rc1 -m "Release Candidate 1 · núcleo financiero cerrado · 6 P0 resueltos"
git push origin v1.0.0-rc1
```

---

## Paso 2 · MongoDB Atlas

### 2.1 Crear cuenta
1. `mongodb.com/cloud/atlas/register` → cuenta con email corporativo.
2. Habilitar MFA inmediatamente (Settings ▸ Security).

### 2.2 Crear proyecto + cluster
1. Nuevo proyecto: **MediaDView**.
2. Deploy cluster: **M10** (~$60/mes), región **AWS us-east-1 (N. Virginia)**.
3. Nombre del cluster: `mediadview-prod`.
4. Habilitar **Backup** (incluido en M10).
5. Habilitar **Point-in-Time Recovery**.

### 2.3 Network Access
1. Network Access ▸ Add IP Address.
2. Añadir CIDRs de Render (obtenlos de: Render Dashboard ▸ Networking ▸ Outbound IPs).
3. Descripción: "Render production egress".
4. **NO usar 0.0.0.0/0** en producción.

### 2.4 Database Access (usuario de la app)
1. Database Access ▸ Add New Database User.
2. Auth method: SCRAM (password).
3. Username: `mediadview_app`.
4. Password: generar 32 chars con `openssl rand -base64 24`.
5. Role: `readWrite` sobre database `mediadview_prod`.

### 2.5 Obtener `MONGO_URL`
1. Clusters ▸ Connect ▸ Drivers ▸ Python 3.11.
2. Copiar la SRV URI:
   ```
   mongodb+srv://mediadview_app:<PASS>@mediadview-prod.xxxx.mongodb.net/?retryWrites=true&w=majority
   ```
3. Reemplazar `<PASS>` con la real. **GUARDAR EN GESTOR DE CONTRASEÑAS.**

### 2.6 Configurar alertas
- Project ▸ Alerts ▸ Add Alert:
  - Cluster CPU > 80% for 10 min → email
  - Connections > 80% of max → email
  - Any query > 1000ms → email

---

## Paso 3 · Upstash Redis

### 3.1 Crear cuenta y base
1. `upstash.com` → cuenta con GitHub SSO.
2. Console ▸ Redis ▸ Create Database.
3. Nombre: `mediadview-prod`.
4. Region: **us-east-1** (misma que Atlas y Render).
5. Type: **Regional** (mejor performance que Global para SaaS single-region).
6. TLS: **Enabled** (obligatorio).
7. Eviction: **allkeys-lru** (cache safe).

### 3.2 Obtener `REDIS_URL`
1. Copiar de **REST API** ▸ **REDIS_URL** el string `rediss://default:XXXX@xxxx.upstash.io:6379`.
2. **GUARDAR EN GESTOR DE CONTRASEÑAS.**

### 3.3 Configurar cuotas (Free plan da 10 000 requests/día)
- Si prevés más tráfico, upgrade a **Pay-as-you-go** ($0.2 / 100K comandos).

---

## Paso 4 · Cloudflare

### 4a · DNS

1. Cuenta `cloudflare.com` con MFA.
2. Add Site → `mediadview.com`.
3. Cambia los NS del registrar del dominio a los que Cloudflare te da.
4. Espera propagación (5 min – 24 h). Verifica con `dig NS mediadview.com`.

### 4b · R2 (media storage)

1. R2 ▸ Create bucket → `mediadview-prod`.
2. Region: **Automatic** (Cloudflare la decide).
3. Public Access:
   - Settings ▸ Public Access ▸ **Custom Domain** → `r2.mediadview.com`.
   - Cloudflare crea automáticamente el DNS record.
4. CORS Policy (Settings ▸ CORS):
   ```json
   [{
     "AllowedOrigins": ["https://app.mediadview.com", "https://mediadview.com"],
     "AllowedMethods": ["GET","PUT","POST","DELETE","HEAD"],
     "AllowedHeaders": ["*"],
     "ExposeHeaders": ["ETag"],
     "MaxAgeSeconds": 3600
   }]
   ```
5. Manage R2 API Tokens ▸ Create API Token:
   - Nombre: `mediadview-prod-backend`
   - Permissions: **Object Read & Write** en `mediadview-prod`
   - TTL: 1 año
6. Guardar `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`.
7. Verificar que `R2_PUBLIC_BASE_URL=https://r2.mediadview.com` responde.

---

## Paso 5 · Resend

1. `resend.com` → cuenta.
2. Domains ▸ Add Domain → `mediadview.com`.
3. Agregar los DNS records SPF/DKIM/DMARC que Resend te da → añadirlos como TXT/CNAME en Cloudflare DNS.
4. Verify (5–10 min).
5. API Keys ▸ Create API Key → `mediadview-prod`, permiso "Send only".
6. Guardar `RESEND_API_KEY=re_...`.
7. Verificar con:
   ```
   curl -X POST 'https://api.resend.com/emails' \
     -H "Authorization: Bearer re_..." \
     -H "Content-Type: application/json" \
     -d '{"from":"no-reply@mediadview.com","to":"tu@correo.com","subject":"test","html":"<p>ok</p>"}'
   ```

---

## Paso 6 · Sentry

1. `sentry.io` → cuenta.
2. Projects ▸ Create Project → **FastAPI**, nombre `mediadview-backend`.
3. Copy `SENTRY_DSN`.
4. Alerts ▸ Create Alert:
   - New issues in project → Slack/Email
   - >20 errors/min for 3 min → PagerDuty / Slack
5. Environments: creará `production` y `staging` automáticamente cuando lleguen eventos.

---

## Paso 7 · BetterStack

1. `betterstack.com/uptime` → cuenta.
2. Monitors ▸ Create Monitor:
   - URL: `https://staging.mediadview.com/api/health` (después de deploy staging)
   - Type: HTTP(S)
   - Check every: 3 min desde 3 regiones
   - Expected status: 200
   - Expected body contains: `"status":"healthy"`
3. Repetir para `/api/ready` (con umbral más laxo — dependencias externas).
4. On-call schedule ▸ configurar quién recibe alertas.

---

## Paso 8 · Render

### 8.1 Crear cuenta + conectar GitHub
1. `render.com` con GitHub SSO.
2. Autorizar acceso solo al repo `mediadview/platform`.

### 8.2 Blueprint deploy
1. Dashboard ▸ **New** ▸ **Blueprint**.
2. Seleccionar repo `mediadview/platform` + branch `main`.
3. Render detecta `render.yaml` y muestra los 3 recursos:
   - `mediadview-api` (web)
   - `mediadview-worker` (background)
   - `mediadview-redis` (keyvalue) — **NOTA**: si ya tienes Upstash, omite este y usa el `REDIS_URL` externo (§8.4).
4. Region: **Virginia** (coincide con Atlas y Upstash).

### 8.3 Completar los secrets marcados `sync: false`
En cada servicio, pestaña **Environment**, rellenar:

| Variable | Valor |
|----------|-------|
| `MONGO_URL` | de §2.5 |
| `REDIS_URL` | de §3.2 (si usas Upstash externo) |
| `FERNET_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `R2_ACCOUNT_ID` | de §4b |
| `R2_ENDPOINT` | `https://<account_id>.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | de §4b |
| `R2_SECRET_ACCESS_KEY` | de §4b |
| `SMTP_HOST` | `smtp.resend.com` |
| `SMTP_USER` | `resend` |
| `SMTP_PASSWORD` | `RESEND_API_KEY` de §5 |
| `SENTRY_DSN` | de §6 |
| `SEED_ADMIN_PASSWORD` | genera con `openssl rand -base64 24` |
| `SEED_SUPERADMIN_PASSWORD` | genera con `openssl rand -base64 24` |
| `STRIPE_SECRET_KEY` | **DEJAR VACÍO** hasta que digas "Stripe listo" |
| `STRIPE_PUBLISHABLE_KEY` | **DEJAR VACÍO** |
| `STRIPE_WEBHOOK_SECRET` | **DEJAR VACÍO** |

### 8.4 Deploy inicial a STAGING
1. Antes de touch a producción, crear un branch `staging` en GitHub y clonar el blueprint apuntándolo a ese branch.
2. Naming: `mediadview-api-staging`, `mediadview-worker-staging`.
3. Env `ENVIRONMENT=staging`.
4. Usa un DB separado: `DB_NAME=mediadview_staging`.
5. Deploy → esperar ~5 min → verificar `curl https://mediadview-api-staging.onrender.com/api/health`.

### 8.5 Correr las suites contra staging
Desde tu laptop:
```
BASE=https://mediadview-api-staging.onrender.com python -m tests.smoke_c4_reports
# etc.
```

### 8.6 Solo si staging está verde: deploy a producción
1. Merge `staging` → `main`.
2. `main` auto-deploy a los servicios de producción.
3. **NO hagas Cloudflare DNS switch todavía** — usa la URL directa de Render primero.

---

## Paso 9 · Cloudflare DNS switch

Solo cuando el servicio de Render en producción responde 200 en `/api/health` y `/api/ready`:

1. Cloudflare DNS ▸ Records ▸ Add:
   - Type: `CNAME`, Name: `app`, Target: `<render-app-name>.onrender.com`, Proxy: **Proxied** (naranja).
   - Type: `CNAME`, Name: `api`, Target: mismo (opcional si separan dominios).
2. SSL/TLS ▸ Overview: modo **Full (Strict)**.
3. Rules ▸ Transform Rules ▸ Modify Response Header:
   - Añadir `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` si Render no lo pone (nuestro middleware ya lo pone).
4. WAF ▸ Rate Limiting Rules:
   - `POST /api/auth/*` → 5 req/min/IP → Challenge
   - `POST /api/checkout/*` → 30 req/min/IP → Log

5. Verificar en `dig app.mediadview.com` que resuelve al proxy de Cloudflare.

---

## Paso 10 · Post-deploy checklist

Marcar con `[ ]` → `[x]` al confirmar cada punto:

```
INFRAESTRUCTURA
[ ] curl https://app.mediadview.com/api/health → 200 con "healthy"
[ ] curl https://app.mediadview.com/api/ready → 200 con mongo/redis/worker verdes
[ ] Render dashboard muestra ambos servicios "Live" > 1 h sin restart
[ ] Atlas Metrics: CPU < 30%, connections < 20%
[ ] Upstash Console: commands/sec estable

SEGURIDAD (P0-A1)
[ ] securityheaders.com/?q=app.mediadview.com → grade A o A+
[ ] ssllabs.com/ssltest/analyze.html?d=app.mediadview.com → grade A+
[ ] CSP en modo enforcing (NO report-only) — verificar con curl -I

FLUJO ADMIN
[ ] Login admin con SEED_SUPERADMIN_EMAIL funciona
[ ] /api/admin/orders-view carga sin errores en console
[ ] /api/admin/reports-view muestra 12 KPI cards
[ ] LIVE indicator conecta al WebSocket
[ ] Export CSV/XLSX/PDF descarga desde el dashboard

FLUJO GUEST (con orden de prueba)
[ ] /screen/<id> carga con quote+media+intent en dev mode (LocalDevProvider)
[ ] Magic-link email llega desde no-reply@mediadview.com
[ ] Factura PDF descargable desde admin
[ ] Un refund parcial se ejecuta (dev provider) + credit note se emite

OBSERVABILIDAD
[ ] Sentry recibe test-event (forzar excepción)
[ ] BetterStack Monitor muestra 100% uptime en 15 min de observación
[ ] Render logs contienen request-ids correlacionados

DATOS
[ ] tools/reset_for_production.py --dry-run en prod → 0 usuarios demo
[ ] Ledger integrity: /api/admin/ledger/verify?currency=usd → ok:true
[ ] Superadmin password rotado tras primer login (SEED_* → SKIP_SEED=true)

ROLLBACK
[ ] Practicar 1 rollback en staging siguiendo docs/RUNBOOK.md §2
[ ] Practicar 1 restore Atlas Point-in-Time en staging
```

---

## Procedimiento de rollback

**Regla de oro**: Si `/api/health` da 5xx o Sentry > 20 errores/min en los primeros 5 min tras un deploy → rollback INMEDIATO.

Ver `docs/RUNBOOK.md §2` para el procedimiento completo. Resumen:

```
1. Render Dashboard ▸ servicio ▸ Events ▸ (deploy anterior verde) ▸ "Rollback to this deploy"
2. Esperar ~2 min → verificar curl /api/health
3. Documentar en docs/INCIDENTS/YYYY-MM-DD-hhmm.md
4. Si el deploy fallido migró datos: Atlas Point-in-Time Restore según §3 del RUNBOOK.
```

---

## Variables de entorno requeridas

Referencia completa: `backend/.env.example` (40+ vars documentadas).

**Mínimo para arrancar en Render**:
```
ENVIRONMENT=production
MONGO_URL=mongodb+srv://...
DB_NAME=mediadview_prod
REDIS_URL=rediss://...
JWT_SECRET=<generated>
FERNET_KEY=<Fernet.generate_key()>
ORDER_LINK_SECRET=<generated>
COOKIE_SECURE=true
COOKIE_DOMAIN=.mediadview.com
COOKIE_SAMESITE=Lax
CORS_ORIGINS=https://mediadview.com,https://app.mediadview.com
PUBLIC_BASE_URL=https://app.mediadview.com
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=mediadview-prod
R2_PUBLIC_BASE_URL=https://r2.mediadview.com
RESEND_API_KEY=re_...
EMAIL_FROM=notifications@mediadview.com
SENTRY_DSN=https://...@sentry.io/...
SKIP_SEED=false  # PRIMER arranque solamente
SEED_SUPERADMIN_EMAIL=admin@mediadview.com
SEED_SUPERADMIN_PASSWORD=<strong>
# ↓ Stripe queda VACÍO hasta "Stripe listo"
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
```

**Después del primer arranque exitoso**:
```
SKIP_SEED=true
# Eliminar SEED_SUPERADMIN_PASSWORD del panel Render (no hace falta más)
```

---

## Anexos

- `docs/RUNBOOK.md` — procedimientos operativos día a día
- `docs/PRODUCTION_READINESS_AUDIT.md` — auditoría infraestructura
- `docs/FINAL_PRODUCTION_REVIEW.md` — auditoría código
- `docs/P0_CLOSURE_REPORT.md` — cierre de los 6 P0
- `docs/TECHNICAL_DEBT.md` — deuda técnica (D-01 a D-05)
- `docs/BACKUP_RECOVERY.md` — plan de disaster recovery
- `docs/GO_LIVE_CHECKLIST.md` — checklist operativa
- `backend/.env.example` — plantilla de variables
- `tools/reset_for_production.py` — script de limpieza pre-deploy

---

**Cerrar este documento**: la última acción antes de considerar la
Semana 2 terminada es actualizar `docs/RUNBOOK.md §1` con los nombres
reales de los administradores on-call. Sin eso, el sistema queda sin
contactos definidos para incidentes.
