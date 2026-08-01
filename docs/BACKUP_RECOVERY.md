# MediAd View — Backup, Recovery & Rollback

> Estrategia probada para restaurar el sistema completo sin depender del proveedor
> de infraestructura. Diseñada para funcionar igual con MongoDB Atlas Free, Flex
> o clústeres dedicados (M10+).

---

## 1. Qué se respalda y con qué frecuencia

| Capa | Contenido | Frecuencia | Retención | Ubicación |
|------|-----------|------------|-----------|-----------|
| **MongoDB Atlas** (`db.*`) | Todos los datos operacionales: users, screens, campaigns, menus, fin_*, colorlight_*, audit_log | Diaria + snapshots automáticos según plan | 7 días (Flex) / 2 días (M2) / según plan | Atlas + copia offsite en R2 |
| **Cloudflare R2** (`mediadview-prod`) | Todas las imágenes y videos subidos | Continuo (R2 tiene 11×9s durabilidad) | Retención por objeto (ver política más abajo) | R2 nativamente redundante |
| **Código** (`git`) | Todo el repo | Continuo | Ilimitado | GitHub |
| **Env vars / secretos** | JWT, Stripe, R2, SMTP, Sentry | Al cambiar | Ilimitado | Password manager (1Password / Bitwarden / Render Env Groups) |
| **APK Android** | `mediaview-player-*.apk` firmados | Al liberar | Todas las versiones | R2 + repo `/backend/web/` |

---

## 2. Estrategia de respaldo por capa

### 2.1 MongoDB Atlas — plan de respaldo agnóstico al plan

**Opción A (recomendada, cualquier plan ≥ M2)**
Habilitar los snapshots automáticos que ofrece Atlas:
1. Atlas UI → Cluster → **Backup** → activar.
2. Programar snapshot cada 6 h (o el mínimo del plan).
3. Retención: mínimo 2 días.
4. Testear restore mensualmente (procedimiento en §4).

**Opción B (redundancia offsite)**
Además de A, ejecutar `mongodump` diario y subir a R2 (offsite):

```bash
# scripts/backup_mongo.sh — corre como cron dentro del worker
#!/usr/bin/env bash
set -euo pipefail
STAMP=$(date -u +%Y%m%d-%H%M)
DUMP_DIR=/tmp/mongodump-$STAMP
mongodump --uri="$MONGO_URL" --db="$DB_NAME" --gzip --out="$DUMP_DIR"
tar czf "$DUMP_DIR.tar.gz" -C /tmp "mongodump-$STAMP"

aws s3 cp "$DUMP_DIR.tar.gz" \
  "s3://$R2_BUCKET_NAME/backups/mongo/mongodb-$STAMP.tar.gz" \
  --endpoint-url "$R2_ENDPOINT"

rm -rf "$DUMP_DIR" "$DUMP_DIR.tar.gz"
```

Retención en R2: lifecycle rule 30 días.

**Opción C (plan Free / M0 sin snapshots)**
- Solo Opción B (mongodump → R2), corriendo diario.
- Al escalar a Flex/M2 o superior se activa Opción A automáticamente.

> ⚠️ El código NO asume qué plan estás usando. Todo funciona igual porque
> los backups se toman con `mongodump` estándar y el restore con `mongorestore`.

### 2.2 Cloudflare R2

- **Durabilidad nativa**: R2 replica cada objeto 3× dentro de la región.
- **Lifecycle rule recomendada** (en el bucket `mediadview-prod`):
  - Objetos en carpeta `backups/mongo/` → borrar después de 30 días.
  - Objetos en carpeta `media/` → sin política de borrado (viven mientras la campaña esté activa).
  - Objetos en carpeta `archived/` → mover a Infrequent Access tras 60 días.
- **Backup del bucket** (opcional, para desastre total de Cloudflare):
  - `rclone sync r2:mediadview-prod b2:mediadview-backup` (Backblaze B2) semanal.

### 2.3 Código

- Repositorio GitHub privado (Fase 1).
- Rama `main` protegida (require PR review + status checks pasan).
- Tags de release (`v2.2.0`, etc.) inmutables.

### 2.4 Secretos

- **Nunca** en el código, `.env` ni logs.
- Fuente de verdad: Render Env Groups (encriptados en reposo).
- Backup humano: exportar al password manager (1Password vault "MediAd View Prod").
- Rotación cada 90 días: JWT_SECRET, SMTP_PASSWORD, Stripe restricted keys.

---

## 3. Recuperación ante fallos (por escenario)

### 3.1 Web-api caído

- Render lo reinicia automáticamente por health check fallido (`/api/livez` 3× seguidas 503).
- Si persiste: rollback al último deploy verde (§5).

### 3.2 Worker caído

- Render lo reinicia automáticamente.
- `/api/ready` retorna 200 con `worker.ok=false` durante la caída (soft degradation, la API sigue respondiendo).
- Los jobs pendientes quedan en Redis; ARQ los procesa en cuanto el worker vuelve.

### 3.3 Redis caído

