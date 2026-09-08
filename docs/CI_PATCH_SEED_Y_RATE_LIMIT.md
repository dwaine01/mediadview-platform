# Parche pendiente para `.github/workflows/ci.yml` (lo tiene que aplicar duarte)

El token de git del entorno de Maxx no tiene scope `workflow`, así que GitHub rechaza el push
de cualquier cambio dentro de `.github/workflows/`:

```
! [remote rejected] HEAD -> trunk (refusing to allow a Personal Access Token to
  create or update workflow `.github/workflows/ci.yml` without `workflow` scope)
```

Aplicar desde la web de GitHub (botón ✏️ en `.github/workflows/ci.yml`) o darle a Maxx un token
con scope `workflow`. Sin esto, el job **Backend tests** sigue rojo aunque el código esté bien.

Probado en local: los dos cambios de abajo son exactamente los que hicieron pasar de
`44 failed / 31 errors` a las suites en verde (`test_fase4_backend` 20 passed,
`test_self_service_fase2` 27 passed, `test_fase3_advertising` 12 passed).

## Cambio 1 — dos variables en el `env:` del job `test` (Backend tests)

Justo debajo de `REDIS_URL:   ""`:

```yaml
      # ── Protecciones de auth apagadas SOLO en CI ────────────────────────
      # La suite completa hace cientos de logins seguidos: con el límite de
      # 60/minuto y el bloqueo por IP tras 5 fallos, las primeras suites
      # envenenaban a todas las siguientes con 429. `RATE_LIMIT_DISABLED` solo
      # tiene efecto si ENVIRONMENT == "test" (ver rate_limit.is_rate_limit_disabled),
      # así que es imposible que apague el rate limit de staging/production.
      # Los tests de rate limit y fuerza bruta se saltan solos cuando detectan
      # que la protección está apagada.
      RATE_LIMIT_DISABLED: "1"
      LOCKOUT_WINDOW_MIN: "0"
```

## Cambio 2 — paso nuevo, justo ANTES de `- name: pytest (if any)`

Payload verificado contra el backend real: `409` si la cuenta ya existe, `201` si es nueva, y en
los dos casos el login posterior devuelve `200`.

```yaml
      # ── Seed self-service test accounts (workspace/menu suites) ──────────
      - name: Seed self-service test accounts
        run: |
          seed_account() {
            EMAIL="$1"; PASS="$2"; BIZ="$3"
            STATUS=$(curl -s -o /tmp/signup.json -w "%{http_code}" \
              -X POST http://127.0.0.1:8001/api/auth/customer-signup \
              -H "Content-Type: application/json" \
              -d "{\"plan_id\":\"starter\",\"billing_cycle\":\"monthly\",\"business_name\":\"$BIZ\",\"contact_name\":\"CI Tester\",\"contact_email\":\"$EMAIL\",\"password\":\"$PASS\"}")
            echo "signup $EMAIL → $STATUS"
            # 201 = creada. 400/409 = ya existía (el job puede re-ejecutarse).
            case "$STATUS" in
              201|400|409) ;;
              *) cat /tmp/signup.json; echo ""; exit 1 ;;
            esac
            LOGIN=$(curl -s -o /dev/null -w "%{http_code}" \
              -X POST http://127.0.0.1:8001/api/auth/login \
              -H "Content-Type: application/json" \
              -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
            echo "login  $EMAIL → $LOGIN"
            [ "$LOGIN" -eq 200 ] || exit 1
          }
          seed_account "testws@test.com"     "Test1234!"  "Test Business"
          seed_account "pizzeria@demo.com"   "Pizza1234!" "Pizzeria Don Luis"
```

## Comprobación local del payload (salida real)

```
signup testws@test.com → 409
login  testws@test.com → 200
signup pizzeria@demo.com → 409
login  pizzeria@demo.com → 200
signup ci-fresh-587@test.com → 201
login  ci-fresh-587@test.com → 200
exit=0
```
