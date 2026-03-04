"""Research agent: retrieve evidence for planner tasks.

This agent consumes a PlannerResponse, applies vector + metadata
filters per task, and returns a ResearchResponse that the judge
agent can consume.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.app_config import RESEARCH_DISTANCE_METRIC, RESEARCH_TIME_FILTER_ENABLED, RESEARCH_TOP_K  # type: ignore[attr-defined]
from app.db.models import EvidenceChunk
from app.db.session import get_session
from app.ingestion.embedder import embed_texts
from app.schemas.planner import PlannerResponse
from app.schemas.research import EvidenceSnippet, ResearchResponse, ResearchTaskResult


def _similarity_column(embedding_column, query_embedding):
    """Return the appropriate similarity expression based on distance metric.

    Cosine distance uses the `<=>` operator; L2 uses `<->`.
    """
    if RESEARCH_DISTANCE_METRIC == "l2":
        return embedding_column.op("<->")(query_embedding)
    return embedding_column.op("<=>")(query_embedding)


def _build_metadata_filters(task, ec_alias) -> List:  # type: ignore[type-arg]
    """Translate MetadataFilterItem list into SQLAlchemy filter expressions."""
    clauses: List = []
    for item in task.metadata_filter:
        key = item.key
        value = item.value
        if key == "label":
            clauses.append(ec_alias.label == value)
        elif key == "source_document":
            clauses.append(ec_alias.source_document == value)
        else:
            clauses.append(ec_alias.additional_metadata[value].astext == value)
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

            ec = EvidenceChunk
            sim_col = _similarity_column(ec.embedding, query_emb)

            filters = [ec.case_id == str(planner_resp.case_id)]

            # Optional time filter
            if RESEARCH_TIME_FILTER_ENABLED:
                start = planner_resp.search_boundary.start_time
                end = planner_resp.search_boundary.end_time
                if start is not None and end is not None:
                    filters.append(ec.timestamp.between(start, end))

            filters.extend(_build_metadata_filters(task, ec))

            stmt = (
                select(ec, sim_col.label("score"))
                .where(and_(*filters))
                .order_by(sim_col.asc())
                .limit(RESEARCH_TOP_K)
            )

            rows = session.execute(stmt).all()

            evidence_items: List[EvidenceSnippet] = []
            for ec_row, score in rows:
                # Fetch immediate previous and next chunks by id within same document
                prev_stmt = (
                    select(EvidenceChunk)
                    .where(
                        EvidenceChunk.source_document == ec_row.source_document,
                        EvidenceChunk.case_id == ec_row.case_id,
                        EvidenceChunk.id < ec_row.id,
                    )
                    .order_by(EvidenceChunk.id.desc())
                    .limit(1)
                )
                next_stmt = (
                    select(EvidenceChunk)
                    .where(
                        EvidenceChunk.source_document == ec_row.source_document,
                        EvidenceChunk.case_id == ec_row.case_id,
                        EvidenceChunk.id > ec_row.id,
                    )
                    .order_by(EvidenceChunk.id.asc())
                    .limit(1)
                )

                prev_chunk = session.execute(prev_stmt).scalar_one_or_none()
                next_chunk = session.execute(next_stmt).scalar_one_or_none()

                snippet = EvidenceSnippet(
                    source_document=ec_row.source_document,
                    case_id=planner_resp.case_id,
                    score=float(score),
                    chunk_before=prev_chunk.content if prev_chunk else None,
                    chunk=ec_row.content,
                    chunk_after=next_chunk.content if next_chunk else None,
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
