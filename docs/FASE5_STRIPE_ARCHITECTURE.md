# MediAd View — Fase 5: Blueprint arquitectónico de Stripe

**Estado:** propuesta · pendiente de aprobación del stakeholder · sin código todavía.

---

## 1. Arquitectura global

```
                              ┌──────────────────────────┐
                              │        Stripe API        │
                              │  (Payments · Billing ·   │
                              │   Tax · Radar · Refunds) │
                              └────┬───────────┬─────────┘
                                   │           │  webhooks (POST)
              ┌────────────────────┘           ▼
              │                        ┌──────────────────┐
              │                        │  /api/webhooks/  │
              │  create Intent /       │  stripe          │
              │  Subscription /        │  (signature + jti│
              │  Customer /            │   dedup + queue) │
              │  Refund                └───────┬──────────┘
              │                                │  ARQ enqueue
    ┌─────────▼──────────────────────┐         ▼
    │  FastAPI (web-api)             │  ┌──────────────────┐
    │  /api/orders/*                 │◄─┤  ARQ worker       │
    │  /api/checkout/*               │  │  process_webhook  │
    │  /api/customers/*              │  │  charge_recurring │
    │  /api/subscriptions/*          │  │  send_receipt     │
    │  /api/refunds/*                │  └────────┬─────────┘
    └──────────┬─────────────────────┘           │
               │                                 │
       ┌───────▼───────┐    ┌────────────────────▼──────┐
       │  MongoDB      │    │  Redis                    │
       │  (source of   │    │  · idempotency store      │
       │   truth for   │    │  · slot reservations (TTL)│
       │   orders,     │    │  · webhook dedup          │
       │   contracts)  │    │  · rate-limit             │
       └───────────────┘    └───────────────────────────┘
```

**Fuente de verdad:**
| Entidad | Fuente autoritativa | Espejo en Stripe |
|---|---|---|
| Cliente (perfil, contactos, direcciones) | **MediAd View DB** | `stripe.Customer` (metadata + id) |
| Método de pago | **Stripe** | `payment_methods[]` en DB solo por referencia |
| Orden de publicidad | **MediAd View DB** | ninguno (PaymentIntent es artefacto de cobro, no la orden) |
| Contrato mensual | **MediAd View DB** | `stripe.Subscription` |
| Factura interna | **MediAd View DB** | `stripe.Invoice` (solo para Billing recurrente) |
| Pago | **Stripe (autoridad final)** | `db.payments` refleja lo que dice el webhook |
| Estado de cuenta | **MediAd View DB** | computado |

**Regla dura:** una orden solo se marca `paid` cuando llega el webhook `payment_intent.succeeded`. **El frontend nunca puede mover ese estado.**

---

## 2. Flujo QR → Pago → Reproducción (diagrama)

```
Cliente escanea QR                            Backend                       Stripe
──────────────────                            ───────                       ──────
1. GET /api/s/{code}      ──►
                                             lookup screen + stock
   <── HTML público con specs, precio, availability

2. POST /api/checkout/quote {screen_id, dates, times}
                                             calcula server-side precio
                                             crea slot reservation en Redis (TTL 10min)
   <── {quote_id, price_breakdown, total_cents, currency, expires_at}

3. POST /api/media/presign (Fase 4)
   <── {presigned url}
   PUT to R2 direct
   POST /api/media/finalize
   <── {media_id, status:"ready"}

4. POST /api/checkout/create-intent {quote_id, media_id, email}
                                             re-valida quote (no cambió precio)
                                             re-valida slot reservation
                                             crea/reutiliza stripe.Customer
                                             draft Order (status=draft)
                                             crea PaymentIntent con:
                                               - amount = quote.total_cents (server-side)
                                               - idempotency_key = order_id
                                               - metadata = {order_id, screen_id}
                                               - automatic_payment_methods
   <── {client_secret, order_id}                                   ──►  stripe.PaymentIntent
                                                                        (amount_capturable_updated)

5. Frontend: stripe.confirmPayment(client_secret) con Payment Element
                                                                   ──►  3D Secure si aplica
                                                                        payment_intent.succeeded
6.                                                                  ◄── webhook
                                             verifica firma
                                             dedup por event.id
                                             mueve Order: paid → pending_review
                                             confirma slot en DB (remueve reserva Redis)
                                             emite recibo
                                             notifica admin

7. Admin revisa la creatividad → aprueba
                                             Order: pending_review → approved → scheduled
                                             enqueue ARQ sync_screen_job

8. Reproductor descarga y muestra
                                             cada play → play_logs
9. Fin de campaña
                                             Order: playing → completed
                                             genera PDF factura
                                             envía email a cliente
```