- API sigue funcionando pero:
  - Rate-limit degrada a in-memory (aviso en logs).
  - Cache falla open (todos los reads pegan a Mongo).
  - Worker no puede procesar jobs nuevos.
- Restaurar: reiniciar el Redis en Render. Los datos volátiles (cache, rate-limit counters) se pierden pero **no hay corrupción**.

### 3.4 MongoDB Atlas — corrupción o pérdida de datos

**Pasos exactos:**

```bash
# 1. Poner la app en modo mantenimiento
render env set web-api MAINTENANCE_MODE=true

# 2. Elegir el snapshot desde Atlas UI (o el dump de R2)
# 3. Restaurar en un cluster nuevo primero (nunca sobre el prod live)
mongorestore \
  --uri="mongodb+srv://<user>:<pass>@restore-cluster.xxxxx.mongodb.net" \
  --gzip --drop \
  /tmp/mongodb-YYYYMMDD-HHMM/

# 4. Verificar contadores
mongosh "<restore-uri>" --eval "
  print('users:',        db.users.countDocuments({}));
  print('screens:',      db.screens.countDocuments({}));
  print('campaigns:',    db.campaigns.countDocuments({}));
  print('fin_invoices:', db.fin_invoices.countDocuments({}));
"

# 5. Si los conteos son correctos, actualizar MONGO_URL en Render Env Group
# 6. Reiniciar web-api + worker
# 7. Verificar /api/ready → 200 con checks.mongo.ok=true
# 8. Quitar mantenimiento
render env unset web-api MAINTENANCE_MODE
```

**RPO (Recovery Point Objective)**: ≤ 6 h con snapshots + 24 h con dump-a-R2.
**RTO (Recovery Time Objective)**: ~15 min si el restore es local; ~1 h si viene de R2.

### 3.5 Cloudflare R2 — pérdida de un objeto

- Los objetos productivos tienen versionado activado (opción del bucket).
- `wrangler r2 object list-versions <bucket> <key>` → seleccionar versión anterior y restaurarla con `restore-object`.

### 3.6 Pérdida total del proveedor (Render)

Pasos para migrar a otro proveedor (Fly.io, Railway, DigitalOcean App Platform, etc.):

1. Crear proyecto nuevo en el proveedor destino.
2. Levantar Redis + Mongo (o mantener Atlas).
3. Deploy con el mismo Dockerfile — nada de código cambia.
4. Copiar todas las env vars del password manager al nuevo proveedor.
5. Cambiar DNS de Cloudflare para apuntar al nuevo hostname.

**Tiempo estimado**: 1-2 horas.

---

## 4. Prueba trimestral obligatoria

Cada 3 meses (calendario compartido "MediAd View Ops"):

1. Descargar el último `mongodump` de R2.
2. Levantar un cluster Atlas temporal (M0 free).
3. `mongorestore` completo.
4. Verificar los 8 flujos críticos (auth, crear campaña, generar factura PDF, aprobar pago, sync A40, render menu público, WS live, QR generation).
5. Documentar en `docs/restore-tests/YYYY-QQ.md` (fecha, tiempo total, incidencias).
6. Destruir el cluster temporal.

---

## 5. Procedimiento de rollback en despliegue fallido

### Vía A — Rollback automático (Render)

Render conserva las últimas 5 imágenes:

```
Render UI → mediadview-api → Deploys → Deploy anterior → "Rollback to this deploy"
```

Duración: ~30 s. **Los datos NO se ven afectados** (rollback solo cambia el binario).

### Vía B — Rollback manual (Git)

```bash
# 1. Encontrar el sha del último deploy verde en Render logs
LAST_GOOD_SHA=abc1234
git checkout main
git revert --no-commit HEAD              # o crear un commit de rollback específico
git commit -m "rollback: revert to $LAST_GOOD_SHA (deploy failure YYYY-MM-DD)"
git push origin main
# 2. Render auto-deploya el rollback.
```

### Cuándo NO hacer rollback

- Si el fallo involucra una **migración de datos** (por ejemplo un `$rename` masivo en Mongo).
- En ese caso: mantener el deploy roto en modo lectura y restaurar Mongo desde snapshot ANTES del rollback del código.

---

## 6. Checklist post-restore

- [ ] `/api/livez` → 200
- [ ] `/api/ready` → 200 con los 3 checks ok
- [ ] `/api/auth/v2/login` con super admin → 200 + cookie
- [ ] Un menú público renderiza correctamente (WS conecta)
- [ ] El A40 en `Direct Mode` sigue polleando (verificar logs)
- [ ] Un job de ARQ se procesa OK (`send_email_job` con email de prueba)
- [ ] Sentry recibe eventos (forzar uno con `curl -X POST /api/dev/sentry-test` si está habilitado)
- [ ] Cron `evaluate_schedules` corriendo cada minuto en el worker
- [ ] Última factura generada este mes existe

---

## 7. Contactos de emergencia

- Ingeniero on-call: (por definir)
- Cuenta soporte Emergent: support@emergent.sh
- Cuenta soporte MongoDB Atlas: (Support Portal)
- Cuenta soporte Cloudflare: (Dashboard → Support)
- Stripe: dashboard.stripe.com → Support
