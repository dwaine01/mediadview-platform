# MediaView — Go-Live Checklist
> Version: 1.1 — Updated: Fase 6 Production Infrastructure Hardening
> Status: UPDATED — Phase 6 items incorporated
> Previous version: 1.0 (Fase 5 Pre-Production Audit)

---

## HOW TO USE THIS CHECKLIST
Work top to bottom. Each section must be ✅ before marking "PRODUCTION READY".
Items marked 🔴 are P0 BLOCKERS — deployment must not proceed until resolved.
Items marked 🟡 are P1 BEFORE LAUNCH — resolve within 24h of go-live.
Items marked 🔵 are P2 AFTER LAUNCH — resolve within first 30 days.

---

## 0. FASE 6 INFRASTRUCTURE HARDENING (NEW — Must complete before Go-Live)

> These items were added during Fase 6 — Production Infrastructure.
> All code is READY. Real credentials/environments still required for final validation.

### Environment Validation (startup_check.py — DONE ✅)
- [x] ✅ `startup_check.py` validates all critical env vars at boot
- [x] ✅ FAIL FAST: `ENVIRONMENT=production` + localhost `MONGO_URL` → `sys.exit(1)`
- [x] ✅ FAIL FAST: `ENVIRONMENT=production` + weak `JWT_SECRET` (< 32 chars or default) → `sys.exit(1)`
- [x] ✅ FAIL FAST: `ENVIRONMENT=production` + missing `ORDER_LINK_SECRET` → `sys.exit(1)`
- [x] ✅ FAIL FAST: `ENVIRONMENT=production` + `CORS_ORIGINS=*` → `sys.exit(1)`
- [x] ✅ Staging (`ENVIRONMENT=staging`) enforces same rules as production for infra
- [ ] 🔴 Verify startup_check passes on real production deployment with Atlas MONGO_URL

### StorageService Abstraction (storage_service.py — DONE ✅)
- [x] ✅ `StorageService` with `LocalStorageDriver` (dev) and `R2StorageDriver` (prod) implemented
- [x] ✅ `MemoryDriver` for unit testing (no filesystem dependency)
- [x] ✅ No boto3/S3 logic scattered in routes — all goes through `StorageService`
- [x] ✅ `upload_media` route uses `StorageService` exclusively
- [x] ✅ Path traversal protection in upload route (sanitize filename, block `../`)
- [x] ✅ MIME magic-byte validation (blocks spoofed uploads)
- [ ] 🔴 Provide R2 credentials → `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_URL`
- [ ] 🔴 Real R2 upload test with actual bucket (Code Ready / Real Test Pending)

### Liveness vs Readiness Probes (health.py — DONE ✅)
- [x] ✅ `GET /api/livez` — pure liveness (never touches DB, always fast)
- [x] ✅ `GET /api/ready` — readiness (pings Mongo, Storage, Redis, Worker)
- [x] ✅ `GET /api/health` — legacy endpoint preserved (Android Player compat)
- [x] ✅ Readiness returns `{"ok": false}` with 503 if any critical check fails
- [ ] 🟡 Wire `/api/livez` as liveness probe in Kubernetes/Render health check config
- [ ] 🟡 Wire `/api/ready` as readiness probe in Kubernetes/Render routing config

### MongoDB Atlas Migration (DONE — Code Ready ✅ / Real Test Pending ⏳)
- [x] ✅ `startup_check.py` rejects localhost Mongo in production
- [x] ✅ `db_indexes.py` ensure_indexes() is idempotent (tested in Fase 6)
- [x] ✅ `/api/ready` pings Atlas via `db.command("ping")`
- [x] ✅ `docs/MONGODB_ATLAS_MIGRATION.md` created with full step-by-step guide
- [ ] 🔴 Create Atlas cluster + provision credentials → see `docs/MONGODB_ATLAS_MIGRATION.md`
- [ ] 🔴 Update `MONGO_URL` in production environment to Atlas connection string
- [ ] 🔴 Run `mongodump` + `mongorestore` to migrate local data
- [ ] 🔴 Verify `/api/ready` returns `mongo.ok=true` against Atlas

