"""Schemas for planner agent input and output."""
from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PlannerRequest(BaseModel):
    """Request body for the planner agent."""

    case_id: UUID = Field(..., description="Case identifier to plan for")
    fact_to_check: str = Field(..., description="Natural language claim to verify or challenge")


class FrictionSummary(BaseModel):
    """High-level summary of friction between case overview and claim."""

    has_friction: bool = Field(..., description="Whether any inconsistency was detected")
    description: Optional[str] = Field(
        None,
        description="Short description of the inconsistency, if any",
    )


class SearchBoundary(BaseModel):
    """Temporal bounds for searches derived from the case overview/claim."""

    start_time: Optional[datetime] = Field(
        None, description="Start of the search window, if applicable"
    )
    end_time: Optional[datetime] = Field(
        None, description="End of the search window, if applicable"
    )


InvestigativeType = Literal[
    "VERIFICATION",
    "IMPOSSIBILITY",
    "ENVIRONMENTAL",
    "NEGATIVE_PROOF",
    "RECALL_STRESS",
]


class PlannerTask(BaseModel):
    """Single investigative task produced by the planner."""

    type: InvestigativeType = Field(
        ..., description="Investigative category (e.g. VERIFICATION, RECALL_STRESS)"
    )
    question_text: str = Field(
        ..., description="Human-readable investigative question"
    )
    vector_query: str = Field(
        ..., description="Descriptive sentence used for vector search (not a single keyword)"
    )
    metadata_filter: Dict[str, str] = Field(
        ..., description="Metadata filters for SQL/ORM WHERE clauses (e.g., {'label': 'gps_log'})",
        min_items=1,
    )


class PlannerResponse(BaseModel):
    """Full planner output consumed by the researcher and judge."""

    case_id: UUID = Field(..., description="Case identifier")
    fact_to_check: str = Field(..., description="Echo of the input claim")
    friction_summary: FrictionSummary = Field(
        ..., description="Friction summary between overview and claim"
    )
    search_boundary: SearchBoundary = Field(
        ..., description="Temporal search boundaries for evidence retrieval"
    )
    tasks: List[PlannerTask] = Field(
        ..., description="List of investigative tasks (usually 5)"
    )
