# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""
MediAd View — Sign Permit Information (public form + admin management)

Public endpoint /api/sign-permits/submit is rate-limited and does NOT require
auth. Admin endpoints require role in (admin, superadmin).
"""
import base64
import io
import re
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import Response

sp_router = APIRouter(prefix="/api/sign-permits")

STATUSES = ["new", "in_review", "missing_info", "ready_for_permit",
            "submitted", "approved", "closed"]


def _ref():
    """SP-YYMMDD-HHMMSS-XXXX unique reference number."""
    now = datetime.utcnow()
    return f"SP-{now.strftime('%y%m%d-%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"


def _sanitize(s, maxlen=500):
    if s is None:
        return ""
    s = str(s).strip()
    # Strip null bytes + control chars except newline/tab
    s = "".join(c for c in s if c == "\n" or c == "\t" or ord(c) >= 32)
    return s[:maxlen]


def _valid_email(e):
    return bool(e) and bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", e))


# ---------------- IN-MEMORY THROTTLE (soft anti-spam) ----------------
_recent_submits = {}  # ip -> (count, last_ts)


def _throttled(ip):
    now = datetime.utcnow().timestamp()
    cnt, last = _recent_submits.get(ip, (0, 0))
    if now - last > 3600:
        cnt = 0
    if cnt >= 5:
        return True
    _recent_submits[ip] = (cnt + 1, now)
    return False


def _strip(doc):
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


def create_sign_permit_routes(db, require_admin):

    # ============ PUBLIC — SUBMIT ============
    @sp_router.post("/submit")
    async def submit(request: Request, payload: dict = Body(...)):
        ip = request.client.host if request.client else "unknown"
        if _throttled(ip):
            raise HTTPException(429, "Too many submissions from this IP. Try again later.")

        # Honeypot (bots fill hidden fields)
        if payload.get("_hp"):
            raise HTTPException(400, "Submission rejected.")

        # Required fields per spec
        required = {
            "business_name": "Business / Establishment Name",
            "business_owner": "Business Owner / Authorized Representative",
            "business_phone": "Phone Number",
            "business_email": "Email Address",
            "business_address": "Business Address / Sign Location",
            "business_city": "City",
            "business_state": "State",
            "business_zip": "ZIP Code",
            "landlord_company": "Property Owner / Landlord Company Name",
            "landlord_name": "Property Owner / Landlord Name",
            "landlord_phone": "Landlord Phone Number",
            "landlord_mailing": "Landlord Mailing Address",
            "landlord_city": "Landlord City",
            "landlord_state": "Landlord State",
            "landlord_zip": "Landlord ZIP Code",
            "cert_full_name": "Full Name",
            "cert_signature_data": "Signature",
            "cert_date": "Date",
        }
        for k, label in required.items():
            v = payload.get(k)
            if not v or (isinstance(v, str) and not v.strip()):
                raise HTTPException(400, f"Missing required field: {label}")

        if not payload.get("cert_agreed"):
            raise HTTPException(400, "You must accept the certification statement.")

        if not _valid_email(payload["business_email"]):
            raise HTTPException(400, "Invalid business email address.")

        # Signature must be a data URL for a PNG
        sig = payload["cert_signature_data"]
        if not isinstance(sig, str) or not sig.startswith("data:image/"):
            raise HTTPException(400, "Signature is invalid.")
        if len(sig) > 2 * 1024 * 1024:  # 2 MB
            raise HTTPException(413, "Signature image is too large.")

        # Build sanitised doc
        doc = {
            "id": str(uuid.uuid4()),
            "ref": _ref(),
            "status": "new",
            "submitted_at": datetime.utcnow(),
            "submitted_ip": ip,
            # Section 1
            "business_name":     _sanitize(payload["business_name"], 200),
            "legal_company":     _sanitize(payload.get("legal_company", ""), 200),
            "business_owner":    _sanitize(payload["business_owner"], 200),
            "business_phone":    _sanitize(payload["business_phone"], 40),
            "business_email":    _sanitize(payload["business_email"], 200).lower(),
            "business_address":  _sanitize(payload["business_address"], 300),
            "business_city":     _sanitize(payload["business_city"], 100),
            "business_state":    _sanitize(payload["business_state"], 60),
            "business_zip":      _sanitize(payload["business_zip"], 20),
            # Section 2
            "landlord_company":  _sanitize(payload["landlord_company"], 200),
            "landlord_name":     _sanitize(payload["landlord_name"], 200),
            "landlord_contact":  _sanitize(payload.get("landlord_contact", ""), 200),
            "landlord_phone":    _sanitize(payload["landlord_phone"], 40),
            "landlord_email":    _sanitize(payload.get("landlord_email", ""), 200).lower(),
            "landlord_mailing":  _sanitize(payload["landlord_mailing"], 300),
            "landlord_city":     _sanitize(payload["landlord_city"], 100),
            "landlord_state":    _sanitize(payload["landlord_state"], 60),
            "landlord_zip":      _sanitize(payload["landlord_zip"], 20),
            # Section 3
            "sign_business_name":  _sanitize(payload.get("sign_business_name", ""), 200),
            "sign_address":        _sanitize(payload.get("sign_address", ""), 300),
            "sign_type":           _sanitize(payload.get("sign_type", ""), 60),
            "sign_type_other":     _sanitize(payload.get("sign_type_other", ""), 200),
            "sign_description":    _sanitize(payload.get("sign_description", ""), 2000),
            "sign_additional":     _sanitize(payload.get("sign_additional", ""), 2000),
            # Authorization
            "cert_agreed":         True,
            "cert_full_name":      _sanitize(payload["cert_full_name"], 200),
            "cert_signature_data": sig,   # keep the data URL as-is
            "cert_date":           _sanitize(payload["cert_date"], 40),
            # Admin
            "admin_notes": "",
        }

        await db.sign_permits.insert_one(doc)

        # Fire-and-forget email (never blocks the response)
        try:
            await _send_notification_emails(db, doc)
        except Exception as e:
            # Log but don't fail the submission
            print(f"[sign_permits] Email send failed: {e}")

        return {"ok": True, "ref": doc["ref"], "id": doc["id"]}

    # ============ ADMIN — LIST ============
    @sp_router.get("/list")
    async def admin_list(user: dict = Depends(require_admin),
                          status: Optional[str] = None):
        q = {"status": status} if status in STATUSES else {}
        cursor = db.sign_permits.find(q, {"cert_signature_data": 0}).sort("submitted_at", -1)
        return [_strip(d) async for d in cursor]

    # ============ ADMIN — DETAIL ============
    @sp_router.get("/{permit_id}")
    async def admin_detail(permit_id: str, user: dict = Depends(require_admin)):
        d = await db.sign_permits.find_one({"id": permit_id})
        if not d:
            raise HTTPException(404, "Permit not found")
        return _strip(d)

    # ============ ADMIN — UPDATE STATUS / NOTES ============
    @sp_router.put("/{permit_id}")
    async def admin_update(permit_id: str, payload: dict = Body(...),
                            user: dict = Depends(require_admin)):
        update = {}
        if payload.get("status") in STATUSES:
            update["status"] = payload["status"]
        if "admin_notes" in payload:
            update["admin_notes"] = _sanitize(payload["admin_notes"], 5000)
        if not update:
            raise HTTPException(400, "Nothing to update")
        update["updated_at"] = datetime.utcnow()
        update["updated_by"] = user.get("email")
        r = await db.sign_permits.update_one({"id": permit_id}, {"$set": update})
        if r.matched_count == 0:
            raise HTTPException(404, "Permit not found")
        return {"ok": True}

    # ============ ADMIN — PDF EXPORT ============
    @sp_router.get("/{permit_id}/pdf")
    async def admin_pdf(permit_id: str, user: dict = Depends(require_admin)):
        d = await db.sign_permits.find_one({"id": permit_id})
        if not d:
            raise HTTPException(404, "Permit not found")
        pdf = _render_permit_pdf(d)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{d["ref"]}.pdf"'}
        )

    return sp_router


# ============================================================
# Email notifications
# ============================================================
async def _send_notification_emails(db, doc):
    """Send:
       1) Copy of submission to Sales@mediadview.com
       2) Confirmation to customer (business_email)"""
    s = await db.fin_settings.find_one({"_id": "email"})
    if not s or not s.get("enabled"):
        print("[sign_permits] SMTP not configured, emails skipped")
        return
    from email.message import EmailMessage
    from email.utils import formataddr

    import aiosmtplib
    try:
        from finance_email import decrypt_password
        pwd = decrypt_password(s.get("smtp_password", ""))
    except Exception:
        pwd = ""

    port = int(s.get("smtp_port", 587))
    use_tls = port == 465
    start_tls = not use_tls
    from_addr = s.get("from_email") or s.get("smtp_user")
    from_name = s.get("from_name", "MediAd View")

    # -- 1) Admin notification --
    admin_msg = EmailMessage()
    admin_msg["From"] = formataddr((from_name, from_addr))
    admin_msg["To"] = "Sales@mediadview.com"
    admin_msg["Subject"] = f"New Sign Permit Information – {doc['business_name']}"
    admin_msg.set_content(_permit_text_body(doc))
    admin_msg.add_alternative(_permit_html_body(doc, is_admin=True), subtype="html")
    try:
        await aiosmtplib.send(admin_msg,
            hostname=s.get("smtp_host", "smtp.titan.email"),
            port=port, username=s.get("smtp_user"), password=pwd,
            use_tls=use_tls, start_tls=start_tls, timeout=30)
    except Exception as e:
        print(f"[sign_permits] admin email failed: {e}")

    # -- 2) Customer confirmation --
    if _valid_email(doc.get("business_email", "")):
        cust = EmailMessage()
        cust["From"] = formataddr((from_name, from_addr))
        cust["To"] = doc["business_email"]
        cust["Subject"] = f"We received your sign permit information — {doc['ref']}"
        cust.set_content(
            f"Hello {doc.get('cert_full_name') or doc.get('business_owner') or 'there'},\n\n"
            f"Thank you for submitting your Sign Permit Information to MediAd View.\n"
            f"Reference number: {doc['ref']}\n\n"
            f"Our team will review the information and contact you if anything else is needed.\n\n"
            f"— The MediAd View Team\n"
            f"1-877-202-8181  ·  Sales@mediadview.com  ·  mediadview.com\n"
        )
        cust.add_alternative(_permit_html_body(doc, is_admin=False), subtype="html")
        try:
            await aiosmtplib.send(cust,
                hostname=s.get("smtp_host", "smtp.titan.email"),
                port=port, username=s.get("smtp_user"), password=pwd,
                use_tls=use_tls, start_tls=start_tls, timeout=30)
        except Exception as e:
            print(f"[sign_permits] customer email failed: {e}")


def _permit_text_body(d):
    return (
        f"Sign Permit Information — Reference {d['ref']}\n"
        f"Submitted: {d['submitted_at']} UTC\n\n"
        f"BUSINESS\n"
        f"  Business: {d['business_name']}\n"
        f"  Owner: {d['business_owner']}\n"
        f"  Phone: {d['business_phone']}\n"
        f"  Email: {d['business_email']}\n"
        f"  Location: {d['business_address']}, {d['business_city']} {d['business_state']} {d['business_zip']}\n\n"
        f"LANDLORD\n"
        f"  Company: {d['landlord_company']}\n"
        f"  Name: {d['landlord_name']}\n"
        f"  Phone: {d['landlord_phone']}\n"
        f"  Email: {d.get('landlord_email','')}\n"
        f"  Mailing: {d['landlord_mailing']}, {d['landlord_city']} {d['landlord_state']} {d['landlord_zip']}\n\n"
        f"SIGN\n"
        f"  Type: {d.get('sign_type','')}{(' — '+d['sign_type_other']) if d.get('sign_type_other') else ''}\n"
        f"  Description: {d.get('sign_description','')}\n"
        f"  Additional: {d.get('sign_additional','')}\n\n"
        f"AUTHORIZATION\n"
        f"  Signed by: {d['cert_full_name']}\n"
        f"  Date: {d['cert_date']}\n"
    )


def _permit_html_body(d, is_admin=True):
    esc = lambda s: str(s or "").replace("<","&lt;").replace(">","&gt;")
    intro = ("<p>A new Sign Permit Information form has been submitted through the MediAd View website.</p>"
             if is_admin else
             "<p>Thank you for submitting your Sign Permit Information to MediAd View. "
             "Our team will review it and contact you if anything else is needed.</p>")
    return f"""<html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#f4f6fb;padding:24px">