---

## 3. Anti-patrones bloqueados

| Riesgo | Defensa |
|---|---|
| Manipulación de precio desde el navegador | El monto del PaymentIntent lo calcula **exclusivamente** el backend a partir del `quote_id`. El frontend nunca envía monto. |
| Doble reserva del mismo espacio | Redis `slot:{screen_id}:{yyyy-mm-dd}:{hh}` con SETNX + TTL 10 min. Al aprobar el pago, se persiste en `db.reservations` con índice único `{screen_id, day, hour}`. |
| Pago sin disponibilidad | Antes de crear el PaymentIntent se **re-verifica** el slot; si expiró/se ocupó, se devuelve el dinero automáticamente (`stripe.PaymentIntent.cancel`). |
| Pago aprobado sin webhook | La orden queda en `payment_processing` hasta que llegue el webhook. **Nunca** se marca `paid` desde el frontend. |
| Publicación de contenido no aprobado | Estado obligatorio `pending_review` → `approved` antes de que el reproductor lea la playlist. La API del player filtra `status IN ('scheduled','playing')`. |
| Doble webhook | `db.stripe_events` con índice único en `event.id` → segundo insert falla, se ignora. |
| Webhook fuera de orden | Cada evento trae `created` timestamp; comparamos con `orders.stripe_state_updated_at`; solo aplicamos si el evento es más reciente **o** si el estado destino es válido según la state machine. |

---

## 4. Rediseño de `screen-public.html`

### **Opción A — Guest checkout (DEFAULT recomendado)**

Razones:
- QR se escanea por *walk-ins*, mayormente compra única y baja fricción gana.
- Elimina el anti-pattern `password = 'cl_' + email`.
- Menos superficie de seguridad (no hay password que gestionar).

Flujo:
1. Cliente escanea QR → llega a checkout público.
2. Ingresa: email + nombre + teléfono.
3. Configura pauta + sube media + paga.
4. Recibe email con **magic-link** `https://mediadview.com/o/{order_token}` (JWT firmado, 30 días de vigencia).
5. El link permite ver una sola orden. Sin listado, sin panel completo.

**Token de orden:**
- JWT firmado con `JWT_SECRET` distinto (`ORDER_LINK_SECRET`) para separar dominios.
- Claims: `{order_id, purpose:"order_view", exp:+30d, jti}`.
- Guardado en `db.order_tokens` con `revoked=false`; consultamos DB además del JWT → permite revocar.
- Endpoint `/api/orders/{token}` valida firma **y** DB (no revocado, no expirado).

### **Opción B — Cuenta opcional**

- Al final del checkout guest: "¿Quieres administrar campañas futuras? Crear cuenta".
- Usa el mismo email; si ya existe orden guest con ese email, se **linkea automáticamente** (`orders.customer_id = user.id`).
- Contraseña elegida por el usuario **o** magic-link vía email.
- Nunca password autogenerado.

### **Guest → Account promotion**
Cuando un usuario invitado decide crear cuenta:
1. Verificamos email por magic-link.
2. Buscamos `db.orders WHERE guest_email=email AND customer_id IS NULL`.
3. Fusionamos: `customer_id = new_user.id`, `stripe.Customer.metadata.user_id = new_user.id`.
4. Cero duplicación de cliente en Stripe (reutilizamos `stripe_customer_id`).

---

## 5. Máquina de estados de órdenes

```
                       ┌──► rejected ──► [terminal]
draft ─► awaiting_payment ─► payment_processing ─► paid ─► pending_review ─► changes_requested (loop)
   │           │                    │                            │
   │           └──► cancelled       └── payment_failed            └──► approved ─► scheduled ─► playing ─► completed
   │                                                                                                        │
   └──► [expired after 30min → cancelled]                                                                   ▼
                                                                                                     refund_pending
                                                                                                        │
                                                                                    ┌───────────────────┼──────────────┐
                                                                                    ▼                   ▼              ▼
                                                                                refunded          disputed        [chargeback flow]
```

**Reglas de transición:**
- Solo el webhook Stripe mueve `payment_processing` → `paid | payment_failed | cancelled`.
- Solo `role in (admin, superadmin)` mueve `pending_review` → `approved | rejected | changes_requested`.
- Ningún cliente puede mover a `scheduled` o `playing`.
- Un chargeback en `playing` → suspende inmediatamente el player + notifica admin.
- Un refund tras `approved` → cancela la campaña + libera slots.

---

## 6. Modelo de datos

### Colecciones nuevas

