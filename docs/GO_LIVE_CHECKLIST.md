# MediAd View — GO-LIVE CHECKLIST

**Documento oficial de verificación previa al despliegue en producción.**

> Regla: ningún ítem se marca ✅ únicamente porque "esté implementado".  
> Cada ítem debe tener **verificación objetiva** (comando, captura, o URL
> pública que un tercero pueda auditar). Los 3 niveles de validación
> (unit / integration / real E2E — ver `TESTING_STANDARDS.md`) aplican a
> cualquier ítem con lógica de negocio.

**Owner del checklist**: stakeholder principal.  
**Última revisión**: (llenar al ejecutar)  
**Environment**: production (`https://api.mediadview.com` + `https://www.mediadview.com`)

---

## 0 · Pre-flight — Aprobaciones y congelación

| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Sprint 1 · Etapa B validado E2E contra Stripe Test | Existe `test_reports/stripe_live_e2e.md` con los 4 escenarios pasando |
| ⬜ | Sprint 1 · Etapa C (admin approval + facturas + reembolsos) validado | Existe informe de cierre |
| ⬜ | Todas las suites verdes | `pytest backend/tests/` → 100% pass |
| ⬜ | Congelación de código (release branch) | Tag `v1.0.0-rc.N` en Git |
| ⬜ | Backup de datos actuales | Dump de Mongo dev + R2 archived (por si hay que restaurar en emergencia) |
| ⬜ | Runbook impreso o en Notion accesible | Enlace en Slack pinned |

---

## 1 · Infraestructura

### 1.1 · Render (backend + worker)
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Servicio `mediadview-api` desplegado (Docker, plan Standard mínimo) | `render.yaml` aplicado; dashboard muestra "Live" |
| ⬜ | Servicio `mediadview-worker` desplegado (ARQ) | Log muestra `worker started` en los últimos 5 min |
| ⬜ | Autoscaling configurado (min=2 web, max=6, CPU trigger 70%) | Render → Settings → Scaling |
| ⬜ | Health check path `/api/livez` (200 esperado) | Render → Health |
| ⬜ | Health check path `/api/ready` monitoreado externamente | UptimeRobot / Better Stack pings cada 60s |
| ⬜ | Rolling deploys sin downtime | Test: deploy dummy y verificar 0 fallos HTTP durante rollout |
| ⬜ | Región primaria: **Oregon** (o la más cercana al público objetivo) | Confirmar latencia p95 < 200ms desde el mercado objetivo |
| ⬜ | Persistent disk NO usado (todo el estado en Mongo/R2/Redis) | Render → Disks (vacío) |

### 1.2 · MongoDB Atlas
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Cluster **M20** o superior (nunca M0 en prod) | Atlas → Cluster tier |
| ⬜ | Region alineada con Render | latency test < 30ms desde Render |
| ⬜ | Replica set con 3 nodos | Atlas → Clusters |
| ⬜ | Backup continuo activado con PIT recovery de 7 días | Atlas → Backup |
| ⬜ | IP allowlist: solo IPs de Render + IP fija del stakeholder | Atlas → Network Access |
| ⬜ | Usuario Mongo **con permisos mínimos** para el web-api (read-write en DB `mediaview_db`) | Atlas → Database Access |
| ⬜ | Usuario Mongo **separado para audit** (solo `insert` en `financial_audit`) | Referencia: blueprint §12 |
| ⬜ | Alertas habilitadas: CPU > 70%, memoria > 80%, storage > 80% | Atlas → Alerts |
| ⬜ | Índices creados en producción | `ensure_stripe_indexes` + `ensure_auth_indexes` corren al startup; verificar `db.stripe_events.getIndexes()` |
| ⬜ | Log de queries lentas (>500ms) revisado | Atlas → Performance Advisor |

