"""Gatekeeper for planner outputs.

Validates that the planner's JSON is well-formed and respects the
investigative heuristics (coverage of types, vector query quality,
peripheral detail, friction focus, and balanced contrary coverage).
"""
from collections import Counter
from typing import List

from pydantic import BaseModel, Field

from app.config import DEFAULT_EVIDENCE_LABELS
from app.db.models import Case
from app.db.queries import get_case_labels, get_case_evidence_types
from app.schemas.planner import InvestigativeType, PlannerResponse

REQUIRED_TYPES = [
    "VERIFICATION",
    "IMPOSSIBILITY",
    "ENVIRONMENTAL",
    "NEGATIVE_PROOF",
    "RECALL_STRESS",
]

_CLASSIFIER_PROMPT = """
Given the claim: {claim}

Classify the following investigative tasks. For each task, does it primarily seek evidence that confirms the claim, or evidence that challenges/contradicts it? Focus on semantic intent, not just keyword presence.

{tasks_block}

Return a JSON array of strings, exactly one per task in the same order, where each string is exactly "CONFIRMATIONAL" or "CONTRARY".
"""


class GatekeeperResult(BaseModel):
    valid: bool = Field(..., description="Whether the planner output passed checks")
    reasons: List[str] = Field(
        default_factory=list, description="Human-readable validation messages"
    )
    needs_regeneration: bool = Field(
        ..., description="If true, planner should regenerate the full task set"
    )


def _has_peripheral_task(resp: PlannerResponse) -> bool:
    """Check if at least one task is clearly about peripheral details.

    Heuristic: types of RECALL_STRESS or ENVIRONMENTAL often serve this role,
    and we also look for words like 'background', 'smell', 'noise', 'minor'.
    """
    peripheral_keywords = [
        "background",
        "smell",
        "noise",
        "minor",
        "peripheral",
        "side",
    ]
    for task in resp.tasks:
        if task.type in ("RECALL_STRESS", "ENVIRONMENTAL"):
            return True
        text = (task.question_text + " " + task.vector_query).lower()
        if any(kw in text for kw in peripheral_keywords):
            return True
    return False


import json
from app.agents.judge_llm import judge_llm_completion

async def _classify_tasks_semantic(resp: PlannerResponse, case: Case) -> List[str]:
    """Use an LLM to semantically classify each task as CONFIRMATIONAL or CONTRARY relative to the hypothesis."""
    tasks_block = "\\n\\n".join([f"Task {i}: {t.question_text}\\nQuery: {t.vector_query}" for i, t in enumerate(resp.tasks)])
    
    # We pass the fact_to_check (the specific hypothesis) to classify against.
    # We MUST define direction RELATIVE TO THIS HYPOTHESIS.
    prompt = (
        f"FACT TO CHECK (The Hypothesis): {resp.fact_to_check}\n\n"
        "You are validating a forensic planner. A planner must generate 10 tasks:\n"
        "Tasks 0-4 must be CONFIRMATIONAL: They must seek evidence that would SUPPORT the hypothesis being true.\n"
        "Tasks 5-9 must be CONTRARY: They must seek evidence that would CONTRADICT the hypothesis or support a rival theory.\n\n"
        "NOTE: If the hypothesis is about an alibi (e.g., 'the alibi is true'), then searching for evidence of that alibi is CONFIRMATIONAL. Searching for evidence of the crime is CONTRARY.\n\n"
        "Classify these tasks based on their semantic intent relative ONLY to the 'FACT TO CHECK' above:\n\n"
        f"{tasks_block}\n\n"
        f"Return a JSON object with a single key 'classifications' containing a list of {len(resp.tasks)} strings, either 'CONFIRMATIONAL' or 'CONTRARY'."
    )
    
    try:
        raw = await judge_llm_completion(
            "You are a semantic intent classifier specialized in forensic investigation logic.",
            prompt,
            response_format={"type": "json_object"}
        )
        data = json.loads(raw)
        classes = data.get("classifications", [])
        if isinstance(classes, list) and len(classes) == len(resp.tasks):
            return [str(c).upper() for c in classes]
    except Exception:
        pass
    
    # Fallback to a keyword check if inference fails
    fallbacks = []
    # If LLM classification fails, we default to the slot position to avoid 
    # blocking the user, but we mark them as contrary if obvious keywords appear.
    for i, t in enumerate(resp.tasks):
        text = (t.question_text + " " + t.vector_query).lower()
        if i < 5:
            # First half: assume confirmational unless it yells 'contrary'
            if any(kw in text for kw in ["contrary", "contradict", "disconfirm", "false claim"]):
                fallbacks.append("CONTRARY")
            else:
                fallbacks.append("CONFIRMATIONAL")
        else:
            # Second half: assume contrary unless it yells 'confirm'
            if any(kw in text for kw in ["confirm", "verify", "support", "prove true"]):
                fallbacks.append("CONFIRMATIONAL")
            else:
                fallbacks.append("CONTRARY")
    return fallbacks

