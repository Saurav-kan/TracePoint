"""Proof-tester agent: stress-tests key facts via vector search and adjusts the verdict."""

from __future__ import annotations

import json
import logging
from typing import List, Optional
from uuid import UUID

from app.agents.judge_llm import judge_llm_completion
from app.agents.proof_tester_templates import (
    PROOF_ADJUSTER_SYSTEM,
    PROOF_FACT_SELECTOR_SYSTEM,
    PROOF_QUERY_GENERATOR_SYSTEM,
    PROOF_VALIDATOR_SYSTEM,
)
from app.agents.research_agent import run_proof_research
from app.schemas.judge import JudgeTaskFact
from app.schemas.reconciliation import ReconciliationResponse
from app.schemas.proof_tester import (
    ProofFactSelection,
    ProofQuerySet,
    ProofTestResult,
    ProofValidationResult,
)

logger = logging.getLogger(__name__)


def _parse_fact(d: dict) -> JudgeTaskFact:
    """Parse a fact from JSON/dict."""
    return JudgeTaskFact(
        description=str(d.get("description", "")),
        supports_claim=bool(d.get("supports_claim", True)),
        source_task_index=int(d.get("source_task_index", 0)),
        evidence_indices=[int(x) for x in d.get("evidence_indices", []) if isinstance(x, int)],
    )


async def _select_facts(
    claim: str,
    supporting_facts: List[JudgeTaskFact],
    contradicting_facts: List[JudgeTaskFact],
    case_brief: Optional[str] = None,
) -> ProofFactSelection:
    """Step 1: Select top 2 supporting and top 2 contradicting facts."""
    support_str = "\n".join(
        f"[{i}] {f.description}" for i, f in enumerate(supporting_facts)
    )
    contra_str = "\n".join(
        f"[{i}] {f.description}" for i, f in enumerate(contradicting_facts)
    )
    brief_block = f"CASE BRIEF:\n{case_brief}\n\n" if case_brief else ""
    user = (
        f"{brief_block}CLAIM TO VERIFY:\n{claim}\n\n"
        f"SUPPORTING FACTS:\n{support_str or '(none)'}\n\n"
        f"CONTRADICTING FACTS:\n{contra_str or '(none)'}\n\n"
        "Which 2 supporting and 2 contradicting facts are strongest for proof-testing?"
    )
    raw = await judge_llm_completion(
        PROOF_FACT_SELECTOR_SYSTEM,
        user,
        response_format={"type": "json_object"},
    )
    data = json.loads(raw)
    sup_idx = data.get("supporting_indices", [])
    contra_idx = data.get("contradicting_indices", [])
    if not isinstance(sup_idx, list):
        sup_idx = []
    if not isinstance(contra_idx, list):
        contra_idx = []
    sup_idx = [int(x) for x in sup_idx if isinstance(x, (int, float))][:2]
    contra_idx = [int(x) for x in contra_idx if isinstance(x, (int, float))][:2]
    return ProofFactSelection(
        supporting_indices=sup_idx,
        contradicting_indices=contra_idx,
    )


