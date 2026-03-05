"""Judge agent: synthesize research evidence into a verdict.

This first iteration is intentionally simple and deterministic: it does
not call an external LLM yet. Instead, it inspects the research results,
marks questions as sufficiently or insufficiently supported, extracts
basic facts, and produces an aggregate verdict. The structure is
designed so that an LLM-powered implementation can be plugged in later
without breaking the public interface.
"""

from __future__ import annotations

from typing import List

from app.db.models import Case
from app.schemas.judge import (
    JudgeOverallVerdict,
    JudgeResponse,
    JudgeTaskAssessment,
    JudgeTaskFact,
)
from app.schemas.research import ResearchResponse, ResearchTaskResult


def _build_task_assessment(
    task_index: int, task: ResearchTaskResult, claim: str
) -> JudgeTaskAssessment:
    """Create a simple heuristic assessment for a single research task.

    Heuristics:
    - If there is no evidence, mark the task as insufficient.
    - If there is at least one evidence snippet, consider the task
      sufficiently supported and create one fact per snippet that
      supports the claim.
    """
    if not task.evidence:
        return JudgeTaskAssessment(
            question_text=task.question_text,
            answer="Insufficient evidence retrieved to answer this question.",
            sufficient_evidence=False,
            confidence=0.0,
            key_facts=[],
            notes="No evidence snippets were returned for this task.",
        )

    key_facts: List[JudgeTaskFact] = []
    for idx, snippet in enumerate(task.evidence):
        # Truncate the chunk for a concise fact description.
        snippet_text = snippet.chunk.strip()
        if len(snippet_text) > 240:
            snippet_text = snippet_text[:237].rstrip() + "..."

        fact_description = (
            f"Evidence snippet {idx} from {snippet.source_document or 'unknown source'}: "
            f"{snippet_text}"
        )
        key_facts.append(
            JudgeTaskFact(
                description=fact_description,
                supports_claim=True,
                source_task_index=task_index,
                evidence_indices=[idx],
            )
        )

    answer = (
        "Available evidence snippets provide at least some support relevant to this question. "
        "A more sophisticated judge agent could weigh reliability and contradictions, but this "
        "baseline assumes the retrieved snippets are supportive."
    )

    return JudgeTaskAssessment(
        question_text=task.question_text,
        answer=answer,
        sufficient_evidence=True,
        confidence=0.5,
        key_facts=key_facts,
        notes=None,
    )


def _build_overall_verdict(
    claim: str, task_assessments: List[JudgeTaskAssessment]
) -> JudgeOverallVerdict:
    """Aggregate per-task assessments into a coarse overall verdict."""
    if not task_assessments:
        return JudgeOverallVerdict(
            claim=claim,
            verdict="uncertain",
            rationale="No tasks were available for judgment.",
            supporting_facts=[],
            contradicting_facts=[],
        )

    supported = [t for t in task_assessments if t.sufficient_evidence]
    unsupported = [t for t in task_assessments if not t.sufficient_evidence]

    if not supported:
        verdict = "uncertain"
        rationale = (
            "None of the investigative questions had sufficient evidence, so the claim "
            "cannot be confidently verified or falsified."
        )
    else:
        # For now, if we have at least one supported task, lean toward likely_true.
        verdict = "likely_true"
        rationale = (
            "At least one investigative question had supporting evidence. A more advanced "
            "judge would consider reliability and contradictions, but this baseline treats "
            "supported tasks as leaning the claim toward being true."
        )

    supporting_facts: List[JudgeTaskFact] = []
    contradicting_facts: List[JudgeTaskFact] = []
    for ta in supported:
        supporting_facts.extend(ta.key_facts)
    # This baseline does not derive explicit contradicting facts yet.

    return JudgeOverallVerdict(
        claim=claim,
        verdict=verdict,
        rationale=rationale,
        supporting_facts=supporting_facts,
        contradicting_facts=contradicting_facts,
    )


def run_judge(
    research_resp: ResearchResponse,
    case: Case | None = None,
    *,
    refinement_allowed: bool = True,  # noqa: ARG001 - reserved for future use
) -> JudgeResponse:
    """Run the judge agent over a ResearchResponse and optional Case.

    This baseline implementation:
    - Produces a JudgeTaskAssessment for each research task.
    - Marks tasks with no evidence as insufficient.
    - Aggregates assessments into a coarse overall verdict.
    - Does not yet perform an automatic refinement loop; instead it can
      emit a refinement_suggestion string when overall evidence is weak.
    """
    task_assessments: List[JudgeTaskAssessment] = []
    for idx, task in enumerate(research_resp.tasks):
        task_assessments.append(_build_task_assessment(idx, task, research_resp.fact_to_check))

    overall_verdict = _build_overall_verdict(
        claim=research_resp.fact_to_check,
        task_assessments=task_assessments,
    )

    # Simple refinement heuristic: if all tasks lack sufficient evidence,
    # suggest that additional planner/research passes may be needed.
    refinement_suggestion = None
    if all(not ta.sufficient_evidence for ta in task_assessments):
        refinement_suggestion = (
            "Most investigative questions lacked sufficient evidence. Consider running an "
            "additional planner + research iteration with adjusted metadata filters or new "
            "evidence sources."
        )

    return JudgeResponse(
        case_id=research_resp.case_id,
        fact_to_check=research_resp.fact_to_check,
        tasks=task_assessments,
        overall_verdict=overall_verdict,
        refinement_performed=False,
        refinement_suggestion=refinement_suggestion,
    )

