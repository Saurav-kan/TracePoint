"""Ingest API routes."""
from fastapi import APIRouter, HTTPException

from app.ingestion.pipeline import ingest_document
from app.ingestion.evidence_clerk import EvidenceClerkDetails, extract_evidence_details
from app.schemas.ingest import IngestRequest, IngestResponse

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=IngestResponse)
async def ingest(req: IngestRequest) -> IngestResponse:
    """Ingest a document: clerk extraction, chunk, embed, and store in the database.

    This endpoint uses the evidence clerk (Gemini Flash) to extract structured
    JSON metadata, validates it against `EvidenceClerkDetails`, and stores it
    in the `additional_metadata` column alongside embeddings.
    """
    # Run the evidence clerk first so we can attach metadata to all chunks
    try:
        clerk_details: EvidenceClerkDetails = await extract_evidence_details(req.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evidence clerk error: {e}")

    # Merge clerk metadata into any caller-provided metadata
    merged_metadata = dict(req.additional_metadata or {})
    merged_metadata.setdefault("evidence_clerk", clerk_details.model_dump())

    try:
        count = ingest_document(
            text=req.text,
            label=req.label,
            source_document=req.source_document,
            additional_metadata=merged_metadata,
            case_id=req.case_id,
        )
        return IngestResponse(case_id=req.case_id, chunks_created=count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
