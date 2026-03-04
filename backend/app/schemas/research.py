"""Schemas for research agent input and output.

These models describe the evidence returned for each planner task
and the overall payload handed to the judge agent.
"""
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.planner import MetadataFilterItem


class EvidenceSnippet(BaseModel):
    """Single evidence snippet with local context and citation."""

    source_document: Optional[str] = Field(
        None, description="Source document or file name for this evidence chunk."
    )
    case_id: Optional[UUID] = Field(
        None, description="Case identifier this evidence belongs to."
    )
    score: float = Field(
        ..., description="Similarity score between query embedding and this chunk."
    )
    chunk_before: Optional[str] = Field(
        None, description="Immediate preceding chunk content, if available."
    )
    chunk: str = Field(..., description="Primary evidence chunk content.")
    chunk_after: Optional[str] = Field(
        None, description="Immediate following chunk content, if available."
    )


class ResearchTaskResult(BaseModel):
    """Research results for a single planner task."""

    question_text: str = Field(
        ..., description="Original investigative question from the planner."
    )
    vector_query: str = Field(
        ..., description="Descriptive sentence used for vector search."
    )
    metadata_filter: List[MetadataFilterItem] = Field(
        ..., description="Metadata filters applied when retrieving evidence."
    )
    evidence: List[EvidenceSnippet] = Field(
        default_factory=list,
        description="Ranked evidence snippets relevant to this task.",
    )


class ResearchResponse(BaseModel):
    """Full research output consumed by the judge agent."""

    case_id: UUID = Field(..., description="Case identifier shared across tasks.")
    fact_to_check: str = Field(
        ..., description="Natural language claim that the pipeline is verifying."
    )
    tasks: List[ResearchTaskResult] = Field(
        ..., description="Per-task research results, aligned with planner tasks."
    )