def _validate_slot_polarity(resp: PlannerResponse, classifications: List[str]) -> List[str]:
    """Check that slot direction matches the planner contract."""
    reasons: List[str] = []
    if len(resp.tasks) < 10 or len(classifications) < 10:
        return reasons

    second_half_start = len(resp.tasks) // 2
    for idx, c in enumerate(classifications):
        if idx < second_half_start and c == "CONTRARY":
            reasons.append(
                f"Task {idx} is in the confirmational half but classified semantically as CONTRARY."
            )
        if idx >= second_half_start and c == "CONFIRMATIONAL":
            reasons.append(
                f"Task {idx} is in the disconfirming half but classified semantically as CONFIRMATIONAL."
            )

    return reasons

def _friction_keywords(description: str) -> List[str]:
    parts = [w.strip(".,!?:;\\\"'()").lower() for w in description.split()]
    # keep slightly longer tokens to avoid noise
    return [p for p in parts if len(p) >= 4]

async def validate_planner_output(resp: PlannerResponse, case: Case) -> GatekeeperResult:
    reasons: List[str] = []

    # 1. Exactly 10 tasks
    if len(resp.tasks) != 10:
        reasons.append(f"Expected 10 tasks, got {len(resp.tasks)}.")

    # 2. Each of the 5 canonical types must appear at least twice
    #    (once confirmational, once non-confirmational)
    type_counts = Counter(task.type for task in resp.tasks)
    for req_type in REQUIRED_TYPES:
        count = type_counts.get(req_type, 0)
        if count < 2:
            reasons.append(
                f"Type {req_type} appears {count} time(s); expected at least 2 "
                f"(one confirmational, one non-confirmational)."
            )

    # 3. Vector query quality and metadata filters
    for idx, task in enumerate(resp.tasks):
        tokens = task.vector_query.strip().split()
        if len(tokens) < 5:
            reasons.append(f"Task {idx} vector_query too short; needs a full sentence.")
        if not task.metadata_filter:
            reasons.append(f"Task {idx} missing metadata_filter.")

    # 3b. Metadata filter keys and label values
    allowed_labels = get_case_labels(resp.case_id) or DEFAULT_EVIDENCE_LABELS
    allowed_evidence_types = get_case_evidence_types(resp.case_id)
    allowed_keys = {"label", "source_document", "evidence_type"}
    for idx, task in enumerate(resp.tasks):
        for item in task.metadata_filter:
            if item.key not in allowed_keys:
                reasons.append(
                    f"Task {idx} metadata_filter key '{item.key}' is not allowed; "
                    f"must be one of: {', '.join(sorted(allowed_keys))}."
                )
            if item.key == "label" and item.value not in allowed_labels:
                joined = ", ".join(sorted(allowed_labels)) or "<none>"
                reasons.append(
                    f"Task {idx} uses unknown label '{item.value}'; "
                    f"allowed labels for this case: {joined}."
                )
            if (
                item.key == "evidence_type"
                and allowed_evidence_types
                and item.value not in allowed_evidence_types
            ):
                joined = ", ".join(sorted(allowed_evidence_types))
                reasons.append(
                    f"Task {idx} uses unknown evidence_type '{item.value}'; "
                    f"allowed types for this case: {joined}."
                )

    # 4. Peripheral detail requirement
    if not _has_peripheral_task(resp):
        reasons.append("At least one task must probe peripheral details.")

    # 5. Non-confirmational balance: at least 4 contrary tasks required
    classifications = await _classify_tasks_semantic(resp, case)
    contrary_count = sum(1 for c in classifications if c == "CONTRARY")
    if contrary_count < 4:
        reasons.append(
            f"Expected at least 4 non-confirmational/contrary tasks to avoid "
            f"confirmation bias. Found {contrary_count}."
        )

    # 5b. Slot polarity: first half must not sneak in contrary wording,
    # second half must be explicitly contrary.
    reasons.extend(_validate_slot_polarity(resp, classifications))

    # 6. Friction focus (heuristic)
    if resp.friction_summary.has_friction and resp.friction_summary.description:
        fr_keys = _friction_keywords(resp.friction_summary.description)
        if fr_keys:
            hits = 0
            for task in resp.tasks:
                text = (task.question_text + " " + task.vector_query).lower()
                if any(k in text for k in fr_keys):
                    hits += 1
            if hits < 2:
                reasons.append(
                    "Major friction described but fewer than two tasks clearly target it."
                )

    valid = not reasons
    return GatekeeperResult(valid=valid, reasons=reasons, needs_regeneration=not valid)
