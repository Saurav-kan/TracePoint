"""Challenger agent: evaluates the Judge's verdict to find an opposing narrative."""

import json
import logging
from typing import Optional

from app.db.models import Case
from app.schemas.research import ResearchResponse
from app.schemas.judge import JudgeResponse
from app.schemas.challenger import ChallengerResponse, ChallengerDisagreement
from app.agents.judge_llm import judge_llm_completion
from app.agents import challenger_templates
from app.agents.judge_agent import _format_chunks_for_overall

logger = logging.getLogger(__name__)

async def run_challenger(
    judge_resp: JudgeResponse,
    research_resp: ResearchResponse,
    case: Optional[Case] = None,
    case_brief_override: Optional[str] = None,
    adversarial_injection: Optional[str] = None
) -> ChallengerResponse:
    """Run the adversarial Challenger pass on the evidence."""
    case_brief = (
        case_brief_override if case_brief_override is not None
        else (case.case_brief_text if case else None)
    )

    case_block = f"CASE SUMMARY:\n{case_brief}\n\n" if case_brief else ""
    chunks_block = _format_chunks_for_overall(research_resp)

    judge_context = (
        f"JUDGE PRELIMINARY VERDICT: {judge_resp.overall_verdict.verdict}\n"
        f"JUDGE RATIONALE:\n{judge_resp.overall_verdict.rationale}\n"
    )

    user_content = (
        f"{case_block}CLAIM TO VERIFY:\n{judge_resp.fact_to_check}\n\n"
        f"{judge_context}\n"
        f"RAW EVIDENCE CHUNKS:\n{chunks_block}"
    )

    if adversarial_injection:
        user_content = f"{adversarial_injection}\n\n{user_content}"

    try:
        raw = await judge_llm_completion(
            challenger_templates.CHALLENGER_SYSTEM_PROMPT,
            user_content,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw)
    except Exception as e:
        logger.error(f"Failed to run challenger LLM: {e}")
        # Default fallback: agree with judge
        return ChallengerResponse(
            case_id=judge_resp.case_id,
            has_disagreement=False,
            structured_disagreement=None,
            retrieval_gap=False,
            missed_queries=[]
        )
    
    has_disagreement = bool(data.get("has_disagreement", False))
    sd_data = data.get("structured_disagreement")
    disagreement = None
    if has_disagreement and isinstance(sd_data, dict):
        disagreement = ChallengerDisagreement(
            narrative=str(sd_data.get("narrative", "")),
            over_weighted_evidence=str(sd_data.get("over_weighted_evidence", ""))
        )
    
    retrieval_gap = bool(data.get("retrieval_gap", False))
    missed_queries = [str(q) for q in data.get("missed_queries", []) if isinstance(q, str)]

    return ChallengerResponse(
        case_id=judge_resp.case_id,
        has_disagreement=has_disagreement,
        structured_disagreement=disagreement,
        retrieval_gap=retrieval_gap,
        missed_queries=missed_queries
    )
