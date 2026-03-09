"""Schemas for the streaming workflow API and investigation logs."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.agents.gatekeeper import GatekeeperResult
from app.schemas.judge import JudgeResponse
from app.schemas.planner import PlannerResponse
from app.schemas.research import ResearchResponse

EffortLevel = Literal["low", "medium", "high"]

EFFORT_ITERATIONS: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
}

class WorkflowRequest(BaseModel):
    """Request body for the streaming workflow endpoint."""

    case_id: UUID = Field(..., description="Case identifier to investigate")
    fact_to_check: str = Field(..., description="Natural language claim to verify")
    brief_id: Optional[int] = Field(
        None, description="Use this case brief instead of the case default"
    )
    effort_level: EffortLevel = Field(
        "low",
        description="Controls how many planner/research/judge passes are allowed.",
    )


class PipelineStepEvent(BaseModel):
    """Single SSE event payload describing pipeline progress."""

    step: str = Field(..., description="Pipeline stage: planner | gatekeeper | research | judge")
    status: str = Field(..., description="running | complete")
    iteration: int = Field(1, description="1-based investigation pass index")
    total_iterations: int = Field(1, description="Maximum allowed investigation passes")
    progress: Optional[str] = Field(None, description="Fraction progress string, e.g. '3/10'")
    data: Optional[dict[str, Any]] = Field(
        None, description="Step output payload when status is 'complete'"
    )


class IterationResult(BaseModel):
    """Bundled outputs from a single investigation pass."""

    iteration: int
    planner: PlannerResponse
    gatekeeper: GatekeeperResult
    research: ResearchResponse
    judge: JudgeResponse


class WorkflowResponse(BaseModel):
    """Full response persisted after all iterations complete."""

    log_id: int
    effort_level: EffortLevel
    iterations: list[IterationResult] = Field(
        default_factory=list,
        description="All completed planner/research/judge passes.",
    )
    final_verdict: JudgeResponse


class InvestigationLogSummary(BaseModel):
    """Lightweight item for listing past investigations."""
    id: int
    claim: str
    effort_level: EffortLevel
    verdict: str
    created_at: datetime
