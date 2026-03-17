"""Schemas for the challenger agent input and output."""

from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ChallengerDisagreement(BaseModel):
    """Structured explanation of an opposing narrative."""

    narrative: str = Field(
        ..., description="The strongest alternative narrative supported by the evidence that opposes the Judge's verdict."
    )
    over_weighted_evidence: str = Field(
        ..., description="Explanation of which evidence pieces the Judge over-weighted or misinterpreted."
    )


class ChallengerResponse(BaseModel):
    """Output from the adversarial Challenger node."""

    case_id: UUID = Field(..., description="Case identifier.")
    has_disagreement: bool = Field(
        ..., description="True if a viable opposing narrative was found against the Judge's verdict."
    )
    structured_disagreement: Optional[ChallengerDisagreement] = Field(
        None, description="Details of the disagreement if has_disagreement is True."
    )
    retrieval_gap: bool = Field(
        False, description="True if critical evidence that could prove the alternative narrative wasn't even searched for."
    )
    missed_queries: List[str] = Field(
        default_factory=list, description="Follow-up queries to fill the retrieval gap."
    )
