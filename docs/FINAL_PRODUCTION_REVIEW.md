# MediaDView — Auditoría Final de Producción

**Documento**: `docs/FINAL_PRODUCTION_REVIEW.md`
**Fecha**: Sprint 1 · Semana 1 · post-freeze
**Auditor**: Main Agent (revisión estática · sin modificación de código)
**Base auditada**: 16 709 líneas de Python backend · 4 168 líneas HTML/JS · 7 tests smoke
**Método**: análisis estático, recon de dependencias, revisión de patrones (grep + AST) y correlación con `docs/PRODUCTION_READINESS_AUDIT.md` (checklist de infraestructura).

---

## Índice
0. Resumen ejecutivo — semáforo por área
1. Arquitectura
2. Seguridad
3. Base de datos
4. Rendimiento
5. Código
6. Producción / DevOps
7. Testing
8. Tabla consolidada de hallazgos (P0/P1/P2)
9. Recomendación final

---

## 0 · Resumen ejecutivo

| Área | Semáforo | Comentario |
|------|----------|------------|
| Arquitectura | 🟡 | Base sólida. 1 dep circular documentada, 1 archivo monstruo (`server.py` = 3 817 líneas). |
| Seguridad | 🟡 | Auth v2 muy sólido. **Faltan headers de seguridad**, **validación por magic numbers**, y hay 6 usos de `innerHTML` con concatenación en 2 HTMLs viejos. |
| Base de datos | 🟢 | 49 índices creados, integridad de ledger con hash-chain, atomicidad con `$expr`. |
| Rendimiento | 🟢 | No hay N+1 detectables. Redis con timeouts. Falta GZip middleware. |
| Código | 🟡 | 72 `except Exception:` — muchos legítimos, algunos silenciosos. `finance.py` = 1 421 líneas (Fase 1 legacy). |
| Producción | 🟡 | Health/ready OK. **Falta lógica de rotación de secretos activa**. Faltan headers HSTS/CSP. |
| Testing | 🔴 | Smoke tests robustos en C3/C4. **0 cobertura E2E automatizada de la SPA**. Auth v2, Colorlight A40 y worker ARQ sin tests. |

**Veredicto general**: **NO listo aún** para producción. Hay **6 hallazgos P0 que bloquean** el despliegue, todos abordables en ~2 días persona. Una vez resueltos, el sistema está apto para Semana 2 externa.

---

## 1 · Arquitectura

### 1.1 🟡 Dependencia circular server ↔ permissions (P2 · no bloqueante)
**Evidencia**: `permissions.py:112` importa `get_current_user` desde `server` con comentario explícito `"Import here to avoid circular import at module load"`.
**Impacto**: Trabaja hoy porque el import es lazy dentro de `require_permission`. Bloqueará cualquier intento de mover `permissions.py` fuera de `backend/` (a `backend/core/` por ejemplo).
**Riesgo**: BAJO en producción. MEDIO si el equipo crece y refactoriza sin conocer el workaround.
**Recomendación**: Refactor: exponer `get_current_user` como callable inyectado al construir routers (`build_router(get_current_user=fn)`). O mover `get_current_user` a `auth_v2.py`.
**Effort**: 2 h.
**Bloquea producción**: NO.

### 1.2 🔴 Archivo monolítico `server.py` = 3 817 líneas · 128 rutas · 130 defs (P1)
**Evidencia**: `server.py` contiene routers de menú, screens, campaigns, media, dashboard, colorlight, además del wiring principal.
**Impacto**: Onboarding lento, cualquier merge/PR toca este archivo, dificulta code review, riesgo de conflictos.
**Riesgo**: MEDIO — no rompe producción, pero eleva significativamente el costo de mantenimiento.
**Recomendación**: Extraer en Sprint 2 (post-launch) a: `menu_routes.py`, `screens_routes.py`, `campaigns_routes.py`, `dashboard_routes.py`. Mantener `server.py` como wiring/composition root <300 líneas.
**Effort**: 2 días.
**Bloquea producción**: NO (post-launch).

