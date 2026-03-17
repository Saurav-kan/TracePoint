"""Schemas for the reconciliation agent input and output."""

from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from app.schemas.judge import JudgeTaskFact


class ReconciliationResponse(BaseModel):
    """Ultimate verdict resolving conflict between Judge and Challenger."""

    case_id: UUID = Field(..., description="Case identifier.")
    verdict: Literal["true", "likely_true", "uncertain", "likely_false", "false"] = Field(
        ..., description="Final resolved verdict."
    )
    rationale: str = Field(
        ..., description="Explanation of how the conflict was resolved using the evidence hierarchy."
    )
    supporting_facts: List[JudgeTaskFact] = Field(
        default_factory=list, description="Facts supporting the final verdict."
    )
    contradicting_facts: List[JudgeTaskFact] = Field(
        default_factory=list, description="Facts contradicting the final verdict."
    )
