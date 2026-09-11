"""certification_routes.py -- the 2 /certification/* routes: a TV device
submits its self-test results, and results can be listed back.

Fase 2B-10c of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md).
Pure relocation: identical paths, methods, decorators and logic, registered
on a router with prefix="/api" so the final routes match api_router exactly
as before. No behavior change.

Note: /certified-devices (a separate, public, static-data endpoint reading
the CERTIFIED_DEVICES constant) is NOT part of this phase -- it's thematically
adjacent but not one of the "2 /certification/*" routes agreed, and stays in
server.py for now.

Dependency notes:
  - gen_id and serialize_doc are threaded in, same pattern as every prior
    phase: both stay in server.py because they're shared with code that is
    NOT moving here.
  - db (database.py) is imported directly, same precedent as every prior
    phase.
  - CertificationResult moves here as a plain module-level pydantic model:
    grep-verified no use outside this exact route.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from database import db


class CertificationResult(BaseModel):
    device_brand: str
    device_model: str
    os_version: str
    screen_resolution: str
    user_agent: str
    tests_passed: int
    tests_failed: int
    tests_total: int
    test_details: list
    stability_minutes: Optional[int] = None
    manual_checks: Optional[dict] = None


def create_certification_routes(gen_id, serialize_doc):
    router = APIRouter(prefix="/api", tags=["Certification"])

    @router.post("/certification/submit")
    async def submit_certification(data: CertificationResult):
        """TV submits certification test results to server."""
        result = {
            "id": gen_id(),
            "device_brand": data.device_brand,
            "device_model": data.device_model,
            "os_version": data.os_version,
            "screen_resolution": data.screen_resolution,
            "user_agent": data.user_agent,
            "tests_passed": data.tests_passed,
            "tests_failed": data.tests_failed,
            "tests_total": data.tests_total,
            "pass_rate": round(data.tests_passed / max(data.tests_total, 1) * 100, 1),
            "test_details": data.test_details,
            "stability_minutes": data.stability_minutes,
            "manual_checks": data.manual_checks,
            "certified": data.tests_failed == 0,
            "created_at": datetime.utcnow()
        }
        await db.certification_results.insert_one(result)
        return serialize_doc(result)

    @router.get("/certification/results")
    async def get_certification_results():
        """Get all certification test results."""
        results = await db.certification_results.find({}).sort("created_at", -1).to_list(100)
        return serialize_doc(results)

    return router