### Fase 6 Acceptance Tests (DONE ✅ — 17 PASSED)
- [x] ✅ Test A: Development accepts local Mongo
- [x] ✅ Test B: Production rejects localhost Mongo (FAIL FAST)
- [x] ✅ Test C: Production rejects weak JWT_SECRET
- [x] ✅ Test D: Production rejects missing ORDER_LINK_SECRET
- [x] ✅ Test E: Production rejects CORS wildcard (`*`)
- [x] ✅ Test F: LocalDriver upload / get_url / delete works
- [x] ✅ Test G: R2Driver mock contract passes (MemoryDriver)
- [x] ✅ Test H: Invalid MIME type rejected (415)
- [x] ✅ Test I: Path traversal filename rejected (400)
- [x] ✅ Test J: Oversized upload rejected (400/413)
- [x] ✅ Test K: DB indexes idempotent (run twice, no duplicates)
- [x] ✅ Test L: Scheduler mode respected
- [x] ✅ Readiness probe returns 200 + storage.ok + mongo.ok
- [x] ✅ Liveness probe always 200 (never touches DB)
- [x] ✅ Legacy /health still works (Android Player compat)
- [x] ✅ Test N: Fase 3 /marketplace/screens regression (PUBLIC_ADVERTISING)
- [x] ✅ Test O: Fase 4 /managed/dashboard regression
- [ ] ⏳ Test M: Fase 2 self-service (skipped — test user needed in env)
- [ ] ⏳ Test P: Player playlist regression (skipped — screen data needed in env)

---



### DNS & TLS
- [ ] 🔴 Custom domain configured (e.g., `api.mediaview.io`) and DNS propagated
- [ ] 🔴 TLS/SSL certificate valid and auto-renewing (Render / Cloudflare)
- [ ] 🔴 HTTP → HTTPS redirect enforced (no plain HTTP traffic accepted)
- [ ] 🔴 `CORS_ORIGINS` set to exact frontend domain (NOT `*`)
- [ ] 🟡 `COOKIE_SECURE=true` confirmed in production `.env`
- [ ] 🟡 `COOKIE_SAMESITE=strict` or `lax` set appropriately

### Environment Variables — Mandatory for Production
All the following must be set in the Render/deployment environment:

```
ENVIRONMENT=production
JWT_SECRET=<strong-random-256bit-hex>          # SECRET ROTATION REQUIRED
ORDER_LINK_SECRET=<strong-random-hex>           # SECRET ROTATION REQUIRED
MONGO_URL=<atlas-cluster-connection-string>
REDIS_URL=<redis-cloud-url>                     # Required for multi-instance RL
CORS_ORIGINS=https://app.mediaview.io           # Exact domain, NO wildcard
COOKIE_SECURE=true
SCHEDULER_MODE=arq                              # Use ARQ worker, disable in-process scheduler
SEED_DEMO=false                                 # CRITICAL: never seed demo users in production
ADMIN_PASS=<strong-password>                    # Production admin password
SUPERADMIN_PASS=<strong-password>               # Production superadmin password
```

Optional but recommended:
```
JWT_ACCESS_TOKEN_MINUTES=15                     # Reduce from 30 to 15 in production
JWT_REFRESH_TOKEN_DAYS=14                       # Reduce from 30 to 14 in production
SENTRY_DSN=<sentry-project-dsn>                 # Error monitoring
```

- [ ] 🔴 All mandatory env vars are set (app will FAIL FAST if missing)
- [ ] 🔴 `SEED_DEMO=false` or unset in production environment
- [ ] 🔴 `JWT_SECRET` rotated from development value
- [ ] 🔴 `ORDER_LINK_SECRET` rotated from development value
- [ ] 🔴 `ADMIN_PASS` / `SUPERADMIN_PASS` set to strong non-default values
- [ ] 🟡 `REDIS_URL` configured (rate limiter is in-memory without it — not multi-instance safe)

---

## 2. DATABASE

### MongoDB Atlas Setup
- [ ] 🔴 MongoDB Atlas cluster created (NOT localhost/free tier for production)
- [ ] 🔴 Network Access limited to deployment IP or private VPC
- [ ] 🔴 Database user with least-privilege credentials (read+write, NOT Atlas Admin)
- [ ] 🔴 `MONGO_URL` updated to Atlas connection string in production environment
- [ ] 🟡 IP Allowlist configured (Render static IPs or VPC peering)

