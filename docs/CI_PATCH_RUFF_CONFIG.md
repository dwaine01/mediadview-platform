# Parche de CI: que ruff use `backend/ruff.toml` como única fuente de verdad

**Para: duarte.** Este es el único cambio que **no puedo pushear yo**: mi token no tiene el scope
`workflow`, y GitHub rechaza cualquier push que toque `.github/workflows/`. Son **7 líneas** y se
aplica desde la web en 2 minutos.

## Qué arregla

El mail de «Lint (ruff) failed» que te llegó. **No es nada roto y no lo introdujo el refactor.**

En ruff, un `--ignore` pasado por línea de comando **reemplaza** el `ignore` del archivo de
configuración, no se suma. `backend/ruff.toml` tiene una lista de deuda técnica heredada
(`E701`, `E702`, `E741`, `E731`, `F811`, `W293`, `W605`) que existe desde el `server.py`
monolítico original, pero los flags que tenía el workflow la anulaban por completo. Resultado:
CI reportaba código que ya estaba en `production` (`622da1ad`) desde **antes de la primera fase
del refactor** — las mismas líneas de «ambiguous variable `l`» y de `if not w: raise ...`.
Cualquier push a `main` que tocara `backend/` iba a fallar, con o sin refactor.

El otro lado del arreglo (ordenar los imports de los 3 archivos que sí eran nuestros) **ya está
en `trunk` y `main`**, commit `3442566`.

## Cómo aplicarlo

1. Andá a
   `https://github.com/dwaine01/mediadview-platform/edit/main/.github/workflows/ci.yml`
2. Buscá el paso **`Run ruff`** (alrededor de la línea 45).
3. Reemplazá esto:

```yaml
      - name: Run ruff
        run: ruff check backend --select E,F,W,I --ignore E501,E402,F401,F403,F841
```

por esto:

```yaml
      - name: Run ruff
        # Sin flags: la unica fuente de verdad es backend/ruff.toml. En ruff, un
        # --ignore por linea de comando REEMPLAZA el ignore del archivo de config
        # en vez de sumarse, asi que los flags que estaban aca anulaban la lista
        # de deuda tecnica del .toml (E701/E702/E741/E731/F811/W293/W605) y CI
        # fallaba por codigo que ya existia antes del refactor.
        run: ruff check backend
```

4. Commit directo a `main` (o por PR, como prefieras).

No hace falta tocar nada más: `backend/ruff.toml` ya declara `select = ["E", "F", "W", "I"]`, o sea
exactamente el mismo alcance que tenía el flag. Lo único que cambia es que su propia lista de
`ignore` vuelve a respetarse.

## Verificado localmente sobre el trunk actual

```
$ ruff check backend
All checks passed!
```

Cero avisos. Con el comando viejo daban 7. Y el código nuevo sigue igual de vigilado: los códigos
que **no** están en la lista de `ruff.toml` siguen rompiendo CI como antes.
