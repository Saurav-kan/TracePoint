"""Pydantic schemas for ingest API."""
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    """Request body for document ingestion."""

    text: str = Field(..., description="Raw document text to ingest")
    label: str = Field("", description="Evidence type (e.g., witness, gps, alibi). If empty, auto-labeled.")
    case_id: UUID = Field(..., description="Case identifier this evidence belongs to")
    source_document: str | None = Field(None, description="Source document name")
    additional_metadata: dict[str, Any] | None = Field(
        None, description="Optional metadata"
    )


class IngestResponse(BaseModel):
    """Response after ingestion."""

    case_id: UUID = Field(..., description="Case identifier used for ingestion")
    chunks_created: int = Field(..., description="Number of evidence chunks inserted")
    source_document: str | None = Field(None, description="Source filename that was ingested")
