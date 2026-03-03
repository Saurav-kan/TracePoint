"""Orchestrates the ingestion pipeline: parse/chunk -> embed -> score -> write."""
from pathlib import Path
from typing import Any
from uuid import UUID

from app.ingestion.chunker import chunk_file, chunk_text
from app.ingestion.db_writer import write_evidence_chunks
from app.ingestion.embedder import embed_texts
from app.ingestion.reliability import get_reliability_score


def ingest_document(
    text: str | None = None,
    file_path: str | Path | None = None,
    label: str = "",
    source_document: str | None = None,
    additional_metadata: dict[str, Any] | None = None,
    case_id: UUID | None = None,
) -> int:
    """Ingest a document: parse/chunk, embed, score, and store in the database.

    Provide either file_path (for PDF, DOCX, images, etc.) or text (raw string).

    Args:
        text: Raw document text (use when uploading pasted/API content).
        file_path: Path to document file (PDF, DOCX, images, Markdown, etc.).
        label: Evidence type (e.g., 'witness', 'gps', 'alibi').
        source_document: Optional source document name.
        additional_metadata: Optional metadata dict.
        case_id: Case identifier to associate with all evidence chunks.

    Returns:
        Number of evidence chunks inserted.
    """
    if file_path is not None:
        chunks = chunk_file(file_path)
        src = source_document or str(Path(file_path).name)
    elif text is not None:
        chunks = chunk_text(text)
        src = source_document or "text"
    else:
        raise ValueError("Provide either file_path or text")

    source_document = src
    if not chunks:
        return 0

    embeddings = embed_texts(chunks)
    reliability_score = get_reliability_score(label)

    return write_evidence_chunks(
        chunks=chunks,
        embeddings=embeddings,
        label=label,
        reliability_score=reliability_score,
        source_document=source_document,
        additional_metadata=additional_metadata,
        case_id=case_id,
    )