### 1.3 · Redis
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Redis gestionado (Upstash / Render Redis / AWS ElastiCache) | NO Redis en el pod app |
| ⬜ | Modo persistente (AOF o RDB cada 1min mínimo) | Provider dashboard |
| ⬜ | Alta disponibilidad multi-AZ | Provider config |
| ⬜ | `REDIS_URL` con TLS (`rediss://`) | verificar prefijo |
| ⬜ | Password/auth token rotado y fuera de Git | Provider settings |
| ⬜ | Latencia p50 < 5ms desde Render | `redis-cli -u $REDIS_URL --latency` |
| ⬜ | Max memory policy: `allkeys-lru` (para caché) o `noeviction` (para rate-limit + slot reservations) | Nuestro uso es principalmente rate-limit + dedup → **`noeviction` recomendado** |
| ⬜ | Alertas: memoria > 80%, latencia p99 > 50ms | Provider dashboard |

### 1.4 · Cloudflare (CDN + R2)
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Zona `mediadview.com` en Cloudflare | DNS records propagados |
| ⬜ | Proxy activo (nube naranja) para `www.mediadview.com` y `api.mediadview.com` | Cloudflare → DNS |
| ⬜ | SSL mode: **Full (Strict)** | Cloudflare → SSL/TLS |
| ⬜ | HSTS habilitado (max-age 6 meses, includeSubDomains) | Cloudflare → SSL/TLS → Edge Certificates |
| ⬜ | Bucket R2 `mediadview-media` creado | Cloudflare → R2 |
| ⬜ | Public bucket URL configurada + CDN | verificar con `curl https://cdn.mediadview.com/some-key` |
| ⬜ | Vida útil de los objetos definida (Sprint 2 puede añadir lifecycle) | R2 → Object lifecycle |
| ⬜ | CORS del bucket: solo `https://www.mediadview.com` en `AllowedOrigins` | R2 → Settings |
| ⬜ | Access keys R2 rotados en las últimas 90 días | inventario de credenciales |
| ⬜ | WAF: reglas managed + rate-limit por IP para `/api/checkout/*` (nunca para `/api/webhooks/stripe`) | Cloudflare → Security → WAF |

### 1.5 · Dominios y SSL
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | `mediadview.com` registrado a nombre del titular con auto-renew | Registrar dashboard |
| ⬜ | `www.mediadview.com` → sirve el frontend | `curl -I https://www.mediadview.com` → 200 |
| ⬜ | `api.mediadview.com` → sirve el backend | `curl -I https://api.mediadview.com/api/livez` → 200 |
| ⬜ | Certificado válido por al menos 30 días | `openssl s_client -connect www.mediadview.com:443 -servername www.mediadview.com < /dev/null 2>/dev/null \| openssl x509 -noout -dates` |
| ⬜ | Redirects: `http://` → `https://`, `mediadview.com` → `www.mediadview.com` | curl con `-I -L` |
| ⬜ | DMARC / SPF / DKIM configurados si enviamos emails desde `@mediadview.com` | mxtoolbox check |

### 1.6 · Variables de entorno de producción
| ✅ | Variable | Origen | Verificación |
|---|---|---|---|
| ⬜ | `ENVIRONMENT=production` | Render env group | `curl /api/livez` reporta `env=production` |
| ⬜ | `MONGO_URL` | Atlas connection string | conexión OK en logs |
| ⬜ | `DB_NAME` | `mediaview_prod` | separado de dev |
| ⬜ | `JWT_SECRET` (48+ chars random, único a prod) | `python -c "import secrets; print(secrets.token_urlsafe(48))"` | ≥ 32 chars, distinto de dev |
| ⬜ | `ORDER_LINK_SECRET` (48+ chars random, distinto de JWT_SECRET) | ídem | verificado |
| ⬜ | `REDIS_URL` con `rediss://` | provider | ping OK |
| ⬜ | `CORS_ORIGINS=https://www.mediadview.com` (NO `*` en prod) | Render env | verificar respuesta OPTIONS |
| ⬜ | `SEED_SUPERADMIN_EMAIL` + `SEED_SUPERADMIN_PASSWORD` (contraseña ≥ 20 chars) | secreto único | login funciona |
| ⬜ | `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ENDPOINT`, `R2_PUBLIC_BASE` | Cloudflare R2 | `/api/media/presign` responde |
| ⬜ | `SENTRY_DSN` | Sentry project | eventos llegan |
| ⬜ | `STRIPE_SECRET_KEY` (sk_live_* SOLO en prod, sk_test_* en staging) | Stripe Dashboard | ver §3 |
| ⬜ | `STRIPE_PUBLISHABLE_KEY` | ídem | ver §3 |
| ⬜ | `STRIPE_WEBHOOK_SECRET` (whsec_ del endpoint de PRODUCCIÓN, distinto al de dev) | Stripe → Webhooks | ver §3 |
| ⬜ | `STRIPE_WEBHOOK_SECRET_ALLOW_EMPTY=false` (o sin definir) | verificado |
| ⬜ | Ninguna variable con valor default de desarrollo | grep del código: no `mediaview-secure-jwt-secret-2026` en prod |

