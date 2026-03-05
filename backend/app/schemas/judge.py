"""Schemas for judge agent input and output.

These models describe how the judge agent summarizes evidence for each
planner task and produces an overall verdict for the claim.
"""

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.research import EvidenceSnippet


class JudgeTaskFact(BaseModel):
    """Single fact extracted from one or more evidence snippets."""

    description: str = Field(..., description="Short natural-language fact.")
    supports_claim: bool = Field(
        ..., description="Whether this fact supports (True) or weakens (False) the claim."
    )
    source_task_index: int = Field(
        ..., description="Index of the planner/research task this fact came from."
    )
    evidence_indices: List[int] = Field(
        default_factory=list,
        description="Indices of EvidenceSnippet items within the source task that support this fact.",
    )


class JudgeTaskAssessment(BaseModel):
    """Judge's assessment for a single investigative question."""

    question_text: str = Field(..., description="The investigative question being judged.")
    answer: str = Field(..., description="Judge's answer to this specific question.")
    sufficient_evidence: bool = Field(
        ...,
        description=(
            "True if the available evidence snippets are sufficient to answer the question "
            "with reasonable confidence; False otherwise."
        ),
    )
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Optional confidence score in [0,1].",
    )
    key_facts: List[JudgeTaskFact] = Field(
        default_factory=list,
        description="Key facts derived from this task's evidence.",
    )
    notes: Optional[str] = Field(
        None,
        description="Optional additional commentary or caveats for this assessment.",
    )


class JudgeOverallVerdict(BaseModel):
    """Overall judgment about the claim, aggregating across all tasks."""

    claim: str = Field(..., description="The original fact or claim being evaluated.")
    verdict: Literal["true", "likely_true", "uncertain", "likely_false", "false"] = (
        Field(..., description="Discrete verdict label for the claim.")
    )
    rationale: str = Field(
        ..., description="Natural-language explanation of how the verdict was reached."
    )
    supporting_facts: List[JudgeTaskFact] = Field(
        default_factory=list,
        description="Facts that most strongly support the claim.",
    )
    contradicting_facts: List[JudgeTaskFact] = Field(
        default_factory=list,
        description="Facts that most strongly undermine or contradict the claim.",
    )


class JudgeResponse(BaseModel):
    """Top-level payload returned by the judge agent."""

    case_id: UUID = Field(..., description="Case identifier.")
    fact_to_check: str = Field(
        ..., description="Natural language claim that was evaluated."
    )
    tasks: List[JudgeTaskAssessment] = Field(
        ..., description="Per-question assessments aligned with research tasks."
    )
    overall_verdict: JudgeOverallVerdict = Field(
        ..., description="Aggregated verdict across all tasks and facts."
    )
    refinement_performed: bool = Field(
        False,
        description=(
            "Whether a refinement pass (e.g., additional planner/research iteration) "
            "was already performed before producing this response."
        ),
    )
    refinement_suggestion: Optional[str] = Field(
        None,
        description=(
            "If refinement_performed is False and evidence is insufficient, this field "
            "may contain guidance for follow-up planner/research iterations."
        ),
    )

