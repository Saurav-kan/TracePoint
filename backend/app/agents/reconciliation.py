"""Reconciliation agent: arbitrates conflict between Judge and Challenger."""

import json
import logging
from typing import Optional, List

from app.db.models import Case
from app.schemas.judge import JudgeResponse, JudgeTaskFact
from app.schemas.challenger import ChallengerResponse
from app.schemas.reconciliation import ReconciliationResponse
from app.agents.judge_llm import judge_llm_completion
from app.agents import reconciliation_templates

logger = logging.getLogger(__name__)

async def run_reconciliation(
    judge_resp: JudgeResponse,
    challenger_resp: ChallengerResponse,
    case: Optional[Case] = None,
    case_brief_override: Optional[str] = None
) -> ReconciliationResponse:
    """Run the reconciliation arbiter to resolve the final verdict."""
    if not challenger_resp.has_disagreement or not challenger_resp.structured_disagreement:
        # No conflict to resolve, just confirm the Judge's verdict
        return ReconciliationResponse(
            case_id=judge_resp.case_id,
            verdict=judge_resp.overall_verdict.verdict,
            rationale=judge_resp.overall_verdict.rationale,
            supporting_facts=judge_resp.overall_verdict.supporting_facts,
            contradicting_facts=judge_resp.overall_verdict.contradicting_facts
        )
    
    case_brief = (
        case_brief_override if case_brief_override is not None
        else (case.case_brief_text if case else None)
    )

    case_block = f"CASE SUMMARY:\n{case_brief}\n\n" if case_brief else ""

    judge_context = (
        f"JUDGE VERDICT: {judge_resp.overall_verdict.verdict}\n"
        f"JUDGE RATIONALE:\n{judge_resp.overall_verdict.rationale}\n"
    )

    challenger_context = (
        f"CHALLENGER NARRATIVE:\n{challenger_resp.structured_disagreement.narrative}\n"
        f"OVER-WEIGHTED EVIDENCE CLAIM:\n{challenger_resp.structured_disagreement.over_weighted_evidence}\n"
    )

    user_content = (
        f"{case_block}CLAIM TO VERIFY:\n{judge_resp.fact_to_check}\n\n"
        f"{judge_context}\n"
        f"{challenger_context}\n"
        "Evaluate the dispute and return the reconciled final verdict based on the evidence hierarchy."
    )

    try:
        raw = await judge_llm_completion(
            reconciliation_templates.RECONCILIATION_SYSTEM_PROMPT,
            user_content,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw)
    except Exception as e:
        logger.error(f"Failed to run reconciliation LLM: {e}")
        return ReconciliationResponse(
            case_id=judge_resp.case_id,
            verdict="uncertain",
            rationale="Reconciliation failed to parse. Underlying conflict remains unresolved. Both narratives exist.",
            supporting_facts=[],
            contradicting_facts=[]
        )
    
    verdict = str(data.get("verdict", "uncertain")).lower()
    if verdict not in ("true", "likely_true", "uncertain", "likely_false", "false"):
        verdict = "uncertain"
        
    def _parse_facts(fact_list) -> List[JudgeTaskFact]:
        parsed = []
        for f in fact_list:
            if isinstance(f, dict):
                parsed.append(JudgeTaskFact(
                    description=str(f.get("description", "")),
                    supports_claim=bool(f.get("supports_claim", True)),
                    source_task_index=int(f.get("source_task_index", 0)),
                    evidence_indices=[int(x) for x in f.get("evidence_indices", []) if isinstance(x, int)]
                ))
        return parsed
        
    supporting = _parse_facts(data.get("supporting_facts", []))
    contradicting = _parse_facts(data.get("contradicting_facts", []))

    return ReconciliationResponse(
        case_id=judge_resp.case_id,
        verdict=verdict, # type: ignore
        rationale=str(data.get("rationale", "No rationale provided.")),
        supporting_facts=supporting,
        contradicting_facts=contradicting
    )
