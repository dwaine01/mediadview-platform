# Fase 2B-6 — mapa real de las rutas `/admin/*` y `/superadmin/*`

Generado por AST sobre `backend/server.py` en **`258bbae`** (`trunk` = `main`, ya con la 2B-5
fusionada). **Los números de línea de cualquier mapa anterior a este commit ya no sirven:**
`server.py` se corrió ~1000 líneas al salir `/player/*` y `/devices/*`.

## Corrección al conteo del plan

`docs/REFACTOR_FASE2_PLAN.md` decía «46 `/admin/*` + 5 `/superadmin/*`» (51). El conteo real hoy
es **46 rutas en total**: **41 `/admin/*` + 5 `/superadmin/*`**, y ocupan **868 líneas** de
handlers (sin contar modelos ni helpers). La diferencia es que 13 rutas `/admin/screens*` ya se
fueron en la 2B-3 y algunas `/admin/*` de finanzas/facturación nunca estuvieron en `server.py`
(viven en `admin_invoices_routes.py`, `admin_orders_routes.py`, `admin_refunds_routes.py`,
`finance.py`, `reports_routes.py`).

Consecuencia para el plan: **no hay bloque de «finanzas» que extraer de `server.py`** — el
tercer PR previsto se convierte en «superadmin + usuarios/RBAC + vistas HTML».

## Reparto por segundo segmento

| Rutas | Grupo | Rutas | Grupo |
|---|---|---|---|
| 12 | `/admin/devices/*` | 3 | `/admin/rbac/*` |
| 5 | `/admin/campaigns/*` | 3 | `/superadmin/admins*` |
| 4 | `/admin/widgets/*` | 3 | `/admin/customer-orders/*` |
| 2 | `/admin/player-release` | 2 | `/admin/users*` |
| 2 | `/admin/campaign-scheduler/*` | 3 | `/admin/*-view` (HTML) |
| 1 cada | `/admin/analytics`, `/admin/payments`, `/admin/playlogs`, `/admin/client-errors`, `/admin/migrate-operation-types`, `/superadmin/create-admin`, `/superadmin/overview` | | |

## Corte propuesto en 3 PRs

Criterio: cada PR agrupa un dominio cerrado y **ningún PR mezcla rutas que compartan helpers con
otro PR**, para que el script de extracción no tenga que threadear lo mismo dos veces.

### PR 2B-6a — `admin_devices_routes.py` (17 rutas, ~340 líneas)
El bloque más contiguo (`1887`→`2208`) y el que ya conocemos bien tras la 2B-5: comparte
`gen_activation_code` con `player_routes.py` y `screens_routes.py` (ya threadeado en ambos).

| Líneas | Método | Ruta | Handler |
|---|---|---|---|
| 1887-1909 | POST | `/admin/player-release` | `set_player_release` |
| 1911-1918 | GET | `/admin/player-release` | `get_player_release` |
| 1921-1925 | GET | `/admin/devices/{device_id}/logs` | `admin_device_logs` |
| 1927-1949 | GET | `/admin/devices/{device_id}/diagnostics` | `admin_device_diagnostics` |
| 1953-1969 | PUT | `/admin/devices/{device_id}/power-schedule` | `set_power_schedule` |
| 1971-1977 | GET | `/admin/devices/{device_id}/power-schedule` | `get_power_schedule` |
| 1979-1996 | POST | `/admin/devices/{device_id}/power` | `device_power_control` |
| 2002-2026 | GET | `/admin/devices` | `admin_list_devices` |
| 2028-2070 | POST | `/admin/devices/activate` | `admin_activate_device` |
| 2072-2108 | POST | `/admin/devices/provision` | `admin_provision_device` |
| 2110-2116 | DELETE | `/admin/devices/{device_id}` | `admin_remove_device` |
| 2118-2132 | PUT | `/admin/devices/{device_id}/reassign` | `admin_reassign_device` |
| 2134-2144 | PUT | `/admin/devices/{device_id}/unlink` | `admin_unlink_device` |
| 2162-2191 | GET | `/admin/playlogs` | `get_play_logs` |
| 2195-2208 | PUT | `/admin/devices/{device_id}/command` | `send_device_command` |
| 1220-1223 | GET | `/admin/client-errors` | `list_client_errors` |
| 1754-1778 | GET | `/admin/analytics` | `admin_analytics` |

