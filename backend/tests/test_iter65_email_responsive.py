"""Iter 65 — Verificación independiente del fix responsive de las 3 plantillas.

El dueño abrió la factura en Titán desde el celular y se veía «gigante» porque
la tarjeta tenía `width="600"` fijo. Este archivo comprueba, sin depender del
navegador, que:

  · las 3 plantillas (factura, recordatorio, recibo) traen el meta viewport,
    la media query `@media only screen and (max-width:620px)` y las clases
    `mv-card` / `mv-pad` que usa esa media query,
  · en ninguna queda un `width="600"` fijo y el techo pasa a `max-width:600px`,
  · el contenido de cada correo no se rompió (resumen de factura, botón online,
    datos del banco, pie con la dirección, resumen del recordatorio y del
    recibo),
  · el logo se sigue adjuntando como parte inline con Content-ID `<mavlogo>`.

Además, si Playwright está disponible, mide el ancho real del documento a
390×844 (celular) y a 1440×900 (escritorio) para confirmar que no hay scroll
horizontal en el celular y que la tarjeta topa en 600px en escritorio.
"""
import os
import re
import sys
from email.message import EmailMessage

import pytest

sys.path.insert(0, "/app/backend")

from collections_engine import STAGES, receipt_body, reminder_body  # noqa: E402
from finance_email import (  # noqa: E402
    EMAIL_LOGO_CID,
    attach_email_logo,
    render_invoice_email_html,
)

WEB_DIR = "/app/backend/web"
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001").rstrip("/")


# ---------- fixtures de datos ----------
INV = {
    "id": "iter65-inv-1",
    "invoice_number": "OH-2026-0001",
    "period_start": "2026-08-01",
    "period_end": "2026-08-31",
    "issue_date": "2026-07-25",
    "due_date": "2026-08-01",
    "total": 255.0,
    "balance": 255.0,
}
CLIENT = {
    "business_name": "Pizzería La Prueba",
    "representative": "Franklin Test",
    "email": "test@example.com",
    "contact_name": "Franklin",
    "name": "Pizzería La Prueba",
}


def _all_templates():
    return {
        "invoice": render_invoice_email_html(INV, CLIENT,
                                             base_url="https://panel.mediadview.com"),
        "reminder_pre": reminder_body(INV, CLIENT, STAGES[0])[1],
        "reminder_late30": reminder_body(INV, CLIENT, STAGES[4])[1],
        "receipt_partial": receipt_body(INV, CLIENT, 100.0, False)[1],
        "receipt_full": receipt_body(INV, CLIENT, 255.0, True)[1],
    }


# ---------- 1) armazón responsive ----------
class TestResponsiveScaffolding:
    """El HTML tiene que traer el viewport, la media query y las clases nuevas."""

    @pytest.mark.parametrize("name,html", list(_all_templates().items()))
    def test_meta_viewport(self, name, html):
        assert '<meta name="viewport" content="width=device-width,initial-scale=1">' in html, name

    @pytest.mark.parametrize("name,html", list(_all_templates().items()))
    def test_media_query(self, name, html):
        assert "@media only screen and (max-width:620px)" in html, name

    @pytest.mark.parametrize("name,html", list(_all_templates().items()))
    def test_no_fixed_width_600(self, name, html):
        # No debe quedar ningún width="600" fijo en la tarjeta principal.
        assert 'width="600"' not in html, f"{name}: la tarjeta sigue con ancho fijo"

    @pytest.mark.parametrize("name,html", list(_all_templates().items()))
    def test_card_has_max_width_and_classes(self, name, html):
        assert "max-width:600px" in html, f"{name}: falta el techo de 600px"
        assert 'class="mv-card"' in html, f"{name}: falta la clase mv-card"
        assert 'class="mv-pad"' in html, f"{name}: falta la clase mv-pad"

    @pytest.mark.parametrize("name,html", list(_all_templates().items()))
    def test_media_query_targets_expected_classes(self, name, html):
        for cls in ("mv-wrap", "mv-card", "mv-head", "mv-pad",
                    "mv-logo", "mv-title", "mv-sub", "mv-btn"):
            assert f".{cls}" in html, f"{name}: la media query no toca .{cls}"


# ---------- 2) contenido intacto ----------
class TestInvoiceContentIntact:
    """La factura tiene que seguir mostrando resumen + botón + banco + pie."""

    def setup_method(self):
        self.html = render_invoice_email_html(
            INV, CLIENT, base_url="https://panel.mediadview.com")

    def test_summary_labels(self):
        for label in ("Client", "Invoice #", "Issue Date", "Due Date", "Amount Due"):
            assert label in self.html, f"falta '{label}' en el resumen"

    def test_summary_values(self):
        assert CLIENT["business_name"] in self.html
        assert INV["invoice_number"] in self.html
        assert "$255.00" in self.html          # balance formateado
        assert "August 01, 2026" in self.html  # fecha formateada

    def test_view_online_button_and_link(self):
        assert "View Invoice Online" in self.html
        assert (
            f'href="https://panel.mediadview.com/api/finance/invoices/{INV["id"]}/render"'
            in self.html
        )

    def test_bank_info_present(self):
        for label in ("Bank:", "Account #:", "Routing #:", "Make payable to:"):
            assert label in self.html, f"falta '{label}'"

    def test_footer_has_address(self):
        # El pie oscuro con la dirección de la empresa.
        assert "background:#0f172a;padding:18px 32px" in self.html
        assert "Columbus" in self.html or "OH" in self.html or "USA" in self.html


