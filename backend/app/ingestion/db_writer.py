"""Write evidence chunks to the database."""
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.db.models import EvidenceChunk
from app.db.session import get_session


def write_evidence_chunks(
    chunks: list[str],
    embeddings: list[list[float]],
    label: str,
    reliability_score: float,
    source_document: str | None = None,
    additional_metadata: dict[str, Any] | None = None,
    case_id: UUID | None = None,
) -> int:
    """Bulk insert evidence chunks.

    Args:
        chunks: List of chunk text content.
        embeddings: List of embedding vectors (same length as chunks).
        label: Evidence type label.
        reliability_score: Reliability score 0-1.
        source_document: Optional source document name.
        additional_metadata: Optional JSON metadata.
        case_id: Case identifier for all chunks.

    Returns:
        Number of rows inserted.
    """
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings must have the same length")
    if not chunks:
        return 0

    score = Decimal(str(round(reliability_score, 2)))
    meta = additional_metadata if additional_metadata is not None else {}

    records = [
        EvidenceChunk(
            content=c,
            embedding=emb,
            label=label,
            reliability_score=score,
            source_document=source_document,
            additional_metadata=meta,
            timestamp=None,
            case_id=str(case_id) if case_id is not None else None,
        )
        for c, emb in zip(chunks, embeddings)
    ]

    session = get_session()
    try:
        session.add_all(records)
        session.commit()
        return len(records)
    finally:
        session.close()