### Indexes (verified — `db_indexes.py` runs at startup)
- [ ] ✅ `users.email` — unique index for auth queries
- [ ] ✅ `screens.pairing_code` — unique sparse index
- [ ] ✅ `screens.organization_id` + compound org+type index
- [ ] ✅ `devices.screen_id` + heartbeat compound index
- [ ] ✅ `ad_campaigns` status+dates compound for scheduler
- [ ] ✅ `client_requests` status+created compound
- [ ] ✅ `audit_logs` TTL index (2 year expiry)
- [ ] ✅ `proof_of_play` TTL index (3 year expiry)
- [ ] ✅ `sessions` TTL index (auto-expire refresh tokens)
- [ ] 🟡 Verify index coverage in Atlas after first real traffic (use explain())

### Backups
- [ ] 🔴 MongoDB Atlas continuous backups enabled (or equivalent)
- [ ] 🔴 Point-in-time recovery window defined (minimum 7 days)
- [ ] 🟡 Restore procedure tested at least once in staging:
  - Export: `mongodump --uri=$MONGO_URL --archive=backup.gz --gzip`
  - Restore: `mongorestore --uri=$MONGO_URL_STAGING --archive=backup.gz --gzip`
- [ ] 🟡 Backup alert configured (notify if backup is >24h old)

---

## 3. AUTHENTICATION & SECURITY

### JWT / Tokens
- [ ] 🔴 `JWT_SECRET` is a strong random value (min 256 bits) — NOT the default dev value
- [ ] 🔴 Legacy tokens now enforce session_epoch (SEC-002 fix applied in Fase 5)
- [ ] 🟡 `JWT_ACCESS_TOKEN_MINUTES` set to 15 (current: 30 in dev)
- [ ] 🟡 Old legacy login endpoint (`/api/auth/login`) issues tokens with `ver=session_epoch`

### Demo / Test Users
- [ ] 🔴 `SEED_DEMO=false` or unset in production — verified no test accounts exist:
  - `advertiser@test.mediaview.com` — MUST NOT exist
  - `managed.viewer@demo.mediaview.com` — MUST NOT exist
  - `sarah@brightagency.com`, `carlos@urbanmedia.co` — MUST NOT exist
  - `rbac.*@test.com` — MUST NOT exist
  
  Verification command:
  ```bash
  mongosh "$MONGO_URL" --eval 'db.users.find({email: {$regex: /@test\.|@demo\./}}).count()'
  # Expected: 0
  ```

### CORS
- [ ] 🔴 `CORS_ORIGINS` is NOT `*` in production
- [ ] 🔴 `CORS_ORIGINS` matches exact frontend origin (protocol + domain + port)

### Rate Limiting
- [ ] 🟡 `REDIS_URL` set — rate limiter becomes cluster-safe
- [ ] 🟡 Verify login endpoint blocked at 5/minute/IP (test in staging)
- [ ] 🟡 Verify register endpoint blocked at 3/minute/IP in production config

### RBAC
- [ ] ✅ `MANAGED_VIEWER` role blocks: screen create, media upload, publish playlist
- [ ] ✅ Tenant isolation verified: cross-org reads return 403/empty
- [ ] ✅ Admin endpoints require `SUPER_ADMIN` or `MEDIAVIEW_ADMIN` role

---

## 4. STORAGE

### Current State
IMPORTANT: Media is currently stored on local filesystem (`/app/backend/uploads/`).
This is ephemeral in containerized environments and will be lost on redeploy.

### Action Required Before Go-Live with Real Media
- [ ] 🔴 Configure Cloudflare R2 (or equivalent) before accepting real media uploads:
  - Set `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` in env
  - Set `R2_PUBLIC_URL` for serving
  - Verify `StorageService` R2 driver is active (check `R2_ENABLED` flag in `storage.py`)
- [x] ✅ `StorageService` abstraction implemented (Fase 6) — no scattered boto3 in routes
- [x] ✅ Upload security: MIME magic-byte validation + path traversal protection (Fase 6)
- [ ] 🔴 Ensure media upload path uses R2 when env vars are set
- [ ] 🟡 Set max upload file size in environment (currently ~50MB per request)
- [ ] 🟡 Media CDN (Cloudflare) configured for public serving
- [ ] 🟡 Signed URLs for private media (advertiser creatives)
- [ ] 🔵 Old filesystem media migrated to R2 (non-destructive)

### APK / Player Updates
- [ ] 🟡 APK files served from R2/CDN (not local filesystem)
- [ ] 🟡 APK version endpoint returns correct version for player self-update

---

## 5. SCHEDULER / WORKERS