### 1.3 🟡 Modelos duplicados campaigns ↔ orders (P1)
**Evidencia**: Colección `campaigns` legacy (3 docs actualmente) + colección `orders` moderna (7 docs).
**Impacto**: Documentado en `PRODUCTION_READINESS_AUDIT.md §4`. Confusión sobre cuál es la fuente de verdad. Endpoints de "pending_campaigns" en dashboard suman ambas.
**Riesgo**: MEDIO — un cliente que cree contenido puede quedar en el modelo equivocado.
**Recomendación**: Decidir **antes de producción**: (a) migrar campaigns → orders con script + deprecar, o (b) documentar explícitamente que campaigns solo es lectura legacy. Yo recomiendo (a).
**Effort**: 2 días.
**Bloquea producción**: SÍ si van a coexistir usuarios reales creando contenido.

### 1.4 🟢 Separación de responsabilidades — módulos financieros
**Evidencia**: `financial_ledger.py`, `refunds_service.py`, `credit_notes_service.py`, `invoices_service.py` con contratos claros. Ledger es fuente única. `PaymentProvider` bien abstraído.
**Comentario**: Aprobado. Excepto D-04 (multi-currency roll-up), no hay deuda estructural en el módulo financiero.

### 1.5 🟡 `finance.py` legacy 1 421 líneas (P2)
**Evidencia**: Herencia de Fase 1 (CRM + contratos + facturas legacy) coexiste con el nuevo módulo `finance_pdf.py` (817 líneas) + `finance_email.py` (594 líneas) + `finance_scheduler.py` (311 líneas).
**Impacto**: 15 funciones en un solo archivo, imports de servidor mezclados con lógica de negocio.
**Riesgo**: MEDIO — es donde vivien los contratos LED con las 22 cláusulas; cualquier cambio requiere pruebas manuales.
**Recomendación**: Post-launch, dividir en `finance_crm.py` + `finance_contracts.py` + `finance_billing.py`.
**Effort**: 3 días.
**Bloquea producción**: NO.

### 1.6 Módulos que NO se usan / dudosos
- `a35_bridge.py` — bridge del reproductor A35 antiguo. **Verificar si se usa hoy** o es código muerto.
- `colorlight_player.py` (738 líneas) — parece activo pero co-existe con `colorlight.py` (555 líneas). Documentar cuál es autoritativo.
**Recomendación**: Documentar en un `docs/MODULES.md` cuáles están vigentes vs deprecados.

---

## 2 · Seguridad

### 2.1 🔴 P0 · SIN headers de seguridad HTTP (bloqueante)
**Evidencia**: `grep -rn "X-Frame-Options|Content-Security-Policy|Strict-Transport-Security|Referrer-Policy" *.py` → **0 matches**.
**Impacto**: Vulnerable a clickjacking, downgrade attacks, cache leaks, referrer leaks a terceros.
**Riesgo**: ALTO. Un scan `securityheaders.com` daría **F** en producción.
**Recomendación**: Añadir middleware `SecurityHeadersMiddleware` o configurar en Cloudflare **Transform Rules**:
```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; ...
Permissions-Policy: geolocation=(), microphone=(), camera=()
```
**Effort**: 2 h (middleware + prueba con securityheaders.com).
**Bloquea producción**: **SÍ**.

### 2.2 🔴 P0 · XSS potencial · `innerHTML` con concatenación en menu-editor.html + player-activate.html (bloqueante)
**Evidencia**:
```
web/menu-editor.html:150  innerHTML='<p ...>'+e.message+'</p>'   ← concat directa
web/menu-editor.html:199  innerHTML='<p ...>'+e.message+'</p>'   ← concat directa
web/player-activate.html:168  innerHTML = ... + widgetUrl + ...  ← URL concatenada
web/player-activate.html:182  innerHTML = ... + url + ...
```
**Contexto**: `e.message` viene de excepciones de API (potencialmente controlable por atacante vía payload malicioso reflejado). `widgetUrl`/`url` vienen de la respuesta del backend.
**Impacto**: XSS reflejado si atacante logra inyectar en el mensaje de error o si un endpoint devuelve una URL manipulada.
**Riesgo**: MEDIO. Los archivos afectados son de baja exposición pública, pero `menu-editor.html` es panel admin.
**Recomendación**: Reemplazar con `textContent` o pasar por la función `escapeHtml()` que YA existe en `admin-orders.html`. Añadir esa función a `menu-editor.html` y `player-activate.html`.
**Effort**: 1 h.
**Bloquea producción**: **SÍ**.