<div style="max-width:640px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.06)">
  <div style="background:linear-gradient(135deg,#0f172a,#1e293b);padding:22px;color:#fff">
    <div style="font-size:11px;letter-spacing:2px;font-weight:800;opacity:.85">MEDIAD VIEW</div>
    <div style="font-size:20px;font-weight:900;margin-top:4px">Sign Permit Information</div>
    <div style="font-size:12px;opacity:.8;margin-top:4px">Reference: <b>{esc(d['ref'])}</b></div>
  </div>
  <div style="padding:22px;color:#0f172a;font-size:13.5px;line-height:1.55">
    {intro}
    <h3 style="margin:16px 0 6px;font-size:13px;color:#64748b;text-transform:uppercase;letter-spacing:1px">Business</h3>
    <div>{esc(d['business_name'])} — {esc(d['business_owner'])}</div>
    <div>{esc(d['business_phone'])} · {esc(d['business_email'])}</div>
    <div>{esc(d['business_address'])}, {esc(d['business_city'])} {esc(d['business_state'])} {esc(d['business_zip'])}</div>

    <h3 style="margin:16px 0 6px;font-size:13px;color:#64748b;text-transform:uppercase;letter-spacing:1px">Landlord</h3>
    <div>{esc(d['landlord_company'])} — {esc(d['landlord_name'])}</div>
    <div>{esc(d['landlord_phone'])} · {esc(d.get('landlord_email',''))}</div>
    <div>{esc(d['landlord_mailing'])}, {esc(d['landlord_city'])} {esc(d['landlord_state'])} {esc(d['landlord_zip'])}</div>

    <h3 style="margin:16px 0 6px;font-size:13px;color:#64748b;text-transform:uppercase;letter-spacing:1px">Sign</h3>
    <div>Type: {esc(d.get('sign_type',''))}{(' — '+esc(d.get('sign_type_other',''))) if d.get('sign_type_other') else ''}</div>
    <div>{esc(d.get('sign_description',''))}</div>

    <p style="margin-top:22px;font-size:11.5px;color:#94a3b8">
      Signed by <b>{esc(d['cert_full_name'])}</b> on {esc(d['cert_date'])}<br>
      MediAd View · 1-877-202-8181 · Sales@mediadview.com · mediadview.com
    </p>
  </div>
