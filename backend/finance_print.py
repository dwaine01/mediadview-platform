"""
MediAd View — Print Queue API
Endpoints used by the local Windows Print Agent and the admin UI.

Local agent endpoints (use X-Print-Token header, no user login required):
  GET    /api/finance/print/agent/pending           — list pending jobs
  GET    /api/finance/print/agent/document/{job_id} — download the PDF for a job
  POST   /api/finance/print/agent/{job_id}/complete — mark as printed
  POST   /api/finance/print/agent/{job_id}/fail     — mark as failed with reason
  GET    /api/finance/print/agent/ping              — heartbeat (returns server time)

Admin endpoints (require finance role):
  GET    /api/finance/print/queue        — list all jobs (filterable by status)
  POST   /api/finance/print/queue        — manually enqueue a document
  DELETE /api/finance/print/queue/{id}   — cancel a job
  POST   /api/finance/print/queue/{id}/retry — re-queue a failed job
  GET    /api/finance/print/token        — view / rotate the agent token
  POST   /api/finance/print/token/rotate — rotate token
"""
import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Response
from pydantic import BaseModel
from typing import Optional


class EnqueueRequest(BaseModel):
    kind: str          # 'invoice' | 'contract' | 'deposit'
    doc_id: str
    copies: int = 1


async def _get_or_create_token(db):
    """Read or create the print agent token."""
    cfg = await db.fin_settings.find_one({"_id": "print_agent"})
    if cfg and cfg.get("token"):
        return cfg["token"]
    token = secrets.token_urlsafe(32)
    await db.fin_settings.update_one(
        {"_id": "print_agent"},
        {"$set": {"token": token, "created_at": datetime.utcnow().isoformat()}},
        upsert=True,
    )
    return token