async def _generate_queries(
    claim: str,
    selected: ProofFactSelection,
    supporting_facts: List[JudgeTaskFact],
    contradicting_facts: List[JudgeTaskFact],
) -> List[ProofQuerySet]:
    """Step 2: Generate 3 vector queries per selected fact."""
    facts_with_meta: List[tuple[int, str, bool]] = []
    for i in selected.supporting_indices:
        if 0 <= i < len(supporting_facts):
            facts_with_meta.append((i, supporting_facts[i].description, True))
    for i in selected.contradicting_indices:
        if 0 <= i < len(contradicting_facts):
            facts_with_meta.append((i, contradicting_facts[i].description, False))

    if not facts_with_meta:
        return []

    fact_desc = "\n".join(
        f"fact_{j}: {desc} (supports={supp})"
        for j, (_, desc, supp) in enumerate(facts_with_meta)
    )
    user = (
        f"CLAIM: {claim}\n\nFACTS TO VALIDATE:\n{fact_desc}\n\n"
        "Generate 3 vector queries per fact to validate or falsify it."
    )
    raw = await judge_llm_completion(
        PROOF_QUERY_GENERATOR_SYSTEM,
        user,
        response_format={"type": "json_object"},
    )
    data = json.loads(raw)
    query_sets: List[ProofQuerySet] = []
    for j, (orig_idx, desc, supp) in enumerate(facts_with_meta):
        key = f"fact_{j}"
        qs = data.get(key)
        if isinstance(qs, list):
            queries = [str(q) for q in qs[:3]]
        else:
            queries = []
        query_sets.append(
            ProofQuerySet(
                fact_index=orig_idx,
                fact_description=desc,
                supports_claim=supp,
                queries=queries,
            )
        )
    return query_sets


async def _validate_fact(
    fact: JudgeTaskFact,
    fact_index: int,
    supports_claim: bool,
    evidence_list: List,
) -> ProofValidationResult:
    """Step 4: Validate a single fact against its retrieval results."""
    evidence_text = ""
    if evidence_list:
        chunks = [
            e.chunk if hasattr(e, "chunk") else str(e)
            for e in evidence_list
            if hasattr(e, "chunk") or e
        ]
        evidence_text = "\n---\n".join(chunks[:10])
    if not evidence_text:
        evidence_text = "(No evidence retrieved)"

    user = (
        f"FACT: {fact.description}\n"
        f"SUPPORTS CLAIM: {supports_claim}\n\n"
        f"RETRIEVED EVIDENCE:\n{evidence_text}\n\n"
        "Is this fact validated, invalidated, or partially_validated?"
    )
    raw = await judge_llm_completion(
        PROOF_VALIDATOR_SYSTEM,
        user,
        response_format={"type": "json_object"},
    )
    data = json.loads(raw)
    status = str(data.get("status", "partially_validated")).lower()
    if status not in ("validated", "invalidated", "partially_validated"):
        status = "partially_validated"
    retrieval_summary = str(data.get("retrieval_summary", ""))
    replacement = None
    if status == "invalidated":
        rep = data.get("replacement_fact")
        if isinstance(rep, dict):
            replacement = _parse_fact(rep)

    return ProofValidationResult(
        fact=fact,
        fact_index=fact_index,
        supports_claim=supports_claim,
        status=status,
        replacement_fact=replacement,
        retrieval_summary=retrieval_summary,
    )


