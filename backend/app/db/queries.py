"""Convenience database query helpers."""

from typing import List
from uuid import UUID

from sqlalchemy import Select, distinct, select
from sqlalchemy.orm import Session

from app.db.models import EvidenceChunk
from app.db.session import get_session


def get_case_labels(case_id: UUID) -> List[str]:
    """Return distinct evidence labels for a given case_id.

    This is used by the planner + gatekeeper to constrain metadata_filter
    values to labels that actually exist for the case.
    """
    session: Session = get_session()
    try:
        stmt: Select[str] = select(distinct(EvidenceChunk.label)).where(
            EvidenceChunk.case_id == str(case_id)
        )
        rows = session.execute(stmt).all()
        return [row[0] for row in rows if row[0] is not None]
    finally:
        session.close()

