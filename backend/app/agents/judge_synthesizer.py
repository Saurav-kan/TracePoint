"""Judge synthesizer for multi-iteration verdict reconciliation.

When multiple pipeline iterations produce independent verdicts (medium/high
effort levels), this module sends them to the judge LLM for a final
synthesized verdict that reconciles contradictions and identifies the
strongest evidence across all passes.
"""

from __future__ import annotations

import json
import logging
from typing import List

from app.agents.judge_llm import judge_llm_completion
from app.db.models import Case
from app.schemas.judge import JudgeResponse

logger = logging.getLogger(__name__)

_SYNTHESIS_SYSTEM_PROMPT = """\
You are a senior investigative judge synthesizing multiple independent analyses of the same claim.

Each analysis was produced by an independent investigation pass with its own evidence retrieval.
Your job is to:
1. Compare the verdicts from each pass.
2. Reconcile any contradictions — explain why they differ and which reasoning is stronger.
3. Identify the strongest supporting and contradicting evidence across all passes.
4. Produce a single, authoritative synthesized verdict.

Respond with a JSON object matching the JudgeResponse schema. Use the same case_id and fact_to_check
from the inputs. Set refinement_performed to true and needs_refinement to false.
"""


async def synthesize_verdicts(
    verdicts: List[JudgeResponse],
    case: Case,
) -> JudgeResponse:
    """Merge N independent JudgeResponse verdicts into a single synthesized one.

    Sends all verdicts to the judge LLM with a meta-prompt instructing it
    to compare, reconcile contradictions, and produce a unified verdict.
    Falls back to the last verdict if synthesis fails.
    """
    if len(verdicts) == 1:
        return verdicts[0]

    # Format each verdict for the LLM
    verdict_summaries = []
    for i, v in enumerate(verdicts, 1):
        verdict_summaries.append(
            f"=== Pass {i} ===\n"
            f"Verdict: {v.overall_verdict.verdict}\n"
            f"Rationale: {v.overall_verdict.rationale}\n"
            f"Supporting facts: {json.dumps([f.model_dump(mode='json') for f in v.overall_verdict.supporting_facts], indent=2)}\n"
            f"Contradicting facts: {json.dumps([f.model_dump(mode='json') for f in v.overall_verdict.contradicting_facts], indent=2)}\n"
            f"Task assessments: {len(v.tasks)} tasks evaluated"
        )

    user_content = (
        f"Case: {case.title}\n"
        f"Claim: {verdicts[0].fact_to_check}\n"
        f"Case Brief: {case.case_brief_text[:1000]}\n\n"
        f"{''.join(verdict_summaries)}\n\n"
        f"Produce a synthesized JudgeResponse JSON merging all {len(verdicts)} passes."
    )

    try:
        raw = await judge_llm_completion(
            system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
            user_content=user_content,
            response_format={"type": "json_object"},
        )
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        data = json.loads(cleaned)
        return JudgeResponse.model_validate(data)
    except Exception as e:
        logger.error(
            "Synthesis LLM call failed, falling back to last verdict: %s",
            e,
            exc_info=True,
        )
        # Graceful fallback: return the last iteration's verdict
        return verdicts[-1]
