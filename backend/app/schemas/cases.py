"""Pydantic schemas for case overview API."""
from datetime import datetime
from typing import Optional
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