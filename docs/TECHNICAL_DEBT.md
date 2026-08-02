# MediaDView — Deuda Técnica registrada

Documento vivo. Se actualiza al final de cada fase. Se cierra un ítem
solo cuando el usuario confirma que la solución en producción es
aceptable.

---

## D-01 · SLA muestra `None` cuando no hay `approved_at`
**Registrado por**: usuario · aprobación de C4
**Módulo**: `reports_service.sla_metrics`, `web/admin-reports.html`
**Estado actual**: Cuando una orden no tiene `approved_at` en la muestra,
las métricas devuelven `None` y la UI imprime literalmente el texto
"None".
**Comportamiento esperado**: Mostrar **"N/A"** o **"Sin datos
suficientes"** en la UI, y devolver `null` explícito con un flag
`insufficient_data: true` en la respuesta JSON. El PDF/XLSX debe rendir
"N/A" también.
**Prioridad**: 🟡 Media — cosmético pero necesario antes de producción
**Fix effort**: ~30 min
**Bloquea producción**: SÍ

---

## D-02 · Ocupación con default silencioso de 14 h/día
**Registrado por**: usuario · aprobación de C4
**Módulo**: `reports_service.screen_occupancy`, `web/admin-reports.html`
**Estado actual**: Cuando una pantalla no tiene
`operating_hours_per_day` configurado, la ocupación asume 14 h/día
silenciosamente.
**Comportamiento esperado**: 
- La respuesta JSON debe incluir `operating_hours_source: "configured" | "default_14h" | "unknown"` para que la UI muestre un indicador.
- La UI debe mostrar **"Horario no configurado"** o el valor default con badge amarillo **"(default 14h — configurar en pantalla)"**.
- El export debe llevar la misma bandera.
**Prioridad**: 🟡 Media — evita interpretaciones erróneas del reporte
**Fix effort**: ~1 h (backend + UI + export)
**Bloquea producción**: SÍ

---

## D-03 · Pantallas con nombre `(unknown)` en reportes
**Registrado por**: usuario · aprobación de C4
**Módulo**: seed data + `reports_service.revenue_by_screen`
**Estado actual**: Órdenes de smoke test referencian `screen_id` que no
existen en `db.screens`; se muestran como "(unknown)".
**Acción**: Correr script de limpieza `tools/cleanup_test_data.py`
(pendiente de crear) antes de producción. Marca la orden con
`data_quality_issue: "screen_missing"` para no perder trazabilidad.
**Prioridad**: 🟡 Media
**Fix effort**: ~1 h (script de limpieza + verificación)
**Bloquea producción**: SÍ (higiene de datos)

---

## D-04 · Consolidado multi-moneda USD ↔ DOP sin auto-conversión
**Registrado por**: usuario · aprobación de C4
**Módulo**: `reports_service.executive_dashboard`
**Estado actual**: El dashboard opera en una moneda a la vez; no hay
consolidado USD+DOP+EUR+… porque falta fuente confiable de tasas.
**Decisión del usuario**: Se DEJA PENDIENTE hasta que se integre una
fuente confiable de tasas (candidatos: XE.com, Open Exchange Rates,
Banco Central RD para DOP/USD). No hacer conversiones automáticas hasta
entonces.
**Prioridad**: 🟢 Baja — feature futura, no bloqueante
**Fix effort**: ~1 día (integración de proveedor de tasas + tabla
`fx_rates` + snapshot diario)
**Bloquea producción**: NO — se mantiene como Sprint 3+

---

## Nota estructural
Todos los ítems D-01, D-02, D-03 se agrupan como bloque **"Higiene de
Reportes"** y se abordarán juntos en Fase 6 · Sub-fase 6.0 (previo al
primer deploy en Render).