### 1.7 · Backups y retención
Referencia: `docs/BACKUP_RECOVERY.md`.

| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Backup automático Mongo Atlas cada 6h con PIT 7d | Atlas → Backup |
| ⬜ | Prueba de restauración a un cluster secundario (documentada) | Report Notion |
| ⬜ | R2 versioning habilitado O bucket-espejo en otra región | R2 → Settings |
| ⬜ | Redis: snapshot diario descargado a R2 archived (`mediadview-backups`) | ARQ cron `backup_redis` (Sprint 2 puede ampliar) |
| ⬜ | Retención de logs (Render): 30 días mínimo | plan Render |
| ⬜ | Runbook de restore en `docs/BACKUP_RECOVERY.md` actualizado | fecha revisión < 90 días |

### 1.8 · Sentry (errores + performance)
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Proyecto Sentry `mediadview-api` creado | dashboard accesible |
| ⬜ | `SENTRY_DSN` en Render env group | tests: forzar excepción → aparece en Sentry |
| ⬜ | `beforeSend` con `_scrub` activo (redacción de PII) | `observability.py` → verificado por tests |
| ⬜ | Release identificado por commit SHA | Sentry release matches Render deploy |
| ⬜ | Rate: capturar 100% errors, 10% performance transactions | Sentry → Settings |
| ⬜ | Alertas: >5 errores nuevos / 5min → Slack/email | Sentry → Alerts |

### 1.9 · Health checks y alertas
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | `/api/livez` monitorizado externamente cada 60s | UptimeRobot / Better Stack |
| ⬜ | `/api/ready` monitorizado con `mongo/redis/worker` sub-checks | consumer confirma degradación granular |
| ⬜ | Alerta si `/api/livez` down 2 minutos consecutivos → SMS al stakeholder | monitor config |
| ⬜ | Alerta si `stripe_events` procesados < 90% en 15 min → Slack (posible webhook down) | Sentry / custom metric |
| ⬜ | Alerta si `orders` en `payment_processing` > 30 min → Slack (posible webhook perdido) | ARQ cron para detección |

---

## 2 · Seguridad

### 2.1 · Secretos y credenciales
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Ningún secreto en el repo git | `git log --all --full-history -p \| grep -E "sk_test_\|sk_live_\|whsec_"` → vacío |
| ⬜ | `.env` en `.gitignore` (dev y prod) | `git check-ignore backend/.env` |
| ⬜ | Todos los secretos en Render Env Group encriptado | Render → Environment |
| ⬜ | Rotación planificada cada 90 días para JWT_SECRET, ORDER_LINK_SECRET, R2 keys | calendario recordatorio |
| ⬜ | Rotación planificada cada 6 meses para Stripe API keys | ídem |
| ⬜ | Redacción validada con casos de test (`observability._redact`) | 8/8 casos pasan |
| ⬜ | Sentry NO captura headers `Authorization`, `Cookie`, `Stripe-Signature` | verificado en `observability.py` |