class TestReminderContentIntact:
    def test_reminder_shows_invoice_due_and_balance(self):
        subject, html = reminder_body(INV, CLIENT, STAGES[2])   # late_7
        assert INV["invoice_number"] in subject
        assert "Factura" in html
        assert "Vencimiento" in html
        assert "Saldo pendiente" in html
        assert INV["invoice_number"] in html
        assert "01/08/2026" in html
        assert "$255.00" in html


class TestReceiptContentIntact:
    def test_partial_payment_shows_invoice_amount_balance(self):
        subject, html = receipt_body(INV, CLIENT, 100.0, False)
        assert INV["invoice_number"] in subject
        assert "Factura" in html
        assert "Pago recibido" in html
        assert "Saldo" in html
        assert "$100.00" in html
        assert "$255.00" in html

    def test_full_payment_shows_zero_balance(self):
        _, html = receipt_body(INV, CLIENT, 255.0, True)
        assert "$255.00" in html
        assert "$0.00" in html   # saldo cero al pagar todo


# ---------- 3) logo inline ----------
class TestLogoStillAttachedInline:
    def test_attach_returns_true_and_adds_image_png_with_cid(self):
        html = render_invoice_email_html(INV, CLIENT, base_url="")
        msg = EmailMessage()
        msg["From"] = "a@b.com"; msg["To"] = "c@d.com"; msg["Subject"] = "t"
        msg.set_content("texto plano")
        msg.add_alternative(html, subtype="html")
        assert attach_email_logo(msg) is True

        found = [
            (p.get_content_type(), p.get("Content-ID"))
            for p in msg.walk()
        ]
        assert ("image/png", f"<{EMAIL_LOGO_CID}>") in found, found


# ---------- 4) render real en navegador (opcional) ----------
def _write_tmp_html(name: str, html: str) -> str:
    """Guarda el HTML en /app/backend/web/_tmp_xxx.html reemplazando el CID
    del logo por la URL pública del archivo servido; devuelve el path."""
    html = html.replace(f"cid:{EMAIL_LOGO_CID}", "/api/web/logo-email.png")
    path = os.path.join(WEB_DIR, f"_tmp_iter65_{name}.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path


class TestRenderedWidths:
    """Mide document.documentElement.scrollWidth a 390 y 1440 px."""

    def test_mobile_no_horizontal_scroll_and_desktop_capped_at_600(self):
        try:
            from playwright.sync_api import sync_playwright   # type: ignore
        except ImportError:
            pytest.skip("playwright no está instalado en este entorno")
        # Si el binario del navegador no está disponible, se saltea también:
        # el render en 390/1440px se verificó por fuera con el navegador del
        # entorno de testing (mcp_browser_automation) y quedó registrado en
        # /app/test_reports/iteration_62.json.
        try:
            with sync_playwright() as _p:
                _p.chromium.launch().close()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"binario de chromium no disponible: {exc}")

        tmp_paths = []
        try:
            urls = {}
            for name, html in _all_templates().items():
                path = _write_tmp_html(name, html)
                tmp_paths.append(path)
                urls[name] = f"{BASE_URL}/api/web/{os.path.basename(path)}"

            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    ctx_mobile = browser.new_context(viewport={"width": 390, "height": 844})
                    ctx_desktop = browser.new_context(viewport={"width": 1440, "height": 900})
                    for name, url in urls.items():
                        # celular: sin scroll horizontal
                        page = ctx_mobile.new_page()
                        page.goto(url, wait_until="load", timeout=15000)
                        sw = page.evaluate("document.documentElement.scrollWidth")
                        assert sw <= 390, (
                            f"{name}: scrollWidth={sw} en 390px (hay scroll horizontal)")
                        page.close()
                        # escritorio: tarjeta tope 600px
                        page = ctx_desktop.new_page()
                        page.goto(url, wait_until="load", timeout=15000)
                        card_w = page.evaluate(
                            "() => document.querySelector('.mv-card').getBoundingClientRect().width"
                        )
                        assert card_w <= 601, (
                            f"{name}: la tarjeta mide {card_w}px en 1440 (debería tope 600)")
                        assert card_w >= 580, (
                            f"{name}: la tarjeta mide {card_w}px (parece rota)")
                        page.close()
                finally:
                    browser.close()
        finally:
            for path in tmp_paths:
                try:
                    os.remove(path)
                except OSError:
                    pass


# ---------- 5) sanity: media query solo achica, no ensancha ----------
def test_media_query_reduces_paddings_and_logo():
    """La media query tiene que apretar (menos padding, menor logo/título)."""
    html = render_invoice_email_html(INV, CLIENT, base_url="")
    mq = re.search(r"@media only screen and \(max-width:620px\)\{(.+?)\}\s*</style>",
                   html, re.S)
    assert mq, "no encontré el bloque de la media query"
    body = mq.group(1)
    # los valores nuevos del breakpoint que documenta el fix
    assert "padding:22px 18px" in body           # mv-head (era 30px 32px)
    assert "padding-left:18px" in body           # mv-pad (era 32px)
    assert "width:175px" in body                 # mv-logo (era 230px)
    assert "font-size:19px" in body              # mv-title (era 22px)
    assert "display:block" in body               # mv-btn ancho completo
