"""Shared state for the cyclic workflow graph."""

from operator import add
from typing import Annotated, Optional, TypedDict

from app.agents.gatekeeper import GatekeeperResult
from app.db.models import Case
from app.schemas.judge import JudgeResponse
from app.schemas.planner import PlannerRequest, PlannerResponse
from app.schemas.research import ResearchResponse
from app.schemas.challenger import ChallengerResponse
from app.schemas.proof_tester import ProofTestResult
from app.schemas.reconciliation import ReconciliationResponse

class WorkflowIteration(TypedDict):
    """Completed outputs for a single investigation pass."""

    iteration: int
    planner: PlannerResponse
    gatekeeper: GatekeeperResult
    research: ResearchResponse
    judge: JudgeResponse
    challenger: Optional[ChallengerResponse]
    reconciliation: Optional[ReconciliationResponse]

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
    challenger_result: ChallengerResponse
    reconciliation_result: ReconciliationResponse
    iterations: Annotated[list[WorkflowIteration], add]
    effort_mode: str
    final_verdict: JudgeResponse | ReconciliationResponse
    proof_test_result: ProofTestResult | None
    investigation_traces: Annotated[list[dict], add]
