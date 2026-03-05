"""Workflow API routes: planner -> research -> judge pipeline."""
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.agents.gatekeeper import GatekeeperResult, validate_planner_output
from app.agents.judge_agent import run_judge
from app.agents.planner_agent import run_planner
from app.agents.research_agent import run_research
from app.db.models import Case
from app.db.session import get_session
from app.schemas.judge import JudgeResponse
from app.schemas.planner import PlannerRequest, PlannerResponse
from app.schemas.research import ResearchResponse

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/run", response_model=JudgeResponse)
async def run_workflow(req: PlannerRequest) -> JudgeResponse:
    """Run the full pipeline: planner -> research -> judge.

    Returns the JudgeResponse with per-task assessments and overall verdict.
    """
    session: Session = get_session()
    try:
        case = session.get(Case, str(req.case_id))
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
    finally:
        session.close()

    # 1. Planner
    max_attempts = 3
    last_result: PlannerResponse | None = None
    last_gate: GatekeeperResult | None = None

    for _ in range(max_attempts):
        resp = await run_planner(case, req)
        gate = validate_planner_output(resp, case)
        last_result = resp
        last_gate = gate
        if not gate.needs_regeneration:
            break

    if last_result is None or (last_gate and last_gate.needs_regeneration):
        detail = "Planner output failed validation: " + "; ".join(
            last_gate.reasons if last_gate else ["unknown error"]
        )
        raise HTTPException(status_code=500, detail=detail)

    planner_resp = last_result

    # 2. Research
    research_resp: ResearchResponse = run_research(planner_resp)

    # 3. Judge
    session = get_session()
    try:
        case = session.get(Case, str(research_resp.case_id))
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        return await run_judge(research_resp, case=case)
    finally:
        session.close()
