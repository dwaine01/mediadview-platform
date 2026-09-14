# Plantillas de WhatsApp de MediaView (para pegar en WhatsApp Manager)

Las cuatro plantillas son las que usa `backend/whatsapp.py` (`TEMPLATES`). El
**nombre**, el **idioma** y el **orden de las variables** tienen que coincidir
exacto con lo aprobado en Meta: el código manda los datos en ese orden y no los
busca por nombre.

| Plantilla (nombre exacto) | Encabezado | {{1}} | {{2}} | {{3}} | {{4}} |
|---|---|---|---|---|---|
| `mediaview_invoice_created` | DOCUMENTO (PDF de la factura) | contacto | nº factura | monto | vencimiento |
| `mediaview_invoice_due` | ninguno | contacto | nº factura | monto | vencimiento |
| `mediaview_invoice_overdue` | ninguno | contacto | nº factura | monto | vencimiento |
| `mediaview_payment_received` | ninguno | contacto | nº factura | monto pagado | saldo restante |

Categoría de las cuatro: **Utilidad** (Utility). Idiomas: **Español** y,
opcional, **Inglés (EE. UU.)** — el idioma que se manda sale del campo
`language` del cliente (`es` → `es`, `en` → `en_US`).

Sin botones: el código no manda parámetros de botón. Si más adelante se quiere
un botón "Ver factura", hay que agregarlo también en `send_template`.

---

## 1) mediaview_invoice_created

- Categoría: **Utilidad** · Idioma: **Español**
- Encabezado: **Documento** (subir un PDF de muestra; en producción viaja la
  factura real)
- Cuerpo:

```
Hola {{1}}, tu factura {{2}} de MediaView ya está disponible por {{3}}, con vencimiento el {{4}}. Te la adjuntamos en PDF. Cualquier duda, respondé este mensaje.
```

- Pie de página: `MediaView · Publicidad digital`
- Muestras: {{1}} `Josue` · {{2}} `INV-2026-0142` · {{3}} `$450.00` · {{4}} `2026-07-05`

Inglés (EE. UU.):

```
Hi {{1}}, your MediaView invoice {{2}} for {{3}} is ready, due on {{4}}. The PDF is attached. Reply here if you have any questions.
```

## 2) mediaview_invoice_due

- Categoría: **Utilidad** · Sin encabezado
- Cuerpo:

```
Hola {{1}}, te recordamos que la factura {{2}} por {{3}} vence el {{4}}. Si ya la pagaste, avisanos respondiendo este mensaje.
```

- Pie de página: `MediaView · Publicidad digital`
- Muestras: `Josue` · `INV-2026-0142` · `$450.00` · `2026-07-05`

Inglés:

```
Hi {{1}}, a reminder that invoice {{2}} for {{3}} is due on {{4}}. If you already paid, just reply to this message.
```

## 3) mediaview_invoice_overdue

- Categoría: **Utilidad** · Sin encabezado
- Cuerpo:

```
Hola {{1}}, la factura {{2}} por {{3}} está vencida desde el {{4}}. Escribinos por acá para coordinar el pago y mantener tu servicio activo.
```

- Pie de página: `MediaView · Publicidad digital`
- Muestras: `Josue` · `INV-2026-0142` · `$450.00` · `2026-06-05`

Inglés:

```
Hi {{1}}, invoice {{2}} for {{3}} has been overdue since {{4}}. Reply here so we can arrange payment and keep your service active.
```

## 4) mediaview_payment_received

- Categoría: **Utilidad** · Sin encabezado
- Cuerpo (ojo: {{3}} es lo pagado y {{4}} el saldo que queda):

```
Hola {{1}}, recibimos tu pago de {{3}} para la factura {{2}}. Saldo pendiente: {{4}}. ¡Gracias por confiar en MediaView!
```

- Pie de página: `MediaView · Publicidad digital`
- Muestras: `Josue` · `INV-2026-0142` · `$450.00` · `$0.00`

Inglés:

```
Hi {{1}}, we received your payment of {{3}} for invoice {{2}}. Remaining balance: {{4}}. Thank you for choosing MediaView!
```

---

## Reglas que hacen que Meta rechace

- Tono publicitario en categoría Utilidad (promos, descuentos, "aprovechá").
- Variable al principio o al final del cuerpo, o dos variables pegadas.
- Muestras vacías o que no tengan el formato del dato real.
- Cambiar el nombre: si se aprueba con otro nombre, hay que actualizar
  `TEMPLATES` en `backend/whatsapp.py`.

Aprobación habitual: 5 minutos a 1 hora.