### SCHEDULER_MODE
- [ ] 🔴 Set `SCHEDULER_MODE=arq` in production (if ARQ worker is deployed)
- [ ] 🔴 If only one process: set `SCHEDULER_MODE=apscheduler`
- [ ] 🔴 NEVER run both simultaneously (dual-execution causes duplicate campaign transitions)

### ARQ Worker (if deployed)
- [ ] 🟡 Redis is accessible from the worker process
- [ ] 🟡 Worker has `cron_campaign_scheduler_tick` registered
- [ ] 🟡 Finance scheduler registered in ARQ worker (if `SCHEDULER_MODE=arq`)
- [ ] 🟡 Colorlight scheduler registered in ARQ worker (if applicable)

### Campaign Scheduler
- [ ] 🟡 Campaign status transitions tested in staging (PENDING → APPROVED → SCHEDULED → ACTIVE → COMPLETED)
- [ ] 🟡 Cron tick interval verified (every minute in production)

---

## 6. STRIPE / PAYMENTS

### Current State — BILLING IS MOCKED
ALL payments are currently mocked. `payment_status = "mocked_paid"` is used throughout.

### Mock Locations (must be replaced for Stripe Live)
1. `advertising_routes.py:475` — Campaign payment mock
   `payment_ref = f"MOCK-PAY-{...}"` to replace with Stripe Checkout
2. `advertising_routes.py:481,491` — `payment_status: "mocked_paid"` to `"stripe_paid"`
3. `advertising_routes.py:777` — Revenue report counts `mocked_paid` as revenue
4. `campaign_scheduler.py:38` — `VALID_PAYMENT_STATUSES = {"mocked_paid", "paid", "stripe_paid"}`
5. `server.py:1556` — `stripe_payment_id: mock_pi_...`
6. `self_service_routes.py` — Subscription activation is mocked

### Before Stripe Live
- [ ] 🔴 Stripe Live keys (`sk_live_...`, `pk_live_...`) configured in env
- [ ] 🔴 Stripe webhook secret (`whsec_...`) configured
- [ ] 🔴 Remove `mocked_paid` as a valid payment status from campaign_scheduler
- [ ] 🔴 All 6 mock locations above replaced with real Stripe logic
- [ ] 🔴 Stripe webhook endpoint tested (`POST /api/billing/webhook`)
- [ ] 🔴 Test a real charge in Stripe test mode first
- [ ] 🟡 Payment failure handling tested (card declined, insufficient funds)
- [ ] 🟡 Refund flow tested

---

## 7. PLAYER (ANDROID)

### Pre-Launch Tests (MANUAL — STAGING REQUIRED)
Each test requires a physical Android device or emulator:

- [ ] 🔴 Pairing: QR code pairing completes successfully
- [ ] 🔴 Reboot recovery: Player restarts and reconnects after device reboot
- [ ] 🔴 Auto-start: Player starts on boot (Android BOOT_COMPLETED intent)
- [ ] 🔴 Playlist playback: Images play at correct intervals
- [ ] 🔴 Video playback: Videos play without black screen
- [ ] 🔴 Portrait/Landscape: Screen orientation matches configuration
- [ ] 🟡 Offline mode: Last playlist serves from cache when internet lost
- [ ] 🟡 Internet recovery: Player resumes fetching updates after reconnect
- [ ] 🟡 Content update: New published playlist appears within 5 minutes
- [ ] 🟡 Atomic update: Content switches cleanly without black frame
- [ ] 🟡 Heartbeat: Server marks device online within 5 minutes
- [ ] 🟡 Campaign ad: Ad creatives served at correct frequency
- [ ] 🟡 Proof-of-play: Play events appear in admin panel
- [ ] 🔵 APK update: Self-update OTA flow completes successfully
- [ ] 🔵 8h endurance test: No memory leaks, crashes, or black screens after 8h

### Player Recovery Tests (MANUAL)
- [ ] 🟡 Internet loss → Player shows cached content (not crash)
- [ ] 🟡 API unavailable → Player logs error and retries with backoff
- [ ] 🟡 Corrupt asset → Player skips corrupted item and continues
- [ ] 🟡 404 asset → Player logs and skips, does not crash
- [ ] 🟡 Expired device token → Player shows re-pair screen
- [ ] 🔵 OOM/memory pressure → Player handled gracefully

---

## 8. OBSERVABILITY

### Logging
- [ ] 🔴 Verify no passwords, JWT tokens, or secrets appear in logs
- [ ] 🟡 Structured logs enabled in production (JSON format preferred)
- [ ] 🟡 Log aggregation configured (Papertrail, Datadog, or Render logs)
- [ ] 🟡 Log retention policy: minimum 30 days

