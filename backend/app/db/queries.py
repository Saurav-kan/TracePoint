"""Convenience database query helpers."""

from typing import List
from uuid import UUID

from sqlalchemy import Select, distinct, select
from sqlalchemy.orm import Session

from app.db.models import EvidenceChunk
from app.db.session import get_session
from app.ingestion.evidence_clerk import canonicalize_evidence_type


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


def get_case_evidence_types(case_id: UUID) -> List[str]:
    """Return distinct canonical evidence_type values for a case.

    The evidence clerk stores structured metadata in additional_metadata
    under the 'evidence_clerk' key. Prefer the post-processed
    'canonical_evidence_type' field; fall back to the raw 'evidence_type'
    only for older rows that predate normalization.
    """
    session: Session = get_session()
    try:
        canonical_expr = EvidenceChunk.additional_metadata["evidence_clerk"][
            "canonical_evidence_type"
        ].astext
        stmt = (
            select(distinct(canonical_expr))
            .where(
                EvidenceChunk.case_id == str(case_id),
                EvidenceChunk.additional_metadata.isnot(None),
            )
        )
        rows = session.execute(stmt).all()
        canonical_values = [row[0] for row in rows if row[0] is not None]
        if canonical_values:
            return canonical_values

        raw_expr = EvidenceChunk.additional_metadata["evidence_clerk"]["evidence_type"].astext
        legacy_stmt = (
            select(distinct(raw_expr))
            .where(
                EvidenceChunk.case_id == str(case_id),
                EvidenceChunk.additional_metadata.isnot(None),
            )
        )
        rows = session.execute(legacy_stmt).all()
        legacy_values = [row[0] for row in rows if row[0] is not None]
        normalized = {
            canonicalize_evidence_type(raw_value, []) for raw_value in legacy_values
        }
        return sorted(normalized)
    finally:
        session.close()