</div></body></html>"""


# ============================================================
# PDF rendering (reportlab)
# ============================================================
def _render_permit_pdf(d):
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    w, h = LETTER
    y = h - 0.6 * inch

    # Logo (best-effort — from /app/backend/web/logo-dark.png)
    try:
        import os

        from reportlab.lib.utils import ImageReader
        for candidate in ["/app/backend/web/logo-dark.png",
                          "/app/backend/web/logo-new.png"]:
            if os.path.exists(candidate):
                c.drawImage(ImageReader(candidate), 0.5*inch, y-0.05*inch,
                            width=1.7*inch, height=0.6*inch,
                            preserveAspectRatio=True, mask='auto')
                break
    except Exception:
        pass

    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(w - 0.5*inch, y + 0.15*inch, "Sign Permit Information")
    c.setFont("Helvetica", 9); c.setFillGray(0.4)
    c.drawRightString(w - 0.5*inch, y - 0.05*inch, f"Ref: {d['ref']}")
    c.drawRightString(w - 0.5*inch, y - 0.20*inch,
                       f"Submitted: {d['submitted_at'].strftime('%Y-%m-%d %H:%M UTC')}")
    c.setFillGray(0)
    y -= 0.9*inch
    c.setStrokeGray(0.85); c.line(0.5*inch, y, w-0.5*inch, y); y -= 0.25*inch

    def section(title, rows, y_):
        c.setFont("Helvetica-Bold", 10); c.setFillGray(0.35)
        c.drawString(0.5*inch, y_, title.upper())
        c.setFillGray(0); y_ -= 0.20*inch
        c.setFont("Helvetica", 10)
        for label, val in rows:
            if val is None or val == "": val = "—"
            val = str(val)
            c.setFillGray(0.45); c.drawString(0.55*inch, y_, label)
            c.setFillGray(0)
            # wrap long values
            words = val.split()
            line = ""; xx = 2.1*inch; maxw = w - 2.6*inch
            for wd in words:
                trial = (line + " " + wd).strip()
                if c.stringWidth(trial, "Helvetica", 10) > maxw:
                    c.drawString(xx, y_, line); y_ -= 0.16*inch; line = wd
                else:
                    line = trial
            if line: c.drawString(xx, y_, line); y_ -= 0.16*inch
            if y_ < 1.4*inch:
                c.showPage(); y_ = h - 0.7*inch
                c.setFont("Helvetica", 10)
        y_ -= 0.10*inch
        return y_

    y = section("Business / Tenant", [
        ("Business Name:",   d['business_name']),
        ("Legal Company:",   d.get('legal_company','')),
        ("Owner / Rep:",     d['business_owner']),
        ("Phone:",           d['business_phone']),
        ("Email:",           d['business_email']),
        ("Address:",         f"{d['business_address']}, {d['business_city']} {d['business_state']} {d['business_zip']}"),
    ], y)
    y = section("Landlord / Property Owner", [
        ("Landlord Company:", d['landlord_company']),
        ("Landlord Name:",    d['landlord_name']),
        ("Contact:",          d.get('landlord_contact','')),
        ("Phone:",            d['landlord_phone']),
        ("Email:",            d.get('landlord_email','')),
        ("Mailing Address:",  f"{d['landlord_mailing']}, {d['landlord_city']} {d['landlord_state']} {d['landlord_zip']}"),
    ], y)
    y = section("Sign Project", [
        ("Business Name on Sign:", d.get('sign_business_name','')),
        ("Sign Address:",          d.get('sign_address','')),
        ("Type of Sign:",          d.get('sign_type','') + (f" — {d.get('sign_type_other','')}" if d.get('sign_type_other') else '')),
        ("Description:",           d.get('sign_description','')),
        ("Additional:",            d.get('sign_additional','')),
    ], y)

    # Authorization + signature
    if y < 3.2*inch:
        c.showPage(); y = h - 0.7*inch
    y = section("Authorization", [
        ("Certified by:", d['cert_full_name']),
        ("Date:",         d['cert_date']),
    ], y)
    # Signature image
    try:
        sig = d.get('cert_signature_data','')
        if sig.startswith("data:image/"):
            b64 = sig.split(",", 1)[1]
            from reportlab.lib.utils import ImageReader
            img = ImageReader(io.BytesIO(base64.b64decode(b64)))
            c.setFillGray(0.45); c.setFont("Helvetica", 9)
            c.drawString(0.55*inch, y, "Signature:")
            c.setFillGray(0)
            c.drawImage(img, 2.1*inch, y-1.05*inch, width=3.2*inch, height=1.2*inch,
                        preserveAspectRatio=True, mask='auto')
            y -= 1.30*inch
    except Exception:
        pass

    # Footer
    c.setFont("Helvetica", 8); c.setFillGray(0.5)
    c.drawString(0.5*inch, 0.5*inch,
                  "MediAd View · 1-877-202-8181 · Sales@mediadview.com · mediadview.com")

    c.save()
    return buf.getvalue()
