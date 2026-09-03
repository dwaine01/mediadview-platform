# MediaView — MongoDB Atlas Migration Guide
> Fase 6: Production Infrastructure  
> Status: CODE READY — REAL TEST PENDING (Atlas credentials required)  
> Prepared: 2026-06 | Environment: development → production

---

## Overview

MediaView currently runs against **`mongodb://localhost:27017`** (development).  
Before Go-Live the database MUST be migrated to **MongoDB Atlas** (managed cloud cluster).  
This document describes every step required to make that migration safely and without data loss.

---

## 1. Why Atlas (Not Local Mongo)?

| Concern | Local Mongo | MongoDB Atlas |
|---------|-------------|---------------|
| High Availability | ❌ Single point of failure | ✅ Replica set (3-node min) |
| Automatic Backups | ❌ Manual only | ✅ Continuous backups + PITR |
| Network Security | ❌ Exposed to container network | ✅ VPC peering + IP Allowlist |
| Monitoring | ❌ None | ✅ Atlas Performance Advisor |
| Scaling | ❌ Manual vertical | ✅ Auto-scale or easy tier change |
| Disaster Recovery | ❌ No PITR | ✅ Point-in-time recovery (7 days+) |

---

## 2. Pre-Migration Checklist

Before executing any migration step, verify these are in place:

- [ ] MongoDB Atlas account created at [cloud.mongodb.com](https://cloud.mongodb.com)
- [ ] Project created inside Atlas (e.g., `mediaview-prod`)
- [ ] Cluster tier selected (M10 minimum for production; M0 free tier for staging only)
- [ ] Database user created with **`readWrite`** privileges on `mediaview_db` only (NOT `atlasAdmin`)
- [ ] Network Access: Add deployment IP (Render, EC2, etc.) to IP Allowlist
- [ ] Atlas connection string copied: `mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/mediaview_db?retryWrites=true&w=majority`

---

## 3. Environment Variable Update

When you have the Atlas connection string, update your production environment (NOT local `.env`):

```bash
# In Render / Railway / ECS / etc. — set as a secret env var
MONGO_URL=mongodb+srv://<user>:<password>@<cluster-url>/mediaview_db?retryWrites=true&w=majority
```

> **CRITICAL:** The startup validator (`startup_check.py`) will **FAIL FAST** and refuse to start  
> if `ENVIRONMENT=production` and `MONGO_URL` contains `localhost` or `127.0.0.1`.

**Validation rule enforced by `startup_check.py`:**
```python
if IS_PROD and ("localhost" in MONGO_URL or "127.0.0.1" in MONGO_URL):
    # → sys.exit(1) with clear error message
```

---

## 4. Data Export from Local MongoDB

### 4a. Export all collections (full dump)

```bash
# Run from the container or your local machine where mongod is running
mongodump \
  --uri="mongodb://localhost:27017/mediaview_db" \
  --archive=/tmp/mediaview_backup_$(date +%Y%m%d_%H%M%S).gz \
  --gzip

# Verify the archive was created
ls -lh /tmp/mediaview_backup_*.gz
```

### 4b. Verify exported data

```bash
# Quick sanity check — list collections in dump
mongodump \
  --uri="mongodb://localhost:27017/mediaview_db" \
  --archive=/dev/null \
  --gzip \
  --verbose 2>&1 | grep "writing"
```

Expected collections to be present:
- `users` — all registered accounts
- `screens` — display screens inventory
- `devices` — paired player devices
- `campaigns` — self-service ad campaigns
- `ad_campaigns` — public advertising campaigns
- `playlists` — content playlists
- `media` — uploaded media metadata
- `audit_logs` — RBAC + security audit trail
- `client_requests` — managed portal requests
- `customer_orders` — transient customer orders
- `sessions` — refresh token store

---

## 5. Data Import to MongoDB Atlas

### 5a. Import dump to Atlas

```bash
mongorestore \
  --uri="mongodb+srv://<user>:<password>@<cluster>.mongodb.net/mediaview_db?retryWrites=true&w=majority" \
  --archive=/tmp/mediaview_backup_<timestamp>.gz \
  --gzip \
  --drop          # ← drops target collections before import (safe on first migration)

# Confirm document counts match
mongosh "mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/mediaview_db" \
  --eval 'db.getCollectionNames().forEach(c => print(c, db[c].countDocuments()))'
```

### 5b. Cross-check document counts

Run this on **local** and compare output with **Atlas**:

```bash
mongosh "mongodb://localhost:27017/mediaview_db" \
  --eval 'db.getCollectionNames().forEach(c => print(c, db[c].countDocuments()))'
```

All counts must match exactly before proceeding.

---

## 6. Index Verification

MediaView creates all indexes automatically via `db_indexes.py` at startup.  
After migration, verify they were created on Atlas:

```bash
mongosh "mongodb+srv://..." --eval '
  ["users","screens","devices","campaigns","ad_campaigns","sessions","audit_logs"].forEach(col => {
    print("=== " + col + " ===");
    printjson(db[col].getIndexes().map(i => i.name));
  });
'
```

Expected key indexes:
| Collection | Index | Type |
|-----------|-------|------|
| `users` | `email_1` | Unique |
| `users` | `rbac_role_1` | Regular |
| `screens` | `pairing_code_1` | Unique Sparse |
| `screens` | `organization_id_1_type_1` | Compound |
| `devices` | `screen_id_1` | Regular |
| `ad_campaigns` | `status_1_start_date_1_end_date_1` | Compound |
| `audit_logs` | `created_at_1` | TTL (2 years) |
| `sessions` | `expires_at_1` | TTL (auto-expire) |

---

## 7. Startup Validation Flow

Once `MONGO_URL` is updated and backend is restarted, the following occurs automatically:

```
[startup_check.py]
  1. Reads ENVIRONMENT, MONGO_URL, JWT_SECRET, ORDER_LINK_SECRET, CORS_ORIGINS
  2. ENVIRONMENT=production + localhost Mongo → FAIL FAST (sys.exit 1)
  3. ENVIRONMENT=production + weak JWT → FAIL FAST
  4. ENVIRONMENT=production + CORS=* → FAIL FAST
  5. All checks PASS → server starts normally

[db_indexes.py — called at startup via lifespan]
  6. Connects to Atlas
  7. Creates all indexes idempotently (safe to run multiple times)
  8. Logs "indexes ensured"

[GET /api/ready]
  9. Pings Atlas: db.command("ping")
  10. Returns {"ok": true, "checks": {"mongo": {"ok": true, "latency_ms": N}}}
```

---

## 8. Staging vs Production

| Setting | Staging | Production |
|---------|---------|------------|
| `ENVIRONMENT` | `staging` | `production` |
| `MONGO_URL` | Atlas staging cluster | Atlas production cluster |
| Localhost Mongo | ❌ Rejected (same as prod) | ❌ Rejected |
| `CORS_ORIGINS=*` | ❌ Rejected | ❌ Rejected |
| Stripe | Test mode (`sk_test_...`) | Live mode (`sk_live_...`) |
| `SEED_DEMO` | Allowed in staging | MUST be `false` |

> **Staging behaves like production for all infrastructure checks.**  
> The only difference is Stripe remains in test mode until explicit cutover.

---

## 9. Post-Migration Smoke Tests

Run immediately after deploying with Atlas `MONGO_URL`:

```bash
BASE="https://api.your-domain.com/api"

# 1. Readiness probe — must show mongo.ok=true against Atlas
curl -s "$BASE/ready" | python3 -m json.tool

# 2. Login still works (verifies auth collection migrated correctly)
TOKEN=$(curl -s -X POST "$BASE/auth/v2/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"superadmin@mediadview.com","password":"<prod-password>"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3. Admin dashboard
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/analytics/dashboard" | python3 -m json.tool

# 4. Screen count (verify data migrated)
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/admin/screens" | python3 -c "import sys,json; print('Screens:', len(json.load(sys.stdin)))"
```

---

## 10. Rollback Plan

If Atlas migration fails or causes regressions:

1. **Revert `MONGO_URL`** to local/previous value in deployment environment
2. Redeploy backend (startup_check.py will validate correctly)
3. Data remains intact in local Mongo (export was non-destructive)
4. File a ticket with the Atlas error and latency observations
5. Re-attempt migration after root cause is identified

---

## 11. Atlas Configuration Recommended Settings

```yaml
Cluster Tier: M10 (2 vCPU, 2 GB RAM) minimum for production
Storage: 10 GB initial, auto-scale enabled
Backup:
  - Continuous backups: ENABLED
  - Point-in-time recovery: 7 days
  - Snapshot frequency: every 6 hours
  - Snapshot retention: 7 days
Network Access:
  - Deployment server IP(s) only
  - VPC peering preferred (Render Private Services / AWS VPC)
Monitoring:
  - Atlas Performance Advisor: ENABLED
  - Real-time Performance Panel: ENABLED
  - Alert: any replica set election → page on-call
  - Alert: storage > 80% → email DevOps
```

---

## Status at Time of Writing (Fase 6)

| Component | Status |
|-----------|--------|
| Code support for Atlas URL | ✅ READY |
| `startup_check.py` enforces Atlas in prod | ✅ READY |
| `db_indexes.py` idempotent on Atlas | ✅ READY (test K passed locally) |
| `/api/ready` pings Atlas | ✅ READY (code) |
| Real Atlas cluster provisioned | ⏳ PENDING (awaiting user credentials) |
| Real Atlas connection tested | ⏳ PENDING (awaiting user credentials) |
| Data migrated to Atlas | ⏳ PENDING |

---

*Document generated: Fase 6 — Production Infrastructure*  
*Author: MediaView Engineering*  
*Next review: Before Go-Live cutover*
