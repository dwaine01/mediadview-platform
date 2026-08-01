# MediAd View — Backlog Sprint 2 (post cierre Sprint 1)

## Items registrados por el stakeholder al aprobar la Etapa B (Sprint 1)

### 🔒 S2-01 · Validación de contenido por magic numbers
**Contexto**: Actualmente `POST /api/checkout/media` valida el `content_type`
del header y el tamaño, pero un atacante podría subir un binario con
extensión `.png` y `content_type: image/png` que en realidad contiene
código ejecutable u otro formato.

**Objetivo**: Rechazar archivos cuyo primer *magic-number* no coincida
con el `content_type` declarado.

**Plan sugerido**:
- Nueva utilidad `media_signatures.py` con la tabla:
  ```
  image/jpeg   → FF D8 FF
  image/png    → 89 50 4E 47 0D 0A 1A 0A
  image/webp   → RIFF … WEBP
  image/gif    → 47 49 46 38 (37|39) 61
  video/mp4    → …ftyp (offset 4)
  video/webm   → 1A 45 DF A3
  video/quicktime → …ftypqt (offset 4)
  ```
- Verificar `payload[:16]` en `stripe_routes.checkout_media` **antes** de
  aceptar el archivo.
- Si no coincide → HTTP 400 `"file signature does not match declared type"`.

**Riesgo mitigado**: MIME spoofing, upload de ejecutables enmascarados,
polyglots básicos.

**Esfuerzo estimado**: 1 hora.

---

### 🦠 S2-02 · Escaneo antivirus con estado `under_analysis`
**Contexto**: Sprint 1 marca el media como `status = "ready"` inmediatamente
tras subirlo. Antes de exponerlo en pantallas físicas queremos escanear
el binario.

**Objetivo**: Introducir un estado intermedio `under_analysis` y una
integración pluggable de escaneo (ClamAV, VirusTotal, S3 Malware Scanning,
etc.).

**Plan sugerido**:
1. En `POST /api/checkout/media`: crear el documento con `status="under_analysis"` en vez de `"ready"`.
2. Encolar un job ARQ `scan_media(media_id)` que:
   - Descarga el binario (R2 o disco local).
   - Ejecuta el escaneo (backend configurable: `MEDIA_SCANNER=clamav|virustotal|noop`).
   - Actualiza `status="ready"` o `status="infected"` según resultado.
   - Registra en `financial_audit`.
3. En `checkout_service._validate_media_for_order`:
   - Rechazar si `status="under_analysis"` con mensaje "Please wait — your file is being scanned".
   - Rechazar si `status="infected"` con mensaje "Uploaded file failed the safety scan".
4. Frontend `screen-public.html`: polling ligero (`GET /api/checkout/media/{id}/status`) hasta ver `ready` antes de habilitar el botón de pago.
5. Documentación: `docs/MEDIA_SCANNING.md` describiendo cómo cambiar el proveedor.

**Riesgo mitigado**: Distribución involuntaria de malware desde nuestra
plataforma; cumplimiento con políticas de app-store si en el futuro
distribuimos apps para reproductores.

**Esfuerzo estimado**: 1–2 días (depende del proveedor elegido).

---

### Otros items para Sprint 2 (ya acordados en el blueprint original)

- **S2-03** · Stripe Setup Intents + payment methods guardados (portal cliente).
- **S2-04** · Stripe Subscriptions / Billing recurrente (contratos B2B).
- **S2-05** · Stripe Tax (multi-estado USA).
- **S2-06** · Reconciliación diaria ARQ (Stripe list vs Mongo orders).
- **S2-07** · Purga real de la colección `payments_legacy`.
- **S2-08** · ACH para clientes corporativos.
- **S2-09** · Multi-moneda (arquitectura ya preparada).
- **S2-10** · Rate limit per-IP más agresivo en endpoints públicos NO críticos (nunca en el webhook).