**`orders`** (fuente de verdad de la orden)
```
{
  id, order_number,        # #INV-2026-000123 consecutivo atómico
  customer_id, guest_email, guest_phone,
  screen_ids[], schedule{start_date, end_date, days[], times[]},
  media_id, duration_seconds, frequency,
  price_breakdown{ base, tax, discount, extras, total_cents, currency },
  status, status_history[],   # array de {from, to, at, by, reason}
  stripe_customer_id, stripe_payment_intent_id, stripe_charge_id,
  order_token_id,             # link a db.order_tokens
  created_at, paid_at, approved_at, completed_at
}
```

**`stripe_events`** (webhook dedup)
```
{ event_id UNIQUE, type, received_at, processed_at, result, error, retry_count }
```

**`payment_methods`** (referencias, nunca PAN)
```
{ customer_id, stripe_payment_method_id, brand, last4, exp_month, exp_year, is_default, added_at }
```

**`subscriptions`**
```
{ id, customer_id, contract_id, stripe_subscription_id, status,
  price_id, quantity, trial_end, current_period_end,
  cancel_at, canceled_at, screen_ids[] }
```

**`refunds`**
```
{ id, order_id, invoice_id, stripe_refund_id,
  amount_cents, reason, authorized_by, authorized_at, status }
```

**`slot_reservations`** (short-lived, en Redis + snapshot final en Mongo)
```
{ screen_id, day, hour, quote_id, order_id, expires_at, confirmed:bool }
UNIQUE INDEX { screen_id, day, hour }  # previene doble reserva
```

**`financial_audit`** (append-only, sin update ni delete)
```
{ ts, user_id, role, ip, request_id, idempotency_key,
  action, entity_type, entity_id,
  stripe_event_id, stripe_customer_id, payment_intent_id, invoice_id, subscription_id, refund_id,
  amount_cents, currency, state_before, state_after, reason, metadata }
```
Índice: `{ts:-1}`, `{entity_id}`, `{stripe_event_id}`. Se crea un usuario Mongo separado sin `update/delete` permission para escribir ahí.

### Colecciones modificadas

- **`fin_clients`** → +`stripe_customer_id`, +`default_payment_method_id`, +`credit_balance_cents`
- **`fin_invoices`** → +`stripe_invoice_id`, +`external_source:"stripe"|"internal"`
- **`fin_contracts`** → +`subscription_id`, +`billing_mode:"one-time"|"recurring"`
- **`payments`** MOCK → renombrar a `payments_legacy`, crear `payments` nuevo alimentado solo por webhook

---

## 7. Webhooks — arquitectura

**Endpoint:** `POST /api/webhooks/stripe`
1. Lee raw body **antes** de parsear (Stripe firma bytes exactos).
2. `stripe.Webhook.construct_event(body, sig_header, WEBHOOK_SECRET)` → verifica firma.
3. INSERT en `stripe_events` con `event_id UNIQUE`; si duplicado → 200 OK sin procesar.
4. Enqueue en ARQ `process_stripe_event_job(event_id)` → responde 200 rápido.
5. Worker procesa idempotente (siempre relee la orden por `payment_intent.id`).

**Eventos manejados** (16 tipos):
- `payment_intent.{succeeded, payment_failed, canceled}`
- `checkout.session.completed` (fallback si algún flujo usa Checkout hosted)
- `setup_intent.succeeded`
- `invoice.{created, finalized, paid, payment_failed}`
- `customer.subscription.{created, updated, deleted}`
- `charge.refunded`
- `charge.dispute.{created, closed}`

**Retries:** Stripe reintenta hasta 3 días con backoff exponencial. Nuestra idempotencia lo tolera.

---

## 8. Idempotencia (matriz)

| Operación | Idempotency key | Store |
|---|---|---|
| Crear PaymentIntent | `order:{order_id}` | Header a Stripe |
| Crear Refund | `refund:{refund_request_id}` | Header a Stripe |
| Crear Customer | `customer:{user_id}` | Header a Stripe |
| Procesar webhook | `event.id` | `stripe_events.event_id UNIQUE` |
| ARQ job | `stripe_evt:{event.id}` | Redis SETNX (Fase 3 ya lo tiene) |
| Reservar slot | `slot:{screen_id}:{day}:{hour}` | Redis SETNX TTL |
| Emitir factura interna | `invoice:{order_id}` | `fin_invoices.order_id UNIQUE` |

---

## 9. Impuestos — recomendación

**Recomiendo Stripe Tax** por:
- Cálculo automático por estado (USA multi-state complejo).
- Registro de impuestos con jurisdicciones.
- Reporte anual listo para el contador.
- ~0.5% del volumen procesado (costo bajo vs errores de compliance).

