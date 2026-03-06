"""Gatekeeper for judge outputs.

Validates grounding (facts overlap with linked evidence), relevance
(answer-question, fact-claim), fact-evidence linking, and overall
verdict consistency.
"""
from typing import List, Set

from pydantic import BaseModel, Field

from app.config import JUDGE_GATEKEEPER_STRICT_LINKING
from app.schemas.judge import JudgeResponse, JudgeTaskAssessment, JudgeTaskFact
from app.schemas.research import ResearchResponse, ResearchTaskResult


class JudgeGatekeeperResult(BaseModel):
    valid: bool = Field(
        ..., description="Whether the judge output passed all validation checks"
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="Human-readable validation messages",
    )
    needs_regeneration: bool = Field(
        ...,
        description="If true, judge should retry and regenerate the output",
    )


def _significant_tokens(text: str) -> Set[str]:
    """Extract tokens of length >= 4, normalized to lowercase."""
    import re

    words = re.findall(r"\b\w{4,}\b", text.lower())
    return set(words)


def _check_grounding(
    fact: JudgeTaskFact,
    task: ResearchTaskResult,
) -> List[str]:
    """Check that fact description has meaningful lexical overlap with linked evidence.

    Requires at least 1 significant token from the fact to appear in the
    combined evidence text for the linked snippets.
    """
    if not fact.evidence_indices or not task.evidence:
        return []

    fact_tokens = _significant_tokens(fact.description)
    if len(fact_tokens) < 1:
        return []  # Very short fact, skip overlap check

    evidence_text_parts: List[str] = []
    for idx in fact.evidence_indices:
        if 0 <= idx < len(task.evidence):
            s = task.evidence[idx]
            for part in (s.chunk_before, s.chunk, s.chunk_after):
                if part:
                    evidence_text_parts.append(part)

    evidence_text = " ".join(evidence_text_parts)
    evidence_tokens = _significant_tokens(evidence_text)
    overlap = fact_tokens & evidence_tokens
    if len(overlap) >= 1:
        return []
    desc_preview = fact.description[:60] + ("..." if len(fact.description) > 60 else "")
    return [
        f"Fact '{desc_preview}' has insufficient overlap with "
        f"linked evidence (need 1+ significant token, got {len(overlap)})"
    ]


def _check_answer_question_relevance(
    assessment: JudgeTaskAssessment,
) -> List[str]:
    """Check that a substantive answer relates to the question."""
    answer_lower = assessment.answer.lower()
    if (
        "insufficient" in answer_lower
        or "cannot answer" in answer_lower
        or "no evidence" in answer_lower
        or "missing" in answer_lower
    ):
        return []  # Explicitly insufficient, no content to validate

    if not assessment.sufficient_evidence:
        return []

    q_tokens = _significant_tokens(assessment.question_text)
    a_tokens = _significant_tokens(assessment.answer)
    overlap = q_tokens & a_tokens
    if len(overlap) >= 2:
        return []
    return [
        f"Task answer has insufficient overlap with question "
        f"'{assessment.question_text[:50]}...'"
    ]


def _check_fact_relevance(
    fact: JudgeTaskFact,
    claim: str,
    question_text: str,
) -> List[str]:
    """Check that fact description shares at least one significant token with claim or question."""
    fact_tokens = _significant_tokens(fact.description)
    claim_tokens = _significant_tokens(claim)
    question_tokens = _significant_tokens(question_text)
    if fact_tokens & (claim_tokens | question_tokens):
        return []
    return [
        f"Fact '{fact.description[:50]}...' has no significant overlap with "
        "claim or question"
    ]


def _all_per_task_fact_descriptions(resp: JudgeResponse) -> Set[str]:
    """Collect all key fact descriptions from per-task assessments."""
    descs: Set[str] = set()
    for ta in resp.tasks:
        for kf in ta.key_facts:
            descs.add(kf.description.lower())
    return descs


def _fact_overlaps_per_task(
    fact_desc: str,
    per_task_descs: Set[str],
) -> bool:
    """Check if a fact description overlaps with any per-task key fact."""
    fact_tokens = _significant_tokens(fact_desc)
    if len(fact_tokens) < 2:
        return True  # Short fact, allow
    for other in per_task_descs:
        other_tokens = _significant_tokens(other)
        if len(fact_tokens & other_tokens) >= 1:
            return True
    return False


def validate_judge_output(
    resp: JudgeResponse,
    research_resp: ResearchResponse,
) -> JudgeGatekeeperResult:
    """Validate judge output for grounding, relevance, and consistency."""
    reasons: List[str] = []

    # 1. Answer-question relevance (per task)
    for ti, ta in enumerate(resp.tasks):
        for r in _check_answer_question_relevance(ta):
            reasons.append(f"Task {ti}: {r}")

    # 2. Fact-claim/question relevance (skip when fact is linked to evidence)
    for ti, ta in enumerate(resp.tasks):
        for fi, kf in enumerate(ta.key_facts):
            if kf.evidence_indices:
                continue  # Evidence-linked facts are treated as relevant
            for r in _check_fact_relevance(
                kf, resp.fact_to_check, ta.question_text
            ):
                reasons.append(f"Task {ti} fact {fi}: {r}")

    # 3. Fact-evidence linking
    for ti, ta in enumerate(resp.tasks):
        if ti >= len(research_resp.tasks):
            continue
        task = research_resp.tasks[ti]
        for fi, kf in enumerate(ta.key_facts):
            if not kf.evidence_indices:
                if JUDGE_GATEKEEPER_STRICT_LINKING and task.evidence:
                    reasons.append(
                        f"Task {ti} fact {fi}: missing evidence_indices "
                        "(strict linking required)"
                    )
                # Soft mode: just note, don't fail
            else:
                # Validate indices are in range (already done at parse, but double-check)
                max_idx = len(task.evidence) - 1
                for idx in kf.evidence_indices:
                    if idx < 0 or idx > max_idx:
                        reasons.append(
                            f"Task {ti} fact {fi}: invalid evidence index {idx}"
                        )
                        break

    # 4. Grounding validation
    for ti, ta in enumerate(resp.tasks):
        if ti >= len(research_resp.tasks):
            continue
        task = research_resp.tasks[ti]
        for fi, kf in enumerate(ta.key_facts):
            for r in _check_grounding(kf, task):
                reasons.append(f"Task {ti} fact {fi}: {r}")

    # 5. Overall verdict consistency (skip if no per-task facts to compare)
    per_task_descs = _all_per_task_fact_descriptions(resp)
    ov = resp.overall_verdict
    if per_task_descs:
        for fi, kf in enumerate(ov.supporting_facts):
            if not _fact_overlaps_per_task(kf.description, per_task_descs):
                reasons.append(
                    f"Overall supporting fact {fi} '{kf.description[:40]}...' "
                    "does not overlap with per-task key facts"
                )
        for fi, kf in enumerate(ov.contradicting_facts):
            if not _fact_overlaps_per_task(kf.description, per_task_descs):
                reasons.append(
                    f"Overall contradicting fact {fi} '{kf.description[:40]}...' "
                    "does not overlap with per-task key facts"
                )

    valid = not reasons
    return JudgeGatekeeperResult(
        valid=valid, reasons=reasons, needs_regeneration=not valid
    )