⚠️ `admin_activate_device` usa `gen_activation_code`; `admin_provision_device` define/usa el
modelo `DeviceProvision`. Revisar si ese modelo lo usa alguien más antes de moverlo.

### PR 2B-6b — `admin_campaigns_routes.py` (12 rutas, ~300 líneas)

| Líneas | Método | Ruta | Handler |
|---|---|---|---|
| 1389-1435 | GET | `/admin/campaigns` | `admin_list_campaigns` |
| 1437-1457 | PUT | `/admin/campaigns/{campaign_id}/approve` | `admin_approve` |
| 1459-1473 | PUT | `/admin/campaigns/{campaign_id}/reject` | `admin_reject` |
| 1807-1864 | POST | `/admin/campaigns/repair` | `admin_repair_campaigns` |
| 2481-2491 | DELETE | `/admin/campaigns/{campaign_id}/media/{media_id}` | `admin_remove_media_from_campaign` |
| 3442-3471 | GET | `/admin/campaign-scheduler/status` | `campaign_scheduler_status` |
| 3473-3480 | POST | `/admin/campaign-scheduler/run-now` | `campaign_scheduler_run_now` |
| 2226-2236 | POST | `/admin/widgets` | `create_widget` |
| 2238-2242 | GET | `/admin/widgets` | `list_widgets` |
| 2244-2251 | DELETE | `/admin/widgets/{widget_id}` | `delete_widget` |
| 2253-2262 | PUT | `/admin/widgets/{widget_id}/toggle` | `toggle_widget` |
| 1789-1803 | GET | `/admin/payments` | `admin_list_payments` |

⚠️ Las de campañas comparten helpers con las rutas `/campaigns/*` **de cliente** que siguen en
`server.py`. Hay que decidir si se threadean o si conviene mover las 6 `/campaigns/*` de cliente
en el mismo PR (mi recomendación: threadear ahora y dejar `/campaigns/*` para un PR aparte, para
no volver a tener un PR gigante).

### PR 2B-6c — `superadmin_routes.py` (17 rutas, ~230 líneas)

| Líneas | Método | Ruta | Handler |
|---|---|---|---|
| 1310-1325 | POST | `/superadmin/create-admin` | `create_admin` |
| 1327-1338 | GET | `/superadmin/admins` | `list_admins` |
| 1340-1348 | PUT | `/superadmin/admins/{admin_id}/toggle` | `toggle_admin` |
| 1350-1357 | DELETE | `/superadmin/admins/{admin_id}` | `delete_admin` |
| 1359-1373 | GET | `/superadmin/overview` | `superadmin_overview` |
| 1377-1380 | GET | `/admin/users` | `admin_list_users` |
| 1382-1387 | PUT | `/admin/users/{user_id}` | `admin_update_user` |
| 1545-1555 | GET | `/admin/rbac/info` | `rbac_info` |
| 1582-1591 | GET | `/admin/rbac/screens-by-type` | `screens_by_operation_type` |
| 1594-1752 | POST | `/admin/rbac/seed-test-users` | `seed_rbac_test_users` |
| 1557-1580 | POST | `/admin/migrate-operation-types` | `migrate_operation_types` |
| 932-941 | GET | `/admin/customer-orders` | `admin_customer_orders` |
| 943-949 | GET | `/admin/customer-orders/{oid}` | `admin_customer_order_detail` |
| 955-966 | PUT | `/admin/customer-orders/{oid}/status` | `admin_customer_order_status` |
| 3524-3528 | GET | `/admin/orders-view` | `serve_admin_orders_page` |
| 3530-3534 | GET | `/admin/clients-view` | `serve_admin_clients_page` |
| 3536-3539 | GET | `/admin/reports-view` | `serve_admin_reports_page` |

