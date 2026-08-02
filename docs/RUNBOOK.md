# MediaDView — Operations Runbook

> **Documento operativo real** — cualquier administrador debe poder seguir
> este documento en caso de emergencia sin conocimiento previo del sistema.
> Ubicación: `docs/RUNBOOK.md` · Última revisión: Sprint 1 · Semana 1.

## Contactos y responsables
Rellenar antes de producción:

| Rol | Nombre | Email | Teléfono | Horario |
|-----|--------|-------|----------|---------|
| Owner | | | | 24/7 |
| DevOps on-call | | | | rotativo |
| Backend | | | | horas laborables |
| Finanzas | | | | horas laborables |

**Escalado**: DevOps → Backend → Owner. Si `owner` no responde en 30 min y hay pérdida de ingresos, contactar directamente a soporte de Render / Atlas.

**Fuentes externas de soporte**:
- Render: `https://render.com/support`
- Atlas: `https://support.mongodb.com`
- Cloudflare: `https://dash.cloudflare.com/support`
- Upstash: `https://upstash.com/docs/help`
- Stripe: `https://support.stripe.com`

---

## 1 · Procedimiento de despliegue estándar

**Requisitos previos**: PR mergeado a `main`, CI verde, backup manual de Atlas confirmado (<24 h).

### Despliegue estándar (Render auto-deploy)
1. En el dashboard de Render → servicio `mediadview-api` → Events → confirmar que el deploy corresponde al commit correcto.
2. Ver `Deploy logs` — esperar mensaje `Uvicorn running on ...` y `✓ Stripe/finance indexes ensured`.
3. Verificar salud:
   ```
   curl https://app.mediadview.com/api/health
   # Debe devolver: {"status":"healthy",...}
   curl https://app.mediadview.com/api/ready
   # Debe devolver 200 con dependencias verdes.
   ```
4. Verificar que el worker ARQ esté vivo (Render Background Worker `mediadview-worker` en estado `Live`).
5. Smoke manual (2 min):
   - Login con superadmin en `https://app.mediadview.com`
   - Abrir `/api/admin/reports-view` → dashboard renderiza sin errores en consola
   - Abrir `/api/admin/orders-view` → lista carga
6. Anunciar deploy en canal Slack #ops (o equivalente).

### Ventana de mantenimiento (deploy con downtime esperado)
1. Anunciar en `mediadview.com/status` con 24 h de anticipación.
2. Habilitar Cloudflare "Under Attack Mode" para servir página estática.
3. Ejecutar migración/deploy.
4. Verificar health + smoke.
5. Deshabilitar Under Attack Mode.
6. Post-mortem en 24 h.

---

## 2 · Rollback

**Regla de oro**: Si en <5 min tras un deploy los errores de Sentry >20/min o `/api/ready` da 500, rollback inmediato SIN debate.

### Rollback rápido (Render)
1. Render dashboard → servicio → `Events` → clic en un deploy anterior verde.
2. "Rollback to this deploy" → confirmar.
3. Render redespliega la versión anterior en ~2 min.
4. Verificar `/api/health` + `/api/ready`.
5. **Documentar** en `docs/INCIDENTS/YYYY-MM-DD-hhmm.md` (crear si no existe):
   - Deploy que se revirtió (commit SHA)
   - Síntomas observados
   - Métricas Sentry/BetterStack
   - Decisión + hora

### Rollback con migración de datos
Si el deploy que falló ejecutó migraciones destructivas:
1. Rollback del código en Render (arriba).
2. Restaurar Atlas al snapshot inmediatamente anterior (ver §3).
3. Verificar consistencia con:
   ```
   curl https://app.mediadview.com/api/admin/ledger/verify?currency=usd \
        -H "Authorization: Bearer <token>"
   # Debe devolver {"ok": true, ...}
   ```

---

## 3 · Restauración desde backup

### MongoDB Atlas (Point-in-Time Recovery)
1. Atlas dashboard → cluster → `Backup` → `Point in Time Restore`.
2. Elegir timestamp (Atlas ofrece precisión al segundo en las últimas 24 h, cada hora hasta 7 días).
3. Elegir "Restore to this cluster" (destructivo) o "Restore to a new cluster" (seguro para investigación).
4. Esperar ~15-30 min según tamaño.
5. Verificar integridad del ledger:
   ```
   /api/admin/ledger/verify?currency=usd     # ok: true
   /api/admin/ledger/verify?currency=dop     # ok: true
   ```