async def run_proof_test(
    reconciliation_result: ReconciliationResponse,
    claim: str,
    case_id: UUID,
    case_brief: Optional[str] = None,
) -> tuple[ProofTestResult, ReconciliationResponse]:
    """Run the full proof-test pass and return (ProofTestResult, adjusted ReconciliationResponse)."""

    supporting = reconciliation_result.supporting_facts
    contradicting = reconciliation_result.contradicting_facts

    # Step 1: Select facts
    selection = await _select_facts(claim, supporting, contradicting, case_brief)

    # Step 2: Generate queries
    query_sets = await _generate_queries(
        claim, selection, supporting, contradicting
    )
    all_queries: List[str] = []
    for qs in query_sets:
        all_queries.extend(qs.queries)

    # Step 3: Research
    evidence_per_query: List[List] = []
    if all_queries:
        evidence_per_query = await run_proof_research(case_id, all_queries)

    # Build evidence per fact (3 queries per fact)
    idx = 0
    validated_supporting: List[JudgeTaskFact] = []
    validated_contradicting: List[JudgeTaskFact] = []
    invalidated_supporting: List[ProofValidationResult] = []
    invalidated_contradicting: List[ProofValidationResult] = []
    replacements: List[JudgeTaskFact] = []

    for qs in query_sets:
        ev_for_fact: List = []
        for _ in qs.queries:
            if idx < len(evidence_per_query):
                ev_for_fact.extend(evidence_per_query[idx])
            idx += 1

        fact = None
        if qs.supports_claim and 0 <= qs.fact_index < len(supporting):
            fact = supporting[qs.fact_index]
        elif not qs.supports_claim and 0 <= qs.fact_index < len(contradicting):
            fact = contradicting[qs.fact_index]

        if fact is None:
            continue

        # Step 4: Validate
        val = await _validate_fact(
            fact, qs.fact_index, qs.supports_claim, ev_for_fact
        )

        if val.status == "validated":
            if qs.supports_claim:
                validated_supporting.append(fact)
            else:
                validated_contradicting.append(fact)
        elif val.status == "invalidated":
            if qs.supports_claim:
                invalidated_supporting.append(val)
                if val.replacement_fact:
                    replacements.append(val.replacement_fact)
            else:
                invalidated_contradicting.append(val)
                if val.replacement_fact:
                    replacements.append(val.replacement_fact)
        # partially_validated: add original to validated lists (keep as-is)
        else:
            if qs.supports_claim:
                validated_supporting.append(fact)
            else:
                validated_contradicting.append(fact)

    # Build updated fact sets for adjuster: validated + replacements for invalidated
    final_supporting: List[JudgeTaskFact] = list(validated_supporting)
    final_contradicting: List[JudgeTaskFact] = list(validated_contradicting)
    for v in invalidated_supporting:
        if v.replacement_fact:
            if v.replacement_fact.supports_claim:
                final_supporting.append(v.replacement_fact)
            else:
                final_contradicting.append(v.replacement_fact)
    for v in invalidated_contradicting:
        if v.replacement_fact:
            if not v.replacement_fact.supports_claim:
                final_contradicting.append(v.replacement_fact)
            else:
                final_supporting.append(v.replacement_fact)

    # Step 6: Adjust verdict
    user = (
        f"CLAIM: {claim}\n\n"
        f"ORIGINAL VERDICT: {reconciliation_result.verdict}\n"
        f"ORIGINAL RATIONALE: {reconciliation_result.rationale}\n\n"
        f"VALIDATED SUPPORTING: {len(validated_supporting)}\n"
        f"VALIDATED CONTRADICTING: {len(validated_contradicting)}\n"
        f"INVALIDATED SUPPORTING: {len(invalidated_supporting)}\n"
        f"INVALIDATED CONTRADICTING: {len(invalidated_contradicting)}\n"
        f"REPLACEMENTS: {len(replacements)}\n\n"
        "Produce the final proof-adjusted verdict."
    )
    raw = await judge_llm_completion(
        PROOF_ADJUSTER_SYSTEM,
        user,
        response_format={"type": "json_object"},
    )
    data = json.loads(raw)
    verdict = str(data.get("verdict", reconciliation_result.verdict)).lower()
    if verdict not in ("true", "likely_true", "uncertain", "likely_false", "false"):
        verdict = reconciliation_result.verdict
    rationale = str(data.get("rationale", reconciliation_result.rationale))
    sup_facts = [_parse_fact(f) for f in data.get("supporting_facts", []) if isinstance(f, dict)]
    contra_facts = [_parse_fact(f) for f in data.get("contradicting_facts", []) if isinstance(f, dict)]
    if not sup_facts:
        sup_facts = final_supporting
    if not contra_facts:
        contra_facts = final_contradicting

    adjusted = ReconciliationResponse(
        case_id=reconciliation_result.case_id,
        verdict=verdict,
        rationale=rationale,
        supporting_facts=sup_facts,
        contradicting_facts=contra_facts,
    )

    proof_result = ProofTestResult(
        validated_supporting=validated_supporting,
        validated_contradicting=validated_contradicting,
        invalidated_supporting=invalidated_supporting,
        invalidated_contradicting=invalidated_contradicting,
        replacements=replacements,
        adjusted_verdict=adjusted.model_dump(),
    )

    return proof_result, adjusted