### Monitoring
- [ ] 🟡 Uptime monitor on `GET /api/health` (every 1 minute, alert on 2 failures)
- [ ] 🟡 Database connection monitor (alert if pool exhausted)
- [ ] 🟡 Redis connection monitor (if deployed)
- [ ] 🟡 Sentry DSN configured (`SENTRY_DSN` env var)
- [ ] 🔵 Alert on campaign scheduler tick failures
- [ ] 🔵 Alert on offline screens (>30 min without heartbeat)

### Health Endpoints (Updated — Fase 6)
- [x] ✅ `GET /api/health` — Legacy liveness (returns `{"status":"healthy","ok":true}`) — **VERIFIED FASE 6**
- [x] ✅ `GET /api/livez` — Full liveness probe (uptime, env, version) — **NEW FASE 6**
- [x] ✅ `GET /api/ready` — Readiness probe: checks Mongo + Storage + Redis + Worker — **NEW FASE 6**
- [ ] 🟡 Configure K8s/Render liveness on `/api/livez` (never touches DB — fast)
- [ ] 🟡 Configure K8s/Render readiness on `/api/ready` (touches DB — gates traffic)

---

## 9. DEPLOYMENT

### Deployment Process
- [ ] 🔴 Production deployment uses immutable container image (not direct code push)
- [ ] 🔴 Zero-downtime deployment configured (health check before traffic swap)
- [ ] 🟡 Deployment smoke test script:
  ```bash
  curl -f https://api.mediaview.io/api/health
  curl -f -X POST https://api.mediaview.io/api/auth/v2/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@mediaview.io","password":"..."}'
  ```

### Rollback Procedure
1. Backend rollback (Render): Dashboard → Service → Deployments → Select previous → Redeploy
2. Frontend rollback: Same as backend. Or redeploy previous git tag.
3. Database rollback (if needed):
   - Stop backend service
   - Restore from Atlas point-in-time backup
   - Restart backend
   - Verify with smoke test
4. Player/APK rollback:
   - Update player_version endpoint to return previous APK version
   - Players will self-downgrade on next check
5. Emergency maintenance mode:
   - Set `MAINTENANCE_MODE=true` in env vars
   - Redeploy — API returns 503 for all non-health endpoints
   - Reverts by unsetting the variable

---

## 10. PRE-LAUNCH SMOKE TESTS

Run these against the production environment immediately after deployment:

```bash
# 1. Health check
curl -f https://api.mediaview.io/api/health

# 2. Login as admin (use production credentials)
TOKEN=$(curl -s -X POST https://api.mediaview.io/api/auth/v2/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@mediaview.io","password":"..."}' | jq -r .access_token)

# 3. Admin dashboard
curl -f -H "Authorization: Bearer $TOKEN" \
  https://api.mediaview.io/api/analytics/dashboard

# 4. Confirm no test users exist
curl -X POST https://api.mediaview.io/api/auth/v2/login \
  -H "Content-Type: application/json" \
  -d '{"email":"advertiser@test.mediaview.com","password":"Advertiser#2026"}'
# Expected: 401 (user does not exist)

# 5. Confirm CORS rejects unknown origin
curl -H "Origin: https://attacker.com" https://api.mediaview.io/api/health
# Expected: No Access-Control-Allow-Origin header for unknown origins
```

---

## 11. POST-LAUNCH (FIRST 72 HOURS)

- [ ] 🟡 Monitor error rate in Sentry / logs
- [ ] 🟡 Watch campaign scheduler logs for any stuck transitions
- [ ] 🟡 Verify first real advertiser payment goes through Stripe correctly
- [ ] 🟡 Test at least one full MANAGED_VIEWER client flow
- [ ] 🟡 Verify player heartbeats visible in admin dashboard
- [ ] 🔵 Review MongoDB Atlas performance advisor for slow queries
- [ ] 🔵 Enable MongoDB Atlas Performance Insights alerts

---

## SIGN-OFF

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Backend Lead | | | |
| DevOps / Infra | | | |
| QA Lead | | | |
| Security Review | | | |
| Product Owner | | | |

---
*This checklist was auto-generated during MediaView Fase 5 Pre-Production Audit.*  
*Updated during Fase 6 — Production Infrastructure Hardening.*  
*Last updated: 2026-06 — Review and update before each major release.*
