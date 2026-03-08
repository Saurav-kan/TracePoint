"""Judge agent: synthesize research evidence into a verdict.

Supports heuristic (no LLM) and LLM modes. When JUDGE_PROVIDER is groq or
siliconflow, uses a two-phase LLM workflow: per-task assessment then overall
verdict. When JUDGE_PROVIDER is none, uses deterministic heuristics.

Both paths populate needs_refinement / refinement_questions so the graph
can route to a supplemental research pass when evidence is insufficient.
"""

from __future__ import annotations

import json
from typing import List, Tuple

from app.config import JUDGE_FINAL_VIEW_CHUNKS, JUDGE_PROVIDER
from app.db.models import Case
from app.schemas.judge import (
    JudgeOverallVerdict,
    JudgeResponse,
    JudgeTaskAssessment,
    JudgeTaskFact,
)
from app.schemas.research import EvidenceSnippet, ResearchResponse, ResearchTaskResult

from app.agents.judge_gatekeeper import validate_judge_output
from app.agents.judge_llm import judge_llm_completion
from app.agents import judge_templates


def _format_evidence_snippet(snippet: EvidenceSnippet) -> str:
    """Format a single snippet as [source] before | chunk | after."""
    parts = []
    if snippet.chunk_before:
        parts.append(snippet.chunk_before.strip())
    parts.append(snippet.chunk.strip())
    if snippet.chunk_after:
        parts.append(snippet.chunk_after.strip())
    body = " | ".join(parts)
    source = snippet.source_document or "unknown"
    return f"[{source}]\n{body}"


def _format_evidence_for_task(task: ResearchTaskResult) -> str:
    """Format all evidence snippets for a task as a block for the prompt."""
    lines = []
    for i, s in enumerate(task.evidence):
        lines.append(f"--- Snippet {i} ---")
        lines.append(_format_evidence_snippet(s))
    return "\n".join(lines) if lines else "(No evidence)"


def _build_task_assessment(
    task_index: int, task: ResearchTaskResult, claim: str
) -> JudgeTaskAssessment:
    """Create a heuristic assessment (no LLM) for a single research task."""
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

    return JudgeTaskAssessment(
        question_text=task.question_text,
        answer=(
            "Available evidence snippets provide at least some support relevant to this question. "
            "A more sophisticated judge agent could weigh reliability and contradictions, but this "
            "baseline assumes the retrieved snippets are supportive."
        ),
        sufficient_evidence=True,
        confidence=0.5,
        key_facts=key_facts,
        notes=None,
    )


async def _build_task_assessment_llm(
    task_index: int,
    task: ResearchTaskResult,
    claim: str,
    case_brief: str | None,
) -> JudgeTaskAssessment:
    """Use LLM to assess a single task. Fall back to heuristic on parse failure."""
    if not task.evidence:
        return _build_task_assessment(task_index, task, claim)

    evidence_block = _format_evidence_for_task(task)
    case_block = f"CASE SUMMARY:\n{case_brief}\n\n" if case_brief else ""
    user_content = (
        f"{case_block}CLAIM TO VERIFY:\n{claim}\n\n"
        f"INVESTIGATIVE QUESTION:\n{task.question_text}\n\n"
        f"EVIDENCE:\n{evidence_block}"
    )

    try:
        raw = await judge_llm_completion(
            judge_templates.JUDGE_TASK_SYSTEM_PROMPT,
            user_content,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, KeyError):
        return _build_task_assessment(task_index, task, claim)

    max_idx = len(task.evidence) - 1 if task.evidence else -1
    key_facts: List[JudgeTaskFact] = []
    for kf in data.get("key_facts", []):
        if isinstance(kf, dict) and "description" in kf:
            raw_indices = kf.get("evidence_indices", [])
            evidence_indices: List[int] = []
            if isinstance(raw_indices, list) and max_idx >= 0:
                for x in raw_indices:
                    if isinstance(x, int) and 0 <= x <= max_idx:
                        evidence_indices.append(x)
            key_facts.append(
                JudgeTaskFact(
                    description=str(kf["description"]),
                    supports_claim=bool(kf.get("supports_claim", True)),
                    source_task_index=task_index,
                    evidence_indices=evidence_indices,
                )
            )

    return JudgeTaskAssessment(
        question_text=task.question_text,
        answer=str(data.get("answer", "No answer provided.")),
        sufficient_evidence=bool(data.get("sufficient_evidence", False)),
        confidence=float(data.get("confidence", 0.5)),
        key_facts=key_facts,
        notes=str(data["notes"]) if data.get("notes") else None,
    )


