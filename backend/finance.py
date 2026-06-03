"""
MediAd View — Finance & Administration Module
Phase 1: Clients (CRM), Contracts, Invoices, Deposits, Payments
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timedelta, date
from calendar import monthrange
import uuid
import re

finance_router = APIRouter(prefix="/api/finance")

# ==================== COMPANY CONSTANTS ====================
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
    "logo_url": "/api/web/logo.png",
}

# ==================== MODELS ====================
class LocationScreen(BaseModel):
    id: Optional[str] = None
    model: str = "MAV-30540S"
    units: int = 1
    day_price: float = 8.50
    serial: Optional[str] = ""
    notes: Optional[str] = ""

class ClientLocation(BaseModel):
    id: Optional[str] = None
    name: str  # e.g. "Dulce Vida - Brickell"
    address_line1: str
    city: str = ""
    state: str = ""
    zip: str = ""
    phone: Optional[str] = ""
    screens: List[LocationScreen] = []
    status: str = "active"  # active, paused, closed

class ClientCreate(BaseModel):
    business_name: str
    representative: str
    email: Optional[str] = ""
    phone: str
    address_line1: str
    city: str = ""
    state: str = ""
    zip: str = ""
    country: str = "USA"
    notes: Optional[str] = ""
    # Default rental setup (pre-filled when generating contracts/invoices)
    default_screens: int = 1
    default_screen_model: str = "MAV-30540S"
    default_day_price: float = 8.50
    default_term_months: int = 12
    default_deposit_per_screen: float = 250.00
    default_late_fee: float = 50.00
    default_nsf_fee: float = 85.00
    default_install_location: Optional[str] = ""  # Defaults to address_line1 if empty
    locations: Optional[List[ClientLocation]] = None

class ClientUpdate(BaseModel):
    business_name: Optional[str] = None
    representative: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    default_screens: Optional[int] = None
    default_screen_model: Optional[str] = None
    default_day_price: Optional[float] = None
    default_term_months: Optional[int] = None
    default_deposit_per_screen: Optional[float] = None
    default_late_fee: Optional[float] = None
    default_nsf_fee: Optional[float] = None
    default_install_location: Optional[str] = None

class ContractScreen(BaseModel):
    model: str = "MAV-30540S"
    units: int = 1
    location: str = ""  # installation address
    day_price: float = 8.50

class ContractCreate(BaseModel):
    client_id: str
    start_date: str  # YYYY-MM-DD
    term_months: int = 12  # 6, 12, 18, 24, or custom
    screens: List[ContractScreen]
    security_deposit_per_screen: float = 250.00
    late_fee_per_day: float = 50.00
    nsf_fee: float = 85.00
    additional_terms: Optional[str] = ""
    notes: Optional[str] = ""

class ContractUpdate(BaseModel):
    status: Optional[str] = None  # draft, active, expired, cancelled
    end_date: Optional[str] = None
    notes: Optional[str] = None
    lessor_signature: Optional[str] = None
    lessee_signature: Optional[str] = None
    signed_at: Optional[str] = None

class PaymentRecord(BaseModel):
    invoice_id: Optional[str] = None
    deposit_id: Optional[str] = None
    client_id: str
    amount: float
    method: str = "ACH"  # ACH, check, cash, card
    reference: Optional[str] = ""  # check number, etc
    date: Optional[str] = None
    notes: Optional[str] = ""

class ExpenseCreate(BaseModel):
    category: str  # rent, salaries, marketing, utilities, equipment, other
    description: str
    amount: float
    date: str
    vendor: Optional[str] = ""
    payment_method: Optional[str] = "ACH"
    notes: Optional[str] = ""

# ==================== HELPERS ====================
async def next_doc_number(db, prefix: str = "OH") -> str:
    """Auto-generate sequential document number (OH#######) starting at 5571009"""
    START = 5571009
    # Ensure counter is initialized with the starting value
    existing = await db.finance_counters.find_one({"_id": "main"})
    if not existing:
        await db.finance_counters.insert_one({"_id": "main", "value": START - 1})
    counter = await db.finance_counters.find_one_and_update(
        {"_id": "main"},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=True,
    )
    val = counter.get("value", START) if counter else START
    return f"{prefix}{val}"

def parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")

def add_months(d: datetime, months: int) -> datetime:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return d.replace(year=y, month=m, day=day)

def days_in_period(start: str, end: str) -> int:
    s = parse_date(start)
    e = parse_date(end)
    return (e - s).days + 1

def format_date_us(s: str) -> str:
    """YYYY-MM-DD → MM/DD/YY"""
    try:
        d = parse_date(s)
        return d.strftime("%m/%d/%y")
    except Exception:
        return s

def role_can_finance(user: dict) -> bool:
    return user.get("role") in ("superadmin", "admin", "accounting", "sales", "viewer", "technical")

def role_can_edit_finance(user: dict) -> bool:
    return user.get("role") in ("superadmin", "admin", "accounting", "sales")

def role_can_manage_clients(user: dict) -> bool:
    return user.get("role") in ("superadmin", "admin", "accounting", "sales")

# ==================== ROUTE FACTORY ====================
def create_finance_routes(db, get_current_user):
    """Bind routes to the main app's db & auth dependency"""

    async def require_finance(user: dict = Depends(get_current_user)):
        if not role_can_finance(user):
            raise HTTPException(403, "Finance module access required")
        return user

    async def require_finance_edit(user: dict = Depends(get_current_user)):
        if not role_can_edit_finance(user):
            raise HTTPException(403, "Finance edit access required")
        return user

    # ============ CLIENTS (CRM) ============
    @finance_router.get("/clients")
    async def list_clients(user: dict = Depends(require_finance)):
        items = await db.fin_clients.find().sort("created_at", -1).to_list(2000)
        for c in items:
            c.pop("_id", None)
            # attach quick balance/active info
            inv_open = await db.fin_invoices.count_documents({"client_id": c["id"], "status": {"$in": ["pending", "overdue"]}})
            c["open_invoices"] = inv_open
        return items

    @finance_router.post("/clients")
    async def create_client(data: ClientCreate, user: dict = Depends(require_finance_edit)):
        doc = data.dict()
        doc["id"] = str(uuid.uuid4())
        doc["status"] = "active"
        doc["created_at"] = datetime.utcnow().isoformat()
        doc["created_by"] = user.get("email", "")
        # Auto-create first location if none provided
        if not doc.get("locations"):
            loc_addr = (doc.get("default_install_location") or "").strip() or doc.get("address_line1", "")
            doc["locations"] = [{
                "id": str(uuid.uuid4()),
                "name": f"{doc.get('business_name')} — Main",
                "address_line1": loc_addr,
                "city": doc.get("city", ""),
                "state": doc.get("state", ""),
                "zip": doc.get("zip", ""),
                "phone": doc.get("phone", ""),
                "screens": [{
                    "id": str(uuid.uuid4()),
                    "model": doc.get("default_screen_model", "MAV-30540S"),
                    "units": int(doc.get("default_screens", 1)),
                    "day_price": float(doc.get("default_day_price", 8.50)),
                    "serial": "",
                    "notes": "",
                }],
                "status": "active",
            }]
        else:
            # Ensure IDs on incoming locations/screens
            for loc in doc["locations"]:
                loc["id"] = loc.get("id") or str(uuid.uuid4())
                for sc in loc.get("screens", []):
                    sc["id"] = sc.get("id") or str(uuid.uuid4())
        await db.fin_clients.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @finance_router.get("/clients/{client_id}")
    async def get_client(client_id: str, user: dict = Depends(require_finance)):
        c = await db.fin_clients.find_one({"id": client_id})
        if not c:
            raise HTTPException(404, "Client not found")
        c.pop("_id", None)
        contracts = await db.fin_contracts.find({"client_id": client_id}).sort("created_at", -1).to_list(100)
        invoices = await db.fin_invoices.find({"client_id": client_id}).sort("issue_date", -1).to_list(200)
        deposits = await db.fin_deposits.find({"client_id": client_id}).sort("created_at", -1).to_list(50)
        payments = await db.fin_payments.find({"client_id": client_id}).sort("date", -1).to_list(200)
        for arr in (contracts, invoices, deposits, payments):
            for d in arr:
                d.pop("_id", None)
        # balance
        total_invoiced = sum(i.get("total", 0) for i in invoices)
        total_paid = sum(p.get("amount", 0) for p in payments if not p.get("deposit_id"))
        balance = total_invoiced - total_paid
        c["contracts"] = contracts
        c["invoices"] = invoices
        c["deposits"] = deposits
        c["payments"] = payments
        c["balance"] = balance
        c["total_invoiced"] = total_invoiced
        c["total_paid"] = total_paid
        return c

    @finance_router.put("/clients/{client_id}")
    async def update_client(client_id: str, data: ClientUpdate, user: dict = Depends(require_finance_edit)):
        upd = {k: v for k, v in data.dict().items() if v is not None}
        if not upd:
            return {"ok": True}
        upd["updated_at"] = datetime.utcnow().isoformat()
        await db.fin_clients.update_one({"id": client_id}, {"$set": upd})
        return {"ok": True}

    @finance_router.delete("/clients/{client_id}")
    async def delete_client(client_id: str, user: dict = Depends(require_finance_edit)):
        # archive instead of hard delete
        await db.fin_clients.update_one({"id": client_id}, {"$set": {"status": "archived"}})
        return {"ok": True}

    # ============ LOCATIONS & SCREENS ============
    @finance_router.post("/clients/{client_id}/locations")
    async def add_location(client_id: str, data: ClientLocation, user: dict = Depends(require_finance_edit)):
        cl = await db.fin_clients.find_one({"id": client_id})
        if not cl:
            raise HTTPException(404, "Client not found")
        loc = data.dict()
        loc["id"] = str(uuid.uuid4())
        for sc in loc.get("screens", []):
            sc["id"] = sc.get("id") or str(uuid.uuid4())
        await db.fin_clients.update_one({"id": client_id}, {"$push": {"locations": loc}})
        return loc

    @finance_router.put("/clients/{client_id}/locations/{location_id}")
    async def update_location(client_id: str, location_id: str, payload: dict,
                              user: dict = Depends(require_finance_edit)):
        allowed = {"name","address_line1","city","state","zip","phone","status"}
        sets = {f"locations.$.{k}": v for k, v in payload.items() if k in allowed and v is not None}
        if sets:
            await db.fin_clients.update_one(
                {"id": client_id, "locations.id": location_id},
                {"$set": sets},
            )
        return {"ok": True}

    @finance_router.delete("/clients/{client_id}/locations/{location_id}")
    async def delete_location(client_id: str, location_id: str, user: dict = Depends(require_finance_edit)):
        await db.fin_clients.update_one(
            {"id": client_id},
            {"$pull": {"locations": {"id": location_id}}},
        )
        return {"ok": True}

    @finance_router.post("/clients/{client_id}/locations/{location_id}/screens")
    async def add_screen(client_id: str, location_id: str, data: LocationScreen,
                          user: dict = Depends(require_finance_edit)):
        sc = data.dict()
        sc["id"] = str(uuid.uuid4())
        r = await db.fin_clients.update_one(
            {"id": client_id, "locations.id": location_id},
            {"$push": {"locations.$.screens": sc}},
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Location not found")
        return sc

    @finance_router.put("/clients/{client_id}/locations/{location_id}/screens/{screen_id}")
    async def update_screen(client_id: str, location_id: str, screen_id: str, payload: dict,
                            user: dict = Depends(require_finance_edit)):
        # Need to update nested array — fetch, modify, save
        cl = await db.fin_clients.find_one({"id": client_id})
        if not cl:
            raise HTTPException(404, "Client not found")
        for loc in cl.get("locations", []):
            if loc.get("id") == location_id:
                for sc in loc.get("screens", []):
                    if sc.get("id") == screen_id:
                        for k in ("model","units","day_price","serial","notes"):
                            if k in payload and payload[k] is not None:
                                sc[k] = payload[k]
                await db.fin_clients.update_one({"id": client_id}, {"$set": {"locations": cl["locations"]}})
                return {"ok": True}
        raise HTTPException(404, "Screen not found")

    @finance_router.delete("/clients/{client_id}/locations/{location_id}/screens/{screen_id}")
    async def delete_screen(client_id: str, location_id: str, screen_id: str,
                            user: dict = Depends(require_finance_edit)):
        await db.fin_clients.update_one(
            {"id": client_id, "locations.id": location_id},
            {"$pull": {"locations.$.screens": {"id": screen_id}}},
        )
        return {"ok": True}

    # ============ CONTRACTS ============
    @finance_router.get("/contracts")
    async def list_contracts(client_id: Optional[str] = None, user: dict = Depends(require_finance)):
        q = {"client_id": client_id} if client_id else {}
        items = await db.fin_contracts.find(q).sort("created_at", -1).to_list(500)
        # join client info
        ids = list({i.get("client_id") for i in items})
        clients = {c["id"]: c for c in await db.fin_clients.find({"id": {"$in": ids}}).to_list(500)}
        for c in items:
            c.pop("_id", None)
            cl = clients.get(c.get("client_id"))
            c["client_name"] = cl.get("business_name") if cl else "—"
        return items

    @finance_router.post("/contracts")
    async def create_contract(data: ContractCreate, user: dict = Depends(require_finance_edit)):
        client = await db.fin_clients.find_one({"id": data.client_id})
        if not client:
            raise HTTPException(404, "Client not found")
        start = parse_date(data.start_date)
        end = add_months(start, data.term_months)
        total_screens = sum(s.units for s in data.screens)
        monthly_total = 0.0
        for s in data.screens:
            monthly_total += s.units * s.day_price * 30  # baseline 30 days
        security_deposit = total_screens * data.security_deposit_per_screen
        contract_no = await next_doc_number(db, "MV-C-")
        doc = {
            "id": str(uuid.uuid4()),
            "contract_number": contract_no,
            "client_id": data.client_id,
            "start_date": data.start_date,
            "end_date": end.strftime("%Y-%m-%d"),
            "term_months": data.term_months,
            "screens": [s.dict() for s in data.screens],
            "total_units": total_screens,
            "monthly_total": round(monthly_total, 2),
            "security_deposit_per_screen": data.security_deposit_per_screen,
            "security_deposit": round(security_deposit, 2),
            "late_fee_per_day": data.late_fee_per_day,
            "nsf_fee": data.nsf_fee,
            "additional_terms": data.additional_terms or "",
            "notes": data.notes or "",
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "created_by": user.get("email", ""),
        }
        await db.fin_contracts.insert_one(doc)

        # Auto-create deposit receipt
        deposit_no = await next_doc_number(db)
        dep = {
            "id": str(uuid.uuid4()),
            "receipt_number": deposit_no,
            "contract_id": doc["id"],
            "client_id": data.client_id,
            "amount": round(security_deposit, 2),
            "tax": 0.0,
            "total": round(security_deposit, 2),
            "screens": [s.dict() for s in data.screens],
            "status": "pending",
            "issue_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "created_at": datetime.utcnow().isoformat(),
        }
        await db.fin_deposits.insert_one(dep)
        doc.pop("_id", None)
        dep.pop("_id", None)
        return {"contract": doc, "deposit": dep}

    @finance_router.post("/clients/{client_id}/quick-contract")
    async def quick_contract(client_id: str, payload: dict = None,
                              user: dict = Depends(require_finance_edit)):
        """One-click contract generation using ALL client locations × screens."""
        cl = await db.fin_clients.find_one({"id": client_id})
        if not cl:
            raise HTTPException(404, "Client not found")
        payload = payload or {}
        start = payload.get("start_date") or datetime.utcnow().strftime("%Y-%m-%d")
        term = int(payload.get("term_months") or cl.get("default_term_months", 12))
        deposit_per = float(payload.get("deposit_per_screen") or cl.get("default_deposit_per_screen", 250))

        # Build screens list from ALL active locations
        screens = []
        for loc in cl.get("locations", []):
            if loc.get("status", "active") != "active":
                continue
            loc_addr = ", ".join(filter(None, [
                loc.get("address_line1", ""),
                loc.get("city", ""),
                loc.get("state", ""),
                loc.get("zip", ""),
            ]))
            for sc in loc.get("screens", []):
                screens.append(ContractScreen(
                    model=sc.get("model", "MAV-30540S"),
                    units=int(sc.get("units", 1)),
                    location=f"{loc.get('name','')} — {loc_addr}".strip(' —'),
                    day_price=float(sc.get("day_price", 8.50)),
                ))

        # Fallback to defaults if no locations exist
        if not screens:
            screens.append(ContractScreen(
                model=cl.get("default_screen_model", "MAV-30540S"),
                units=int(cl.get("default_screens", 1)),
                location=(cl.get("default_install_location") or cl.get("address_line1", "")),
                day_price=float(cl.get("default_day_price", 8.50)),
            ))

        start_d = parse_date(start)
        end_d = add_months(start_d, term)
        total_screens = sum(s.units for s in screens)
        monthly_total = sum(s.units * s.day_price * 30 for s in screens)
        security_deposit = total_screens * deposit_per
        contract_no = await next_doc_number(db, "MV-C-")
        doc = {
            "id": str(uuid.uuid4()),
            "contract_number": contract_no,
            "client_id": client_id,
            "start_date": start,
            "end_date": end_d.strftime("%Y-%m-%d"),
            "term_months": term,
            "screens": [s.dict() for s in screens],
            "total_units": total_screens,
            "monthly_total": round(monthly_total, 2),
            "security_deposit_per_screen": deposit_per,
            "security_deposit": round(security_deposit, 2),
            "late_fee_per_day": float(cl.get("default_late_fee", 50)),
            "nsf_fee": float(cl.get("default_nsf_fee", 85)),
            "additional_terms": "",
            "notes": "",
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "created_by": user.get("email", ""),
        }
        await db.fin_contracts.insert_one(doc)
        deposit_no = await next_doc_number(db)
        dep = {
            "id": str(uuid.uuid4()),
            "receipt_number": deposit_no,
            "contract_id": doc["id"],
            "client_id": client_id,
            "amount": round(security_deposit, 2),
            "tax": 0.0,
            "total": round(security_deposit, 2),
            "screens": [s.dict() for s in screens],
            "status": "pending",
            "issue_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "created_at": datetime.utcnow().isoformat(),
        }
        await db.fin_deposits.insert_one(dep)
        doc.pop("_id", None); dep.pop("_id", None)
        return {"contract": doc, "deposit": dep}

    @finance_router.post("/contracts/{contract_id}/quick-invoice")
    async def quick_invoice(contract_id: str, payload: dict = None,
                            user: dict = Depends(require_finance_edit)):
        """One-click invoice for a contract — defaults to current month."""
        ct = await db.fin_contracts.find_one({"id": contract_id})
        if not ct:
            raise HTTPException(404, "Contract not found")
        payload = payload or {}
        now = datetime.utcnow()
        y = int(payload.get("year") or now.year)
        m = int(payload.get("month") or now.month)
        period_start = date(y, m, 1)
        period_end = date(y, m, monthrange(y, m)[1])
        days = (period_end - period_start).days + 1
        # Check duplicate
        existing = await db.fin_invoices.find_one({"contract_id": contract_id, "period_start": period_start.isoformat()})
        if existing and existing.get("status") != "cancelled":
            existing.pop("_id", None)
            return {"invoice": existing, "duplicate": True}
        items = []
        total = 0.0
        for idx, s in enumerate(ct.get("screens", []), 1):
            line_total = s["units"] * s["day_price"] * days
            items.append({
                "line_no": f"{idx:02d}",
                "description": f"LED Ultra Brightness {s.get('model','MAV-30540S')}",
                "day_price": s["day_price"],
                "days": days,
                "units": s["units"],
                "total": round(line_total, 2),
            })
            total += line_total
        inv_no = await next_doc_number(db)
        inv = {
            "id": str(uuid.uuid4()),
            "invoice_number": inv_no,
            "contract_id": contract_id,
            "client_id": ct["client_id"],
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "issue_date": period_start.isoformat(),
            "due_date": period_start.isoformat(),
            "items": items,
            "subtotal": round(total, 2),
            "tax": 0.0,
            "total": round(total, 2),
            "amount_paid": 0.0,
            "balance": round(total, 2),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "auto_generated": True,
        }
        await db.fin_invoices.insert_one(inv)
        inv.pop("_id", None)
        return {"invoice": inv, "duplicate": False}

    @finance_router.get("/contracts/{contract_id}")
    async def get_contract(contract_id: str, user: dict = Depends(require_finance)):
        c = await db.fin_contracts.find_one({"id": contract_id})
        if not c:
            raise HTTPException(404, "Contract not found")
        c.pop("_id", None)
        return c

    @finance_router.put("/contracts/{contract_id}")
    async def update_contract(contract_id: str, data: ContractUpdate, user: dict = Depends(require_finance_edit)):
        upd = {k: v for k, v in data.dict().items() if v is not None}
        if not upd:
            return {"ok": True}
        upd["updated_at"] = datetime.utcnow().isoformat()
        await db.fin_contracts.update_one({"id": contract_id}, {"$set": upd})
        return {"ok": True}

    @finance_router.delete("/contracts/{contract_id}")
    async def delete_contract(contract_id: str, user: dict = Depends(require_finance_edit)):
        await db.fin_contracts.delete_one({"id": contract_id})
        return {"ok": True}

    # ============ INVOICES ============
    @finance_router.get("/invoices")
    async def list_invoices(status: Optional[str] = None, client_id: Optional[str] = None,
                            user: dict = Depends(require_finance)):
        q = {}
        if status: q["status"] = status
        if client_id: q["client_id"] = client_id
        items = await db.fin_invoices.find(q).sort("issue_date", -1).to_list(1000)
        ids = list({i.get("client_id") for i in items})
        clients = {c["id"]: c for c in await db.fin_clients.find({"id": {"$in": ids}}).to_list(1000)}
        today = datetime.utcnow().date().isoformat()
        for i in items:
            i.pop("_id", None)
            cl = clients.get(i.get("client_id"))
            i["client_name"] = cl.get("business_name") if cl else "—"
            # auto-mark overdue
            if i.get("status") == "pending" and i.get("due_date") and i["due_date"] < today:
                await db.fin_invoices.update_one({"id": i["id"]}, {"$set": {"status": "overdue"}})
                i["status"] = "overdue"
        return items

    @finance_router.post("/invoices/generate-monthly")
    async def generate_monthly_invoices(period_year: Optional[int] = None, period_month: Optional[int] = None,
                                         user: dict = Depends(require_finance_edit)):
        """Generate invoices for all active clients for the given month. Defaults to current month."""
        now = datetime.utcnow()
        y = period_year or now.year
        m = period_month or now.month
        period_start = date(y, m, 1)
        period_end = date(y, m, monthrange(y, m)[1])
        days = (period_end - period_start).days + 1

        created = []
        contracts = await db.fin_contracts.find({"status": "active"}).to_list(2000)
        for ct in contracts:
            # Check contract is in effect for this period
            cs = parse_date(ct["start_date"]).date()
            ce = parse_date(ct["end_date"]).date()
            if cs > period_end or ce < period_start:
                continue
            # Avoid duplicate for this period
            existing = await db.fin_invoices.find_one({
                "contract_id": ct["id"],
                "period_start": period_start.isoformat(),
            })
            if existing:
                continue
            # Build line items
            items = []
            total = 0.0
            for idx, s in enumerate(ct.get("screens", []), 1):
                line_total = s["units"] * s["day_price"] * days
                items.append({
                    "line_no": f"{idx:02d}",
                    "description": f"LED Ultra Brightness {s.get('model','MAV-30540S')}",
                    "day_price": s["day_price"],
                    "days": days,
                    "units": s["units"],
                    "total": round(line_total, 2),
                })
                total += line_total
            inv_no = await next_doc_number(db)
            inv = {
                "id": str(uuid.uuid4()),
                "invoice_number": inv_no,
                "contract_id": ct["id"],
                "client_id": ct["client_id"],
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "issue_date": period_start.isoformat(),
                "due_date": period_start.isoformat(),
                "items": items,
                "subtotal": round(total, 2),
                "tax": 0.0,
                "total": round(total, 2),
                "amount_paid": 0.0,
                "balance": round(total, 2),
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
                "auto_generated": True,
            }
            await db.fin_invoices.insert_one(inv)
            inv.pop("_id", None)
            created.append(inv)
        return {"created": len(created), "period": f"{y}-{m:02d}", "invoices": created}

    @finance_router.post("/invoices/manual")
    async def create_manual_invoice(payload: dict, user: dict = Depends(require_finance_edit)):
        """Create an invoice manually for a client/contract."""
        client_id = payload.get("client_id")
        contract_id = payload.get("contract_id")
        if not client_id:
            raise HTTPException(400, "client_id required")
        items = payload.get("items", [])
        subtotal = sum(i.get("total", 0) for i in items)
        tax = float(payload.get("tax", 0))
        total = subtotal + tax
        inv_no = await next_doc_number(db)
        inv = {
            "id": str(uuid.uuid4()),
            "invoice_number": inv_no,
            "contract_id": contract_id,
            "client_id": client_id,
            "period_start": payload.get("period_start"),
            "period_end": payload.get("period_end"),
            "issue_date": payload.get("issue_date", datetime.utcnow().strftime("%Y-%m-%d")),
            "due_date": payload.get("due_date", datetime.utcnow().strftime("%Y-%m-%d")),
            "items": items,
            "subtotal": round(subtotal, 2),
            "tax": round(tax, 2),
            "total": round(total, 2),
            "amount_paid": 0.0,
            "balance": round(total, 2),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "auto_generated": False,
        }
        await db.fin_invoices.insert_one(inv)
        inv.pop("_id", None)
        return inv

    @finance_router.get("/invoices/{invoice_id}")
    async def get_invoice(invoice_id: str, user: dict = Depends(require_finance)):
        i = await db.fin_invoices.find_one({"id": invoice_id})
        if not i:
            raise HTTPException(404, "Invoice not found")
        i.pop("_id", None)
        return i

    @finance_router.put("/invoices/{invoice_id}")
    async def update_invoice(invoice_id: str, payload: dict, user: dict = Depends(require_finance_edit)):
        allowed = {"status", "due_date", "notes", "tax"}
        upd = {k: v for k, v in payload.items() if k in allowed}
        if "tax" in upd:
            inv = await db.fin_invoices.find_one({"id": invoice_id})
            if inv:
                upd["total"] = round(inv.get("subtotal", 0) + float(upd["tax"]), 2)
                upd["balance"] = round(upd["total"] - inv.get("amount_paid", 0), 2)
        if upd:
            upd["updated_at"] = datetime.utcnow().isoformat()
            await db.fin_invoices.update_one({"id": invoice_id}, {"$set": upd})
        return {"ok": True}

    @finance_router.delete("/invoices/{invoice_id}")
    async def delete_invoice(invoice_id: str, user: dict = Depends(require_finance_edit)):
        await db.fin_invoices.update_one({"id": invoice_id}, {"$set": {"status": "cancelled"}})
        return {"ok": True}

    # ============ DEPOSITS ============
    @finance_router.get("/deposits")
    async def list_deposits(client_id: Optional[str] = None, user: dict = Depends(require_finance)):
        q = {"client_id": client_id} if client_id else {}
        items = await db.fin_deposits.find(q).sort("created_at", -1).to_list(500)
        ids = list({i.get("client_id") for i in items})
        clients = {c["id"]: c for c in await db.fin_clients.find({"id": {"$in": ids}}).to_list(500)}
        for d in items:
            d.pop("_id", None)
            cl = clients.get(d.get("client_id"))
            d["client_name"] = cl.get("business_name") if cl else "—"
        return items

    @finance_router.get("/deposits/{deposit_id}")
    async def get_deposit(deposit_id: str, user: dict = Depends(require_finance)):
        d = await db.fin_deposits.find_one({"id": deposit_id})
        if not d:
            raise HTTPException(404, "Deposit not found")
        d.pop("_id", None)
        return d

    @finance_router.put("/deposits/{deposit_id}")
    async def update_deposit(deposit_id: str, payload: dict, user: dict = Depends(require_finance_edit)):
        allowed = {"status", "notes"}
        upd = {k: v for k, v in payload.items() if k in allowed}
        if upd:
            await db.fin_deposits.update_one({"id": deposit_id}, {"$set": upd})
        return {"ok": True}

    # ============ PAYMENTS ============
    @finance_router.get("/payments")
    async def list_payments(client_id: Optional[str] = None, user: dict = Depends(require_finance)):
        q = {"client_id": client_id} if client_id else {}
        items = await db.fin_payments.find(q).sort("date", -1).to_list(2000)
        ids = list({i.get("client_id") for i in items})
        clients = {c["id"]: c for c in await db.fin_clients.find({"id": {"$in": ids}}).to_list(2000)}
        for p in items:
            p.pop("_id", None)
            cl = clients.get(p.get("client_id"))
            p["client_name"] = cl.get("business_name") if cl else "—"
        return items

    @finance_router.post("/payments")
    async def record_payment(data: PaymentRecord, user: dict = Depends(require_finance_edit)):
        pay = data.dict()
        pay["id"] = str(uuid.uuid4())
        pay["date"] = pay.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
        pay["created_at"] = datetime.utcnow().isoformat()
        pay["created_by"] = user.get("email", "")
        await db.fin_payments.insert_one(pay)

        # Update related invoice / deposit
        if pay.get("invoice_id"):
            inv = await db.fin_invoices.find_one({"id": pay["invoice_id"]})
            if inv:
                paid = inv.get("amount_paid", 0) + data.amount
                bal = inv.get("total", 0) - paid
                status = "paid" if bal <= 0.01 else inv.get("status", "pending")
                await db.fin_invoices.update_one(
                    {"id": pay["invoice_id"]},
                    {"$set": {"amount_paid": round(paid, 2), "balance": round(bal, 2), "status": status}},
                )
        if pay.get("deposit_id"):
            await db.fin_deposits.update_one({"id": pay["deposit_id"]}, {"$set": {"status": "received", "received_at": pay["date"]}})

        pay.pop("_id", None)
        return pay

    @finance_router.delete("/payments/{payment_id}")
    async def delete_payment(payment_id: str, user: dict = Depends(require_finance_edit)):
        p = await db.fin_payments.find_one({"id": payment_id})
        if not p:
            raise HTTPException(404, "Payment not found")
        # Revert invoice balance
        if p.get("invoice_id"):
            inv = await db.fin_invoices.find_one({"id": p["invoice_id"]})
            if inv:
                paid = max(0, inv.get("amount_paid", 0) - p.get("amount", 0))
                bal = inv.get("total", 0) - paid
                status = "paid" if bal <= 0.01 else ("overdue" if inv.get("due_date", "") < datetime.utcnow().date().isoformat() else "pending")
                await db.fin_invoices.update_one(
                    {"id": p["invoice_id"]},
                    {"$set": {"amount_paid": round(paid, 2), "balance": round(bal, 2), "status": status}},
                )
        await db.fin_payments.delete_one({"id": payment_id})
        return {"ok": True}

    # ============ EXPENSES ============
    @finance_router.get("/expenses")
    async def list_expenses(year: Optional[int] = None, month: Optional[int] = None,
                            user: dict = Depends(require_finance)):
        q = {}
        if year and month:
            d0 = date(year, month, 1).isoformat()
            d1 = date(year, month, monthrange(year, month)[1]).isoformat()
            q = {"date": {"$gte": d0, "$lte": d1}}
        items = await db.fin_expenses.find(q).sort("date", -1).to_list(1000)
        for e in items:
            e.pop("_id", None)
        return items

    @finance_router.post("/expenses")
    async def create_expense(data: ExpenseCreate, user: dict = Depends(require_finance_edit)):
        doc = data.dict()
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = datetime.utcnow().isoformat()
        doc["created_by"] = user.get("email", "")
        await db.fin_expenses.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @finance_router.delete("/expenses/{expense_id}")
    async def delete_expense(expense_id: str, user: dict = Depends(require_finance_edit)):
        await db.fin_expenses.delete_one({"id": expense_id})
        return {"ok": True}

    # ============ FINANCIAL DASHBOARD ============
    @finance_router.get("/dashboard")
    async def finance_dashboard(user: dict = Depends(require_finance)):
        now = datetime.utcnow()
        y, m = now.year, now.month
        m_start = date(y, m, 1).isoformat()
        m_end = date(y, m, monthrange(y, m)[1]).isoformat()
        today = now.date().isoformat()

        # Auto-mark overdue
        await db.fin_invoices.update_many(
            {"status": "pending", "due_date": {"$lt": today}},
            {"$set": {"status": "overdue"}},
        )

        total_clients = await db.fin_clients.count_documents({"status": "active"})
        total_contracts = await db.fin_contracts.count_documents({"status": "active"})
        # monthly billed
        monthly_invs = await db.fin_invoices.find({"issue_date": {"$gte": m_start, "$lte": m_end}}).to_list(2000)
        billed_this_month = sum(i.get("total", 0) for i in monthly_invs)
        paid_this_month_pipeline = [
            {"$match": {"date": {"$gte": m_start, "$lte": m_end}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        agg = await db.fin_payments.aggregate(paid_this_month_pipeline).to_list(1)
        collected_this_month = agg[0]["total"] if agg else 0
        # overdue
        overdue = await db.fin_invoices.find({"status": "overdue"}).to_list(2000)
        overdue_total = sum(i.get("balance", i.get("total", 0)) for i in overdue)
        overdue_count = len(overdue)
        # pending
        pending = await db.fin_invoices.find({"status": "pending"}).to_list(2000)
        pending_total = sum(i.get("balance", i.get("total", 0)) for i in pending)
        # AR (total receivable)
        ar_total = overdue_total + pending_total
        # expenses
        exp_pipeline = [
            {"$match": {"date": {"$gte": m_start, "$lte": m_end}}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
        ]
        expenses = await db.fin_expenses.aggregate(exp_pipeline).to_list(50)
        expenses_total = sum(e["total"] for e in expenses)
        # Last 12 months cashflow (revenue collected - expenses)
        cashflow = []
        for off in range(11, -1, -1):
            # compute month offset
            yy = y; mm = m - off
            while mm <= 0:
                mm += 12; yy -= 1
            s = date(yy, mm, 1).isoformat()
            e = date(yy, mm, monthrange(yy, mm)[1]).isoformat()
            r_agg = await db.fin_payments.aggregate([
                {"$match": {"date": {"$gte": s, "$lte": e}}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
            ]).to_list(1)
            ex_agg = await db.fin_expenses.aggregate([
                {"$match": {"date": {"$gte": s, "$lte": e}}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
            ]).to_list(1)
            cashflow.append({
                "month": f"{yy}-{mm:02d}",
                "revenue": round(r_agg[0]["total"] if r_agg else 0, 2),
                "expenses": round(ex_agg[0]["total"] if ex_agg else 0, 2),
            })

        # Recent invoices
        recent_invs = await db.fin_invoices.find().sort("issue_date", -1).limit(8).to_list(8)
        ids = list({i.get("client_id") for i in recent_invs})
        client_map = {c["id"]: c.get("business_name") for c in await db.fin_clients.find({"id": {"$in": ids}}).to_list(50)}
        for ri in recent_invs:
            ri.pop("_id", None)
            ri["client_name"] = client_map.get(ri.get("client_id"), "—")

        return {
            "stats": {
                "total_clients": total_clients,
                "total_contracts": total_contracts,
                "billed_this_month": round(billed_this_month, 2),
                "collected_this_month": round(collected_this_month, 2),
                "pending_total": round(pending_total, 2),
                "overdue_total": round(overdue_total, 2),
                "overdue_count": overdue_count,
                "ar_total": round(ar_total, 2),
                "expenses_total": round(expenses_total, 2),
                "net_profit": round(collected_this_month - expenses_total, 2),
            },
            "cashflow": cashflow,
            "expense_breakdown": [{"category": e["_id"], "total": round(e["total"], 2)} for e in expenses],
            "recent_invoices": recent_invs,
            "period": f"{y}-{m:02d}",
        }

    # ============ DOCUMENT TEMPLATES (HTML PRINTABLE) ============
    @finance_router.get("/contracts/{contract_id}/render", response_class=HTMLResponse)
    async def render_contract(contract_id: str):
        c = await db.fin_contracts.find_one({"id": contract_id})
        if not c:
            raise HTTPException(404, "Contract not found")
        client = await db.fin_clients.find_one({"id": c["client_id"]})
        return HTMLResponse(render_contract_html(c, client or {}))

    @finance_router.get("/invoices/{invoice_id}/render", response_class=HTMLResponse)
    async def render_invoice(invoice_id: str):
        i = await db.fin_invoices.find_one({"id": invoice_id})
        if not i:
            raise HTTPException(404, "Invoice not found")
        client = await db.fin_clients.find_one({"id": i["client_id"]})
        return HTMLResponse(render_invoice_html(i, client or {}))

    @finance_router.get("/deposits/{deposit_id}/render", response_class=HTMLResponse)
    async def render_deposit(deposit_id: str):
        d = await db.fin_deposits.find_one({"id": deposit_id})
        if not d:
            raise HTTPException(404, "Deposit not found")
        client = await db.fin_clients.find_one({"id": d["client_id"]})
        return HTMLResponse(render_deposit_html(d, client or {}))

    # ============ PDF GENERATION (ReportLab) ============
    @finance_router.get("/contracts/{contract_id}/pdf")
    async def pdf_contract(contract_id: str):
        from finance_pdf import generate_contract_pdf
        c = await db.fin_contracts.find_one({"id": contract_id})
        if not c:
            raise HTTPException(404, "Contract not found")
        client = await db.fin_clients.find_one({"id": c["client_id"]}) or {}
        pdf = generate_contract_pdf(c, client)
        filename = f"Contract_{c.get('contract_number','')}.pdf"
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{filename}"'})

    @finance_router.get("/invoices/{invoice_id}/pdf")
    async def pdf_invoice(invoice_id: str):
        from finance_pdf import generate_invoice_pdf
        i = await db.fin_invoices.find_one({"id": invoice_id})
        if not i:
            raise HTTPException(404, "Invoice not found")
        client = await db.fin_clients.find_one({"id": i["client_id"]}) or {}
        pdf = generate_invoice_pdf(i, client)
        filename = f"Invoice_{i.get('invoice_number','')}.pdf"
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{filename}"'})

    @finance_router.get("/deposits/{deposit_id}/pdf")
    async def pdf_deposit(deposit_id: str):
        from finance_pdf import generate_deposit_pdf
        d = await db.fin_deposits.find_one({"id": deposit_id})
        if not d:
            raise HTTPException(404, "Deposit not found")
        client = await db.fin_clients.find_one({"id": d["client_id"]}) or {}
        pdf = generate_deposit_pdf(d, client)
        filename = f"Deposit_{d.get('receipt_number','')}.pdf"
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{filename}"'})

    return finance_router


# ==================== HTML TEMPLATES ====================
DOC_CSS = """
*{margin:0;padding:0;box-sizing:border-box;font-family:'Helvetica','Arial',sans-serif}
body{background:#f3f4f6;padding:30px 20px;color:#111}
.page{max-width:850px;margin:0 auto;background:#fff;padding:48px 60px;box-shadow:0 4px 20px rgba(0,0,0,.08);min-height:1100px;position:relative}
.hdr{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:3px solid #2563eb;padding-bottom:22px;margin-bottom:30px}
.brand{display:flex;align-items:center;gap:14px}
.brand img{width:64px;height:64px;object-fit:contain}
.brand h1{font-size:24px;font-weight:800;color:#0f172a;letter-spacing:-.5px}
.brand .tag{font-size:10px;color:#2563eb;letter-spacing:2px;font-weight:700;margin-top:2px}
.hdr .co{text-align:right;font-size:11px;line-height:1.6;color:#475569}
.title-block{margin-bottom:28px}
.title{font-size:26px;font-weight:800;color:#0f172a;letter-spacing:-.4px}
.subtitle{font-size:13px;color:#64748b;margin-top:4px}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px}
.box{background:#f8fafc;border-radius:8px;padding:16px 18px;border-left:3px solid #2563eb}
.box-lbl{font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.box-val{font-size:14px;font-weight:600;color:#1e293b;line-height:1.5}
.box .name{font-size:16px;font-weight:700;color:#0f172a}
table{width:100%;border-collapse:collapse;margin:20px 0}
table th{background:#0f172a;color:#fff;padding:11px 12px;font-size:11px;text-align:left;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
table th.r,table td.r{text-align:right}
table th.c,table td.c{text-align:center}
table td{padding:13px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#334155}
.totals{display:flex;justify-content:flex-end;margin-top:12px}
.totals-box{width:280px}
.tr{display:flex;justify-content:space-between;padding:8px 16px;font-size:13px;color:#475569}
.tr.total{font-size:18px;font-weight:800;color:#0f172a;background:#dbeafe;border-top:2px solid #2563eb;margin-top:6px;padding:12px 16px}
.pay-info{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:16px;margin-top:24px;font-size:12px;color:#1e3a8a}
.pay-info .lbl{font-weight:700;color:#1e40af}
.pay-info-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px}
.terms{margin-top:24px;padding-top:20px;border-top:1px solid #e2e8f0;font-size:11px;color:#64748b;line-height:1.6}
.terms h3{font-size:12px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}
.footer{position:absolute;bottom:30px;left:60px;right:60px;text-align:center;font-size:11px;color:#94a3b8;padding-top:14px;border-top:1px solid #e2e8f0}
.thanks{text-align:center;font-size:15px;font-weight:700;color:#2563eb;margin-top:24px}
.clause{margin-bottom:14px;font-size:11px;line-height:1.6;color:#334155;text-align:justify}
.clause strong{color:#0f172a}
.sig-block{display:grid;grid-template-columns:1fr 1fr;gap:30px;margin-top:40px}
.sig{border-top:1px solid #94a3b8;padding-top:8px}
.sig .role{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px}
.sig .name{font-size:13px;font-weight:700;color:#0f172a}
.sig .meta{font-size:11px;color:#64748b;margin-top:2px}
.badge{display:inline-block;padding:3px 10px;font-size:10px;font-weight:700;border-radius:4px;letter-spacing:.5px;text-transform:uppercase}
.badge-pending{background:#fef3c7;color:#92400e}
.badge-paid{background:#d1fae5;color:#065f46}
.badge-overdue{background:#fee2e2;color:#991b1b}
.badge-cancelled{background:#e5e7eb;color:#374151}
@media print {
  body{background:#fff;padding:0}
  .page{box-shadow:none;padding:30px 40px;min-height:auto}
  .no-print{display:none !important}
}
.actions{position:fixed;top:20px;right:20px;display:flex;gap:8px;z-index:100}
.actions button{padding:9px 16px;background:#2563eb;color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:600;font-size:13px;box-shadow:0 4px 12px rgba(37,99,235,.3)}
.actions button:hover{background:#1d4ed8}
"""


def doc_header_html():
    return f"""
    <div class="hdr">
      <div class="brand">
        <img src="{COMPANY['logo_url']}" alt="MediAd View">
        <div>
          <h1>MediAd View</h1>
          <div class="tag">{COMPANY['tagline']}</div>
        </div>
      </div>
      <div class="co">
        {COMPANY['address_line1']}<br>
        {COMPANY['address_line2']}<br>
        {COMPANY['phone_1']}<br>
        {COMPANY['phone_2']}
      </div>
    </div>
    """


def doc_payment_info_html():
    return f"""
    <div class="pay-info">
      <div class="lbl">{COMPANY['name']} — Payment Information</div>
      <div class="pay-info-grid">
        <div><span class="lbl">Bank:</span> {COMPANY['bank_name']}</div>
        <div><span class="lbl">Account #:</span> {COMPANY['account_number']}</div>
        <div><span class="lbl">Routing:</span> {COMPANY['routing']}</div>
        <div><span class="lbl">Method:</span> ACH transfers &amp; deposits</div>
      </div>
    </div>
    """


def doc_actions_html():
    return """
    <div class="actions no-print">
      <button onclick="window.print()">Print / Save PDF</button>
    </div>
    """


def render_invoice_html(inv: dict, client: dict) -> str:
    items_rows = "".join([
        f"""<tr>
          <td class="c">{it['line_no']}</td>
          <td>{it['description']}</td>
          <td class="r">${it['day_price']:.2f}</td>
          <td class="c">{it['days']}</td>
          <td class="r">${it['total']:.2f}</td>
        </tr>"""
        for it in inv.get("items", [])
    ])
    status = inv.get("status", "pending")
    badge_cls = f"badge-{status}"
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Invoice {inv.get('invoice_number','')}</title>
<style>{DOC_CSS}</style></head><body>
{doc_actions_html()}
<div class="page">
  {doc_header_html()}
  <div class="title-block">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div><div class="title">INVOICE</div><div class="subtitle">Period: {format_date_us(inv.get('period_start',''))} – {format_date_us(inv.get('period_end',''))}</div></div>
      <span class="badge {badge_cls}">{status}</span>
    </div>
  </div>
  <div class="row2">
    <div class="box">
      <div class="box-lbl">Invoice To</div>
      <div class="box-val">
        <div class="name">{client.get('business_name','—')}</div>
        {client.get('address_line1','')}<br>
        {client.get('city','')} {client.get('state','')} {client.get('zip','')}<br>
        {client.get('phone','')}
      </div>
    </div>
    <div class="box" style="text-align:right">
      <div class="box-lbl">Invoice Details</div>
      <div class="box-val">
        <div><strong>Invoice #:</strong> {inv.get('invoice_number','')}</div>
        <div><strong>Issue Date:</strong> {format_date_us(inv.get('issue_date',''))}</div>
        <div><strong>Due Date:</strong> {format_date_us(inv.get('due_date',''))}</div>
      </div>
    </div>
  </div>
  <table>
    <thead><tr>
      <th class="c" style="width:50px">LED</th>
      <th>ITEM DESCRIPTION</th>
      <th class="r" style="width:110px">DAY PRICE</th>
      <th class="c" style="width:70px">DAYS</th>
      <th class="r" style="width:120px">TOTAL</th>
    </tr></thead>
    <tbody>{items_rows}</tbody>
  </table>
  <div class="totals">
    <div class="totals-box">
      <div class="tr"><span>Sub-Total</span><span>${inv.get('subtotal',0):.2f}</span></div>
      <div class="tr"><span>Tax</span><span>${inv.get('tax',0):.2f}</span></div>
      <div class="tr total"><span>TOTAL</span><span>${inv.get('total',0):.2f}</span></div>
      {f'<div class="tr"><span>Amount Paid</span><span>${inv.get("amount_paid",0):.2f}</span></div>' if inv.get('amount_paid',0)>0 else ''}
      {f'<div class="tr" style="font-weight:700;color:#dc2626"><span>Balance Due</span><span>${inv.get("balance",0):.2f}</span></div>' if inv.get('balance',0)>0 and inv.get('amount_paid',0)>0 else ''}
    </div>
  </div>
  {doc_payment_info_html()}
  <div class="thanks">Thank You For Your Business</div>
  <div class="terms">
    <h3>Terms and Conditions</h3>
    <p>We may condition future contract renewals/service renewals or suspend our services to you until such amount is paid in full.</p>
  </div>
  <div class="footer">{COMPANY['website']} · {COMPANY['phone_1']}</div>
</div>
</body></html>"""


def render_deposit_html(dep: dict, client: dict) -> str:
    screens = dep.get("screens", [])
    rows = ""
    total_units = 0
    for idx, s in enumerate(screens, 1):
        total_units += s.get("units", 1)
        rows += f"""<tr>
          <td class="c">{idx}</td>
          <td>Screen LED Ultra Brightness Rent {s.get('model','MAV-30540S')}</td>
          <td class="c">{s.get('units',1)}</td>
          <td class="r">${dep.get('amount',0)/(len(screens) or 1):.2f}</td>
        </tr>"""
    location_line = ""
    if screens:
        location_line = f"{total_units} unit(s) at {screens[0].get('location') or client.get('address_line1','')}"

    status = dep.get("status", "pending")
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Deposit {dep.get('receipt_number','')}</title>
<style>{DOC_CSS}</style></head><body>
{doc_actions_html()}
<div class="page">
  {doc_header_html()}
  <div class="title-block">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div><div class="title">Security Deposit Receipt</div><div class="subtitle">Refundable upon return of equipment in good condition</div></div>
      <span class="badge badge-{'paid' if status=='received' else 'pending'}">{'Received' if status=='received' else 'Pending'}</span>
    </div>
  </div>
  <div class="row2">
    <div class="box">
      <div class="box-lbl">Customer</div>
      <div class="box-val">
        <div class="name">{client.get('business_name','—')}</div>
        {client.get('address_line1','')}<br>
        {client.get('city','')} {client.get('state','')} {client.get('zip','')}<br>
        {client.get('phone','')}
      </div>
    </div>
    <div class="box" style="text-align:right">
      <div class="box-lbl">Receipt</div>
      <div class="box-val">
        <div><strong>Receipt #:</strong> {dep.get('receipt_number','')}</div>
        <div><strong>Date:</strong> {format_date_us(dep.get('issue_date',''))}</div>
      </div>
    </div>
  </div>
  <table>
    <thead><tr>
      <th class="c" style="width:50px">LED</th>
      <th>ITEM DESCRIPTION</th>
      <th class="c" style="width:80px">QTY</th>
      <th class="r" style="width:140px">TOTAL</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {f'<div style="font-size:11px;color:#64748b;margin-top:6px;font-style:italic">{location_line}</div>' if location_line else ''}
  <div class="totals">
    <div class="totals-box">
      <div class="tr"><span>Sub-Total</span><span>${dep.get('amount',0):.2f}</span></div>
      <div class="tr"><span>Tax</span><span>${dep.get('tax',0):.2f}</span></div>
      <div class="tr total"><span>TOTAL</span><span>${dep.get('total',0):.2f}</span></div>
    </div>
  </div>
  {doc_payment_info_html()}
  <div class="thanks">Thank You For Your Business</div>
  <div class="terms">
    <h3>Terms and Conditions</h3>
    <p>This security deposit will be returned to the Lessee upon completion of the rental agreement, less any damages or unpaid balances. We may condition future contract renewals/service renewals or suspend our services until such amount is paid in full.</p>
  </div>
  <div class="footer">{COMPANY['website']} · {COMPANY['phone_1']}</div>
</div>
</body></html>"""


def render_contract_html(ct: dict, client: dict) -> str:
    screens_descr = ""
    locations_descr = ""
    total_units = 0
    for s in ct.get("screens", []):
        total_units += s.get("units", 1)
        screens_descr += f"<li>{s.get('units',1)} UNIT(s) ULTRA SLIM LED DISPLAY Model: <strong>{s.get('model','MAV-30540S')}</strong> @ ${s.get('day_price',8.5):.2f}/day</li>"
        locations_descr += f"<li>{s.get('units',1)} unit(s) at <strong>{s.get('location') or client.get('address_line1','')}</strong></li>"

    start_display = format_date_us(ct.get('start_date','')) if ct.get('start_date') else ""
    end_display = format_date_us(ct.get('end_date','')) if ct.get('end_date') else ""
    contract_date = datetime.fromisoformat(ct.get('created_at', datetime.utcnow().isoformat())).strftime("%B %d, %Y") if ct.get('created_at') else datetime.utcnow().strftime("%B %d, %Y")
    monthly_total = ct.get("monthly_total", 0)
    security_deposit = ct.get("security_deposit", 0)
    deposit_per_screen = ct.get("security_deposit_per_screen", 250)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Contract {ct.get('contract_number','')}</title>
<style>{DOC_CSS} .clause-h{{font-weight:700;color:#1e293b;font-size:12px;margin:14px 0 4px}}</style></head><body>
{doc_actions_html()}
<div class="page" style="min-height:1100px">
  {doc_header_html()}
  <div class="title-block" style="text-align:center;border-bottom:2px solid #1e293b;padding-bottom:14px">
    <div class="title" style="text-align:center">LED DISPLAY RENTAL AGREEMENT</div>
    <div class="subtitle" style="text-align:center;margin-top:6px">Contract # {ct.get('contract_number','')} · {contract_date}</div>
  </div>

  <div class="clause"><strong>I. THE PARTIES.</strong> This Equipment Rental Agreement (&ldquo;Agreement&rdquo;) is made on this <strong>{contract_date}</strong> by and between:</div>
  <div class="row2" style="margin:14px 0 18px">
    <div class="box">
      <div class="box-lbl">Lessor</div>
      <div class="box-val">
        <div class="name">{COMPANY['name']}</div>
        {COMPANY['address_line1']}<br>{COMPANY['address_line2']}<br>Phone: {COMPANY['phone_1']}
      </div>
    </div>
    <div class="box" style="border-left-color:#10b981">
      <div class="box-lbl">Lessee</div>
      <div class="box-val">
        <div class="name">{client.get('business_name','—')}</div>
        Representative: <strong>{client.get('representative','—')}</strong><br>
        {client.get('address_line1','')}<br>
        Phone: {client.get('phone','')}
      </div>
    </div>
  </div>

  <div class="clause"><span class="clause-h">II. EQUIPMENT DESCRIPTION.</span><br>The Lessor hereby leases to Lessee the following equipment:
    <ul style="margin-left:20px;margin-top:6px">{screens_descr}</ul>
    Distributed in {total_units} location(s) as follows:
    <ul style="margin-left:20px;margin-top:6px">{locations_descr}</ul>
  </div>

  <div class="clause"><span class="clause-h">III. LEASE TYPE.</span> This Agreement shall be considered a fixed agreement starting on <strong>{start_display}</strong> and ending on <strong>{end_display}</strong> (&ldquo;Lease Term&rdquo;) — <strong>{ct.get('term_months',12)} months</strong>. At the end of the Lease Term and no renewal is made, the Lessee shall be required to return the Equipment to the Lessor.</div>

  <div class="clause"><span class="clause-h">IV. RENT.</span> Lessee agrees to pay Lessor a total of <strong>${monthly_total:.2f}</strong> per month for the rental of the Equipment (&ldquo;Rent&rdquo;) to be paid monthly.
    <br><br><strong>a.) Rent Instructions.</strong> The Rent will be paid by direct deposit or check every <strong>first day of each month</strong> to:<br>
    <span style="font-family:monospace;display:inline-block;margin-top:4px">{COMPANY['name']} · Account: {COMPANY['account_number']} · {COMPANY['bank_name']} · Routing: {COMPANY['routing']}</span>
  </div>

  <div class="clause"><span class="clause-h">V. LATE CHARGES.</span> If any amount of Rent is more than 5 day(s) late, the Lessee will be obligated to pay a late fee of <strong>${ct.get('late_fee_per_day',50):.2f}</strong> for each day Rent is late.</div>

  <div class="clause"><span class="clause-h">VI. NON-SUFFICIENT FUNDS.</span> The Lessee shall be charged <strong>${ct.get('nsf_fee',85):.2f}</strong> for each check that is returned for lack of sufficient funds.</div>

  <div class="clause"><span class="clause-h">VII. SECURITY DEPOSIT.</span> Prior to taking possession of the Equipment, Renter shall pay a deposit of <strong>${deposit_per_screen:.2f}</strong> per screen for a total of <strong>${security_deposit:.2f}</strong>, for performance under this Agreement and any damages caused by the Lessee to the Equipment during the Lease Term.</div>

  <div class="clause"><span class="clause-h">VIII. DELIVERY OF EQUIPMENT.</span> The delivery of the Equipment to the Lessee at the start of the Lease Term and returning to the Lessor at the end of the Lease Term shall be the responsibility of the Lessor.</div>

  <div class="clause"><span class="clause-h">IX. REPAIRS AND MAINTENANCE.</span> If for any reason the Equipment shall need repairs or maintenance due to wear-and-tear, the Lessor shall be responsible.</div>

  <div class="clause"><span class="clause-h">X. INSURANCE.</span> There shall be no requirement for the Lessee to have any type or kind of insurance as part of this Agreement.</div>

  <div class="clause"><span class="clause-h">XI. ACCEPTANCE OF EQUIPMENT.</span> The Lessee shall have twenty-four (24) hours from the delivery date to inform the Lessor of any discrepancies. If the Equipment was not as described, the Lessee may return it and obtain a full refund.</div>

  <div class="clause"><span class="clause-h">XII. NO WARRANTY.</span> The Lessor makes no warranties, express or implied, as to the equipment leased.</div>

  <div class="clause"><span class="clause-h">XIV. RISK OF LOSS OR DAMAGE.</span> The Lessee assumes all risk of loss or damage to the Equipment and agrees to return it in the condition received, with the exception of wear and tear.</div>

  <div class="clause"><span class="clause-h">XV. TAXES AND FEES.</span> During the Lease Term, the Lessee shall be responsible for any applicable taxes, assessments, licenses, registrations or fees associated with the operation of the Equipment.</div>

  <div class="clause"><span class="clause-h">XVI. DEFAULT.</span> The occurrence of any of the following shall constitute a default: (a) failure of payment; (b) violation of agreement not corrected within 5 business days of notice; (c) bankruptcy; (d) seizure of Lessee&rsquo;s property.</div>

  <div class="clause"><span class="clause-h">XVII. RIGHTS UNDER DEFAULT.</span> If the Lessee defaults, the Lessor may take possession of the Equipment with the right to deduct the costs of recovery, including attorney&rsquo;s fees.</div>

  <div class="clause"><span class="clause-h">XVIII. ASSIGNMENT.</span> The Lessee is strictly prohibited from assigning or subletting the Equipment unless written consent is given by the Lessor.</div>

  <div class="clause"><span class="clause-h">XIX. SEVERABILITY.</span> If any portion of this Agreement is held invalid or unenforceable, the remaining provisions shall constitute to be valid and enforceable.</div>

  <div class="clause"><span class="clause-h">XX. GOVERNING LAW.</span> This Agreement shall be construed and governed in accordance with the laws of the State where the Equipment is being rented.</div>

  <div class="clause"><span class="clause-h">XXI. ENTIRE AGREEMENT.</span> This Agreement constitutes the entire agreement between the Parties. No modification shall be effective unless in writing and signed by both Parties.</div>

  <div class="clause"><span class="clause-h">XXII. ADDITIONAL TERMS &amp; CONDITIONS.</span>
    <ol style="margin-left:20px;margin-top:4px">
      <li>The LED screen cannot be manipulated by anyone who is not authorized. Only MediAd View technicians can install and uninstall the screen.</li>
      <li>Unauthorized tampering or opening of the LED screen will damage it and incur charges of <strong>$8,500.00</strong>.</li>
      <li>The tenant agrees to send changes and updates to their offers to the guidelines department.</li>
      {f'<li>{ct.get("additional_terms")}</li>' if ct.get('additional_terms') else ''}
    </ol>
  </div>

  <div class="clause" style="margin-top:18px"><span class="clause-h">XXIII. EXECUTION.</span> Lessee and Lessor each represent that each person executing this Agreement on behalf of each party is duly authorized.</div>

  <div class="sig-block">
    <div class="sig">
      <div class="role">Lessor&rsquo;s Signature</div>
      <div class="name">{COMPANY['name']}</div>
      <div class="meta">Date: ________________</div>
      <div class="meta">Phone: {COMPANY['phone_1']}</div>
      {f'<div style="margin-top:8px;color:#10b981;font-weight:700;font-size:11px">✓ Signed on {ct.get("signed_at","")}</div>' if ct.get('lessor_signature') else ''}
    </div>
    <div class="sig">
      <div class="role">Lessee&rsquo;s Signature</div>
      <div class="name">{client.get('business_name','—')}</div>
      <div class="meta">Representative: {client.get('representative','—')}</div>
      <div class="meta">Date: ________________</div>
      <div class="meta">Phone: {client.get('phone','')}</div>
      {f'<div style="margin-top:8px;color:#10b981;font-weight:700;font-size:11px">✓ Signed on {ct.get("signed_at","")}</div>' if ct.get('lessee_signature') else ''}
    </div>
  </div>

  <div class="footer">{COMPANY['website']} · {COMPANY['phone_1']} · Contract # {ct.get('contract_number','')}</div>
</div>
</body></html>"""
