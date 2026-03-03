"""Planner API routes."""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.agents.gatekeeper import GatekeeperResult, validate_planner_output
from app.agents.planner_agent import run_planner
from app.db.models import Case
from app.db.session import get_session
from app.schemas.planner import PlannerRequest, PlannerResponse

router = APIRouter(prefix="/planner", tags=["planner"])


@router.post("/plan", response_model=PlannerResponse)
async def plan(req: PlannerRequest) -> PlannerResponse:
    """Generate a set of investigative tasks for a case and fact-to-check.

    This endpoint runs the planner LLM, validates the output with the
    gatekeeper, optionally retries a few times, and then returns the
    approved PlannerResponse JSON. If validation repeatedly fails, an
    HTTP 500 is raised.
    """
    session: Session = get_session()
    try:
        case = session.get(Case, str(req.case_id))
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
    finally:
        session.close()

    max_attempts = 3
    last_result: PlannerResponse | None = None
    last_gate: GatekeeperResult | None = None

    for _ in range(max_attempts):
        resp = await run_planner(case, req)
        gate = validate_planner_output(resp, case)
        last_result = resp
        last_gate = gate
        if not gate.needs_regeneration:
            return resp

    # If we get here, validation failed repeatedly
    detail = "Planner output failed validation: " + "; ".join(
        last_gate.reasons if last_gate else ["unknown error"]
    )
    raise HTTPException(status_code=500, detail=detail)