### 2.2 · Auth v2
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | JWT firmado con HS256 y `JWT_SECRET` >= 32 chars random | `startup_check.py` valida |
| ⬜ | Access token TTL: 15 min | `auth_v2.ACCESS_TOKEN_TTL` |
| ⬜ | Refresh token TTL: 30 días con rotación por request | `auth_v2` → `rotate_refresh` |
| ⬜ | Cookie `Secure`, `HttpOnly`, `SameSite=Lax` en prod | inspector del navegador |
| ⬜ | Brute-force protection (5 intentos → bloqueo 15 min) | `login_attempts` collection + smoke test |
| ⬜ | Family revocation en refresh reuse | `refresh_tokens.parent_jti` |
| ⬜ | Audit log de login/logout/rotate | `audit_log` collection |
| ⬜ | Password hashing bcrypt cost 12 mínimo | `auth_v2` config |

### 2.3 · CSP / HTTP headers
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | `Content-Security-Policy` restrictiva incluyendo `js.stripe.com` y `r.stripe.com` en `script-src` y `connect-src` | curl -I → header presente |
| ⬜ | `X-Frame-Options: DENY` | curl -I |
| ⬜ | `X-Content-Type-Options: nosniff` | curl -I |
| ⬜ | `Referrer-Policy: strict-origin-when-cross-origin` | curl -I |
| ⬜ | `Permissions-Policy` mínima (camera=(), microphone=(), geolocation=()) | curl -I |
| ⬜ | HSTS ya cubierto en Cloudflare (§1.4) | verificado |
| ⬜ | `Set-Cookie` con `Secure; HttpOnly; SameSite=Lax` | inspector |

### 2.4 · Rate limits
Referencia: `backend/rate_limit.py`.

| ✅ | Endpoint | Límite | Verificación |
|---|---|---|---|
| ⬜ | `POST /api/auth/v2/login` | 10/min por IP | test con `hey` o `ab` |
| ⬜ | `POST /api/auth/v2/refresh` | 60/min por IP | ídem |
| ⬜ | `POST /api/checkout/quote` | 30/min por IP | ídem |
| ⬜ | `POST /api/checkout/media` | 10/min por IP | ídem |
| ⬜ | `POST /api/checkout/create-intent` | 20/min por IP | ídem |
| ⬜ | `POST /api/webhooks/stripe` | **SIN límite por IP** — solo body cap 256KB + firma + dedup | curl 100 veces con firma válida → todas 200 |
| ⬜ | Redis backend usado en prod (no memoria in-proc) | `redis_client.is_fallback` → False |

### 2.5 · CORS
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | `CORS_ORIGINS=https://www.mediadview.com` (una lista explícita, NO `*`) | curl con `Origin: https://evil.com` → sin `Access-Control-Allow-Origin` |
| ⬜ | Métodos permitidos: `GET, POST, PUT, DELETE, OPTIONS` | verificado |
| ⬜ | Credentials: `true` (para cookies de Auth v2) | verificado |

### 2.6 · Validación de archivos (subidas)
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | MIME whitelist en `checkout_service.ALLOWED_MEDIA_MIMES` | `image/jpeg\|png\|webp\|gif`, `video/mp4\|webm\|quicktime` |
| ⬜ | Size cap 25 MB en checkout, 200 MB en admin | verificar constantes |
| ⬜ | Base64 pre-check antes de decodificar | evita OOM |
| ⬜ | **Magic numbers** (Sprint 2 · S2-01) | ⬜ backlog |
| ⬜ | **Escaneo antivirus** con estado `under_analysis` (Sprint 2 · S2-02) | ⬜ backlog |

### 2.7 · Verificación de firma Stripe
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | `stripe.Webhook.construct_event(raw_body, sig_header, secret)` presente | `stripe_routes.py` |
| ⬜ | `raw body` leído ANTES de cualquier parse | verificado en test |
| ⬜ | Body size cap 256 KB antes de parseo | verificado |
| ⬜ | Signature bad → 400 sin procesar | smoke test PASS |
| ⬜ | Signature good pero body malformado → 400 sin llegar a handlers | verificado |

---

## 3 · Stripe

