"""Shared state for the cyclic workflow graph."""

from operator import add
from typing import Annotated, Optional, TypedDict

from app.agents.gatekeeper import GatekeeperResult
from app.db.models import Case
from app.schemas.judge import JudgeResponse
from app.schemas.planner import PlannerRequest, PlannerResponse
from app.schemas.research import ResearchResponse


class WorkflowIteration(TypedDict):
    """Completed outputs for a single investigation pass."""

    iteration: int
    planner: PlannerResponse
    gatekeeper: GatekeeperResult
    research: ResearchResponse
    judge: JudgeResponse


class PipelineState(TypedDict, total=False):
    """Typed state shared across the planner/research/judge loop."""

    case: Case
    request: PlannerRequest
    brief_text_override: Optional[str]
    max_iterations: int

    refinement_context: Optional[str]

    planner_result: PlannerResponse
    gatekeeper_result: GatekeeperResult
    research_result: ResearchResponse
    judge_result: JudgeResponse
    iterations: Annotated[list[WorkflowIteration], add]
    final_verdict: JudgeResponse