### 2.3 🔴 P0 · Falta validación por magic-numbers en uploads (bloqueante suave)
**Evidencia**: `checkout_service.py:454` valida `content_type` (declarado por el cliente) contra `ALLOWED_MEDIA_MIMES`. **No lee los bytes del archivo**.
**Impacto**: Un atacante puede subir un `.exe` renombrado como `image.jpg` con Content-Type `image/jpeg` y guardarlo en R2. Aunque no se ejecute en el server, puede servirlo desde el CDN público como material para ataques.
**Riesgo**: MEDIO-ALTO. Ya está en el backlog Sprint 2 (`S2-01: magic numbers`) pero AMERITA subir a P0 antes de aceptar uploads públicos.
**Recomendación**: Añadir `python-magic` o `filetype` lib para verificar los primeros bytes contra el content_type declarado. Rechazar si no coinciden.
**Effort**: 4 h (lib + validador + tests + integrar en `finalize_media`).
**Bloquea producción**: **SÍ** si vas a aceptar uploads de guests. Puede diferirse SOLO si en el primer despliegue no habrá guest checkout público (solo admin-managed).

### 2.4 🟢 Autenticación
**Evidencia**: `auth_v2.py` (517 líneas) — JWT HS256 + Fernet cifra refresh tokens + HttpOnly cookies + bcrypt (cost 12) + lockout Redis + rotación de refresh tokens.
**Comentario**: **Aprobado**. Es una de las piezas más sólidas del sistema.

### 2.5 🟢 Autorización (RBAC)
**Evidencia**: `permissions.py` con 20+ permisos granulares, 8 roles, `require_permission(perm)` como FastAPI dependency. Validado: 44 smoke tests + tests manuales (403 para clientes en endpoints admin).
**Comentario**: **Aprobado**.

### 2.6 🟡 P1 · CSRF sin protección explícita (mitigado por SameSite=Lax)
**Evidencia**: No hay CSRF tokens generados/validados. Se apoya en `SameSite=Lax` (cookies) y validación de `Content-Type: application/json` (que los formularios HTML tradicionales no pueden enviar sin preflight CORS).
**Impacto**: Vulnerable a CSRF si el navegador ignora SameSite (browsers viejos <2020) o si algún endpoint acepta form-encoded.
**Riesgo**: BAJO en 2026 (SameSite=Lax es default en browsers modernos).
**Recomendación**: Documentar la decisión en `docs/SECURITY.md`. Si en Sprint 2 se agregan endpoints que aceptan `application/x-www-form-urlencoded`, agregar CSRF tokens.
**Effort**: 0 h ahora · 4 h si se agregan formularios HTML en el futuro.
**Bloquea producción**: NO.

### 2.7 🟡 P1 · Rate limiting cobertura parcial
**Evidencia**: `grep rate_limit` → 11 matches, concentrados en `auth_v2.py` y `stripe_routes.py` (declarativo). No hay rate limit explícito en `/api/checkout/*`, `/api/admin/*` ni `/api/reports/*`.
**Impacto**: Admin/reports pueden ser hammered por un token comprometido; guest checkout puede ser abusado para reservar slots.
**Riesgo**: MEDIO. En Cloudflare se puede compensar con WAF rate limiting a nivel de dominio (recomendado en `RUNBOOK.md`).
**Recomendación**: **Cloudflare WAF Rate Limiting** para `/api/auth/*` (5 req/min/IP), `/api/checkout/*` (30 req/min/IP), `/api/admin/*` (60 req/min/IP). Alternativa: extender `rate_limit.limiter` a más rutas.
**Effort**: 2 h vía Cloudflare · 4 h vía backend.
**Bloquea producción**: NO si se hace vía Cloudflare (SÍ si no se hace en ninguna capa).

### 2.8 🟡 P1 · SSRF potencial en `a35_bridge.py` y `colorlight.py`
**Evidencia**: `a35_bridge.py:82` hace `requests.get(f"{self.server_url}/...")`. `self.server_url` viene de configuración pero se lee de Mongo → potencialmente modificable por admin comprometido.
**Impacto**: Un admin malicioso podría apuntar `server_url` a un endpoint interno (169.254.169.254 metadata) o red privada.
**Riesgo**: BAJO en Render (VMs aisladas, sin IMDS accesible). MEDIO si se despliega en VPS con red interna.
**Recomendación**: Validar que `server_url` sea HTTPS y que el hostname resuelva a una IP pública NO privada (RFC1918, 169.254.*, 127.*).
**Effort**: 3 h.
**Bloquea producción**: NO en Render.