### 3.1 · Cuentas y modos
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Cuenta Stripe verificada (KYC completado) | Dashboard verde |
| ⬜ | Country/currency alineado con el negocio | Dashboard → Settings |
| ⬜ | Modo Test: keys inyectadas en staging | `sk_test_*`, `pk_test_*`, `whsec_*` |
| ⬜ | Modo Live: keys inyectadas en prod | `sk_live_*`, `pk_live_*`, `whsec_*` **distinto al de test** |
| ⬜ | Safety switch `stripe_config.py` verificado — refuse test-in-prod y live-in-dev | boot logs |
| ⬜ | Ningún endpoint devuelve secret ni webhook secret | `curl /api/checkout/config` → solo publishable |

### 3.2 · Webhooks
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Endpoint prod registrado en Dashboard: `https://api.mediadview.com/api/webhooks/stripe` | Stripe → Webhooks |
| ⬜ | Eventos suscritos (Sprint 1): `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled`, `charge.refunded`, `charge.dispute.created` | Stripe → Webhooks → Events |
| ⬜ | `STRIPE_WEBHOOK_SECRET` prod separado del de test | inventario |
| ⬜ | Retries de Stripe validados (>3 días con backoff) | forzar 500 → repetición observada |
| ⬜ | TTL de 90d en `stripe_events` (dedup) | `db.stripe_events.getIndexes()` |
| ⬜ | Sprint 2: eventos de billing añadidos cuando corresponda | `invoice.paid`, `customer.subscription.*`, `setup_intent.succeeded` |

### 3.3 · Payment Element
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | `js.stripe.com/dahlia/stripe.js` cargado en `screen-public.html` | inspector browser |
| ⬜ | Publishable key expuesta SOLO por `/api/checkout/config` | verificado |
| ⬜ | Appearance theme corporativo aplicado (colors matching landing) | visual review |
| ⬜ | Pago exitoso con 4242 → Order paid → magic-link | E2E test PASS |
| ⬜ | Pago fallido → `payment_failed` → slots liberados | E2E test PASS |
| ⬜ | 3D-Secure completado sin crash → `paid` | E2E test PASS |
| ⬜ | Errores de tarjeta se muestran inline (no alert) | UX check |

### 3.4 · Billing / Products / Prices (Sprint 2)
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Productos "Subscription Plan Basic/Pro/Enterprise" creados | Stripe → Products |
| ⬜ | Prices (monthly/yearly) creados con IDs versionados | inventario |
| ⬜ | Customer Portal habilitado | Stripe → Settings → Billing |
| ⬜ | Tax mode decidido: SÍ Stripe Tax / NO por ahora | política documentada |
| ⬜ | Recurring webhook events suscritos | ver §3.2 |

### 3.5 · Verificación Test/Live antes del switch
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Boot logs muestran `mode=live` en prod | Render logs |
| ⬜ | Boot logs muestran `mode=test` en staging | Render logs |
| ⬜ | Cuenta de prueba en prod: primer $1.00 real → refund inmediato → verificar audit | operativo controlado |
| ⬜ | `/api/checkout/config` de prod devuelve `mode:"live"` | curl |

---

## 4 · Operación (Día 0)

### 4.1 · Primer administrador
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Seed `superadmin` corrido con `SEED_SUPERADMIN_EMAIL` + `SEED_SUPERADMIN_PASSWORD` fuertes | login OK |
| ⬜ | Password cambiado tras primer login (obligatorio) | política |
| ⬜ | 2FA/MFA planificado (Sprint 2 / 3) | backlog |
| ⬜ | Audit `user.login` visible en `/admin/audit` | verificado |

### 4.2 · Primer cliente (real)
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Cliente creado en CRM con todos los campos legales | `/admin/finance/clients` |
| ⬜ | Contrato firmado y guardado como PDF en `fin_contracts` | doc en Mongo |
| ⬜ | `stripe_customer_id` linkeado tras primer pago | verificado |

### 4.3 · Primera pantalla
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Pantalla registrada con `hourly_rate` correcto | `/admin/screens` |
| ⬜ | Ubicación completa (address, city, state, country, geo) | ídem |
| ⬜ | Access code + QR generados | prueba de canvas |
| ⬜ | Colorlight A40 pareado y online | `/admin/colorlight/devices` verde |

