"""Workflow API routes: LangGraph-based planner -> research -> judge pipeline."""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Case, CaseBrief
from app.db.session import get_session
from app.graph.graph import compiled_graph
from app.graph.state import PipelineState
from app.schemas.judge import JudgeResponse
from app.schemas.planner import PlannerRequest

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/run", response_model=JudgeResponse)
async def run_workflow(req: PlannerRequest) -> JudgeResponse:
    """Run the full pipeline: planner -> research -> judge via LangGraph.

    Returns the JudgeResponse with per-task assessments and overall verdict.
    If req.brief_id is set, use that case brief's text for the planner.
    """
    session: Session = get_session()
    brief_text_override: str | None = None
    try:
        case = session.get(Case, str(req.case_id))
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        if req.brief_id is not None:
            brief = session.get(CaseBrief, req.brief_id)
            if brief is None or str(brief.case_id) != str(req.case_id):
                raise HTTPException(status_code=404, detail="Brief not found")
            brief_text_override = brief.brief_text
    finally:
        session.close()

    initial_state: PipelineState = {
        "case": case,
        "request": req,
        "brief_text_override": brief_text_override,
        "planner_response": None,
        "planner_attempts": 0,
        "planner_gate": None,
        "research_response": None,
        "judge_response": None,
        "judge_refinement_attempts": 0,
        "refinement_context": None,
        "planner_supplemental_response": None,
    }

    result = await compiled_graph.ainvoke(initial_state)
    return result["judge_response"]
