# Línea base de pytest ANTES de la Fase 2B-5

Medida en el entorno del fork nuevo (no comparable en números absolutos con la de 2B-4, que se
midió en otra máquina con otra base de datos sembrada). Lo que importa es que el **conjunto de
IDs que fallan sea idéntico** antes y después de la extracción.

- Commit: `de45af4` (`trunk-local`, = `trunk`/`main`)
- `backend/server.py`: 4761 líneas, 113 rutas declaradas con `@api_router.*`
- Comando: `cd /app/backend && TEST_BASE_URL=http://localhost:8001 python -m pytest tests/ -q`
- Resultado: **465 passed, 22 failed, 35 skipped, 20 errors** en 161 s

## IDs que fallan en la base (fallos preexistentes de entorno, NO regresiones)

Casi todos son datos de prueba no sembrados en este fork (`/api/plans` devuelve el catálogo
real pero los tests esperan 4 planes concretos, `testws@test.com` sin organización creada, etc.).

```
ERROR tests/test_p1_saas_customer.py::TestWorkspaceBilling::test_billing_has_pricing_agreement
ERROR tests/test_p1_saas_customer.py::TestWorkspaceBilling::test_billing_has_subscription
ERROR tests/test_p1_saas_customer.py::TestWorkspaceBilling::test_billing_returns_200
ERROR tests/test_p1_saas_customer.py::TestWorkspaceContext::test_context_has_organization
ERROR tests/test_p1_saas_customer.py::TestWorkspaceContext::test_context_has_plan_config
ERROR tests/test_p1_saas_customer.py::TestWorkspaceContext::test_context_has_stats
ERROR tests/test_p1_saas_customer.py::TestWorkspaceContext::test_context_has_subscription
ERROR tests/test_p1_saas_customer.py::TestWorkspaceContext::test_context_no_cross_tenant_leak
ERROR tests/test_p1_saas_customer.py::TestWorkspaceContext::test_context_returns_200_for_ws_user
ERROR tests/test_phase2c_p1.py::TestWorkspaceContext::test_context_has_organization_name
ERROR tests/test_phase2c_p1.py::TestWorkspaceContext::test_context_has_required_fields
ERROR tests/test_phase2c_p1.py::TestWorkspaceContext::test_context_returns_200_for_ws_user
ERROR tests/test_phase2c_p1.py::TestWorkspaceContext::test_context_stats_has_screens_users_devices
ERROR tests/test_phase2c_p1.py::TestWorkspaceSubRoutes::test_billing
ERROR tests/test_phase2c_p1.py::TestWorkspaceSubRoutes::test_billing_has_plan_config
ERROR tests/test_phase2c_p1.py::TestWorkspaceSubRoutes::test_menus_list
ERROR tests/test_phase2c_p1.py::TestWorkspaceSubRoutes::test_menus_list_is_array
ERROR tests/test_phase2c_p1.py::TestWorkspaceSubRoutes::test_screens_list
ERROR tests/test_phase2c_p1.py::TestWorkspaceSubRoutes::test_screens_list_is_array
ERROR tests/test_playlist_diskless_iter34.py::test_playlist_survives_a_wiped_disk
FAILED tests/test_i18n_and_ceo_portrait.py::TestHtmlIncludesI18n::test_landing_has_data_i18n_attrs
FAILED tests/test_p0_player_diagnostics_playlist_contract.py::test_playlist_display_mode_is_normalized_and_delivered_as_cover
FAILED tests/test_p1_saas_customer.py::TestCustomerSignup::test_signup_creates_full_stack
FAILED tests/test_p1_saas_customer.py::TestCustomerSignup::test_signup_duplicate_email_returns_409
FAILED tests/test_p1_saas_customer.py::TestCustomerSignup::test_signup_invalid_plan_returns_400
FAILED tests/test_p1_saas_customer.py::TestCustomerSignup::test_signup_short_password_returns_422
FAILED tests/test_p1_saas_customer.py::TestPlansAPI::test_plans_canonical_ids
FAILED tests/test_p1_saas_customer.py::TestPlansAPI::test_plans_have_required_fields
FAILED tests/test_p1_saas_customer.py::TestPlansAPI::test_plans_returns_200
FAILED tests/test_p1_saas_customer.py::TestPlansAPI::test_plans_returns_4_plans
FAILED tests/test_p1_saas_customer.py::TestPlansAPI::test_plans_sorted_by_display_order
FAILED tests/test_p1_saas_customer.py::TestWorkspaceContext::test_context_requires_auth
FAILED tests/test_p1_saas_customer.py::TestWorkspaceNewSignup::test_new_user_login_and_context
FAILED tests/test_phase2c_p1.py::TestPlansPublic::test_get_plans_returns_200
FAILED tests/test_phase2c_p1.py::TestPlansPublic::test_get_plans_returns_4_plans
FAILED tests/test_phase2c_p1.py::TestPlansPublic::test_plan_ids_include_expected
FAILED tests/test_phase2c_p1.py::TestPlansPublic::test_plans_response_time
FAILED tests/test_phase2c_p1.py::TestWorkspaceContext::test_context_requires_auth
FAILED tests/test_player_backend_contracts_2026.py::test_device_playlist_returns_controlled_empty_state_when_unpaired
FAILED tests/test_playlist_professional_platform.py::test_menu_theme_colors_persist_and_render
FAILED tests/test_playlist_professional_platform.py::test_owned_playlist_timeline_edit_publish_and_player_contract
FAILED tests/test_rbac_fase1.py::TestD_SelfServiceOwnerCreaPropiaOrg::test_ssowner_orga_crea_pantalla_propia
```

`tests/test_route_inventory.py` pasa en verde contra `route_inventory_snapshot.json`
(492 rutas congeladas). Ese es el test que NO se debe regenerar.

## Rutas objetivo de la 2B-5 (localizadas en `de45af4`)

| Línea | Ruta |
|---|---|
| 1607 | `POST /devices/pair` |
| 2011 | `GET /player/{screen_id}/playlist` |
| 2032 | `GET /player/{screen_id}/version` |
| 2052 | `GET /player/{screen_id}/diagnose` |
| 2155 | `GET /player/{screen_id}/schedule` |
| 2182 | `GET /player/media/{media_id}` |
| 2214 | `GET /player/{screen_id}/web` (HTMLResponse) |
| 2311 | `GET /player/{screen_id}/export` |
| 2370 | `GET /player/{screen_id}/status` |
| 2395 | `POST /devices/register` |
| 2474 | `GET /devices/{device_id}/check` |
| 2541 | `POST /devices/{device_id}/heartbeat` |
| 2661 | `GET /devices/{device_id}/update-check` |
| 2720 | `POST /devices/{device_id}/log` |
| 2823 | `GET /devices/{device_id}/playlist` |
| 3952 | `GET /player/{screen_id}/test` (HTMLResponse) |

`GET /player-activate` (línea 4407) **NO** entra: es un `FileResponse` de un HTML estático de
`WEB_DIR`, pertenece al grupo de rutas de archivos estáticos/SPA junto a `/public/playlist`,
`/download`, `/screen` y `/marketplace`. Decisión de duarte, 2026-06.

## Condición de cierre acordada con duarte

El plan marca la 2B-5 como **riesgo rojo**: aunque el script pase AST 1:1 + F821 + suite igual a
esta línea base, **no se fusiona a `trunk` hasta que duarte lo pruebe en una TV box real**. Los
tests automatizados no bastan para dar el visto bueno en esta fase.
