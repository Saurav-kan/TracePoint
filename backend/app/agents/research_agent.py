"""Research agent: retrieve evidence for planner tasks.

This agent consumes a PlannerResponse, applies vector + metadata
filters per task, and returns a ResearchResponse that the judge
agent can consume.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Float

from app.config import RESEARCH_DISTANCE_METRIC, RESEARCH_METADATA_FILTER_ENABLED, RESEARCH_TIME_FILTER_ENABLED, RESEARCH_TOP_K  # type: ignore[attr-defined]
from app.db.models import EvidenceChunk
from app.db.session import get_session

# Table reference for column-only selects (avoids ORM loading the Vector column)
_ec_table = EvidenceChunk.__table__
from app.ingestion.embedder import embed_texts
from app.schemas.planner import PlannerResponse
from app.schemas.research import EvidenceSnippet, ResearchResponse, ResearchTaskResult
from app.agents.judge_llm import judge_llm_completion
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

class ResearchScratchpad:
    def __init__(self):
        self.discovered_ips = []
        self.discovered_macs = []
        self.discovered_people = []

    def update(self, new_entities: dict):
        for k, v in new_entities.items():
            if hasattr(self, k):
                current = getattr(self, k)
                if isinstance(v, list):
                    current.extend(v)
                else:
                    current.append(v)
            else:
                setattr(self, k, v if isinstance(v, list) else [v])

async def _extract_entities_from_evidence(evidence: List[EvidenceSnippet]) -> dict:
    if not evidence:
        return {}
    text_blocks = "\n".join(e.chunk for e in evidence[:3])
    prompt = f"Extract key investigative entities (IP addresses, MAC addresses, Person names) from the following evidence.\\n\\n{text_blocks}\\n\\nReturn EXACTLY a JSON object with keys like 'discovered_ips', 'discovered_macs', 'discovered_people'. Each should map to a list of strings."
    try:
        raw = await judge_llm_completion("You are an extraction assistant.", prompt, response_format={"type": "json_object"})
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to extract entities: {e}")
        return {}



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
            # Prefer canonical evidence_type, but continue matching legacy raw
            # evidence_type values for documents ingested before normalization.
            clauses.append(
                or_(
                    meta_col["evidence_clerk"]["canonical_evidence_type"].astext == value,
                    meta_col["evidence_clerk"]["evidence_type"].astext == value,
                    label_col == value,
                )
            )
        else:
            clauses.append(meta_col[value].astext == value)
    return clauses


async def run_research(planner_resp: PlannerResponse) -> ResearchResponse:
    """Run research for all planner tasks and return structured evidence.

    This function is async. It handles execution order, scratchpad formatting,
    and entity extraction.
    """
    session: Session = get_session()
    tasks_results: List[ResearchTaskResult] = []
    scratchpad = ResearchScratchpad()

    # Sort tasks by dependency order so order 0 executes before order 1
    sorted_tasks = sorted(planner_resp.tasks, key=lambda t: t.dependency_order)

    try:
        for task in sorted_tasks:
            try:
                formatted_query = task.vector_query.format(scratchpad=scratchpad)
            except (KeyError, IndexError, AttributeError) as e:
                logger.warning(f"Task skipped due to missing dependency '{e}'")
                tasks_results.append(
                    ResearchTaskResult(
                        question_text=task.question_text,
                        vector_query=task.vector_query,
                        metadata_filter=task.metadata_filter,
                        evidence=[],
                    )
                )
                tasks_results[-1].notes = "SKIPPED_DUE_TO_MISSING_DEPENDENCY"
                continue

            # 1. Embed the vector query
            embeddings = await asyncio.to_thread(embed_texts, [formatted_query])
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

            if RESEARCH_METADATA_FILTER_ENABLED:
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

            # Executing query synchronously since it's blocking locally. 
            # In a true async stack this would use AsyncSession.
            rows = await asyncio.to_thread(session.execute, stmt)
            rows = rows.all()

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

            if evidence_items:
                extracted = await _extract_entities_from_evidence(evidence_items)
                scratchpad.update(extracted)

            tasks_results.append(
                ResearchTaskResult(
                    question_text=task.question_text,
                    vector_query=formatted_query,
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