### Cloudflare R2 (versioning)
1. Cloudflare dashboard → R2 → bucket → objeto afectado → `Versions`.
2. Seleccionar versión previa → `Restore`.
3. Actualizar cualquier referencia si el hash cambió.

### Ledger append-only (backup semanal)
Si detectamos manipulación del ledger:
1. Comparar `hash_chain` actual vs último backup semanal.
2. Encontrar entry_number del "salto" en el chain.
3. Este es un incidente FINANCIERO — escalar inmediatamente al Owner.

---

## 4 · Rotación de secretos

**Frecuencia**: cada 6 meses o inmediatamente si sospecha de fuga.

### JWT_SECRET (rotación estándar)
Rotarlo invalida todos los tokens activos (usuarios deberán loguearse de nuevo).
1. Anunciar ventana de mantenimiento (5 min).
2. Generar nuevo: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
3. Render → env vars → actualizar `JWT_SECRET` → save (auto-redeploy).
4. Verificar login + refresh en cuenta de test.

### FERNET_KEY (rotación CRÍTICA)
Rotarlo invalida **refresh tokens** (usuarios pierden sesión pero no acceso).
**Procedimiento doble-key** (evita downtime):
1. **Fase 1**: Añadir `FERNET_KEY_OLD=<current>` y generar nuevo `FERNET_KEY`.
2. Modificar `auth_v2.py` para decodificar con ambos (aceptar OLD, cifrar con NEW) durante 24 h.
3. **Fase 2** (24 h después): Remover `FERNET_KEY_OLD` — todos los tokens ya usan la nueva key.
4. Documentar en `docs/INCIDENTS/rotation-<fecha>.md`.

### ORDER_LINK_SECRET
Invalida magic-links activos (los guests deberán solicitar uno nuevo).
1. Anunciar en el checkout que los links son válidos por 30 días.
2. Notificar via email a órdenes con magic-links pendientes.
3. Rotar de golpe (sin ventana suave necesaria).

### R2, Stripe, Resend, Sentry
Rotación cada 12 meses o si el equipo cambia:
1. Generar nueva key en cada dashboard.
2. Actualizar env vars en Render.
3. Verificar operación de la integración (upload media, envío email de test).
4. Revocar la key vieja SOLO tras verificar.

### Passwords de superadmin
- Cada 90 días forzar rotación (`must_rotate_password: true` en el user doc).
- Usar 2FA cuando esté implementado.

---

## 5 · Renovación SSL

Render provee certificados Let's Encrypt automáticos. Cloudflare (frente a Render) también.

### Verificación mensual
```
curl -vI https://app.mediadview.com 2>&1 | grep "expire date"
# Debe faltar > 30 días. Si <30, forzar renovación:
```

### Renovación forzada (si falla auto-renewal)
1. Cloudflare → SSL/TLS → Edge Certificates → `Renew`.
2. En Render, si el certificado propio expira: Settings → `Custom Domains` → `Renew Certificate`.
3. Verificar con `https://www.ssllabs.com/ssltest/?d=app.mediadview.com` — objetivo grade A+.

---

## 6 · Recuperación ante caída de Render

### Diagnóstico rápido
```
curl -I https://app.mediadview.com/api/health
# Timeout / 5xx → caída del servicio
# 4xx → problema de aplicación, no infra
```

### Escenario A: Servicio caído por deploy roto
→ Rollback (§2).

### Escenario B: Render tiene incidente regional
1. Verificar `https://status.render.com`.
2. Si es incidente confirmado:
   - Activar página de mantenimiento en Cloudflare (Transform Rule para servir HTML estático).
   - Notificar en `mediadview.com/status`.
   - Esperar resolución de Render.
3. Cuando Render vuelve:
   - Verificar deploys automáticos.
   - Desactivar mantenimiento.
   - Documentar tiempo total de caída para SLA.

### Escenario C: Migración de urgencia a otro proveedor
Solo si Render tiene incidente >4 h:
1. Cluster de Atlas + Redis Upstash siguen accesibles.
2. Deploy manual a Fly.io / Railway / DO App Platform como fallback:
   - `git clone`, mismas env vars, `uvicorn server:app --host 0.0.0.0 --port 8001`.
