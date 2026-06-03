"""
MediAd View — PDF Generation using ReportLab
Mirrors EXACTLY the user's original physical documents:
  • Security Deposit Receipt
  • Invoice
  • LED Display Rental Agreement (Contract)
Clean layout, no boxed UI; logo top-right; subtle gray table lines.
"""
from io import BytesIO
from datetime import datetime
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY

DARK   = colors.HexColor("#222222")
GRAY   = colors.HexColor("#666666")
LIGHT  = colors.HexColor("#999999")
LINE   = colors.HexColor("#c8c8c8")
ACCENT = colors.HexColor("#7a4ad5")  # subtle accent matching purple logo gradient

LOGO_PATH = "/app/backend/web/logo-pdf.png"  # smaller version for embedding
PAGE_W, PAGE_H = letter

COMPANY = {
    "name": "MediAd View LLC",
    "brand": "MediAd View",
    "tagline": "ADVERTISING SOLUTION",
    "address_line1": "2998 Riat Run Rd",
    "address_line2": "Grove City Ohio 43123",
    "phone_1": "1-877-202-8181",
    "phone_2": "1-614-745-8686",
    "bank_name": "CHASE Bank",
    "account_number": "891786730",
    "routing": "044000037",
    "website": "www.mediadview.com",
}


def fmt_money(v):
    try:
        return f"{float(v or 0):,.2f}"
    except Exception:
        return "0.00"


def _fmt(s):
    """YYYY-MM-DD → MM/DD/YY"""
    if not s:
        return ""
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%m/%d/%y")
    except Exception:
        return s


def _styles():
    s = getSampleStyleSheet()
    return {
        "title":   ParagraphStyle("title",   fontSize=26, leading=30, textColor=DARK,  fontName="Helvetica-Bold"),
        "brand":   ParagraphStyle("brand",   fontSize=22, leading=24, textColor=DARK,  fontName="Helvetica-Bold", alignment=TA_RIGHT),
        "tagline": ParagraphStyle("tagline", fontSize=9,  leading=11, textColor=GRAY,  fontName="Helvetica",      alignment=TA_RIGHT),
        "co":      ParagraphStyle("co",      fontSize=9,  leading=12, textColor=DARK,  fontName="Helvetica",      alignment=TA_RIGHT),
        "h_label": ParagraphStyle("h_label", fontSize=9,  leading=12, textColor=GRAY,  fontName="Helvetica-Bold", alignment=TA_RIGHT),
        "h_value": ParagraphStyle("h_value", fontSize=11, leading=13, textColor=DARK,  fontName="Helvetica-Bold", alignment=TA_RIGHT),
        "name_lg": ParagraphStyle("name_lg", fontSize=18, leading=22, textColor=DARK,  fontName="Helvetica-Bold"),
        "body":    ParagraphStyle("body",    fontSize=10, leading=14, textColor=DARK,  fontName="Helvetica"),
        "small":   ParagraphStyle("small",   fontSize=9,  leading=12, textColor=DARK,  fontName="Helvetica"),
        "small_g": ParagraphStyle("small_g", fontSize=9,  leading=12, textColor=GRAY,  fontName="Helvetica"),
        "th":      ParagraphStyle("th",      fontSize=9,  leading=11, textColor=GRAY,  fontName="Helvetica-Bold"),
        "td":      ParagraphStyle("td",      fontSize=10, leading=13, textColor=DARK,  fontName="Helvetica"),
        "td_r":    ParagraphStyle("td_r",    fontSize=10, leading=13, textColor=DARK,  fontName="Helvetica",      alignment=TA_RIGHT),
        "tot_lbl": ParagraphStyle("tot_lbl", fontSize=10, leading=14, textColor=DARK,  fontName="Helvetica-Bold", alignment=TA_LEFT),
        "tot_val": ParagraphStyle("tot_val", fontSize=10, leading=14, textColor=DARK,  fontName="Helvetica-Bold", alignment=TA_RIGHT),
        "TOT_LBL": ParagraphStyle("TOT_LBL", fontSize=13, leading=16, textColor=DARK,  fontName="Helvetica-Bold", alignment=TA_LEFT),
        "TOT_VAL": ParagraphStyle("TOT_VAL", fontSize=13, leading=16, textColor=DARK,  fontName="Helvetica-Bold", alignment=TA_RIGHT),
        "thanks":  ParagraphStyle("thanks",  fontSize=12, leading=14, textColor=DARK,  fontName="Helvetica-Bold"),
        "section_t": ParagraphStyle("section_t", fontSize=10, leading=12, textColor=DARK, fontName="Helvetica-Bold"),
        "section_b": ParagraphStyle("section_b", fontSize=9,  leading=12, textColor=DARK, fontName="Helvetica"),
        "clause":  ParagraphStyle("clause",  fontSize=10, leading=14, textColor=DARK,  fontName="Helvetica", alignment=TA_JUSTIFY, spaceAfter=6),
        "sig_lbl": ParagraphStyle("sig_lbl", fontSize=9, leading=11, textColor=GRAY, fontName="Helvetica-Bold"),
    }


