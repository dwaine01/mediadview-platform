"""
MediAd View — PDF Generation using ReportLab
Generates branded PDFs for invoices, contracts, and deposit receipts.
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
    PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY

BRAND_BLUE = colors.HexColor("#2563eb")
BRAND_DARK = colors.HexColor("#0f172a")
BRAND_GRAY = colors.HexColor("#64748b")
BRAND_LIGHT_GRAY = colors.HexColor("#f1f5f9")
BRAND_BORDER = colors.HexColor("#e2e8f0")
BRAND_BG_TINT = colors.HexColor("#eff6ff")

LOGO_PATH = "/app/backend/web/logo.png"

COMPANY = {
    "name": "MediAd View LLC",
    "tagline": "ADVERTISING SOLUTION",
    "address_line1": "2998 Riat Run Rd",
    "address_line2": "Grove City, Ohio 43123",
    "phone_1": "1-877-202-8181",
    "phone_2": "1-614-745-8686",
    "bank_name": "CHASE Bank",
    "account_number": "891786730",
    "routing": "044000037",
    "website": "www.mediadview.com",
}


def fmt_money(v):
    return "$" + f"{float(v or 0):,.2f}"


def _styles():
    s = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=s["Heading1"], fontSize=22, textColor=BRAND_DARK, spaceAfter=2, fontName="Helvetica-Bold"),
        "h2": ParagraphStyle("h2", parent=s["Heading2"], fontSize=12, textColor=BRAND_DARK, fontName="Helvetica-Bold"),
        "brand": ParagraphStyle("brand", fontSize=18, textColor=BRAND_DARK, fontName="Helvetica-Bold", leading=20),
        "tag": ParagraphStyle("tag", fontSize=8, textColor=BRAND_BLUE, fontName="Helvetica-Bold", spaceAfter=0),
        "co": ParagraphStyle("co", fontSize=9, textColor=BRAND_GRAY, alignment=TA_RIGHT, leading=12),
        "section": ParagraphStyle("section", fontSize=8, textColor=BRAND_GRAY, fontName="Helvetica-Bold", spaceAfter=4),
        "body": ParagraphStyle("body", fontSize=10, textColor=BRAND_DARK, leading=14),
        "small": ParagraphStyle("small", fontSize=9, textColor=BRAND_GRAY, leading=12),
        "clause": ParagraphStyle("clause", fontSize=9, textColor=colors.HexColor("#334155"), leading=13, alignment=TA_JUSTIFY, spaceAfter=8),
        "footer": ParagraphStyle("footer", fontSize=8, textColor=BRAND_GRAY, alignment=TA_CENTER),
        "thanks": ParagraphStyle("thanks", fontSize=13, textColor=BRAND_BLUE, alignment=TA_CENTER, fontName="Helvetica-Bold"),
    }


def _header_table(st):
    logo = None
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image(LOGO_PATH, width=0.7*inch, height=0.7*inch)
        except Exception:
            logo = None
    brand_block = [
        [logo or Paragraph("", st["body"]), Paragraph(f"<b>MediAd View</b>", st["brand"])],
        ["", Paragraph(COMPANY["tagline"], st["tag"])],
    ]
    brand_tbl = Table(brand_block, colWidths=[0.85*inch, 2.5*inch])
    brand_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING", (0,0), (-1,-1), 0),
        ("SPAN", (0,0), (0,1)),
    ]))
    co = Paragraph(
        f"{COMPANY['address_line1']}<br/>{COMPANY['address_line2']}<br/>"
        f"{COMPANY['phone_1']}<br/>{COMPANY['phone_2']}",
        st["co"]
    )
    header_tbl = Table([[brand_tbl, co]], colWidths=[3.6*inch, 3.4*inch])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LINEBELOW", (0,0), (-1,-1), 2, BRAND_BLUE),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
    ]))
    return header_tbl


def _payment_info(st):
    txt = (
        f"<b>{COMPANY['name']} — Payment Information</b><br/>"
        f"<b>Bank:</b> {COMPANY['bank_name']} &nbsp;&nbsp; "
        f"<b>Account #:</b> {COMPANY['account_number']} &nbsp;&nbsp; "
        f"<b>Routing:</b> {COMPANY['routing']}<br/>"
        f"<b>Method:</b> ACH transfers &amp; deposits"
    )
    p = Paragraph(txt, ParagraphStyle("payinfo", fontSize=9, textColor=colors.HexColor("#1e3a8a"), leading=13))
    box = Table([[p]], colWidths=[6.9*inch])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), BRAND_BG_TINT),
        ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#bfdbfe")),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
    ]))
    return box


def _info_box(label, content, st, accent=BRAND_BLUE):
    p_lbl = Paragraph(f"<b>{label}</b>", st["section"])
    p_content = Paragraph(content, st["body"])
    inner = Table([[p_lbl], [p_content]], colWidths=[3.3*inch])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("BACKGROUND", (0,0), (-1,-1), BRAND_LIGHT_GRAY),
        ("LINEBEFORE", (0,0), (-1,-1), 3, accent),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    return inner


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(BRAND_GRAY)
    canvas.drawCentredString(letter[0]/2, 0.4*inch,
        f"{COMPANY['website']} · {COMPANY['phone_1']}  ·  Page {doc.page}")
    canvas.restoreState()


# =========================== INVOICE PDF ===========================
def generate_invoice_pdf(inv: dict, client: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.5*inch, bottomMargin=0.6*inch)
    st = _styles()
    story = []
    story.append(_header_table(st))
    story.append(Spacer(1, 14))

    # Title
    status = (inv.get("status") or "pending").upper()
    status_color = {"PAID":"#059669","OVERDUE":"#dc2626","PENDING":"#d97706","CANCELLED":"#64748b"}.get(status, "#64748b")
    title_tbl = Table([[
        Paragraph("<b>INVOICE</b>", ParagraphStyle("t", fontSize=22, textColor=BRAND_DARK, fontName="Helvetica-Bold")),
        Paragraph(f'<font color="{status_color}"><b>{status}</b></font>',
                  ParagraphStyle("st", fontSize=11, alignment=TA_RIGHT, fontName="Helvetica-Bold")),
    ]], colWidths=[5*inch, 2*inch])
    story.append(title_tbl)
    period = f"Period: {_fmt(inv.get('period_start'))} – {_fmt(inv.get('period_end'))}"
    story.append(Paragraph(period, st["small"]))
    story.append(Spacer(1, 16))

    # Info boxes
    addr_lines = []
    if client.get("address_line1"): addr_lines.append(client.get("address_line1"))
    city_line = " ".join(filter(None, [client.get("city",""), client.get("state",""), client.get("zip","")]))
    if city_line: addr_lines.append(city_line)
    if client.get("phone"): addr_lines.append(client.get("phone"))
    bill_to = f"<b>{client.get('business_name','—')}</b><br/>" + "<br/>".join(addr_lines)
    inv_details = (
        f"<b>Invoice #:</b> {inv.get('invoice_number','')}<br/>"
        f"<b>Issue Date:</b> {_fmt(inv.get('issue_date',''))}<br/>"
        f"<b>Due Date:</b> {_fmt(inv.get('due_date',''))}"
    )
    info_tbl = Table([[_info_box("INVOICE TO", bill_to, st),
                       _info_box("INVOICE DETAILS", inv_details, st)]],
                      colWidths=[3.45*inch, 3.45*inch])
    info_tbl.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
                                  ("VALIGN",(0,0),(-1,-1),"TOP"),]))
    story.append(info_tbl)
    story.append(Spacer(1, 18))

    # Items table
    items_data = [["LED", "ITEM DESCRIPTION", "DAY PRICE", "DAYS", "TOTAL"]]
    for it in inv.get("items", []):
        items_data.append([
            it.get("line_no",""),
            it.get("description",""),
            fmt_money(it.get("day_price",0)),
            str(it.get("days",0)),
            fmt_money(it.get("total",0)),
        ])
    items_tbl = Table(items_data, colWidths=[0.55*inch, 3.55*inch, 1.1*inch, 0.6*inch, 1.1*inch])
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), BRAND_DARK),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
        ("ALIGN", (2,0), (2,-1), "RIGHT"),
        ("ALIGN", (3,0), (3,-1), "CENTER"),
        ("ALIGN", (4,0), (4,-1), "RIGHT"),
        ("FONTSIZE", (0,1), (-1,-1), 10),
        ("TEXTCOLOR", (0,1), (-1,-1), colors.HexColor("#334155")),
        ("TOPPADDING", (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 9),
        ("LINEBELOW", (0,0), (-1,-2), 0.5, BRAND_BORDER),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 12))

    # Totals
    rows = [
        ["Sub-Total", fmt_money(inv.get("subtotal", 0))],
        ["Tax", fmt_money(inv.get("tax", 0))],
        ["TOTAL", fmt_money(inv.get("total", 0))],
    ]
    if inv.get("amount_paid", 0) > 0:
        rows.append(["Amount Paid", fmt_money(inv.get("amount_paid", 0))])
        rows.append(["Balance Due", fmt_money(inv.get("balance", 0))])
    totals_tbl = Table(rows, colWidths=[1.8*inch, 1.5*inch])
    totals_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("BACKGROUND", (0,2), (-1,2), BRAND_BG_TINT),
        ("FONTNAME", (0,2), (-1,2), "Helvetica-Bold"),
        ("FONTSIZE", (0,2), (-1,2), 13),
        ("TEXTCOLOR", (0,2), (-1,2), BRAND_DARK),
        ("LINEABOVE", (0,2), (-1,2), 1.5, BRAND_BLUE),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
    ]))
    wrap = Table([["", totals_tbl]], colWidths=[3.6*inch, 3.3*inch])
    wrap.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
    story.append(wrap)
    story.append(Spacer(1, 20))

    story.append(_payment_info(st))
    story.append(Spacer(1, 18))
    story.append(Paragraph("Thank You For Your Business", st["thanks"]))
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_BORDER))
    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>TERMS AND CONDITIONS</b>", st["section"]))
    story.append(Paragraph(
        "We may condition future contract renewals/service renewals or suspend our services to you until such amount is paid in full.",
        ParagraphStyle("terms", fontSize=8, textColor=BRAND_GRAY, leading=11, alignment=TA_JUSTIFY)
    ))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# =========================== DEPOSIT PDF ===========================
def generate_deposit_pdf(dep: dict, client: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.5*inch, bottomMargin=0.6*inch)
    st = _styles()
    story = []
    story.append(_header_table(st))
    story.append(Spacer(1, 14))

    status = "RECEIVED" if dep.get("status") == "received" else "PENDING"
    status_color = "#059669" if dep.get("status") == "received" else "#d97706"
    title_tbl = Table([[
        Paragraph("<b>Security Deposit Receipt</b>", ParagraphStyle("t", fontSize=20, textColor=BRAND_DARK, fontName="Helvetica-Bold")),
        Paragraph(f'<font color="{status_color}"><b>{status}</b></font>',
                  ParagraphStyle("st", fontSize=11, alignment=TA_RIGHT, fontName="Helvetica-Bold")),
    ]], colWidths=[5*inch, 2*inch])
    story.append(title_tbl)
    story.append(Paragraph("Refundable upon return of equipment in good condition", st["small"]))
    story.append(Spacer(1, 16))

    addr = " ".join(filter(None, [client.get("address_line1",""), client.get("city",""), client.get("state",""), client.get("zip","")]))
    cust = f"<b>{client.get('business_name','—')}</b><br/>{addr}<br/>{client.get('phone','')}"
    det = (f"<b>Receipt #:</b> {dep.get('receipt_number','')}<br/>"
           f"<b>Date:</b> {_fmt(dep.get('issue_date',''))}")
    info_tbl = Table([[_info_box("CUSTOMER", cust, st), _info_box("RECEIPT", det, st)]],
                      colWidths=[3.45*inch, 3.45*inch])
    info_tbl.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
                                  ("VALIGN",(0,0),(-1,-1),"TOP")]))
    story.append(info_tbl)
    story.append(Spacer(1, 18))

    screens = dep.get("screens", [])
    rows = [["LED", "ITEM DESCRIPTION", "QTY", "TOTAL"]]
    per = (dep.get("amount", 0) / (len(screens) or 1)) if screens else 0
    for idx, s in enumerate(screens, 1):
        rows.append([str(idx),
                     f"Screen LED Ultra Brightness Rent {s.get('model','MAV-30540S')}",
                     str(s.get('units',1)),
                     fmt_money(per)])
    tbl = Table(rows, colWidths=[0.55*inch, 4.55*inch, 0.7*inch, 1.1*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), BRAND_DARK),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
        ("ALIGN", (2,0), (2,-1), "CENTER"),
        ("ALIGN", (3,0), (3,-1), "RIGHT"),
        ("FONTSIZE", (0,1), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 9),
        ("LINEBELOW", (0,0), (-1,-2), 0.5, BRAND_BORDER),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 12))

    rows = [
        ["Sub-Total", fmt_money(dep.get("amount", 0))],
        ["Tax", fmt_money(dep.get("tax", 0))],
        ["TOTAL", fmt_money(dep.get("total", 0))],
    ]
    totals_tbl = Table(rows, colWidths=[1.8*inch, 1.5*inch])
    totals_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("BACKGROUND", (0,2), (-1,2), BRAND_BG_TINT),
        ("FONTNAME", (0,2), (-1,2), "Helvetica-Bold"),
        ("FONTSIZE", (0,2), (-1,2), 13),
        ("TEXTCOLOR", (0,2), (-1,2), BRAND_DARK),
        ("LINEABOVE", (0,2), (-1,2), 1.5, BRAND_BLUE),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
    ]))
    wrap = Table([["", totals_tbl]], colWidths=[3.6*inch, 3.3*inch])
    wrap.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
    story.append(wrap)
    story.append(Spacer(1, 20))
    story.append(_payment_info(st))
    story.append(Spacer(1, 18))
    story.append(Paragraph("Thank You For Your Business", st["thanks"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# =========================== CONTRACT PDF ===========================
def generate_contract_pdf(ct: dict, client: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.5*inch, bottomMargin=0.7*inch)
    st = _styles()
    story = []
    story.append(_header_table(st))
    story.append(Spacer(1, 10))

    contract_date = ""
    try:
        contract_date = datetime.fromisoformat(ct.get("created_at", datetime.utcnow().isoformat())).strftime("%B %d, %Y")
    except Exception:
        contract_date = datetime.utcnow().strftime("%B %d, %Y")

    title = Table([[
        Paragraph("<b>LED DISPLAY RENTAL AGREEMENT</b>",
                  ParagraphStyle("t", fontSize=18, textColor=BRAND_DARK, fontName="Helvetica-Bold", alignment=TA_CENTER)),
    ]], colWidths=[6.9*inch])
    title.setStyle(TableStyle([("LINEBELOW",(0,0),(-1,-1),1.5,BRAND_DARK),("BOTTOMPADDING",(0,0),(-1,-1),10)]))
    story.append(title)
    story.append(Paragraph(f"Contract # {ct.get('contract_number','')} · {contract_date}",
                           ParagraphStyle("sub", fontSize=10, alignment=TA_CENTER, textColor=BRAND_GRAY)))
    story.append(Spacer(1, 14))

    story.append(Paragraph(
        f"<b>I. THE PARTIES.</b> This Equipment Rental Agreement (&ldquo;Agreement&rdquo;) is made on this <b>{contract_date}</b> by and between:",
        st["clause"]
    ))

    lessor = (f"<b>{COMPANY['name']}</b><br/>{COMPANY['address_line1']}<br/>"
              f"{COMPANY['address_line2']}<br/>Phone: {COMPANY['phone_1']}")
    lessee_addr = " ".join(filter(None, [client.get("city",""), client.get("state",""), client.get("zip","")]))
    lessee = (f"<b>{client.get('business_name','—')}</b><br/>"
              f"Representative: <b>{client.get('representative','—')}</b><br/>"
              f"{client.get('address_line1','')} {lessee_addr}<br/>Phone: {client.get('phone','')}")
    parties_tbl = Table([[_info_box("LESSOR", lessor, st),
                          _info_box("LESSEE", lessee, st, accent=colors.HexColor("#10b981"))]],
                        colWidths=[3.45*inch, 3.45*inch])
    parties_tbl.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
                                     ("VALIGN",(0,0),(-1,-1),"TOP")]))
    story.append(parties_tbl)
    story.append(Spacer(1, 14))

    # Equipment description
    eq_lines = []
    total_units = 0
    for s in ct.get("screens", []):
        total_units += s.get("units", 1)
        eq_lines.append(f"• {s.get('units',1)} UNIT(s) ULTRA SLIM LED DISPLAY Model: <b>{s.get('model','MAV-30540S')}</b> @ {fmt_money(s.get('day_price',8.5))}/day")
    loc_lines = []
    for s in ct.get("screens", []):
        loc_lines.append(f"• {s.get('units',1)} unit(s) at <b>{s.get('location','')}</b>")
    story.append(Paragraph(
        f"<b>II. EQUIPMENT DESCRIPTION.</b> The Lessor hereby leases to Lessee the following equipment:<br/>" +
        "<br/>".join(eq_lines) + f"<br/>Distributed in {total_units} location(s) as follows:<br/>" + "<br/>".join(loc_lines),
        st["clause"]
    ))

    story.append(Paragraph(
        f"<b>III. LEASE TYPE.</b> This Agreement shall be considered a fixed agreement starting on <b>{_fmt(ct.get('start_date',''))}</b> and ending on <b>{_fmt(ct.get('end_date',''))}</b> — <b>{ct.get('term_months',12)} months</b>. At the end of the Lease Term and no renewal is made, the Lessee shall be required to return the Equipment to the Lessor.",
        st["clause"]
    ))

    story.append(Paragraph(
        f"<b>IV. RENT.</b> Lessee agrees to pay Lessor a total of <b>{fmt_money(ct.get('monthly_total',0))}</b> per month for the rental of the Equipment (&ldquo;Rent&rdquo;) to be paid monthly. The Rent will be paid by direct deposit or check every <b>first day of each month</b> to: {COMPANY['name']} · Account: {COMPANY['account_number']} · {COMPANY['bank_name']} · Routing: {COMPANY['routing']}",
        st["clause"]
    ))

    clauses = [
        ("V. LATE CHARGES", f"If any amount of Rent is more than 5 day(s) late, the Lessee will be obligated to pay a late fee of <b>{fmt_money(ct.get('late_fee_per_day',50))}</b> for each day Rent is late."),
        ("VI. NON-SUFFICIENT FUNDS", f"The Lessee shall be charged <b>{fmt_money(ct.get('nsf_fee',85))}</b> for each check that is returned for lack of sufficient funds."),
        ("VII. SECURITY DEPOSIT", f"Prior to taking possession of the Equipment, Renter shall pay a deposit of <b>{fmt_money(ct.get('security_deposit_per_screen',250))}</b> per screen for a total of <b>{fmt_money(ct.get('security_deposit',0))}</b>, for performance under this Agreement and any damages caused by the Lessee to the Equipment during the Lease Term."),
        ("VIII. DELIVERY OF EQUIPMENT", "The delivery of the Equipment to the Lessee at the start of the Lease Term and returning to the Lessor at the end of the Lease Term shall be the responsibility of the Lessor."),
        ("IX. REPAIRS AND MAINTENANCE", "If for any reason the Equipment shall need repairs or maintenance due to wear-and-tear, the Lessor shall be responsible."),
        ("X. INSURANCE", "There shall be no requirement for the Lessee to have any type or kind of insurance as part of this Agreement."),
        ("XI. ACCEPTANCE OF EQUIPMENT", "The Lessee shall have twenty-four (24) hours from the delivery date to inform the Lessor of any discrepancies. If the Equipment was not as described, the Lessee may return it and obtain a full refund."),
        ("XII. NO WARRANTY", "The Lessor makes no warranties, express or implied, as to the equipment leased."),
        ("XIV. RISK OF LOSS OR DAMAGE", "The Lessee assumes all risk of loss or damage to the Equipment and agrees to return it in the condition received, with the exception of wear and tear."),
        ("XV. TAXES AND FEES", "During the Lease Term, the Lessee shall be responsible for any applicable taxes, assessments, licenses, registrations or fees associated with the operation of the Equipment."),
        ("XVI. DEFAULT", "The occurrence of any of the following shall constitute a default: (a) failure of payment; (b) violation of agreement not corrected within 5 business days of notice; (c) bankruptcy; (d) seizure of Lessee's property."),
        ("XVII. RIGHTS UNDER DEFAULT", "If the Lessee defaults, the Lessor may take possession of the Equipment with the right to deduct the costs of recovery, including attorney's fees."),
        ("XVIII. ASSIGNMENT", "The Lessee is strictly prohibited from assigning or subletting the Equipment unless written consent is given by the Lessor."),
        ("XIX. SEVERABILITY", "If any portion of this Agreement is held invalid or unenforceable, the remaining provisions shall constitute to be valid and enforceable."),
        ("XX. GOVERNING LAW", "This Agreement shall be construed and governed in accordance with the laws of the State where the Equipment is being rented."),
        ("XXI. ENTIRE AGREEMENT", "This Agreement constitutes the entire agreement between the Parties. No modification shall be effective unless in writing and signed by both Parties."),
        ("XXII. ADDITIONAL TERMS & CONDITIONS", "1) The LED screen cannot be manipulated by anyone who is not authorized. Only MediAd View technicians can install and uninstall the screen. 2) Unauthorized tampering or opening of the LED screen will damage it and incur charges of <b>$8,500.00</b>. 3) The tenant agrees to send changes and updates to their offers to the guidelines department." + (f" 4) {ct.get('additional_terms','')}" if ct.get('additional_terms') else "")),
        ("XXIII. EXECUTION", "Lessee and Lessor each represent that each person executing this Agreement on behalf of each party is duly authorized."),
    ]
    for title_txt, body in clauses:
        story.append(Paragraph(f"<b>{title_txt}.</b> {body}", st["clause"]))

    story.append(Spacer(1, 20))
    # Signatures
    lessor_sig_img = _sig_image(ct.get("lessor_signature"))
    lessee_sig_img = _sig_image(ct.get("lessee_signature"))
    signed_at = ct.get("signed_at", "")
    sig_left = Table([
        [lessor_sig_img if lessor_sig_img else Spacer(1, 30)],
        [Paragraph("_" * 36, ParagraphStyle("ln", fontSize=8))],
        [Paragraph("<b>LESSOR'S SIGNATURE</b>", st["section"])],
        [Paragraph(f"<b>{COMPANY['name']}</b>", st["body"])],
        [Paragraph(f"Phone: {COMPANY['phone_1']}", st["small"])],
        [Paragraph(f"Date: {signed_at if lessor_sig_img else '________________'}", st["small"])],
    ], colWidths=[3.3*inch])
    sig_right = Table([
        [lessee_sig_img if lessee_sig_img else Spacer(1, 30)],
        [Paragraph("_" * 36, ParagraphStyle("ln", fontSize=8))],
        [Paragraph("<b>LESSEE'S SIGNATURE</b>", st["section"])],
        [Paragraph(f"<b>{client.get('business_name','—')}</b>", st["body"])],
        [Paragraph(f"Representative: {client.get('representative','—')}", st["small"])],
        [Paragraph(f"Date: {signed_at if lessee_sig_img else '________________'}", st["small"])],
    ], colWidths=[3.3*inch])
    sig_tbl = Table([[sig_left, sig_right]], colWidths=[3.45*inch, 3.45*inch])
    sig_tbl.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP")]))
    story.append(sig_tbl)

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _sig_image(sig_b64):
    """Convert base64 signature data URL to ReportLab Image."""
    if not sig_b64 or not isinstance(sig_b64, str) or "base64," not in sig_b64:
        return None
    try:
        import base64
        b64 = sig_b64.split("base64,", 1)[1]
        data = base64.b64decode(b64)
        bio = BytesIO(data)
        return Image(bio, width=2.2*inch, height=0.7*inch)
    except Exception:
        return None


def _fmt(s):
    """YYYY-MM-DD → MM/DD/YY"""
    if not s: return ""
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%m/%d/%y")
    except Exception:
        return s
