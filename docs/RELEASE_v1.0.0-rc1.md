# MediaDView — Release Candidate 1

**Version**: `v1.0.0-rc1`
**Fecha**: Sprint 1 · Semana 1 · Post-P0 closure
**Estado**: 🟢 **READY FOR STAGING DEPLOY**

---

## Resumen

Esta es la **primera Release Candidate de MediaDView**. El código está
congelado en este punto: **no se aceptarán cambios funcionales** hasta
que la RC pase por staging + QA A40 físico y sea promovida a v1.0.0.

Los únicos cambios permitidos sobre la RC son:
- Correcciones de bugs bloqueantes descubiertos en staging (**hotfixes con nueva RC** — v1.0.0-rc2, rc3…).
- Ajustes de documentación (no requieren nueva RC).

---

## Composición de la RC

| Módulo | Cierre | Cobertura test |
|--------|--------|----------------|
| Auth v2 (JWT + Fernet + HttpOnly + lockout) | Fase 4 | E2E básico |
| RBAC granular (20+ permisos, 8 roles) | Sprint 1 · C0 | 44 smoke assertions |
| Guest checkout (Magic-link + Quote HMAC + slot atomic) | Sprint 1 · Etapa B | smoke_etapa_b_v2 |
| Order state machine (10 states) | Sprint 1 · Etapa B | smoke_c3_refunds |
| Admin Orders panel + approval | Sprint 1 · C1 | E2E |
| Invoices (PDF + numbering + reissue) | Sprint 1 · C2 | 18 smoke assertions |
| **Refunds** (4 policies + dual approval + concurrency) | Sprint 1 · C3 | 95% |
| **Credit Notes** (CN-YYYY-000001 + PDF + link) | Sprint 1 · C3 | 90% |
| **Financial Ledger** (append-only + hash chain + multi-currency) | Sprint 1 · C3 | 90% |
| **Executive Dashboard** (16 KPIs + charts + real-time) | Sprint 1 · C4 | 44 smoke assertions |
| **Reports Exports** (CSV/XLSX/PDF × 8 reports) | Sprint 1 · C4 | 24 combinaciones |
| **BI-ready flat endpoints** (Power BI / Tableau / Looker) | Sprint 1 · C4 | Testeado |
| Payment Provider abstraction (Stripe / LocalDev) | Sprint 1 · C0 | Con LocalDev |
| Colorlight A40 player | Fase 3 | 0% (QA físico pendiente) |

---

## Suites de verificación (todas verdes)

| Suite | Resultado |
|-------|-----------|
| `tests/smoke_etapa_a` | ✅ PASSED |
| `tests/smoke_etapa_b_v2` | ✅ PASSED |
| `tests/smoke_c3_refunds` | ✅ **18/18** |
| `tests/smoke_c4_reports` | ✅ **44/44** |
| `tests/e2e_playwright` | ✅ **14/14** |
| `GET /api/health` | ✅ 200 healthy |
| `GET /api/ready` | ✅ 200 mongo+redis+worker OK |
| `tools/reset_for_production.py --dry-run` | ✅ Funcional |

**Total aserciones automatizadas: 76+**

---

## 6 P0 cerrados

| ID | Hallazgo | Fix |
|----|----------|-----|
| P0-A1 | Security headers HTTP | Middleware `security_headers.py` con HSTS/CSP/XFO |
| P0-A2 | XSS en menu-editor + player-activate | `esc()` helper en 6 puntos |
| P0-A3 | Magic-number validation en uploads | `media_validator.py` con `filetype` |
| P0-A4 | 4 `except Exception:` en checkout_service | 3 documentados + 1 corregido |
| P0-A5 | Test Playwright E2E | 14 aserciones cubriendo panel admin |
| P0-A6 | Sentry startup guard en producción | Warning crítico si `SENTRY_DSN` falta |

Detalle en `docs/P0_CLOSURE_REPORT.md`.

---

## Artefactos de infraestructura

Todos listos, ninguno usado en el entorno de dev:

| Archivo | Estado |
|---------|--------|
| `.gitignore` | Excluye `.env`, artefactos test, IDE files |
| `.dockerignore` | Excluye `__pycache__`, tests, docs |
| `Dockerfile` | Multi-stage producción Python 3.11-slim |
| `render.yaml` | Blueprint con `web` + `worker` + secrets `sync:false` |
| `.github/workflows/ci.yml` | 5 jobs: lint, test, e2e, validate, docker |
| `docs/DEPLOYMENT_STEPS.md` | Guía paso-a-paso Semana 2 (433 líneas) |
| `docs/RUNBOOK.md` | Procedimientos operativos (395 líneas) |
| `backend/.env.example` | 40+ vars documentadas |
| `tools/reset_for_production.py` | Script de limpieza pre-deploy (421 líneas) |

---

## Deuda técnica registrada (aceptada para la RC)

| ID | Descripción | Bloquea prod |
|----|-------------|--------------|
| D-01 | SLA muestra "N/A" cuando falta approved_at | ✅ Resuelto |
| D-02 | Ocupación con default 14h (con badge de transparencia) | ✅ Resuelto |
| D-03 | Screens "(unknown)" marcadas con `data_quality_issue` | ✅ Resuelto |
| D-04 | Consolidado multi-moneda pendiente feed de tasas | NO (Sprint 3) |
| D-05 | `/media/presign` sin magic-number check | NO (Sprint 2 cuando se active) |

---

## Freeze declarations

**Congelado durante la RC**:
- Ningún cambio funcional
- Ningún refactor arquitectónico
- Ningún nuevo módulo
- Ninguna integración externa

**Permitido durante la RC**:
- Hotfixes de bugs bloqueantes (nueva rc-N)
- Actualizaciones de documentación
- Configuración de infraestructura externa (no modifica código)

---

## Pendiente para promoción a v1.0.0

- [ ] Deploy en Render staging + validación 24 h
- [ ] QA en 1 A40 físico (playback real de video)
- [ ] Certificado SSL A+ verificado
- [ ] BetterStack monitor con 100% uptime en 24 h
- [ ] `securityheaders.com` grado A o A+
- [ ] `mail-tester.com` correo saliente 10/10
- [ ] Superadmin real creado (no seed) con password rotado
- [ ] Prueba de rollback en staging exitosa
- [ ] Prueba de restore Atlas Point-in-Time exitosa
- [ ] Aprobación final del owner

---

## Firma técnica

- Commit: `<pendiente de tag>`
- Tag: `v1.0.0-rc1`
- Backend: FastAPI 0.110.1 · Python 3.11
- Frontend: Vanilla HTML5/CSS3/JS + Chart.js 4.4.0 CDN
- DB: MongoDB 7 (Motor 3.3.1)
- Cache/Queue: Redis 7 (redis-py + ARQ)
- PDF: reportlab 4.5.1
- Payments: Stripe (pending) via `PaymentProvider` abstraction · **LocalDevProvider active**

---

## Referencias

- `docs/P0_CLOSURE_REPORT.md`
- `docs/FINAL_PRODUCTION_REVIEW.md`
- `docs/PRODUCTION_READINESS_AUDIT.md`
- `docs/DEPLOYMENT_STEPS.md`
- `docs/RUNBOOK.md`
- `docs/TECHNICAL_DEBT.md`