def _header(st):
    """Logo + Brand block on the right, blank space on left."""
    logo = None
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image(LOGO_PATH, width=0.55*inch, height=0.55*inch)
        except Exception:
            logo = None
    brand_row = Table(
        [[logo or Spacer(1, 0.55*inch), Paragraph(COMPANY["brand"], st["brand"])]],
        colWidths=[0.7*inch, 2.3*inch]
    )
    brand_row.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",  (1,0), (1,-1), "RIGHT"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING",(0,0), (-1,-1), 0),
        ("TOPPADDING",  (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    block = Table([
        [brand_row],
        [Paragraph(COMPANY["tagline"], st["tagline"])],
        [Paragraph(
            f"{COMPANY['address_line1']}<br/>{COMPANY['address_line2']}<br/>"
            f"{COMPANY['phone_1']}<br/>{COMPANY['phone_2']}",
            st["co"]
        )],
    ], colWidths=[3.0*inch])
    block.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING",(0,0), (-1,-1), 0),
        ("TOPPADDING",  (0,0), (-1,-1), 2),
        ("BOTTOMPADDING",(0,0),(-1,-1), 2),
        ("ALIGN", (0,0), (-1,-1), "RIGHT"),
    ]))
    # Outer table: left empty (for title later), right = brand block
    outer = Table([[Spacer(1, 1), block]], colWidths=[4.0*inch, 3.0*inch])
    outer.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING",(0,0), (-1,-1), 0),
        ("TOPPADDING",  (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    return outer


def _no_padding(tbl, also_extra=None):
    style = [
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING",(0,0), (-1,-1), 0),
        ("TOPPADDING",  (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]
    if also_extra:
        style.extend(also_extra)
    tbl.setStyle(TableStyle(style))
    return tbl


def _doc(buf, top_margin=0.55*inch):
    return SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=top_margin, bottomMargin=0.55*inch,
        title="MediAd View Document", author="MediAd View",
    )


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(DARK)
    canvas.drawCentredString(PAGE_W/2, 0.32*inch, COMPANY["website"])
    canvas.restoreState()


# ============================================================
# =============== SECURITY DEPOSIT RECEIPT ===================
# ============================================================
def _draw_deposit_tail(canvas, dep):
    """Draw bank info (left) + totals (right) + 'Thank You' + Terms anchored at bottom."""
    canvas.saveState()
    base_y = 0.85*inch
    # --- BANK INFO (left)
    x_left = 0.6*inch
    y = base_y + 1.55*inch
    canvas.setFont("Helvetica-Bold", 10.5)
    canvas.setFillColor(DARK)
    canvas.drawString(x_left, y, COMPANY["name"])
    canvas.setFont("Helvetica", 9)
    y -= 14
    canvas.drawString(x_left, y, f"Account Number   {COMPANY['account_number']}")
    y -= 12
    canvas.drawString(x_left, y, f"Bank Name   {COMPANY['bank_name']}")
    y -= 12
    canvas.drawString(x_left, y, f"Routing   {COMPANY['routing']} deposits and ACH transactions")

    # --- TOTALS (right)
    x_right_label = PAGE_W - 2.55*inch
    x_right_value = PAGE_W - 0.7*inch
    y = base_y + 1.55*inch
    canvas.setFont("Helvetica-Bold", 10.5)
    canvas.drawString(x_right_label, y, "Sub-Total")
    canvas.drawRightString(x_right_value, y, fmt_money(dep.get("amount",0)))
    y -= 18
    canvas.drawString(x_right_label, y, "TAX")
    canvas.drawRightString(x_right_value, y, fmt_money(dep.get("tax",0)))
    y -= 14
    canvas.setStrokeColor(LINE); canvas.setLineWidth(0.7)
    canvas.line(x_right_label, y, x_right_value, y)
    y -= 18
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(x_right_label, y, "TOTAL")
    canvas.drawRightString(x_right_value, y, fmt_money(dep.get("total", dep.get("amount",0))))

    # Thank You (left) + Terms (right) — same line as the totals base
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(0.6*inch, base_y, "Thank You For Your Business")
    canvas.setFont("Helvetica-Bold", 9.5)
    canvas.setFillColor(DARK)
    canvas.drawString(x_right_label - 0.3*inch, base_y + 0.05*inch, "Terms and Conditions")
    canvas.setFont("Helvetica", 8.2)
    from reportlab.pdfbase.pdfmetrics import stringWidth
    terms = ("We may condition future contract renewals/service renewals or suspend our "
             "services to you until such amount is paid in full.")
    # Wrap manually within ~2.85in
    max_w = 2.85*inch
    words = terms.split()
    line = ""
    line_y = base_y - 0.08*inch
    for w in words:
        test = (line + " " + w).strip()
        if stringWidth(test, "Helvetica", 8.2) <= max_w:
            line = test
        else:
            canvas.drawString(x_right_label - 0.3*inch, line_y, line)
            line = w
            line_y -= 11
    if line:
        canvas.drawString(x_right_label - 0.3*inch, line_y, line)

    # website footer
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(DARK)
    canvas.drawCentredString(PAGE_W/2, 0.32*inch, COMPANY["website"])
    canvas.restoreState()


def generate_deposit_pdf(dep: dict, client: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.5*inch, bottomMargin=2.7*inch,
        title="MediAd View Deposit Receipt", author="MediAd View",
    )
    st = _styles()
    story = []
    story.append(_brand_header(st))
    story.append(Spacer(1, 4))

    # Title + customer (left), full-width then horizontal strip with date/receipt
    title_block = Table([
        [Paragraph("Security Deposit Receipt:", st["title"])],
        [Spacer(1, 10)],
        [Paragraph(f"{client.get('business_name','—')}", st["name_lg"])],
        [Paragraph(_addr_html(client), st["small"])],
        [Paragraph(client.get("phone",""), st["small"])],
    ], colWidths=[6.9*inch])
    _no_padding(title_block)
    story.append(title_block)
    story.append(Spacer(1, 18))

    # Horizontal strip with Receipt Date / Receipt No.
    story.append(_period_strip(st, [
        ("RECEIPT DATE", _today_or(dep.get("issue_date"))),
        ("RECEIPT NO.",  dep.get("receipt_number","")),
    ]))
    story.append(Spacer(1, 20))

    # Items table
    screens = dep.get("screens") or []
    rows = [[Paragraph("LED", st["th"]),
             Paragraph("ITEM DESCRIPTION", st["th"]),
             Paragraph("TOTAL", ParagraphStyle("tr", parent=st["th"], alignment=TA_RIGHT))]]
    per = (dep.get("amount", 0) / (len(screens) or 1)) if screens else dep.get("amount", 0)
    for idx, s in enumerate(screens or [{"model":"MAV-30540S","units":1}], 1):
        rows.append([
            Paragraph(str(idx).zfill(2), st["td"]),
            Paragraph(f"Screen LED Ultra Brightness Rent {s.get('model','MAV-30540S')}", st["td"]),
            Paragraph(fmt_money(per), st["td_r"]),
        ])

    items = Table(rows, colWidths=[0.7*inch, 4.7*inch, 1.4*inch])
    items.setStyle(TableStyle([
        ("LINEBELOW", (0,0), (-1,0), 0.7, LINE),
        ("LINEBELOW", (0,-1),(-1,-1), 0.7, LINE),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("LEFTPADDING",(0,0),(-1,-1), 2),
        ("RIGHTPADDING",(0,0),(-1,-1), 2),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(items)
    story.append(Spacer(1, 6))

    loc_text = _loc_summary(screens, client)
    if loc_text:
        story.append(Paragraph(loc_text, st["small_g"]))

    cb = lambda c, d: _draw_deposit_tail(c, dep)
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    return buf.getvalue()


# ============================================================
# ========================= INVOICE ==========================
# ============================================================
def _period_strip(st, items):
    """Horizontal strip with bordered box: 'PERIOD DATE | INVOICE DUE | INVOICE#'."""
    n = len(items)
    cells = []
    for label, value in items:
        cells.append(Table([
            [Paragraph(label, ParagraphStyle("ps_l", fontSize=8.5, leading=10, textColor=GRAY,
                                              fontName="Helvetica-Bold", alignment=TA_LEFT))],
            [Paragraph(str(value or "—"), ParagraphStyle("ps_v", fontSize=11, leading=13, textColor=DARK,
                                                          fontName="Helvetica-Bold", alignment=TA_LEFT))],
        ], colWidths=[2.05*inch]))
    # Equal-width columns
    w = 6.9 / n
    tbl = Table([cells], colWidths=[w*inch]*n)
    # Border + dividers
    style = [
        ("BOX", (0,0), (-1,-1), 0.6, LINE),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 14),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
    ]
    for i in range(1, n):
        style.append(("LINEBEFORE", (i,0), (i,-1), 0.5, LINE))
    tbl.setStyle(TableStyle(style))
    # Strip the inner cell padding so labels sit flush
    for c in cells:
        _no_padding(c)
    return tbl


def _draw_invoice_tail(canvas, inv):
    """Draw bank info (left) + totals (right) + 'Thank You' centered, anchored at bottom of page."""
    canvas.saveState()
    # Bottom block lives between Y=0.55in (above the website footer) up to ~3.2in
    base_y = 0.85*inch  # bottom of the totals area
    # --- BANK INFO (left)
    x_left = 0.6*inch
    y = base_y + 1.55*inch
    canvas.setFont("Helvetica-Bold", 10.5)
    canvas.setFillColor(DARK)
    canvas.drawString(x_left, y, COMPANY["name"])
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(DARK)
    y -= 14
    canvas.drawString(x_left, y, f"Account Number   {COMPANY['account_number']}")
    y -= 12
    canvas.drawString(x_left, y, f"Bank Name   {COMPANY['bank_name']}")
    y -= 12
    canvas.drawString(x_left, y, f"Routing   {COMPANY['routing']} deposits and ACH transactions")

    # --- TOTALS (right column)
    x_right_label = PAGE_W - 2.55*inch
    x_right_value = PAGE_W - 0.7*inch
    y = base_y + 1.55*inch
    canvas.setFont("Helvetica-Bold", 10.5)
    canvas.setFillColor(DARK)
    canvas.drawString(x_right_label, y, "Sub-Total")
    canvas.drawRightString(x_right_value, y, f"${fmt_money(inv.get('subtotal',0))}")
    y -= 18
    canvas.drawString(x_right_label, y, "Tax")
    canvas.drawRightString(x_right_value, y, fmt_money(inv.get("tax",0)))
    # separator line above TOTAL
    y -= 14
    canvas.setStrokeColor(LINE); canvas.setLineWidth(0.7)
    canvas.line(x_right_label, y, x_right_value, y)
    y -= 18
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(x_right_label, y, "TOTAL")
    canvas.drawRightString(x_right_value, y, f"${fmt_money(inv.get('total',0))}")

    # --- Thank You centered, below the block
    canvas.setFont("Helvetica-Bold", 12.5)
    canvas.setFillColor(DARK)
    canvas.drawCentredString(PAGE_W/2, base_y, "Thank You For Your Business")

    # website footer
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(DARK)
    canvas.drawCentredString(PAGE_W/2, 0.32*inch, COMPANY["website"])
    canvas.restoreState()


def generate_invoice_pdf(inv: dict, client: dict) -> bytes:
    buf = BytesIO()
    # Reserve space at the bottom for the totals/bank/thanks block (~2.6in)
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.5*inch, bottomMargin=2.7*inch,
        title="MediAd View Invoice", author="MediAd View",
    )
    st = _styles()
    story = []

    story.append(_brand_header(st))
    story.append(Spacer(1, 4))

    # Top: INVOICE TO (left), brand block already on right via header. Customer info below.
    title_block = Table([
        [Paragraph("INVOICE TO:", st["title"])],
        [Spacer(1, 10)],
        [Paragraph(f"{client.get('business_name','—')}", st["name_lg"])],
        [Paragraph(_addr_html(client), st["small"])],
        [Paragraph(client.get("phone",""), st["small"])],
    ], colWidths=[6.9*inch])
    _no_padding(title_block)
    story.append(title_block)
    story.append(Spacer(1, 18))

    # Horizontal strip with the 3 dates side by side, bordered
    story.append(_period_strip(st, [
        ("PERIOD DATE", f"{_fmt(inv.get('period_start',''))} – {_fmt(inv.get('period_end',''))}"),
        ("INVOICE DUE", _fmt(inv.get("due_date",""))),
        ("INVOICE #",   inv.get("invoice_number","")),
    ]))
    story.append(Spacer(1, 20))

    # Items
    rows = [[
        Paragraph("LED", st["th"]),
        Paragraph("ITEM DESCRIPTION", st["th"]),
        Paragraph("DAY PRICE($)", ParagraphStyle("tr", parent=st["th"], alignment=TA_RIGHT)),
        Paragraph("DAY", ParagraphStyle("tc", parent=st["th"], alignment=TA_CENTER)),
        Paragraph("TOTAL", ParagraphStyle("tr2", parent=st["th"], alignment=TA_RIGHT)),
    ]]
    for it in inv.get("items", []):
        rows.append([
            Paragraph(str(it.get("line_no","")).zfill(2) if str(it.get("line_no","")).isdigit() else str(it.get("line_no","")), st["td"]),
            Paragraph(it.get("description",""), st["td"]),
            Paragraph(f"${fmt_money(it.get('day_price',0))}", st["td_r"]),
            Paragraph(str(it.get("days",0)), ParagraphStyle("tdc", parent=st["td"], alignment=TA_CENTER)),
            Paragraph(fmt_money(it.get("total",0)), st["td_r"]),
        ])
    items = Table(rows, colWidths=[0.55*inch, 3.5*inch, 1.05*inch, 0.5*inch, 1.2*inch])
    items.setStyle(TableStyle([
        ("LINEBELOW", (0,0), (-1,0), 0.7, LINE),
        ("LINEBELOW", (0,-1),(-1,-1), 0.7, LINE),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("LEFTPADDING",(0,0),(-1,-1), 2),
        ("RIGHTPADDING",(0,0),(-1,-1), 2),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(items)

    # The bottom block (bank info + totals + thanks) is drawn via canvas
    cb = lambda c, d: _draw_invoice_tail(c, inv)
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    return buf.getvalue()


# ============================================================
# ===================== CONTRACT (Agreement) =================
# ============================================================
def generate_contract_pdf(ct: dict, client: dict) -> bytes:
    buf = BytesIO()
    doc = _doc(buf, top_margin=0.45*inch)
    # Override margins for contract: tighter to fit in 2 pages
    doc.leftMargin = 0.55*inch
    doc.rightMargin = 0.55*inch
    doc.bottomMargin = 0.45*inch
    st = _styles()
    # Tighter clause style for contract — denser layout to fit in 2 pages
    clause_tight = ParagraphStyle(
        "clause_tight", parent=st["clause"],
        fontSize=9.5, leading=12.5, spaceAfter=4
    )
    story = []
    # Compact header: small logo + name + tagline (no address/phones)
    story.append(_contract_header(st))
    story.append(Spacer(1, 6))

    # Centered title
    story.append(Paragraph(
        "LED DISPLAY RENTAL AGREEMENT",
        ParagraphStyle("ct_title", fontSize=15, leading=18, alignment=TA_CENTER,
                       textColor=DARK, fontName="Helvetica-Bold", spaceAfter=8)
    ))

    # Contract date
    try:
        contract_date = datetime.fromisoformat(ct.get("created_at", datetime.utcnow().isoformat())).strftime("%B %d, %Y")
    except Exception:
        contract_date = datetime.utcnow().strftime("%B %d, %Y")

    # I. THE PARTIES — plain prose
    lessee_addr = client.get("address_line1","")
    city_st = " ".join(filter(None, [client.get("city",""), client.get("state",""), client.get("zip","")]))
    if city_st:
        lessee_addr = (lessee_addr + ", " + city_st).strip(", ")
    rep = client.get("representative", "")
    rep_html = f" (Representative <b>{rep}</b>)" if rep else ""

    story.append(Paragraph(
        f"<b>I. THE PARTIES.</b> This Equipment Rental Agreement (&ldquo;Agreement&rdquo;) is made on this "
        f"<b>{contract_date}</b> by and between:",
        clause_tight
    ))
    story.append(Paragraph(
        f"<b>Lessor:</b> A business entity known as <b>{COMPANY['name']}</b>, with a mailing address of "
        f"{COMPANY['address_line1']}, {COMPANY['address_line2']}, Phone {COMPANY['phone_1']} (&ldquo;Lessor&rdquo;), and",
        clause_tight
    ))
    story.append(Paragraph(
        f"<b>Lessee:</b> A business entity known as <b>{client.get('business_name','—')}</b>{rep_html} with a mailing "
        f"address of {lessee_addr}, Phone {client.get('phone','')} (&ldquo;Lessee&rdquo;).",
        clause_tight
    ))
    story.append(Paragraph(
        "Lessor and Lessee are each referred to herein as a &ldquo;Party&rdquo; and collectively as the "
        "&ldquo;Parties.&rdquo;",
        clause_tight
    ))

    # II. EQUIPMENT DESCRIPTION
    screens = ct.get("screens", []) or []
    total_units = sum(int(s.get("units", 1)) for s in screens)
    model = screens[0].get("model", "MAV-30540S") if screens else "MAV-30540S"
    locs = [f"{int(s.get('units',1))} unit(s) at {s.get('location') or client.get('address_line1','')}"
            for s in screens]
    locs_text = "; ".join(locs) if locs else f"{client.get('address_line1','')}"
    story.append(Paragraph(
        f"<b>II. EQUIPMENT DESCRIPTION.</b> The Lessor hereby leases to Lessee the following equipment: "
        f"Number of rented Equipment <b>{total_units}</b> UNIT ULTRA SLIM LED DISPLAY Model: <b>{model}</b>, "
        f"distributed in <b>{len(locs) or 1}</b> store(s) as follows, {locs_text}.",
        clause_tight
    ))

    # III. LEASE TYPE
    story.append(Paragraph(
        f"<b>III. LEASE TYPE.</b> This Agreement shall be considered a fixed agreement starting on "
        f"<b>{_fmt(ct.get('start_date',''))}</b> and ending on <b>{_fmt(ct.get('end_date',''))}</b> "
        f"(&ldquo;Lease Term&rdquo;). At the end of the Lease Term and no renewal is made, the Lessee shall be "
        f"required to return the Equipment to the Lessor.",
        clause_tight
    ))

    # IV. RENT
    day_price = screens[0].get("day_price", 8.5) if screens else 8.5
    story.append(Paragraph(
        f"<b>IV. RENT.</b> Lessee agrees to pay Lessor <b>${fmt_money(day_price)}</b> per display per day for a "
        f"total of <b>${fmt_money(ct.get('monthly_total',0))}</b> for the rental of the Equipment "
        f"(&ldquo;Rent&rdquo;) to be paid monthly.",
        clause_tight
    ))
    story.append(Paragraph(
        f"<b>a.) Rent Instructions.</b> The Rent will be paid in the following way: direct deposit to the account "
        f"mentioned below or by check every first day of each month — "
        f"<b>{COMPANY['name']}</b>, Account Number <b>{COMPANY['account_number']}</b>, "
        f"Bank Name <b>{COMPANY['bank_name']}</b>, Routing <b>{COMPANY['routing']}</b> deposits and ACH transactions.",
        clause_tight
    ))

    # V. LATE CHARGES
    story.append(Paragraph(
        f"<b>V. LATE CHARGES.</b> If any amount of Rent is late under this Agreement of more than 5 day(s) late, "
        f"the Lessee will be obligated to pay a late fee of <b>${fmt_money(ct.get('late_fee_per_day',50))}</b> for "
        f"each day that Rent is late.",
        clause_tight
    ))
    # VI. NSF
    story.append(Paragraph(
        f"<b>VI. NON-SUFFICIENT FUNDS.</b> The Lessee shall be charged <b>${fmt_money(ct.get('nsf_fee',85))}</b> "
        f"for each check that is returned to the Lessor for lack of sufficient funds.",
        clause_tight
    ))
    # VII. SECURITY DEPOSIT
    sec_per = ct.get("security_deposit_per_screen", 250)
    sec_tot = ct.get("security_deposit", 0)
    story.append(Paragraph(
        f"<b>VII. SECURITY DEPOSIT.</b> Prior to taking possession of the Equipment, Renter shall pay a deposit in "
        f"the amount of <b>${fmt_money(sec_per)}</b> (&ldquo;Security Deposit&rdquo;) per screen for a total of "
        f"<b>${fmt_money(sec_tot)}</b>, for Renter&rsquo;s performance under this Agreement for damages caused by "
        f"the Lessee or Lessee&rsquo;s agents to the Equipment during the Lease Term. In addition, the Security "
        f"Deposit may be applied to any amount owed by the Lessee to the Lessor.",
        clause_tight
    ))

    # VIII–XXIII (fixed clauses)
    clauses = [
        ("VIII. DELIVERY OF EQUIPMENT",
         "The delivery of the Equipment to the Lessee at the start of the Lease Term and returning to the Lessor at "
         "the end of the Lease Term shall be the responsibility of the Lessor."),
        ("IX. REPAIRS AND MAINTENANCE",
         "If for any reason the Equipment shall need repairs or maintenance due to wear-and-tear, the Lessor shall "
         "be responsible."),
        ("X. INSURANCE",
         "There shall be no requirement for the Lessee to have any type or kind of insurance as part of this Agreement."),
        ("XI. ACCEPTANCE OF EQUIPMENT",
         "The Lessee shall inspect each item and part of the Equipment upon delivery and pursuant to this Agreement. "
         "The Lessee shall have twenty-four (24) hours from the delivery date to inform the Lessor of any "
         "discrepancies. If for any reason the Lessee claims the Equipment was not the same or as described under this "
         "Agreement, the Lessee shall be able to return the Equipment and obtain a full refund for any Rent, Security "
         "Deposit, and any other payments made."),
        ("XII. NO WARRANTY",
         "The Lessor makes no warranties, express or implied, as to the equipment leased. The Lessee assumes "
         "responsibility for the condition of the Equipment."),
        ("XIV. RISK OF LOSS OR DAMAGE",
         "The Lessee assumes all risk of loss or damage to the Equipment from any cause and agrees to return it to "
         "the Lessor in the condition received, with the exception of wear and tear, unless otherwise provided in "
         "this Agreement."),
        ("a.) Damaged or Lost Equipment",
         "Unless otherwise provided in this Agreement, if the equipment is damaged or lost, the Lessor shall have "
         "the option of requiring the lessee to either repair the Equipment to a state of good working order or to "
         "replace the Equipment with like-equipment and in equal condition. The final decision for approval of any "
         "lost or damaged Equipment will be ultimately up to the Lessor."),
        ("XV. TAXES AND FEES",
         "During the Lease Term, the Lessee shall be responsible and be required to pay any applicable taxes, "
         "assessments, license, registration, or any other fees associated with the handling and operation of the "
         "Equipment."),
        ("XVI. DEFAULT",
         "The occurrence of any of the following shall constitute a default under this Agreement: "
         "a.) Failure of Payment — The failure of the Lessee to make a required payment under this Agreement; "
         "b.) Violation of Agreement — The violation of any provision of this Agreement that is not corrected "
         "within five (5) business days after written notice has been received; "
         "c.) Bankruptcy — The insolvency or bankruptcy of the Lessee; and "
         "d.) Seizure — The subjection of any of the Lessee&rsquo;s property to any levy, seizure, assignment, "
         "application, or sale for or by any creditor or government agency."),
        ("XVII. RIGHTS UNDER DEFAULT",
         "If the Lessee shall default under this Agreement, and without notice to or demand on the Lessee, the "
         "Lessor may take possession of the Equipment as provided by law with the right to deduct the costs of "
         "recovery, including any attorney&rsquo;s fees and legal costs, in addition to any repair or other costs "
         "to obtain the Equipment and bring to the same condition as the Lessee received upon initial delivery."),
        ("XVIII. ASSIGNMENT",
         "The Lessee is strictly prohibited from assigning or subletting the Equipment in any manner unless written "
         "consent is given by the Lessor. In addition, the Equipment may not be used by any person or associate "
         "other than the Lessee and their agents, employees, and subcontractors."),
        ("XIX. SEVERABILITY",
         "If any portion of this Agreement shall be held invalid or unenforceable for any reason, the remaining "
         "provisions shall constitute to be valid and enforceable."),
        ("XX. GOVERNING LAW",
         "This Agreement shall be construed and governed in accordance with the laws located in the State where the "
         "Equipment is being rented."),
        ("XXI. ENTIRE AGREEMENT",
         "This Agreement constitutes the entire agreement between the Parties. No modification or amendment of this "
         "Agreement shall be effective unless in writing and signed by both Parties. This Agreement replaces any and "
         "all prior agreements made between the Parties."),
        ("XXII. ADDITIONAL TERMS &amp; CONDITIONS",
         "1 - The led screen can not be manipulated by anyone who is not authorized, only mediad view technicians "
         "can install and uninstall the screen.<br/>"
         "2 - Unauthorized tampering or opening of the led screen will damage and incur charges of <b>$8,500.00</b>.<br/>"
         "3 - The tenant agrees to send changes and updates to their offers and say them to the guidelines department."
         + (f"<br/>4 - {ct.get('additional_terms','')}" if ct.get("additional_terms") else "")),
        ("XXIII. EXECUTION",
         "Lessee and Lessor each represent and warrant to the other that each person executing this Agreement on "
         "behalf of each party is duly authorized to execute and deliver this Agreement on behalf of that party."),
    ]
    for label, body in clauses:
        story.append(Paragraph(f"<b>{label}.</b> {body}", clause_tight))

    story.append(Spacer(1, 14))

    # Signature lines (plain, inline style like the original)
    lessor_sig_img = _sig_image(ct.get("lessor_signature"))
    lessee_sig_img = _sig_image(ct.get("lessee_signature"))
    signed_at = ct.get("signed_at", "")

    def _sig_col(sig_img, role_html, name_html, extra=""):
        cells = []
        if sig_img:
            cells.append([sig_img])
        else:
            cells.append([Paragraph("_______________________________", st["body"])])
        cells.append([Paragraph(role_html, st["sig_lbl"])])
        cells.append([Paragraph(name_html, st["body"])])
        if extra:
            cells.append([Paragraph(extra, st["small"])])
        if sig_img and signed_at:
            cells.append([Paragraph(f"Date: {signed_at}", st["small"])])
        else:
            cells.append([Paragraph("Date: ________________", st["small"])])
        t = Table(cells, colWidths=[3.2*inch])
        _no_padding(t)
        return t

    lessor_col = _sig_col(
        lessor_sig_img,
        "<b>Lessor&rsquo;s Signature</b>",
        f"<b>Print Name:</b> {COMPANY['name']}",
        f"Phone {COMPANY['phone_1']}"
    )
    rep = client.get("representative","")
    rep_line = f"Representative {rep}<br/>" if rep else ""
    lessee_col = _sig_col(
        lessee_sig_img,
        "<b>Lessee&rsquo;s Signature</b>",
        f"<b>Print Name:</b> {client.get('business_name','—')}",
        f"{rep_line}Phone {client.get('phone','')}"
    )
    sig_tbl = Table([[lessor_col, lessee_col]], colWidths=[3.45*inch, 3.45*inch])
    _no_padding(sig_tbl, [("VALIGN", (0,0), (-1,-1), "TOP")])
    story.append(KeepTogether(sig_tbl))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# ============================================================
# ============== Shared layout helpers =======================
# ============================================================
def _contract_header(st):
    """Compact header for contracts: small logo + brand name + tagline only.
    No address/phones (those appear inside the I. THE PARTIES section)."""
    logo = None
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image(LOGO_PATH, width=1.1*inch, height=0.33*inch)
        except Exception:
            logo = None
    name_cell = Table([
        [Paragraph(COMPANY["brand"], ParagraphStyle("brand_sm", parent=st["brand"], fontSize=16, leading=18, alignment=TA_LEFT))],
        [Paragraph(COMPANY["tagline"], ParagraphStyle("tag_sm", parent=st["tagline"], alignment=TA_LEFT))],
    ], colWidths=[2.2*inch])
    _no_padding(name_cell)
    row = Table([[logo or Spacer(1, 0.4*inch), name_cell]],
                colWidths=[1.25*inch, 2.4*inch])
    _no_padding(row, [("VALIGN", (0,0), (-1,-1), "MIDDLE")])
    # Centered on the page
    outer = Table([[row]], colWidths=[6.9*inch])
    _no_padding(outer, [("ALIGN", (0,0), (-1,-1), "CENTER")])
    return outer


def _brand_header(st):
    """Right-aligned brand block — LOGO ONLY (the logo already contains brand+tagline)
    + address + phones below."""
    logo = None
    if os.path.exists(LOGO_PATH):
        try:
            # Wide logo (~3.3:1 aspect)
            logo = Image(LOGO_PATH, width=2.0*inch, height=0.6*inch)
        except Exception:
            logo = None

    addr_para = Paragraph(
        f"{COMPANY['address_line1']}<br/>{COMPANY['address_line2']}<br/>"
        f"{COMPANY['phone_1']}<br/>{COMPANY['phone_2']}",
        st["co"]
    )
    right = Table([[logo or Spacer(1, 0.55*inch)], [Spacer(1, 4)], [addr_para]],
                  colWidths=[3.1*inch])
    _no_padding(right, [("ALIGN", (0,0), (-1,-1), "RIGHT")])

    outer = Table([[Spacer(1, 1), right]], colWidths=[3.9*inch, 3.1*inch])
    _no_padding(outer, [("VALIGN", (0,0), (-1,-1), "TOP")])
    return outer


def _header_right_block(st, items):
    """Right side: stacked label/value pairs (e.g., Receipt Date / Receipt No.)."""
    rows = []
    for label, value in items:
        rows.append([Paragraph(label, st["h_label"])])
        rows.append([Paragraph(str(value or ""), st["h_value"])])
        rows.append([Spacer(1, 6)])
    tbl = Table(rows, colWidths=[2.6*inch])
    _no_padding(tbl)
    # Wrap so it sits flush right
    wrap = Table([[Spacer(1, 1), tbl]], colWidths=[0.4*inch, 2.6*inch])
    _no_padding(wrap)
    return wrap


def _bank_block(st):
    rows = [
        [Paragraph(f"<b>{COMPANY['name']}</b>", st["section_t"])],
        [Paragraph(f"<b>Account Number</b> &nbsp; {COMPANY['account_number']}", st["section_b"])],
        [Paragraph(f"<b>Bank Name</b> &nbsp; {COMPANY['bank_name']}", st["section_b"])],
        [Paragraph(f"<b>Routing</b> &nbsp; {COMPANY['routing']} deposits and ACH transactions", st["section_b"])],
    ]
    tbl = Table(rows, colWidths=[3.9*inch])
    _no_padding(tbl)
    return tbl


def _addr_html(client):
    parts = []
    if client.get("address_line1"): parts.append(client.get("address_line1"))
    city_st = " ".join(filter(None, [client.get("city",""), client.get("state",""), client.get("zip","")]))
    if city_st: parts.append(city_st)
    return " ".join(parts)


def _loc_summary(screens, client):
    """e.g., '1 units at 891 Oak St Columbus Oh 43205'."""
    if not screens:
        return ""
    parts = []
    for s in screens:
        loc = s.get("location") or client.get("address_line1","")
        parts.append(f"{int(s.get('units',1))} units at {loc}")
    return " · ".join(parts)


def _today_or(d):
    if d:
        return _fmt(d)
    return datetime.utcnow().strftime("%m/%d/%y")


def _sig_image(sig_b64):
    if not sig_b64 or not isinstance(sig_b64, str) or "base64," not in sig_b64:
        return None
    try:
        import base64
        b64 = sig_b64.split("base64,", 1)[1]
        data = base64.b64decode(b64)
        bio = BytesIO(data)
        return Image(bio, width=2.2*inch, height=0.65*inch)
    except Exception:
        return None
