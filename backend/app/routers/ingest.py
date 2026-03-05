"""Ingest API routes."""
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.ingestion.chunker import chunk_file
from app.ingestion.evidence_clerk import EvidenceClerkDetails, extract_evidence_details
from app.ingestion.pipeline import ingest_document
from app.schemas.ingest import IngestRequest, IngestResponse

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _get_text_from_file(path: Path) -> str:
    """Get document text from a file. For .txt/.md read directly; else use chunker."""
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    chunks = chunk_file(path)
    return "\n\n".join(chunks) if chunks else ""


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


@router.post("/file", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    label: str = Form(...),
    case_id: UUID = Form(...),
) -> IngestResponse:
    """Ingest an uploaded file (PDF, DOCX, TXT, MD, etc.)."""
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

    try:
        count = ingest_document(
            text=text,
            label=label,
            source_document=file.filename,
            additional_metadata=merged_metadata,
            case_id=case_id,
        )
        return IngestResponse(case_id=case_id, chunks_created=count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