⚠️ `seed_rbac_test_users` son 159 líneas y siembra usuarios de prueba: hay tests que dependen de
esa ruta. Y las 3 `*-view` son `FileResponse` de `WEB_DIR`; por coherencia con la decisión que ya
tomamos para `/player-activate`, **podrían quedarse en `server.py`** con el resto de las rutas de
archivos estáticos. Decisión de duarte/Claude.

## Notas para el script

### Rangos actualizados tras la 2B-6a (base `b899732`)

Quedan **29 rutas** `/admin|/superadmin` en `server.py` (46 − 17 de la 2B-6a). Rangos por AST:

**2B-6b — campañas + widgets + pagos (12 rutas)**

| Líneas | Método | Ruta | Handler |
|---|---|---|---|
| 1372-1418 | GET | `/admin/campaigns` | `admin_list_campaigns` |
| 1420-1440 | PUT | `/admin/campaigns/{campaign_id}/approve` | `admin_approve` |
| 1442-1456 | PUT | `/admin/campaigns/{campaign_id}/reject` | `admin_reject` |
| 1747-1761 | GET | `/admin/payments` | `admin_list_payments` |
| 1765-1822 | POST | `/admin/campaigns/repair` | `admin_repair_campaigns` |
| 1901-1911 | POST | `/admin/widgets` | `create_widget` |
| 1913-1917 | GET | `/admin/widgets` | `list_widgets` |
| 1919-1926 | DELETE | `/admin/widgets/{widget_id}` | `delete_widget` |
| 1928-1937 | PUT | `/admin/widgets/{widget_id}/toggle` | `toggle_widget` |
| 2156-2166 | DELETE | `/admin/campaigns/{campaign_id}/media/{media_id}` | `admin_remove_media_from_campaign` |
| 3124-3153 | GET | `/admin/campaign-scheduler/status` | `campaign_scheduler_status` |
| 3155-3162 | POST | `/admin/campaign-scheduler/run-now` | `campaign_scheduler_run_now` |

**2B-6c — superadmin + RBAC + órdenes + vistas (17 rutas)**

| Líneas | Método | Ruta | Handler |
|---|---|---|---|
| 919-928 | GET | `/admin/customer-orders` | `admin_customer_orders` |
| 930-936 | GET | `/admin/customer-orders/{oid}` | `admin_customer_order_detail` |
| 942-953 | PUT | `/admin/customer-orders/{oid}/status` | `admin_customer_order_status` |
| 1293-1308 | POST | `/superadmin/create-admin` | `create_admin` |
| 1310-1321 | GET | `/superadmin/admins` | `list_admins` |
| 1323-1331 | PUT | `/superadmin/admins/{admin_id}/toggle` | `toggle_admin` |
| 1333-1340 | DELETE | `/superadmin/admins/{admin_id}` | `delete_admin` |
| 1342-1356 | GET | `/superadmin/overview` | `superadmin_overview` |
| 1360-1363 | GET | `/admin/users` | `admin_list_users` |
| 1365-1370 | PUT | `/admin/users/{user_id}` | `admin_update_user` |
| 1528-1538 | GET | `/admin/rbac/info` | `rbac_info` |
| 1540-1563 | POST | `/admin/migrate-operation-types` | `migrate_operation_types` |
| 1565-1574 | GET | `/admin/rbac/screens-by-type` | `screens_by_operation_type` |
| 1577-1735 | POST | `/admin/rbac/seed-test-users` | `seed_rbac_test_users` |
| 3206-3210 | GET | `/admin/orders-view` | `serve_admin_orders_page` |
| 3212-3216 | GET | `/admin/clients-view` | `serve_admin_clients_page` |
| 3218-3221 | GET | `/admin/reports-view` | `serve_admin_reports_page` |

### Protocolo

1. Mismo protocolo que en 2B-1…2B-6a: relocalización pura, `reindent()` **consciente de
   `tokenize`**, verificación AST byte a byte (usar `backend/verify_relocation.py`), `flake8
   F821`, `tests/test_route_inventory.py` **sin regenerar el snapshot**, y comparación del
   conjunto de IDs de fallos contra la línea base de `docs/BASELINE_PYTEST_PRE_2B5.md`.
2. El JSON con los rangos se regenera con un walk del AST; no confiar en estas tablas si el
   commit base cambia.

