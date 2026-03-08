"""Ingest API routes."""
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import EvidenceChunk
from app.db.session import get_session
from app.ingestion.chunker import chunk_file
from app.ingestion.evidence_clerk import (
    EvidenceClerkDetails,
    LabelScore,
    extract_evidence_details,
    select_top_labels,
)
from app.ingestion.pipeline import ingest_document
from app.schemas.ingest import IngestRequest, IngestResponse

router = APIRouter(prefix="/ingest", tags=["ingest"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_text_from_file(path: Path) -> str:
    """Get document text from a file. For .txt/.md read directly; else use chunker."""
    if path.suffix.lower() in (".txt", ".md", ".log", ".csv"):
        return path.read_text(encoding="utf-8", errors="replace")
    chunks = chunk_file(path)
    return "\n\n".join(chunks) if chunks else ""


# ---------------------------------------------------------------------------
# Auto-label response schema
# ---------------------------------------------------------------------------

class AutoLabelResponse(BaseModel):
    """Response from /ingest/auto-label with scored label suggestions."""

    suggested_labels: list[str] = Field(
        ..., description="Top labels auto-selected (1-3, score >= cutoff)"
    )
    all_scores: list[LabelScore] = Field(
        ..., description="All labels with their relevance scores (1-10)"
    )
    clerk: EvidenceClerkDetails = Field(
        ..., description="Full evidence clerk extraction"
    )


# ---------------------------------------------------------------------------
# POST /ingest/auto-label
# ---------------------------------------------------------------------------

@router.post("/auto-label", response_model=AutoLabelResponse)
async def auto_label_file(
    file: UploadFile = File(...),
) -> AutoLabelResponse:
    """Upload a file and get auto-suggested labels from the evidence clerk.

    The clerk rates every label 1-10; top 1-3 labels scoring >= 6 are returned
    as `suggested_labels`. The full scores are in `all_scores` for UI display.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        text = _get_text_from_file(tmp_path)
        if not text.strip():
            raise HTTPException(status_code=400, detail="File produced no extractable text")
    finally:
        tmp_path.unlink(missing_ok=True)

    try:
        clerk_details = await extract_evidence_details(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evidence clerk error: {e}")

    suggested = select_top_labels(clerk_details.label_scores)

    return AutoLabelResponse(
        suggested_labels=suggested,
        all_scores=clerk_details.label_scores,
        clerk=clerk_details,
    )


# ---------------------------------------------------------------------------
# POST /ingest (JSON body)
# ---------------------------------------------------------------------------

@router.post("", response_model=IngestResponse)
async def ingest(req: IngestRequest) -> IngestResponse:
    """Ingest a document: clerk extraction, chunk, embed, and store in the database.

    This endpoint uses the evidence clerk (Gemini Flash) to extract structured
    JSON metadata, validates it against `EvidenceClerkDetails`, and stores it
    in the `additional_metadata` column alongside embeddings.
    """
    try:
        clerk_details: EvidenceClerkDetails = await extract_evidence_details(req.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evidence clerk error: {e}")

    merged_metadata = dict(req.additional_metadata or {})
    merged_metadata.setdefault("evidence_clerk", clerk_details.model_dump())

    # If no label provided, auto-select from clerk scores
    label = req.label
    if not label:
        auto_labels = select_top_labels(clerk_details.label_scores)
        label = auto_labels[0] if auto_labels else "forensic_log"

    try:
        count = ingest_document(
            text=req.text,
            label=label,
            source_document=req.source_document,
            additional_metadata=merged_metadata,
            case_id=req.case_id,
        )
        return IngestResponse(
            case_id=req.case_id,
            chunks_created=count,
            source_document=req.source_document,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /ingest/file (multipart upload)
# ---------------------------------------------------------------------------

@router.post("/file", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    label: str = Form(""),
    case_id: UUID = Form(...),
) -> IngestResponse:
    """Ingest an uploaded file (PDF, DOCX, TXT, MD, etc.).

    If `label` is empty or omitted, the evidence clerk auto-selects the best label.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        text = _get_text_from_file(tmp_path)
        if not text.strip():
            raise HTTPException(
                status_code=400,
                detail="File produced no extractable text",
            )
    finally:
        tmp_path.unlink(missing_ok=True)

    try:
        clerk_details: EvidenceClerkDetails = await extract_evidence_details(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evidence clerk error: {e}")

    merged_metadata: dict = {}
    merged_metadata.setdefault("evidence_clerk", clerk_details.model_dump())

    # Auto-select label if not provided
    effective_label = label.strip()
    if not effective_label:
        auto_labels = select_top_labels(clerk_details.label_scores)
        effective_label = auto_labels[0] if auto_labels else "forensic_log"

    try:
        count = ingest_document(
            text=text,
            label=effective_label,
            source_document=file.filename,
            additional_metadata=merged_metadata,
            case_id=case_id,
        )
        return IngestResponse(
            case_id=case_id,
            chunks_created=count,
            source_document=file.filename,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /ingest/document/{case_id}/{source_document}
# ---------------------------------------------------------------------------

@router.get("/document/{case_id}/{source_document}")
async def get_evidence_document(case_id: str, source_document: str):
    """Retrieve the full text of a source document by concatenating stored chunks."""
    session = get_session()
    try:
        stmt = (
            select(EvidenceChunk)
            .where(
                EvidenceChunk.case_id == case_id,
                EvidenceChunk.source_document == source_document,
            )
            .order_by(EvidenceChunk.id)
        )
        chunks = session.execute(stmt).scalars().all()
        if not chunks:
            raise HTTPException(status_code=404, detail="Document not found")
        content = "\n\n".join(c.content for c in chunks)
        return {"source_document": source_document, "content": content}
    finally:
        session.close()