3. Cambiar Cloudflare DNS `A/CNAME` → nuevo host.
4. TTL DNS en Cloudflare debe ser bajo (60s) para permitir failover rápido.

---

## 7 · Recuperación de MongoDB Atlas

### Escenario A: Atlas devuelve errores intermitentes
1. Atlas → cluster → Metrics → identificar CPU/IOPS/connections spike.
2. Si connections >80% del límite: aumentar `maxPoolSize` en el backend O escalar cluster (M10 → M20).
3. Si CPU/IOPS altos por query: revisar Slow Ops → añadir índice si aplica.

### Escenario B: Cluster no responde
1. Verificar `https://status.mongodb.com`.
2. Si el cluster está degraded: Atlas realiza failover automático a réplica secundaria (~10 s).
3. Si falla el failover: contactar soporte Atlas (M10+ tiene 24/7).
4. Como último recurso: Point-in-Time Restore a un cluster nuevo, cambiar `MONGO_URL` en Render.

### Escenario C: Corrupción de datos
1. NO tocar el cluster corrupto.
2. Snapshot manual inmediato para investigación.
3. Restore a un cluster limpio con Point-in-Time desde ANTES de la corrupción.
4. Cambiar `MONGO_URL` en Render → auto-redeploy.
5. Comparar delta de datos perdidos con backup semanal del ledger.

---

## 8 · Recuperación de Redis

Redis es cache + rate limiter + ARQ queue. Su pérdida NO pierde datos financieros (todo está en Mongo).

### Escenario A: Redis inaccesible
1. Health check `/api/ready` reportará degraded pero `/api/health` sigue 200.
2. Rate limiting queda desactivado temporalmente (best-effort).
3. ARQ worker se reconectará automáticamente cuando Redis vuelva.
4. Slot reservations con TTL activo: si Redis cae, los slots pendientes en Mongo persisten hasta expirar (TTL de Mongo también funciona).

### Escenario B: Migración a nuevo Redis
1. Provisionar nueva instancia en Upstash.
2. Actualizar `REDIS_URL` en Render (auto-redeploy).
3. Cache warmup se hace solo con tráfico entrante.
4. Verificar `curl /api/ready` → redis: true.

### Escenario C: Redis con datos inconsistentes (raro)
Flush del namespace:
```
redis-cli -u $REDIS_URL --tls FLUSHDB
```
NO usar FLUSHALL — otras apps podrían compartir Redis.

---

## 9 · Monitoreo

### Fuentes de datos
- **Sentry**: errores de aplicación + performance
- **BetterStack**: uptime + response time desde ubicaciones externas
- **Cloudflare Analytics**: tráfico + WAF blocks + bandwidth
- **Render Metrics**: CPU/RAM/disk del contenedor
- **Atlas Metrics**: DB CPU, connections, slow ops
- **Upstash Console**: comandos/seg, memoria
- **MediaDView Dashboard** (`/api/admin/reports-view`): KPIs de negocio

### Alertas críticas (configurar antes de go-live)
| Alerta | Umbral | Canal | Escalado |
|--------|--------|-------|----------|
| `/api/health` down | 2 fallos en 5 min | Email + Slack | DevOps |
| `/api/ready` down | 3 fallos en 10 min | Email + Slack | DevOps |
| Sentry errors | >10/min por 3 min | Slack | Backend |
| 5xx rate en Cloudflare | >1% del tráfico | Slack | DevOps |
| Atlas CPU | >80% por 10 min | Email | DevOps |
| Atlas connections | >80% del límite | Email | Backend |
| Redis memory | >90% | Email | DevOps |
| SSL expira | <14 días | Email | DevOps |
| Ledger chain broken | inmediato | Email + SMS | Owner + Backend |
| Refund failed | inmediato | Email | Finanzas |

### Revisiones periódicas
- **Diario** (mañana): Sentry issues nuevos, uptime del día anterior
- **Semanal**: performance p95, Atlas slow ops, refund rate
- **Mensual**: costos por servicio, capacidad del cluster, tasa de crecimiento del ledger

---

## 10 · Procedimiento para incidentes críticos

### Definición de "incidente crítico"
- Pérdida de acceso al panel para todos los admin
- Guest checkout inoperativo >5 min
- Errores financieros (refund duplicado, monto incorrecto, ledger corrupto)
- Fuga de credenciales confirmada o sospechada
- Ataque DDoS confirmado