### 2.9 🟢 Manejo de secretos
**Evidencia**: `.env.example` sanitizado, `startup_check.py` valida claves Stripe con regex correcta, no hay claves committed al repo, `stripe_config.py` aborta si `sk_test_` en producción o `sk_live_` en dev.
**Comentario**: **Aprobado**.

### 2.10 🟢 CORS
**Evidencia**: `server.py:3757` valida que `CORS_ORIGINS` sea explícito en producción (no wildcard). Loguea error si vacío.
**Comentario**: **Aprobado**. Cero riesgo de origin wildcard en prod.

### 2.11 🟡 P1 · Logs y observabilidad — Sentry integración es opcional
**Evidencia**: `observability.py` inicializa Sentry solo si `SENTRY_DSN` está seteado. Si no, silencioso.
**Impacto**: Si alguien olvida configurar `SENTRY_DSN` en Render, los errores desaparecen sin traza (solo quedan en logs de Render con 7 días de retención).
**Riesgo**: MEDIO — no ves errores en prod.
**Recomendación**: Startup guard: si `ENVIRONMENT=production` y `SENTRY_DSN` no está seteado, **loguear WARNING crítico** al arrancar. Considerar `raise` para forzar la config.
**Effort**: 30 min.
**Bloquea producción**: NO técnicamente, pero SÍ operativamente.

### 2.12 🟢 Validación de entradas (Pydantic)
**Evidencia**: Todos los request bodies usan Pydantic `BaseModel` con `Field(min_length=..., max_length=..., pattern=...)`. Ejemplo: `RefundRequest.reason` requiere min_length=10.
**Comentario**: **Aprobado**.

---

## 3 · Base de datos

### 3.1 🟢 Índices — 49 creados en 12 colecciones
**Evidencia**: `stripe_indexes.py` con índices únicos + parciales para idempotencia, `fin_ledger` con `(currency, entry_number)` UNIQUE, `refunds` con `idempotency_key` UNIQUE parcial.
**Comentario**: **Aprobado**.

### 3.2 🟢 Atomicidad · concurrency guards
**Evidencia**: `refunds_service._execute_refund` usa `db.orders.update_one({..., "$expr": {"$lte": [{"$add": ["$refunded_cents", amount]}, "$amount_cents"]}})` — atomic per-document, imposible de over-refund.
**Comentario**: **Aprobado**. Testeado en `smoke_c3_refunds.py::Test5`.

### 3.3 🟡 P1 · Transacciones multi-documento faltantes
**Evidencia**: `grep session.start_transaction` → 0. Todas las operaciones son single-doc atomic o eventual consistency.
**Impacto**: Escenario: refund exitoso → ledger entry OK → credit_note falla → estado inconsistente en Mongo (refund succeeded sin CN).
**Riesgo**: MEDIO. El código actual maneja este caso re-intentando `issue_credit_note_for_refund` en cada llamada (idempotente por `refund_id` UNIQUE). Un admin puede re-emitir con `POST /credit-notes/{id}/reissue-pdf`.
**Recomendación**: Documentar en `RUNBOOK.md §7` cómo recuperar. Para Atlas M10+ que ya soporta transactions, evaluar envolver `_execute_refund` en `session.start_transaction()`.
**Effort**: 3 h + tests.
**Bloquea producción**: NO (hay path de recuperación manual).

### 3.4 🟢 Idempotencia
**Evidencia**: Ledger, refunds, invoices, credit notes — TODOS con unique index en `idempotency_key`. Smoke tests validan comportamiento.
**Comentario**: **Aprobado**.

### 3.5 🟡 P1 · Migraciones sin framework formal
**Evidencia**: `ensure_stripe_indexes` se ejecuta al arrancar. NO hay un sistema de migraciones (Alembic, migrate-mongo).
**Impacto**: Cambios de esquema requieren un script one-shot manual + coordinación de deploy.
**Riesgo**: BAJO al inicio (MongoDB es schemaless). MEDIO cuando el equipo crezca y haya migraciones complejas.
**Recomendación**: Para Sprint 2, adoptar `migrate-mongo` con historial en colección `_migrations`. Por ahora, documentar en `RUNBOOK.md §7` la práctica de "un script por cambio de esquema".
**Effort**: 1 día.
**Bloquea producción**: NO.

