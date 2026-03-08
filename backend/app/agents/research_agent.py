"""Research agent: retrieve evidence for planner tasks.

This agent consumes a PlannerResponse, applies vector + metadata
filters per task, and returns a ResearchResponse that the judge
agent can consume.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Float

from app.config import RESEARCH_DISTANCE_METRIC, RESEARCH_TIME_FILTER_ENABLED, RESEARCH_TOP_K  # type: ignore[attr-defined]
from app.db.models import EvidenceChunk
from app.db.session import get_session

# Table reference for column-only selects (avoids ORM loading the Vector column)
_ec_table = EvidenceChunk.__table__
from app.ingestion.embedder import embed_texts
from app.schemas.planner import PlannerResponse
from app.schemas.research import EvidenceSnippet, ResearchResponse, ResearchTaskResult


def _similarity_column(embedding_column, query_embedding):
    """Return the appropriate similarity expression based on distance metric.

    Cosine distance uses the `<=>` operator; L2 uses `<->`.
    return_type=Float ensures the result column is typed as float, not Vector,
    so pgvector's result_processor is not applied to the score (avoids TypeError).
    """
    if RESEARCH_DISTANCE_METRIC == "l2":
        return embedding_column.op("<->", return_type=Float)(query_embedding)
    return embedding_column.op("<=>", return_type=Float)(query_embedding)


def _build_metadata_filters(task, table_or_entity) -> List:  # type: ignore[type-arg]
    """Translate MetadataFilterItem list into SQLAlchemy filter expressions."""
    clauses: List = []
    # Support both Table.c.attr and ORM InstrumentedAttribute
    if hasattr(table_or_entity, "c"):
        label_col = table_or_entity.c.label
        source_doc_col = table_or_entity.c.source_document
        meta_col = table_or_entity.c.additional_metadata
    else:
        label_col = table_or_entity.label
        source_doc_col = table_or_entity.source_document
        meta_col = table_or_entity.additional_metadata
    for item in task.metadata_filter:
        key = item.key
        value = item.value
        if key == "label":
            clauses.append(label_col == value)
        elif key == "source_document":
            clauses.append(source_doc_col == value)
        elif key == "evidence_type":
            # Query clerk-extracted evidence_type from JSONB
            clauses.append(
                meta_col["evidence_clerk"]["evidence_type"].astext == value
            )
        else:
            clauses.append(meta_col[value].astext == value)
    return clauses


def run_research(planner_resp: PlannerResponse) -> ResearchResponse:
    """Run research for all planner tasks and return structured evidence.

    This function is synchronous and uses the existing SQLAlchemy Session
    helper; it is intended to be called from FastAPI endpoints that already
    run in a threadpool.
    """
    session: Session = get_session()
    tasks_results: List[ResearchTaskResult] = []

    try:
        for task in planner_resp.tasks:
            # 1. Embed the vector query
            embeddings = embed_texts([task.vector_query])
            if not embeddings or embeddings[0] is None:
                tasks_results.append(
                    ResearchTaskResult(
                        question_text=task.question_text,
                        vector_query=task.vector_query,
                        metadata_filter=task.metadata_filter,
                        evidence=[],
                    )
                )
                continue
            query_emb = embeddings[0]

            # Use table columns so the result set never includes the Vector column.
            # Selecting from the ORM entity can still trigger pgvector's result_processor
            # and cause TypeError when column order is ambiguous.
            sim_col = _similarity_column(_ec_table.c.embedding, query_emb)
            filters = [_ec_table.c.case_id == str(planner_resp.case_id)]

            # Optional time filter
            if RESEARCH_TIME_FILTER_ENABLED:
                start = planner_resp.search_boundary.start_time
                end = planner_resp.search_boundary.end_time
                if start is not None and end is not None:
                    filters.append(_ec_table.c.timestamp.between(start, end))

            filters.extend(_build_metadata_filters(task, _ec_table))

            stmt = (
                select(
                    _ec_table.c.id,
                    _ec_table.c.content,
                    _ec_table.c.source_document,
                    _ec_table.c.case_id,
                    sim_col.label("score"),
                )
                .where(and_(*filters))
                .order_by(sim_col.asc())
                .limit(RESEARCH_TOP_K)
            )

            rows = session.execute(stmt).all()

            evidence_items: List[EvidenceSnippet] = []
            for row in rows:
                chunk_id, content, source_document, case_id, score = row
                # Fetch immediate previous and next chunk content only (table select, no Vector)
                prev_row = (
                    session.execute(
                        select(_ec_table.c.content).where(
                            _ec_table.c.source_document == source_document,
                            _ec_table.c.case_id == case_id,
                            _ec_table.c.id < chunk_id,
                        ).order_by(_ec_table.c.id.desc()).limit(1)
                    ).first()
                )
                next_row = (
                    session.execute(
                        select(_ec_table.c.content).where(
                            _ec_table.c.source_document == source_document,
                            _ec_table.c.case_id == case_id,
                            _ec_table.c.id > chunk_id,
                        ).order_by(_ec_table.c.id.asc()).limit(1)
                    ).first()
                )

                snippet = EvidenceSnippet(
                    source_document=source_document,
                    case_id=planner_resp.case_id,
                    score=float(score),
                    chunk_before=prev_row[0] if prev_row else None,
                    chunk=content,
                    chunk_after=next_row[0] if next_row else None,
                )
                evidence_items.append(snippet)

            tasks_results.append(
                ResearchTaskResult(
                    question_text=task.question_text,
                    vector_query=task.vector_query,
                    metadata_filter=task.metadata_filter,
                    evidence=evidence_items,
                )
            )

    finally:
        session.close()

    return ResearchResponse(
        case_id=planner_resp.case_id,
        fact_to_check=planner_resp.fact_to_check,
        tasks=tasks_results,
    )