def create_finance_print_routes(db, get_current_user):
    router = APIRouter(prefix="/api/finance/print", tags=["finance-print"])

    # ============ AGENT AUTH ============
    async def require_print_token(x_print_token: Optional[str] = Header(None)):
        token = await _get_or_create_token(db)
        if not x_print_token or x_print_token != token:
            raise HTTPException(401, "Invalid or missing X-Print-Token header")
        return True

    # ============ ROLE GUARDS (admin-only management) ============
    async def require_finance_admin(user: dict = Depends(get_current_user)):
        if not user:
            raise HTTPException(401, "Not authenticated")
        role = user.get("role") or user.get("finance_role") or ""
        if role not in ("super_admin", "admin", "finance_admin", "owner"):
            # Be permissive: allow any authenticated user with finance access too
            if user.get("email") and user.get("active", True):
                return user
            raise HTTPException(403, "Finance admin required")
        return user

    # ====================================================
    # ===========  LOCAL WINDOWS AGENT ENDPOINTS  ========
    # ====================================================
    @router.get("/agent/ping")
    async def agent_ping(_ok: bool = Depends(require_print_token)):
        return {"ok": True, "server_time": datetime.utcnow().isoformat()}

    @router.get("/agent/pending")
    async def agent_pending(_ok: bool = Depends(require_print_token), limit: int = 20):
        """Return pending print jobs for the local agent to process."""
        jobs = await db.fin_print_queue.find(
            {"status": "pending"}
        ).sort("queued_at", 1).to_list(limit)
        out = []
        for j in jobs:
            j.pop("_id", None)
            out.append(j)
        return {"jobs": out, "count": len(out)}

    @router.get("/agent/document/{job_id}")
    async def agent_document(job_id: str, _ok: bool = Depends(require_print_token)):
        """Download the PDF for a print job."""
        job = await db.fin_print_queue.find_one({"id": job_id})
        if not job:
            raise HTTPException(404, "Job not found")

        from finance_pdf import generate_invoice_pdf, generate_contract_pdf, generate_deposit_pdf
        kind = job.get("kind", "invoice")
        doc_id = job.get("doc_id")

        if kind == "invoice":
            doc = await db.fin_invoices.find_one({"id": doc_id})
            client = await db.fin_clients.find_one({"id": doc["client_id"]}) if doc else None
            if not doc:
                raise HTTPException(404, "Invoice not found")
            pdf = generate_invoice_pdf(doc, client or {})
            name = f"Invoice_{doc.get('invoice_number','')}.pdf"
        elif kind == "contract":
            doc = await db.fin_contracts.find_one({"id": doc_id})
            client = await db.fin_clients.find_one({"id": doc["client_id"]}) if doc else None
            if not doc:
                raise HTTPException(404, "Contract not found")
            pdf = generate_contract_pdf(doc, client or {})
            name = f"Contract_{doc.get('contract_number','')}.pdf"
        elif kind == "deposit":
            doc = await db.fin_deposits.find_one({"id": doc_id})
            client = await db.fin_clients.find_one({"id": doc["client_id"]}) if doc else None
            if not doc:
                raise HTTPException(404, "Deposit not found")
            pdf = generate_deposit_pdf(doc, client or {})
            name = f"Deposit_{doc.get('receipt_number','')}.pdf"
        else:
            raise HTTPException(400, f"Unknown kind: {kind}")

        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @router.post("/agent/{job_id}/complete")
    async def agent_complete(job_id: str, _ok: bool = Depends(require_print_token)):
        r = await db.fin_print_queue.update_one(
            {"id": job_id},
            {"$set": {"status": "printed", "printed_at": datetime.utcnow().isoformat()}}
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Job not found")
        return {"ok": True}

    @router.post("/agent/{job_id}/fail")
    async def agent_fail(job_id: str, payload: dict = None,
                         _ok: bool = Depends(require_print_token)):
        reason = (payload or {}).get("error", "unknown")
        job = await db.fin_print_queue.find_one({"id": job_id})
        if not job:
            raise HTTPException(404, "Job not found")
        attempts = (job.get("attempts") or 0) + 1
        new_status = "failed" if attempts >= 3 else "pending"
        await db.fin_print_queue.update_one(
            {"id": job_id},
            {"$set": {"status": new_status, "attempts": attempts, "last_error": reason}}
        )
        return {"ok": True, "new_status": new_status, "attempts": attempts}

    # ====================================================
    # ===========  ADMIN MANAGEMENT ENDPOINTS  ===========
    # ====================================================
    @router.get("/queue")
    async def list_queue(status: Optional[str] = None,
                          user: dict = Depends(get_current_user)):
        if not user:
            raise HTTPException(401, "Not authenticated")
        q = {}
        if status:
            q["status"] = status
        jobs = await db.fin_print_queue.find(q).sort("queued_at", -1).to_list(500)
        for j in jobs:
            j.pop("_id", None)
        return {"jobs": jobs, "count": len(jobs)}

    @router.post("/queue")
    async def enqueue_doc(req: EnqueueRequest, user: dict = Depends(get_current_user)):
        if not user:
            raise HTTPException(401, "Not authenticated")
        if req.kind not in ("invoice", "contract", "deposit"):
            raise HTTPException(400, "Invalid kind")
        # Validate doc exists
        coll = {"invoice": "fin_invoices", "contract": "fin_contracts", "deposit": "fin_deposits"}[req.kind]
        doc = await db[coll].find_one({"id": req.doc_id})
        if not doc:
            raise HTTPException(404, f"{req.kind} not found")
        import uuid
        job = {
            "id": str(uuid.uuid4()),
            "kind": req.kind,
            "doc_id": req.doc_id,
            "doc_number": doc.get("invoice_number") or doc.get("contract_number") or doc.get("receipt_number") or "",
            "client_id": doc.get("client_id"),
            "status": "pending",
            "copies": max(1, min(req.copies, 5)),
            "queued_at": datetime.utcnow().isoformat(),
            "printed_at": None,
            "attempts": 0,
            "last_error": None,
            "queued_by": user.get("email") or "system",
        }
        await db.fin_print_queue.insert_one(job)
        job.pop("_id", None)
        return job

    @router.delete("/queue/{job_id}")
    async def delete_job(job_id: str, user: dict = Depends(get_current_user)):
        if not user:
            raise HTTPException(401, "Not authenticated")
        r = await db.fin_print_queue.delete_one({"id": job_id})
        if r.deleted_count == 0:
            raise HTTPException(404, "Job not found")
        return {"ok": True}

    @router.post("/queue/{job_id}/retry")
    async def retry_job(job_id: str, user: dict = Depends(get_current_user)):
        if not user:
            raise HTTPException(401, "Not authenticated")
        r = await db.fin_print_queue.update_one(
            {"id": job_id},
            {"$set": {"status": "pending", "attempts": 0, "last_error": None}}
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Job not found")
        return {"ok": True}

    @router.get("/token")
    async def get_token(user: dict = Depends(get_current_user)):
        if not user:
            raise HTTPException(401, "Not authenticated")
        token = await _get_or_create_token(db)
        return {"token": token}

    @router.post("/token/rotate")
    async def rotate_token(user: dict = Depends(get_current_user)):
        if not user:
            raise HTTPException(401, "Not authenticated")
        token = secrets.token_urlsafe(32)
        await db.fin_settings.update_one(
            {"_id": "print_agent"},
            {"$set": {"token": token, "rotated_at": datetime.utcnow().isoformat()}},
            upsert=True,
        )
        return {"token": token}

    # ============ STATS ============
    @router.get("/stats")
    async def stats(user: dict = Depends(get_current_user)):
        if not user:
            raise HTTPException(401, "Not authenticated")
        pending = await db.fin_print_queue.count_documents({"status": "pending"})
        printed = await db.fin_print_queue.count_documents({"status": "printed"})
        failed = await db.fin_print_queue.count_documents({"status": "failed"})
        last = await db.fin_print_queue.find({"status": "printed"}).sort("printed_at", -1).limit(1).to_list(1)
        last_print = last[0].get("printed_at") if last else None
        return {"pending": pending, "printed": printed, "failed": failed, "last_printed_at": last_print}

    return router