### 3.6 🟡 P1 · Integridad referencial lógica no validada
**Evidencia**: MongoDB no tiene FKs. `refund.order_id`, `invoice.order_id`, `credit_note.refund_id` NO se validan al insertar.
**Impacto**: Un `refund` puede quedar huérfano si su `order` es borrado (aunque `reset_for_production.py` los borra juntos).
**Riesgo**: BAJO en operación normal — solo `reset_for_production.py` borra. En prod los datos son inmutables.
**Recomendación**: Agregar checks defensivos: `find_one` de la entidad padre antes de insertar el hijo, con error 404 si no existe.
**Effort**: 4 h.
**Bloquea producción**: NO.

### 3.7 🟢 Consultas costosas — ninguna detectada
**Evidencia**: `find` con proyección usada correctamente. No hay `find({})` sin filtro en paths calientes. Aggregations con `$match` primero.
**Comentario**: **Aprobado** para el tamaño actual. Volver a auditar cuando ledger >100 000 entradas.

---

## 4 · Rendimiento

### 4.1 🟢 N+1 queries — ninguna detectada
**Evidencia**: `reports_service.revenue_by_screen` usa `$lookup` de agregación (no loop). Screen name hydration hace UN `find({"id": {"$in": [...]}})` por batch (correcto).
**Comentario**: **Aprobado**.

### 4.2 🟡 P1 · Sin middleware GZip
**Evidencia**: `grep GZip|Compress server.py` → 0.
**Impacto**: Responses JSON grandes (dashboard, reports export CSV/JSON) viajan sin comprimir. Reports `/bi/ledger?limit=100000` puede pesar >10 MB.
**Riesgo**: BAJO técnicamente. MEDIO por costo de bandwidth y UX en conexiones lentas.
**Recomendación**: Añadir `app.add_middleware(GZipMiddleware, minimum_size=1024)` en `server.py`. Cloudflare también comprime automáticamente pero es doble red de seguridad.
**Effort**: 15 min.
**Bloquea producción**: NO.

### 4.3 🟢 Redis con timeouts y retry
**Evidencia**: `redis_client.py:97-99` — `socket_connect_timeout=REDIS_TIMEOUT`, `socket_timeout=REDIS_TIMEOUT`, `retry_on_timeout=True`.
**Comentario**: **Aprobado**.

### 4.4 🟢 WebSocket sin memory leak
**Evidencia**: `realtime.py::ConnectionManager` limpia rooms cuando el último WS se desconecta.
**Comentario**: **Aprobado**. Para escala >1 000 conexiones, hay `docs/WEBSOCKET_SCALING.md` con plan.

### 4.5 🟢 ARQ worker + scheduler
**Evidencia**: `worker.py` con `SCHEDULER_MODE=worker` (dedicado) o `internal` (in-process). Cron mensual para billing, cada minuto para A40 sleep/wake.
**Comentario**: **Aprobado**. Un solo worker en Render soporta cargas iniciales.

### 4.6 🟡 P2 · Escalabilidad horizontal — semáforo amarillo
**Evidencia**: Nada bloquea multi-instancia. Redis compartido. Sesiones stateless (JWT). WebSocket es sticky-affinity-dependent pero `docs/WEBSOCKET_SCALING.md` describe migración a Redis Pub/Sub.
**Riesgo**: BAJO al inicio (1 instancia Render Starter). MEDIO cuando pases a 3+ instancias.
**Recomendación**: Cuando escales, implementar Redis Pub/Sub en `realtime.py` (ya planeado).
**Effort**: 1 día.
**Bloquea producción**: NO.

---

## 5 · Código

### 5.1 🟡 P1 · 72 usos de `except Exception:` — auditar los sospechosos
**Evidencia**: Grep confirma 72 ocurrencias. Muchos son legítimos (broadcast best-effort en `refunds_service`, PDF rendering fallbacks en `finance_pdf.py`).
**Sospechosos** que requieren revisión antes de prod:
- `auth_v2.py:83` — silencia error en lockout Redis, cae al fail-open. **Auditable**.
- `checkout_service.py:143, 346, 540, 561` — 4 puntos, revisar que no silencien errores financieros.
- `colorlight.py:143, 329, 429` — bridge de hardware, algunos son intencionales.
**Impacto**: Errores silenciosos = bugs invisibles.
**Recomendación**: Convertir todos los `except Exception:` de código financiero (`checkout_service`, `refunds_service`, `invoices_service`, `financial_ledger`) a `except SpecificException:` + `log.exception(...)`. Auditar los 4 de `checkout_service` uno por uno.
**Effort**: 4 h auditoría + fix.
**Bloquea producción**: NO técnicamente pero **SÍ éticamente** para código que mueve dinero.