**Alternativa:** cálculo propio en backend con `tax_rate` por estado en `db.tax_rates`. Más control, pero implica mantener nexus + registros manuales.

**Decisión pendiente contigo** antes de implementar.

---

## 10. Test vs Live — safety switch

En `startup_check.py` añadiré:
- `STRIPE_SECRET_KEY` empieza con `sk_test_` **o** `sk_live_`
- `STRIPE_PUBLISHABLE_KEY` debe coincidir en modo (`pk_test_` con `sk_test_`, `pk_live_` con `sk_live_`)
- Si `ENVIRONMENT=production` y detectamos `sk_test_` → **abort startup**
- Si `STRIPE_WEBHOOK_SECRET` vacío → **abort startup**
- Log al arrancar: `"Stripe mode: TEST"` o `"Stripe mode: LIVE"` (nunca las keys)

---

## 11. Migración desde MOCK

**No borro nada sin tu aprobación.** Plan:

1. Renombrar `db.payments` → `db.payments_legacy` (reversible, cero pérdida de datos).
2. Etiquetar cada doc con `{is_mock: true, original_id: pi_mock_xxx}`.
3. Reporte previo: `python scripts/mock_payments_report.py` → JSON con conteos, montos totales, campañas asociadas.
4. **Solo cuando lo autorices** ejecuto `--purge-mock` que borra los legacy y sus referencias.

---

## 12. Riesgos y costos

| Riesgo | Sev | Mitigación |
|---|---|---|
| Webhook secret filtrado | 🔴 | Solo en Render Env Group (encriptado), rotable |
| Sincronía Stripe ↔ DB rota | 🔴 | Reconciliación diaria en ARQ: `stripe.PaymentIntent.list(created={gte:24h})` vs `db.orders` |
| PCI compliance | 🔴 | Payment Element carga en iframe de Stripe; nunca tocamos PAN → SAQ-A (mínimo) |
| Dispute masivo por creatividad rechazada | 🟡 | T&C explícitos + evidence upload en dashboard admin |
| Cambio de precio mid-checkout | 🟡 | Quote con expiración 10 min; re-cotización obligatoria antes de pagar |

**Costos Stripe:**
- Cards: 2.9% + $0.30 USD por transacción exitosa
- Stripe Billing: +0.5% del volumen recurrente (Starter plan)
- Stripe Tax: +0.5% del volumen
- Refunds: gratis, pero no reembolsa la comisión original
- **Estimado inicial:** ~4% del GMV

---

## 13. Cosas que necesito de ti (antes de codear)

1. **Cuenta Stripe** creada con nombre legal MediAd View LLC → me pasas las **test keys** (`sk_test_...`, `pk_test_...`, `whsec_...`) para desarrollo.
2. **Decisión sobre impuestos:** ¿Stripe Tax (recomendado) o propio?
3. **Decisión sobre modelo default de screen-public:** guest checkout (recomendado) confirmado.
4. **Política de reembolsos:** ¿reembolso completo antes de aprobar? ¿parcial durante `playing`? ¿nunca tras `completed`?
5. **Numeración de facturas:** ¿reiniciar por año (`INV-2026-000001`) o continuo global?
6. **Tarjetas aceptadas:** ¿solo Cards o también ACH/US bank transfer para B2B corporativos?
7. **Monedas:** ¿solo USD por ahora?

---

## 14. Orden de implementación por etapas

1. **Etapa A** — Configuración base (keys, webhook endpoint, safety switch en startup, models de datos, financial_audit collection). Sin cobrar todavía.
2. **Etapa B** — Guest checkout QR con PaymentIntent + Payment Element + webhook + state machine básica. Modo test.
3. **Etapa C** — Aprobación admin + emisión de facturas internas + refunds manuales.
4. **Etapa D** — Corporate: Setup Intents, saved payment methods, portal del cliente.
5. **Etapa E** — Subscriptions/Billing para contratos mensuales.
6. **Etapa F** — Stripe Tax (si apruebas).
7. **Etapa G** — Reconciliación diaria + reportes financieros.
8. **Etapa H** — Reemplazo definitivo del MOCK y migración.
9. **Etapa I** — Endurecimiento: Radar rules, disputes automation, alertas.

Cada etapa termina con testing_agent + tu aprobación explícita antes de la siguiente.

---

**Estado:** este blueprint espera tu revisión. **No he escrito código de Stripe.** Cuando lo apruebes (o me pidas ajustes), procedo con Etapa A en Stripe test.
