"""Pydantic schemas for case overview API."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CaseCreateRequest(BaseModel):
    title: str = Field(..., description="Human-readable case title")
    case_brief_text: str = Field(..., description="Full case brief text for the planner agent")
    target_subject_name: Optional[str] = Field(
        None, description="Primary subject or suspect name for this case"
    )
    crime_timestamp_start: Optional[datetime] = None
    crime_timestamp_end: Optional[datetime] = None
    status: Optional[str] = Field(
        "active", description="Case status: active, closed, or cold"
    )


class CaseCreateResponse(BaseModel):
    case_id: UUID = Field(..., description="Unique identifier for the case")
    status: str = Field(..., description="Creation status, e.g., 'created'")


class CaseSummaryResponse(BaseModel):
    """Brief summary of a case for listing."""

    case_id: UUID = Field(..., description="Unique identifier")
    title: str = Field(..., description="Case title")
    status: str = Field(..., description="Case status")
    created_at: datetime = Field(..., description="When the case was created")


class EvidenceSummary(BaseModel):
    """Summary of an evidence document for case display."""

    label: str = Field(..., description="Evidence type label")
    source_document: Optional[str] = Field(None, description="Source document name")
    reliability: float = Field(..., description="Reliability score 0-1")
    summary: str = Field(default="", description="Brief excerpt or summary")


class CaseDetailResponse(BaseModel):
    """Case detail for GET /cases/:id."""

    case_id: UUID = Field(..., description="Unique identifier")
    title: str = Field(..., description="Case title")
    brief: str = Field(..., description="Case brief text")
    status: str = Field(..., description="Case status")
    created_at: datetime = Field(..., description="When the case was created")
    evidence: List[EvidenceSummary] = Field(
        default_factory=list, description="Evidence inventory summary"
    )


class CaseUpdateRequest(BaseModel):
    """Request to update case details."""

    title: Optional[str] = None
    case_brief_text: Optional[str] = None
    status: Optional[str] = None