### 4.4 · Primer QR (marketplace público)
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | QR físico impreso apuntando a `https://www.mediadview.com/api/screen?code=XXXX` | verificado con phone camera |
| ⬜ | Landing carga en mobile en < 3s en 4G | Lighthouse mobile |

### 4.5 · Primera campaña (Guest Checkout real)
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Buyer completa flow con tarjeta REAL en prod | order paid |
| ⬜ | Media subida, revisada por admin y aprobada en < 4 h | política de SLA |
| ⬜ | Campaña visible en reproductor A40 dentro de la ventana programada | verificación física |
| ⬜ | `play_logs` registran el playback | Mongo |

### 4.6 · Primer pago
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | PaymentIntent aparece en Stripe Dashboard con metadata `order_id` correcto | Dashboard |
| ⬜ | Webhook procesado en < 5s desde `succeeded` | audit `stripe.event.succeeded.processed_at - received_at` |
| ⬜ | Factura interna `INV-YYYY-000001` emitida | `fin_invoices` |
| ⬜ | Email de confirmación enviado (Sprint 2 pero puede stub-earse) | inbox check |

### 4.7 · Primer reembolso
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Admin crea refund desde `/admin/finance/refunds` | UI (Etapa C) |
| ⬜ | Política aplicada correctamente (pre-approval 100%, playing partial, etc.) | verificado |
| ⬜ | `charge.refunded` webhook procesado | `refunds` collection |
| ⬜ | Order transiciona a `refunded` (si full) | Mongo |
| ⬜ | Audit del reembolso completo con: quién, por qué, cuándo, cuánto, `stripe_refund_id`, `order_id`, `invoice_id` | `financial_audit` |

---

## 5 · Monitoreo

### 5.1 · Logs
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Logs de Render enviados a un aggregator externo (Datadog / Loki / Better Stack) | dashboard |
| ⬜ | Retention 30d mínimo | verificado |
| ⬜ | Ningún log incluye secretos (test `_redact`) | grep de logs por `sk_test_`, `whsec_` → vacío |
| ⬜ | Request IDs propagados end-to-end (`X-Request-ID` en headers) | `observability.RequestIdMiddleware` |
| ⬜ | Log level default: INFO en prod, DEBUG solo en debug branches | Render env |

### 5.2 · Métricas
| ✅ | Métrica | Umbral | Dashboard |
|---|---|---|---|
| ⬜ | `http_requests_total` por status code y ruta | 5xx < 0.5% | Sentry / custom |
| ⬜ | `http_request_duration_seconds` p95 | < 500ms | ídem |
| ⬜ | `stripe_events_processed_total` por tipo | delta < 5% vs Stripe reporting | reconciliación diaria (Sprint 2) |
| ⬜ | `orders_by_status` snapshot cada 5 min | `payment_processing` < 30min |  ídem |
| ⬜ | `slot_reservations_conflicts_total` | monitorear picos anormales | Sentry |
| ⬜ | Mongo connection pool usage | < 80% | Atlas |
| ⬜ | Redis memory usage | < 70% | provider |

### 5.3 · Dashboards
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Dashboard "Business KPIs": orders/day, revenue/day, avg order value, cart abandonment | Grafana / Metabase apuntando a Mongo replica |
| ⬜ | Dashboard "Ops health": latencia p50/p95/p99, error rate, webhook lag | Sentry Performance |
| ⬜ | Dashboard "Stripe reconciliation": PaymentIntents in Stripe vs Orders in Mongo | Sprint 2 |
| ⬜ | Dashboard accesible vía SSO/passworded URL | link en Notion |

### 5.4 · Alertas
| ✅ | Alerta | Umbral | Canal |
|---|---|---|---|
| ⬜ | API down | livez fail 2min | SMS + Slack |
| ⬜ | Error rate 5xx | > 1% en 5 min | Slack |
| ⬜ | Webhook lag | > 60s en promedio | Slack |
| ⬜ | Orders atascadas en `payment_processing` | > 10 más de 30min | Slack |
| ⬜ | Mongo CPU | > 80% por 10min | Slack |
| ⬜ | Redis memory | > 85% | Slack |
| ⬜ | Certificado SSL | expira en < 21 días | email |
| ⬜ | Stripe dispute abierta | inmediato | SMS |
| ⬜ | Payout Stripe failed | inmediato | SMS |

