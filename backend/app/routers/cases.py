"""Case overview API routes."""
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Case, CaseBrief, EvidenceChunk
from app.db.session import get_session
from app.ingestion.embedder import embed_texts
from app.schemas.cases import (
    CaseBriefResponse,
    CaseBriefUpdateRequest,
    CaseCreateRequest,
    CaseCreateResponse,
    CaseDetailResponse,
    CaseSummaryResponse,
    CaseUpdateRequest,
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
        session.flush()

        initial_brief = CaseBrief(
            case_id=str(db_case.case_id),
            title=payload.title[:80] if len(payload.title) > 80 else payload.title,
            brief_text=payload.case_brief_text,
            brief_embedding=brief_embedding,
        )
        session.add(initial_brief)
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


@router.get("", response_model=list[CaseSummaryResponse])
def list_cases() -> list[CaseSummaryResponse]:
    """List all cases, ordered by created_at descending."""
    session: Session = get_session()
    try:
        stmt = select(Case).order_by(Case.created_at.desc())
        cases = session.execute(stmt).scalars().all()
        return [
            CaseSummaryResponse(
                case_id=UUID(str(c.case_id)),
                title=c.title,
                status=c.status,
                created_at=c.created_at,
            )
            for c in cases
        ]
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
            created_at=case.created_at,
            evidence=evidence_list,
        )
    finally:
        session.close()


@router.patch("/{case_id}", response_model=CaseDetailResponse)
def update_case(case_id: UUID, payload: CaseUpdateRequest) -> CaseDetailResponse:
    """Update case details (title, brief, status)."""
    session: Session = get_session()
    try:
        case = session.get(Case, str(case_id))
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")

        if payload.title is not None:
            case.title = payload.title
        if payload.case_brief_text is not None:
            case.case_brief_text = payload.case_brief_text
            # Re-embed brief if it changed
            embeddings = embed_texts([payload.case_brief_text])
            case.brief_embedding = embeddings[0] if embeddings else None
        if payload.status is not None:
            case.status = payload.status

        session.commit()
        session.refresh(case)
        return get_case(case_id)
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.get("/{case_id}/briefs", response_model=list[CaseBriefResponse])
def list_briefs(case_id: UUID) -> list[CaseBriefResponse]:
    """List all case summaries for a case."""
    session: Session = get_session()
    try:
        case = session.get(Case, str(case_id))
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        briefs = [b for b in case.briefs]
        briefs.sort(key=lambda b: b.created_at)
        return [
            CaseBriefResponse(
                id=b.id,
                case_id=UUID(str(b.case_id)),
                title=b.title,
                brief_text=b.brief_text,
                source_file=b.source_file,
                created_at=b.created_at,
            )
            for b in briefs
        ]
    finally:
        session.close()


@router.post("/{case_id}/briefs", response_model=CaseBriefResponse)
async def add_brief(
    case_id: UUID,
    file: UploadFile | None = File(None),
    title: str | None = Form(None),
    brief_text: str | None = Form(None),
) -> CaseBriefResponse:
    """Add a case summary. Provide either file (e.g. .md, .txt) or brief_text."""
    session: Session = get_session()
    try:
        case = session.get(Case, str(case_id))
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")

        text: str
        source_file: str | None = None
        brief_title: str

        if file and file.filename:
            content = await file.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            text = content
            source_file = file.filename
            brief_title = title or (Path(file.filename).stem if file.filename else "Case Summary")
        elif brief_text:
            text = brief_text
            brief_title = title or "Case Summary"
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide either a file upload or brief_text form field",
            )

        if not text.strip():
            raise HTTPException(status_code=400, detail="Brief text cannot be empty")

        embeddings = embed_texts([text])
        brief_embedding = embeddings[0] if embeddings else None

        db_brief = CaseBrief(
            case_id=str(case_id),
            title=brief_title[:200],
            brief_text=text,
            brief_embedding=brief_embedding,
            source_file=source_file,
        )
        session.add(db_brief)
        session.commit()
        session.refresh(db_brief)

        return CaseBriefResponse(
            id=db_brief.id,
            case_id=UUID(str(db_brief.case_id)),
            title=db_brief.title,
            brief_text=db_brief.brief_text,
            source_file=db_brief.source_file,
            created_at=db_brief.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.patch("/{case_id}/briefs/{brief_id}", response_model=CaseBriefResponse)
def update_brief(
    case_id: UUID, brief_id: int, payload: CaseBriefUpdateRequest
) -> CaseBriefResponse:
    """Update an existing case summary's title or text."""
    session: Session = get_session()
    try:
        stmt = select(CaseBrief).where(
            CaseBrief.case_id == str(case_id), CaseBrief.id == brief_id
        )
        brief = session.execute(stmt).scalar_one_or_none()
        if brief is None:
            raise HTTPException(status_code=404, detail="Brief not found")

        if payload.title is not None:
            brief.title = payload.title
        if payload.brief_text is not None:
            brief.brief_text = payload.brief_text
            # Re-embed if text changed
            embeddings = embed_texts([payload.brief_text])
            brief.brief_embedding = embeddings[0] if embeddings else None

        session.commit()
        session.refresh(brief)
        return CaseBriefResponse(
            id=brief.id,
            case_id=UUID(str(brief.case_id)),
            title=brief.title,
            brief_text=brief.brief_text,
            source_file=brief.source_file,
            created_at=brief.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.delete("/{case_id}/briefs/{brief_id}")
def delete_brief(case_id: UUID, brief_id: int):
    """Delete a case summary."""
    session: Session = get_session()
    try:
        stmt = select(CaseBrief).where(
            CaseBrief.case_id == str(case_id), CaseBrief.id == brief_id
        )
        brief = session.execute(stmt).scalar_one_or_none()
        if brief is None:
            raise HTTPException(status_code=404, detail="Brief not found")

        session.delete(brief)
        session.commit()
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()
