"""Schemas for the proof-tester agent (fact selection, validation, replacement)."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.judge import JudgeTaskFact


class ProofFactSelection(BaseModel):
    """Selected strongest supporting and contradicting facts for proof testing."""

    supporting_indices: List[int] = Field(
        default_factory=list,
        description="Indices of supporting facts to validate (top 2).",
    )
    contradicting_indices: List[int] = Field(
        default_factory=list,
        description="Indices of contradicting facts to validate (top 2).",
    )


class ProofQuerySet(BaseModel):
    """Three vector queries generated to validate a single fact."""

    fact_index: int = Field(..., description="Index of the fact in supporting or contradicting list.")
    fact_description: str = Field(..., description="The fact being validated.")
    supports_claim: bool = Field(..., description="Whether this is a supporting or contradicting fact.")
    queries: List[str] = Field(
        default_factory=list,
        description="Three vector queries aimed at validating the fact.",
    )


class ProofValidationResult(BaseModel):
    """Validation outcome for a single fact after retrieval."""

    fact: JudgeTaskFact = Field(..., description="The original fact.")
    fact_index: int = Field(..., description="Index in supporting or contradicting list.")
    supports_claim: bool = Field(..., description="Whether this is supporting or contradicting.")
    status: Literal["validated", "invalidated", "partially_validated"] = Field(
        ..., description="Validation outcome."
    )
    replacement_fact: Optional[JudgeTaskFact] = Field(
        None,
        description="Replacement fact derived from new evidence when invalidated.",
    )
    retrieval_summary: str = Field(
        default="",
        description="Brief summary of what retrieval found relative to the fact.",
    )


class ProofTestResult(BaseModel):
    """Full proof-test result with validated/invalidated facts and final adjusted verdict."""

    validated_supporting: List[JudgeTaskFact] = Field(
        default_factory=list,
        description="Supporting facts that passed validation.",
    )
    validated_contradicting: List[JudgeTaskFact] = Field(
        default_factory=list,
        description="Contradicting facts that passed validation.",
    )
    invalidated_supporting: List[ProofValidationResult] = Field(
        default_factory=list,
        description="Supporting facts that failed validation.",
    )
    invalidated_contradicting: List[ProofValidationResult] = Field(
        default_factory=list,
        description="Contradicting facts that failed validation.",
    )
    replacements: List[JudgeTaskFact] = Field(
        default_factory=list,
        description="Replacement facts for invalidated ones.",
    )
    adjusted_verdict: dict = Field(
        default_factory=dict,
        description="Final verdict after proof adjustment (verdict, rationale, supporting_facts, contradicting_facts).",
    )