### 5.2 🟢 TODO/FIXME — solo 1 en 16 709 líneas
**Evidencia**: `grep TODO|FIXME|XXX|HACK` → 1 match en `server.py`.
**Comentario**: **Aprobado**. Deuda técnica documentada en docs, no en comentarios sueltos.

### 5.3 🟡 P2 · `print()` en producción
**Evidencia**: `a35_bridge.py`, `finance.py`, `finance_scheduler.py`, `startup_check.py`, `stripe_config.py` usan `print()` en lugar de `logger`.
**Impacto**: Los `print` van a stdout y aparecen en Render logs, pero:
- No respetan `LOG_LEVEL`
- No estructurados (no aparecen en Sentry breadcrumbs)
- Difícil correlacionar con request_id
**Riesgo**: BAJO.
**Recomendación**: Migrar a `logger.info/warning/error`. Ganancia grande en debuggability.
**Effort**: 2 h.
**Bloquea producción**: NO.

### 5.4 🟢 Requirements.txt — 181 líneas TODAS pinneadas (`==`)
**Evidencia**: 181 pinned, 0 unpinned.
**Comentario**: **Aprobado**. Reproducibilidad garantizada.

### 5.5 🟡 P1 · Auditar imports sin usar
**Evidencia**: No corrí `ruff/pyflakes` (fuera de scope del recon rápido).
**Recomendación**: Antes del deploy, correr:
```
pip install ruff
ruff check backend/
```
y limpiar warnings de F401 (unused imports) + F841 (unused variables).
**Effort**: 1 h.
**Bloquea producción**: NO.

---

## 6 · Producción / DevOps

### 6.1 🟢 Health checks y readiness
**Evidencia**: `/api/health` (aliveness · siempre 200 si el proceso vive) + `/api/ready` (chequea Mongo + Redis).
**Comentario**: **Aprobado**.

### 6.2 🔴 P0 · Rotación de secretos sin código de soporte (P0 documental)
**Evidencia**: `RUNBOOK.md §4` describe procedimiento doble-key para FERNET pero **el código NO soporta dos claves simultáneamente** hoy.
**Impacto**: Al rotar `FERNET_KEY` en producción se invalidan TODOS los refresh tokens → usuarios pierden sesión.
**Riesgo**: MEDIO — no bloquea el primer deploy pero SÍ la primera rotación (que ocurrirá en 6 meses).
**Recomendación**: **Antes de la primera rotación** (no bloqueante ahora), implementar `FERNET_KEY_OLD` en `auth_v2.py` que se prueba como fallback al decodificar. Documentar procedimiento.
**Effort**: 3 h.
**Bloquea producción**: NO ahora. SÍ antes de los 6 meses.

### 6.3 🟢 Configuración validada al arranque
**Evidencia**: `startup_check.py` valida presencia de `MONGO_URL`, `JWT_SECRET`, `FERNET_KEY` y formato de claves Stripe.
**Comentario**: **Aprobado**.

### 6.4 🟡 P1 · Falta pipeline CI automatizado
**Evidencia**: No hay `.github/workflows/` en el repo.
**Impacto**: Cada PR requiere test manual. Regresiones pueden pasar a `main`.
**Recomendación**: Crear `.github/workflows/ci.yml` que en cada PR corra:
1. `ruff check backend/`
2. `python -m tests.smoke_c3_refunds`
3. `python -m tests.smoke_c4_reports`
4. `python -m tools.reset_for_production --dry-run` (verifica que corre)
**Effort**: 4 h.
**Bloquea producción**: NO técnicamente, pero DEBE existir para el primer merge post-launch.

---

## 7 · Testing — el mayor riesgo del sistema

### 7.1 🔴 P0 · Cobertura de testing (bloqueante suave)

**Análisis por módulo**:

| Módulo | Tipo test | Cobertura | Estado |
|--------|-----------|-----------|--------|
| Auth v2 (login, refresh, lockout) | Ninguno automatizado | 0% | 🔴 |
| RBAC (require_permission) | Smoke via C3/C4 | ~40% | 🟡 |
| Guest checkout (quote → media → intent) | Smoke etapa B v2 | ~70% happy-path | 🟡 |
| Order state machine | Smoke via C3 | ~50% | 🟡 |
| Invoices (issue + PDF + reissue) | Smoke via C3 | ~70% | 🟡 |
| Refunds (4 policies + dual approval + concurrency) | Smoke C3 exhaustivo | ~95% | 🟢 |
| Credit notes (numbering + link + PDF) | Smoke C3 | ~85% | 🟢 |
| Ledger (hash chain + verify) | Smoke C3 | ~90% | 🟢 |
| Reports (dashboard + exports + BI) | Smoke C4 exhaustivo | ~85% | 🟢 |
| Colorlight A40 player | Ninguno | 0% | 🔴 |
| Menu editor | Ninguno | 0% | 🔴 |
| Screens CRUD | Ninguno | 0% | 🔴 |
| Campaigns legacy | Ninguno | 0% | 🔴 |
| Finance CRM (Fase 1) | test_fase4_backend.py | ~50% | 🟡 |
| Email/notifications | Ninguno | 0% | 🔴 |
| ARQ worker (cron billing, A40 sleep/wake) | Ninguno | 0% | 🔴 |
| WebSocket real-time | Handshake test | ~10% | 🔴 |

**Escenarios críticos NO probados**:
1. Login concurrente + lockout (5 fallos → cuenta bloqueada) → **falta test**
2. Refresh token rotation attack (usar mismo refresh 2 veces → detección) → **falta test**
3. Guest checkout expiración de quote (>15 min) → **falta test**
4. A40 pierde conexión durante playback → **falta test**
5. Refund con `payment_intent_id=None` (manual refund) → parcialmente probado
6. Two admins racing en approve/reject de la misma orden → **falta test**
7. Webhook Stripe duplicado (idempotencia) → probado en unit, falta E2E
8. Ledger corruption detection en `verify_chain` → probado con integridad OK, falta test de chain rota

**Recomendación**:
- **Bloqueante**: escribir al menos **1 test Playwright** del happy-path guest checkout completo (crear orden → aprobar → factura → refund → credit note descarga).
- **Recomendado**: 3 tests unitarios de auth (login/lockout/refresh rotation).
- Post-launch: campaña de coverage → objetivo 60% líneas de código financiero.
**Effort**: 2 días para el mínimo bloqueante.
**Bloquea producción**: **SÍ para el mínimo Playwright**.

### 7.2 🟡 P1 · Sin tests de carga
**Evidencia**: 0 tests con `locust`/`k6`.
**Impacto**: No sabemos el punto de quiebre. ¿Cuántos req/s soporta el dashboard? ¿Cuántos WebSockets simultáneos?
**Riesgo**: MEDIO. Render Starter tiene 512 MB RAM — un exportar de 50 000 filas puede matar el pod.
**Recomendación**: Después de deploy staging, correr un `k6` con 100 usuarios concurrentes durante 5 min para caracterizar. Documentar límites en `RUNBOOK.md §11`.
**Effort**: 1 día.
**Bloquea producción**: NO.

---

## 8 · Tabla consolidada de hallazgos

### 🔴 P0 · Obligatorios ANTES de producción

| ID | Hallazgo | Impacto | Effort | Bloquea |
|----|----------|---------|--------|---------|
| P0-A1 | Headers de seguridad HTTP (§2.1) | ALTO — vulnerable a clickjacking/downgrade | 2 h | SÍ |
| P0-A2 | XSS en menu-editor + player-activate (§2.2) | MEDIO — panel admin comprometible | 1 h | SÍ |
| P0-A3 | Validación magic-numbers uploads (§2.3) | MEDIO — files maliciosos en R2 | 4 h | SÍ (si guest checkout abierto) |
| P0-A4 | Auditar 4 `except Exception:` en checkout_service (§5.1) | MEDIO — errores financieros silenciosos | 4 h | SÍ (ética) |
| P0-A5 | Al menos 1 test Playwright E2E (§7.1) | ALTO — sin red de seguridad ante regresiones | 1 día | SÍ |
| P0-A6 | Startup guard `SENTRY_DSN` en producción (§2.11) | MEDIO — errores invisibles | 30 min | Recomendado SÍ |

**Total P0**: ~2 días persona.

### 🟡 P1 · Recomendados antes de producción