### Playbook de incidente

**Paso 1 · Detección** (0-5 min)
- Confirmar el incidente con: `curl /api/health`, dashboard Sentry, reportes de usuarios.
- Anunciar en canal ops que el incidente está EN INVESTIGACIÓN.
- Un solo "Incident Commander" asignado (típicamente el DevOps on-call).

**Paso 2 · Contención** (5-30 min)
Según tipo:
- Deploy roto → Rollback (§2)
- DDoS → Cloudflare "Under Attack Mode" + firewall rules
- Fuga de credenciales → Rotar TODAS las credenciales afectadas (§4), revocar sesiones activas
- Error financiero → Pausar el módulo afectado (feature flag o endpoint 503), NO borrar datos, snapshot Atlas

**Paso 3 · Comunicación**
- `mediadview.com/status`: mensaje público breve
- Email a clientes activos afectados si el incidente dura >30 min
- Slack #ops: actualización cada 15 min

**Paso 4 · Resolución**
- Aplicar fix definitivo (no parche).
- Verificar con test manual + smoke tests automáticos.
- Restaurar servicios pausados.
- Anunciar resolución.

**Paso 5 · Post-mortem** (dentro de 48 h)
Crear `docs/INCIDENTS/YYYY-MM-DD-<slug>.md`:
- Timeline con timestamps
- Causa raíz
- Impacto (usuarios afectados, revenue perdido si aplica)
- Acción correctiva
- Acción preventiva (mejorar monitoreo, tests, alertas)

### Contactos externos de emergencia
- Render support: soporte 24/7 en planes Team/Enterprise
- Atlas support: 24/7 con severity levels en M10+
- Stripe: <30 min response en horas laborables
- Cloudflare: chat en dashboard Pro+, email support Free

---

## 11 · Checklist de "todo verde" (revisión semanal)

```
□ /api/health responde 200 desde 3 regiones externas (BetterStack)
□ /api/ready reporta todas las deps verdes (mongo, redis, r2 opcional)
□ Sentry con <5 errores nuevos en la semana
□ /api/admin/ledger/verify → ok:true en USD y DOP
□ Ninguna alerta crítica activa
□ Backup Atlas más reciente <24 h
□ SSL válido >30 días
□ /api/admin/reports-view carga sin errores
□ Un refund de prueba (dev/stage) se ejecuta correctamente
□ /api/admin/reports/export/orders.pdf descarga sin errores
```

---

## 12 · Anexo · Comandos útiles

### Ver logs en Render
Render dashboard → servicio → `Logs` (últimas 7 días).
Para stream en vivo: usar la CLI `render logs -f`.

### Correr scripts one-shot en Render
- Render → `Shell` (solo Team+ plan). Alternativa: correr desde local con env vars de prod.
- Ejemplos: `python -m tools.reset_for_production --dry-run`

### Verificar integridad del ledger
```
curl -H "Authorization: Bearer <admin_token>" \
     https://app.mediadview.com/api/admin/ledger/verify?currency=usd
# → {"ok": true, "checked": N, "broken_entry_number": null}
```

### Consulta directa a Mongo (emergencias)
```
mongosh "$MONGO_URL/$DB_NAME"
> db.orders.countDocuments({status: "pending_review"})
> db.fin_ledger.aggregate([
    { $match: { entry_type: "PAYMENT_CAPTURED" } },
    { $group: { _id: "$currency", total: { $sum: "$amount_cents" } } }
  ])
```

### Force refresh de credentials del worker
```
render deploy --service mediadview-worker
```

---

## 13 · Documentos relacionados

- `docs/PRODUCTION_READINESS_AUDIT.md` — auditoría del estado del sistema y roadmap
- `docs/TECHNICAL_DEBT.md` — deuda técnica formalizada (D-01 a D-04)
- `docs/GO_LIVE_CHECKLIST.md` — checklist operativa Sprint 1
- `docs/BACKUP_RECOVERY.md` — plan de recuperación detallado
- `backend/.env.example` — template de variables de entorno
- `tools/reset_for_production.py` — script de limpieza pre-producción

---

**Nota final**: Este documento es LIVE — actualizarlo después de cada incidente
significativo. Al menos una vez por trimestre, alguien del equipo debe **hacer
un simulacro** siguiendo un procedimiento (rollback, rotate secret, restore
backup) para verificar que las instrucciones son correctas.