---

## 6 · Recuperación ante desastres

### 6.1 · Restauración MongoDB
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Runbook en `docs/BACKUP_RECOVERY.md` § "Mongo restore" | fecha ≤ 90 días |
| ⬜ | RTO objetivo: 60 min | drill probado |
| ⬜ | RPO objetivo: 6h (o PIT 7d Atlas) | drill probado |
| ⬜ | Drill semestral con restauración a cluster secundario | fecha del último drill |

### 6.2 · Restauración Cloudflare R2
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Bucket versioning O bucket-espejo cross-region | R2 → Settings |
| ⬜ | Script `restore_r2.sh` en `docs/BACKUP_RECOVERY.md` | probado |
| ⬜ | RTO objetivo: 4h | documentado |

### 6.3 · Restauración Redis
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Redis snapshot diario descargado a R2 archived | ARQ cron `backup_redis` |
| ⬜ | Riesgo aceptado: pérdida de rate-limit counters + slot pending holds (inventario re-consistente vía Mongo) | política documentada |

### 6.4 · Rollback de aplicación
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Render "Manual deploy" con versión anterior probado | drill |
| ⬜ | Migraciones de Mongo idempotentes y backwards-compatible dentro de 1 versión menor | política |
| ⬜ | Feature flags donde aplique | Sprint 3 |
| ⬜ | Tag Git `v1.0.0-rc.N` mapeado a Render deploy ID | inventario |

### 6.5 · Plan de recuperación ante desastres (DR)
| ✅ | Ítem | Verificación |
|---|---|---|
| ⬜ | Documento DR firmado por el stakeholder | `docs/DR_PLAN.md` |
| ⬜ | Contactos de emergencia (Render, Atlas, Cloudflare, Stripe support) accesibles | rolodex |
| ⬜ | Comunicación de incidentes: status page (statuspage.io o Better Stack) | link público |
| ⬜ | Post-mortem template en Notion | plantilla |
| ⬜ | Simulacro anual completo (cluster loss, region outage) | fecha |

---

## 7 · Checklist de "Go / No-Go" final

**Solo si TODOS los ítems marcados ✅ pasa el "GO".**

| ✅ | Ítem crítico |
|---|---|
| ⬜ | Health checks verdes durante 48h continuas en staging clonado de prod |
| ⬜ | Prueba de carga: 100 buyers concurrentes en el marketplace público sin errores 5xx |
| ⬜ | Ninguna alerta abierta en Sentry con severity high/critical |
| ⬜ | Backup restaurado exitosamente en las últimas 2 semanas |
| ⬜ | Documentación entregada al stakeholder: `TESTING_STANDARDS`, `BACKUP_RECOVERY`, `FASE5_STRIPE_TEST_SETUP`, `GO_LIVE_CHECKLIST`, `BACKLOG_SPRINT2`, `WEBSOCKET_SCALING` |
| ⬜ | Runbook de operaciones diarias entregado (Sprint 2 puede pulirlo) |
| ⬜ | Stakeholder principal firma el go-live |

---

## 8 · Post-launch — Primeras 72 horas

- Retención de logs elevada a DEBUG durante 48h para diagnóstico fino.
- Standby técnico 24/7 (o al menos horario extendido).
- Revisión de métricas cada 4h.
- No merges a `main` durante las primeras 72h salvo hotfixes críticos.
- Comunicación con primeros clientes por WhatsApp / email para feedback directo.
- Al 4to día: retrospectiva formal → ajustes → cerrar Sprint 1 oficialmente.

---

**Firmas**  
| Rol | Nombre | Fecha | Firma |
|---|---|---|---|
| Stakeholder principal | | | |
| Tech lead | | | |
| Ops responsable | | | |

**Este documento es vivo**. Cualquier cambio de infraestructura, política de seguridad o proveedor DEBE actualizar la sección correspondiente.