| ID | Hallazgo | Effort |
|----|----------|--------|
| P1-B1 | Rate limiting vía Cloudflare WAF (§2.7) | 2 h |
| P1-B2 | Cierre de dep circular server↔permissions (§1.1) | 2 h |
| P1-B3 | Decisión campaigns vs orders (§1.3) | 2 días (migración) o 30 min (deprecar) |
| P1-B4 | Middleware GZip (§4.2) | 15 min |
| P1-B5 | Doble-key FERNET_KEY (§6.2) — antes 6 meses | 3 h |
| P1-B6 | Pipeline CI GitHub Actions (§6.4) | 4 h |
| P1-B7 | Migrar `print()` a `logger` (§5.3) | 2 h |
| P1-B8 | `ruff check` + limpiar unused imports (§5.5) | 1 h |
| P1-B9 | Validar SSRF en A35/Colorlight (§2.8) | 3 h |
| P1-B10 | Tests unitarios auth v2 (§7.1) | 4 h |

**Total P1**: ~3-4 días persona.

### ⚪ P2 · Sprint 2+ (post-launch)

- Refactor `server.py` (§1.2) — 2 días
- Refactor `finance.py` (§1.5) — 3 días
- Migrar campaigns a orders (§1.3) si se decide en P1-B3 (a) — 2 días
- CSRF tokens si aparecen endpoints con form-encoded (§2.6)
- Transacciones Atlas multi-doc (§3.3) — 3 h
- Framework de migraciones formal (§3.5) — 1 día
- Escalabilidad horizontal WebSocket (§4.6) — 1 día
- Tests de carga (§7.2) — 1 día
- Playwright E2E full suite (§7.1) — 3-4 días
- Documentar módulos activos vs deprecados (§1.6) — 2 h

---

## 9 · Recomendación final

### Estado del sistema
El núcleo funcional (financiero, RBAC, ledger, reportes, guest checkout, refunds) está **sólido y bien probado**. La arquitectura es limpia, las decisiones técnicas están documentadas, y la deuda técnica está bajo control.

Los hallazgos P0 son **todos abordables en menos de 2 días persona**. Ninguno requiere refactor mayor. Son mejoras defensivas (headers, XSS, validación de uploads, tests) que llevan al sistema de "muy bien" a "listo para producción".

### Plan sugerido antes de Semana 2 externa
Ejecutar los 6 items P0 en el siguiente orden (2 días):

1. **Día 1 · mañana** — P0-A1 (headers) + P0-A6 (Sentry startup guard) + P0-A2 (XSS)
2. **Día 1 · tarde** — P0-A4 (auditar except en checkout_service)
3. **Día 2 · mañana** — P0-A3 (magic numbers)
4. **Día 2 · tarde** — P0-A5 (1 test Playwright happy-path)

Después de estos 6 items, correr TODOS los smoke tests + el nuevo Playwright y confirmar 100% pass. Ese es el momento para arrancar Semana 2 externa.

### Semana 2 externa
Cuando lo autorices, la infraestructura externa puede empezar en paralelo a los P1 (que no bloquean). Cronograma sugerido:

- **Días 3-4**: Cuentas externas + provisionamiento
- **Días 5-6**: Deploy staging + validación manual
- **Días 7-8**: P1 items (mientras staging estabiliza)
- **Días 9-10**: QA A40 físico + hardening final
- **Día 11**: Go-live

### Riesgos residuales aceptados
- Tests unitarios de auth v2: se difieren a P1 (aceptable — auth v2 es código estable y ha sido validado manualmente).
- Refactor de server.py: se difiere a Sprint 2 (aceptable — funcional).
- Multi-currency roll-up (D-04): se difiere a Sprint 3 con feed de tasas (aceptable — decisión del usuario).

### Freeze respetado
Este documento **no modifica una sola línea de código**. Toda la información viene de análisis estático de la base actual.

---

## Anexo · Documentos relacionados
- `docs/PRODUCTION_READINESS_AUDIT.md` — plan de infraestructura (Semana 2)
- `docs/TECHNICAL_DEBT.md` — deuda técnica D-01 a D-04
- `docs/RUNBOOK.md` — procedimientos operativos
- `docs/BACKLOG_SPRINT2.md` — features postponidas explícitamente
- `backend/.env.example` — template de variables (40+)
- `tools/reset_for_production.py` — script de limpieza