def _build_overall_verdict(
    claim: str, task_assessments: List[JudgeTaskAssessment]
) -> JudgeOverallVerdict:
    """Heuristic overall verdict (no LLM)."""
    if not task_assessments:
        return JudgeOverallVerdict(
            claim=claim,
            verdict="uncertain",
            rationale="No tasks were available for judgment.",
            supporting_facts=[],
            contradicting_facts=[],
        )

    supported = [t for t in task_assessments if t.sufficient_evidence]
    if not supported:
        return JudgeOverallVerdict(
            claim=claim,
            verdict="uncertain",
            rationale=(
                "None of the investigative questions had sufficient evidence, so the claim "
                "cannot be confidently verified or falsified."
            ),
            supporting_facts=[],
            contradicting_facts=[],
        )

    supporting_facts: List[JudgeTaskFact] = []
    for ta in supported:
        supporting_facts.extend(ta.key_facts)

    return JudgeOverallVerdict(
        claim=claim,
        verdict="likely_true",
        rationale=(
            "At least one investigative question had supporting evidence. A more advanced "
            "judge would consider reliability and contradictions, but this baseline treats "
            "supported tasks as leaning the claim toward being true."
        ),
        supporting_facts=supporting_facts,
        contradicting_facts=[],
    )


def _format_assessments_for_overall(
    task_assessments: List[JudgeTaskAssessment],
) -> str:
    """Format per-task assessments for the overall verdict prompt."""
    lines = []
    for i, ta in enumerate(task_assessments):
        lines.append(f"--- Task {i}: {ta.question_text} ---")
        lines.append(f"Answer: {ta.answer}")
        lines.append(f"Sufficient evidence: {ta.sufficient_evidence}")
        lines.append(f"Confidence: {ta.confidence}")
        for kf in ta.key_facts:
            lines.append(f"  Fact: {kf.description} (supports_claim={kf.supports_claim})")
        if ta.notes:
            lines.append(f"Notes: {ta.notes}")
        lines.append("")
    return "\n".join(lines).strip()


def _format_chunks_for_overall(research_resp: ResearchResponse) -> str:
    """Format all evidence chunks for the overall verdict (if JUDGE_FINAL_VIEW_CHUNKS)."""
    lines = []
    for ti, task in enumerate(research_resp.tasks):
        lines.append(f"--- Task {ti}: {task.question_text} ---")
        lines.append(_format_evidence_for_task(task))
        lines.append("")
    return "\n".join(lines).strip()


async def _build_overall_verdict_llm(
    claim: str,
    task_assessments: List[JudgeTaskAssessment],
    research_resp: ResearchResponse,
    case_brief: str | None,
) -> Tuple[JudgeOverallVerdict, bool, List[str]]:
    """Use LLM for overall verdict. Fall back to heuristic on parse failure.

    Returns (verdict, needs_refinement, refinement_questions).
    """
    assessments_block = _format_assessments_for_overall(task_assessments)
    case_block = f"CASE SUMMARY:\n{case_brief}\n\n" if case_brief else ""

    user_content = (
        f"{case_block}CLAIM TO VERIFY:\n{claim}\n\n"
        f"PER-TASK ASSESSMENTS:\n{assessments_block}"
    )

    if JUDGE_FINAL_VIEW_CHUNKS:
        chunks_block = _format_chunks_for_overall(research_resp)
        user_content += f"\n\nRAW EVIDENCE CHUNKS:\n{chunks_block}"

    try:
        raw = await judge_llm_completion(
            judge_templates.JUDGE_OVERALL_SYSTEM_PROMPT,
            user_content,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, KeyError):
        verdict = _build_overall_verdict(claim, task_assessments)
        needs, questions = _derive_heuristic_refinement(task_assessments)
        return verdict, needs, questions

    supporting: List[JudgeTaskFact] = []
    for kf in data.get("supporting_facts", []):
        if isinstance(kf, dict) and "description" in kf:
            supporting.append(
                JudgeTaskFact(
                    description=str(kf["description"]),
                    supports_claim=True,
                    source_task_index=0,
                    evidence_indices=[],
                )
            )
    contradicting: List[JudgeTaskFact] = []
    for kf in data.get("contradicting_facts", []):
        if isinstance(kf, dict) and "description" in kf:
            contradicting.append(
                JudgeTaskFact(
                    description=str(kf["description"]),
                    supports_claim=False,
                    source_task_index=0,
                    evidence_indices=[],
                )
            )

    verdict_raw = str(data.get("verdict", "uncertain")).lower()
    if verdict_raw not in ("true", "likely_true", "uncertain", "likely_false", "false"):
        verdict_raw = "uncertain"

    verdict = JudgeOverallVerdict(
        claim=claim,
        verdict=verdict_raw,
        rationale=str(data.get("rationale", "No rationale provided.")),
        supporting_facts=supporting,
        contradicting_facts=contradicting,
    )

    # Parse refinement fields from LLM response
    needs_refinement = bool(data.get("needs_refinement", False))
    raw_questions = data.get("refinement_questions", [])
    refinement_questions: List[str] = [
        str(q) for q in raw_questions if isinstance(q, str)
    ][:3]

    return verdict, needs_refinement, refinement_questions


