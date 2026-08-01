# MediAd View — Testing Standards (institutional rule)

## Establecido por el stakeholder al cierre de Sprint 1 · Etapa B

**Ninguna funcionalidad nueva se dará por terminada únicamente porque
compile o pase pruebas unitarias.**

Toda funcionalidad crítica debe pasar los tres niveles siguientes antes
de considerarse cerrada operativamente:

### 1. Pruebas unitarias — correctitud del código
- Ubicación: `backend/tests/smoke_*.py`, `backend/tests/unit_*.py`
- Cubren: máquinas de estado, validaciones puras, firma HMAC, redacción de logs, etc.
- Ejecución: `python -m tests.smoke_<phase>`
- **Criterio de éxito**: 100% verdes, ejecutadas por el agente durante el desarrollo.

### 2. Pruebas de integración — interacción entre módulos
- Ubicación: `backend/tests/test_*.py`
- Cubren: rutas HTTP + Mongo + Redis + rate limit + auditoría, todo dentro
  del proceso pero con dependencias reales (Mongo local, Redis local).
- Ejecución: `pytest backend/tests/`
- **Criterio de éxito**: 100% verdes; `testing_agent` invocado si involucra
  regresiones en features previas.

### 3. Pruebas end-to-end con servicios reales
- Ubicación: `backend/tests/*_live_e2e.py` (Stripe, R2, WhatsApp Business, etc.)
- Cubren: flujo completo contra el proveedor externo real (en modo Test/Sandbox).
- Ejecución: manual por el operador tras inyectar credenciales seguras.
- **Criterio de éxito**: informe en `test_reports/*_live_e2e.md` con IDs
  externos verificables, transiciones de estado observadas, y auditoría
  correspondiente. **Sin este paso, ninguna funcionalidad crítica se cierra.**

---

## Reglas asociadas

- **Credenciales**: NUNCA en chat, código, logs, o reportes de testing.
  Solo variables de entorno seguras. Ver `docs/FASE5_STRIPE_TEST_SETUP.md`.
- **Redacción**: `observability.py` cubre claves de Stripe (`sk_*`, `pk_*`,
  `whsec_*`, `pi_*_secret_*`), JWTs, tarjetas y PII.
- **Nada de modo Live** hasta que el stakeholder lo autorice explícitamente.
- **Rollback plan**: cada cambio crítico debe poder ejecutarse en producción
  sin migraciones destructivas de datos legacy hasta que el stakeholder
  apruebe explícitamente la purga.

---

## Estado del proyecto (a fecha de cierre Sprint 1 · Etapa B)

| Fase | Estado | Validación real completada |
|---|---|---|
| Fase 1 · GitHub Ready | ✅ Aprobado | N/A |
| Fase 2 · Seguridad / Auth v2 | ✅ Aprobado | ✅ (Auth v2 en producción interna) |
| Fase 3 · Docker / Redis / ARQ | ✅ Aprobado | ✅ (ready check verde) |
| Fase 4 · Cloudflare R2 | ✅ Aprobado | ✅ (testing_agent 20/20) |
| Sprint 1 · Etapa A · Stripe base | ✅ Aprobado | ✅ (smoke tests) |
| Sprint 1 · Etapa B · Guest checkout | ✅ Aprobado (dev) | ⏸️ Pendiente `stripe_live_e2e.py` |
| Sprint 1 · Etapa C · Admin / Facturas / Reembolsos | ⏸️ En espera | ⏸️ |
