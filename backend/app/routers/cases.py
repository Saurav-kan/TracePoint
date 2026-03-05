"""Case overview API routes."""
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Case, EvidenceChunk
from app.db.session import get_session
from app.ingestion.embedder import embed_texts
from app.schemas.cases import (
    CaseCreateRequest,
    CaseCreateResponse,
    CaseDetailResponse,
    EvidenceSummary,
)

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseCreateResponse)
def create_case(payload: CaseCreateRequest) -> CaseCreateResponse:
    """Create a new case header and embed the brief.

    Returns the new case_id which the frontend will use when uploading
    evidence and when calling the Planner agent.
    """
    session: Session = get_session()
    try:
        embeddings = embed_texts([payload.case_brief_text])
        brief_embedding = embeddings[0] if embeddings else None

        db_case = Case(
            title=payload.title,
            case_brief_text=payload.case_brief_text,
            brief_embedding=brief_embedding,
            target_subject_name=payload.target_subject_name,
            crime_timestamp_start=payload.crime_timestamp_start,
            crime_timestamp_end=payload.crime_timestamp_end,
            status=payload.status or "active",
        )
        session.add(db_case)
        session.commit()
        session.refresh(db_case)

        # SQL default generates case_id; cast to UUID for response
        cid = UUID(str(db_case.case_id))
        return CaseCreateResponse(case_id=cid, status="created")
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(case_id: UUID) -> CaseDetailResponse:
    """Get case detail with evidence summary for the case workspace."""
    session: Session = get_session()
    try:
        case = session.get(Case, str(case_id))
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")

        stmt = (
            select(EvidenceChunk)
            .where(EvidenceChunk.case_id == str(case_id))
            .order_by(EvidenceChunk.source_document, EvidenceChunk.id)
        )
        chunks = list(session.execute(stmt).scalars().all())

        seen: set[tuple[str, str]] = set()
        evidence_list: list[EvidenceSummary] = []
        for c in chunks:
            key = (c.label, c.source_document or "")
            if key in seen:
                continue
            seen.add(key)
            summary = (c.content[:200] + "...") if len(c.content) > 200 else c.content
            evidence_list.append(
                EvidenceSummary(
                    label=c.label,
                    source_document=c.source_document,
                    reliability=float(c.reliability_score),
                    summary=summary,
                )
            )

        return CaseDetailResponse(
            case_id=UUID(str(case.case_id)),
            title=case.title,
            brief=case.case_brief_text,
            status=case.status,
            evidence=evidence_list,
        )
    finally:
        session.close()