def _derive_heuristic_refinement(
    task_assessments: List[JudgeTaskAssessment],
) -> Tuple[bool, List[str]]:
    """Derive refinement signal from heuristic assessments.

    If any task has insufficient evidence, flag refinement and use the
    question_text of the first 1-3 insufficient tasks as refinement questions.
    """
    insufficient = [
        ta for ta in task_assessments if not ta.sufficient_evidence
    ]
    if not insufficient:
        return False, []
    questions = [ta.question_text for ta in insufficient[:3]]
    return True, questions


async def run_judge(
    research_resp: ResearchResponse,
    case: Case | None = None,
    *,
    case_brief_override: str | None = None,
    refinement_performed: bool = False,
) -> JudgeResponse:
    """Run the judge agent over a ResearchResponse and optional Case.

    When JUDGE_PROVIDER is groq or siliconflow, uses LLM for per-task and
    overall verdict. When JUDGE_PROVIDER is none, uses heuristic logic.
    If case_brief_override is set, use it instead of case.case_brief_text.
    """
    case_brief = (
        case_brief_override
        if case_brief_override is not None
        else (case.case_brief_text if case else None)
    )

    needs_refinement = False
    refinement_questions: List[str] = []

    if JUDGE_PROVIDER in ("groq", "siliconflow"):
        # LLM path: Phase 1 per-task, Phase 2 overall
        task_assessments: List[JudgeTaskAssessment] = []
        for idx, task in enumerate(research_resp.tasks):
            ta = await _build_task_assessment_llm(
                idx, task, research_resp.fact_to_check, case_brief
            )
            task_assessments.append(ta)

        overall_verdict, needs_refinement, refinement_questions = (
            await _build_overall_verdict_llm(
                research_resp.fact_to_check,
                task_assessments,
                research_resp,
                case_brief,
            )
        )
    else:
        # Heuristic path
        task_assessments = [
            _build_task_assessment(idx, task, research_resp.fact_to_check)
            for idx, task in enumerate(research_resp.tasks)
        ]
        overall_verdict = _build_overall_verdict(
            research_resp.fact_to_check, task_assessments
        )
        needs_refinement, refinement_questions = _derive_heuristic_refinement(
            task_assessments
        )

    refinement_suggestion = None
    if all(not ta.sufficient_evidence for ta in task_assessments):
        refinement_suggestion = (
            "Most investigative questions lacked sufficient evidence. Consider running an "
            "additional planner + research iteration with adjusted metadata filters or new "
            "evidence sources."
        )

    resp = JudgeResponse(
        case_id=research_resp.case_id,
        fact_to_check=research_resp.fact_to_check,
        tasks=task_assessments,
        overall_verdict=overall_verdict,
        refinement_performed=refinement_performed,
        refinement_suggestion=refinement_suggestion,
        needs_refinement=needs_refinement,
        refinement_questions=refinement_questions,
    )
    gate = validate_judge_output(resp, research_resp)
    return resp.model_copy(
        update={
            "gatekeeper_passed": gate.valid,
            "gatekeeper_reasons": gate.reasons,
        }
    )
