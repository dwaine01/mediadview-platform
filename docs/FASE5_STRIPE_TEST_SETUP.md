# MediAd View — Sprint 1 · Etapa B · Guía de configuración de Stripe Test

Este documento explica exactamente qué variables debes inyectar en el
entorno seguro del pod para activar el flujo real de pagos.

## 🔒 Modelo de seguridad

- Las **variables sensibles** (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
  `ORDER_LINK_SECRET`) **NUNCA** deben aparecer en:
  - código fuente
  - `.env` versionado en Git
  - logs (redacción automática por `observability.py`)
  - respuestas HTTP de ningún endpoint
  - reportes de testing
  - GitHub Actions logs
- La **`STRIPE_PUBLISHABLE_KEY`** SÍ es pública. Se expone únicamente
  por `GET /api/checkout/config`.
- El `.env` está en `.gitignore` (verificado con `git check-ignore`).
- La redacción cubre: `sk_test_*`, `sk_live_*`, `pk_test_*`, `pk_live_*`,
  `whsec_*`, `pi_*_secret_*`, JWTs completos, tarjetas de crédito, emails,
  y headers sensibles (`Authorization`, `Cookie`, `Stripe-Signature`).

## 📥 Variables que debes inyectar

Copia y pega en el entorno seguro del pod (o en Render Env Group):

```bash
# ── Modo TEST estricto para todo Sprint 1 ──
STRIPE_SECRET_KEY=sk_test_51...     # de Stripe Dashboard → Developers → API keys
STRIPE_PUBLISHABLE_KEY=pk_test_51...
STRIPE_WEBHOOK_SECRET=whsec_...     # de `stripe listen` (local) o Dashboard → Webhooks (prod)

# Dev-only: desactiva el escape hatch tan pronto llenes STRIPE_WEBHOOK_SECRET
STRIPE_WEBHOOK_SECRET_ALLOW_EMPTY=false
```

**El safety switch en `stripe_config.py` hará:**
- Abort si `STRIPE_SECRET_KEY` no empieza con `sk_test_` en dev.
- Abort si `STRIPE_SECRET_KEY` empieza con `sk_test_` en producción.
- Abort si `pk_*` no coincide en modo con `sk_*`.
- Abort si `STRIPE_WEBHOOK_SECRET` no empieza con `whsec_`.

## 🧪 Cómo obtener el webhook secret local

```bash
# Instalar Stripe CLI: https://docs.stripe.com/stripe-cli
stripe login

# En una terminal separada del backend:
stripe listen --forward-to http://localhost:8001/api/webhooks/stripe
# → imprime: "Your webhook signing secret is whsec_..."
```

Copia ese `whsec_...` a la variable `STRIPE_WEBHOOK_SECRET` del pod.
En producción usarás un webhook DISTINTO creado en el Dashboard apuntando
a `https://api.mediadview.com/api/webhooks/stripe`.

## ✅ Después de inyectar las keys

1. Reinicia el backend:
   ```
   sudo supervisorctl restart backend
   ```
2. Verifica:
   ```
   curl -s http://localhost:8001/api/checkout/config
   # → {"enabled":true,"mode":"test","publishable_key":"pk_test_...","currency":"usd","payment_methods":["card"]}
   ```
3. En el navegador ve a `/api/screen`, selecciona la pantalla, configura
   duración, sube una imagen, completa datos, y paga con:
   - **Tarjeta: `4242 4242 4242 4242`**
   - Fecha: cualquier futura (`12/34`)
   - CVC: `123`
   - ZIP: `12345`

4. Con `stripe listen` corriendo verás el evento `payment_intent.succeeded`
   llegar al backend, y la orden pasar a `paid → pending_review`.

## 🧨 Tarjetas de prueba para forzar fallas

Consulta: https://docs.stripe.com/testing#cards

- `4000 0000 0000 9995` → **decline** (`payment_failed`)
- `4000 0000 0000 3220` → **3D Secure** requerido
- `4000 0000 0000 0341` → **decline (fraudulento)**

## 📋 Estado actual

- Con las variables VACÍAS (estado por defecto en el `.env` versionado):
  - Backend arranca normal.
  - `/api/checkout/config` → `{"enabled":false, "mode":"disabled"}`.
  - `POST /api/checkout/create-intent` → HTTP 503.
  - `POST /api/webhooks/stripe` → HTTP 503.
  - El resto de la app funciona sin ninguna regresión.
