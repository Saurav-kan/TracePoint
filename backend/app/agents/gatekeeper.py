"""Gatekeeper for planner outputs.

Validates that the planner's JSON is well-formed and respects the
investigative heuristics (coverage of types, vector query quality,
peripheral detail, friction focus).
"""
from typing import List

from pydantic import BaseModel, Field

from app.config import DEFAULT_EVIDENCE_LABELS
from app.db.models import Case
from app.db.queries import get_case_labels
from app.schemas.planner import InvestigativeType, PlannerResponse


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


def _friction_keywords(description: str) -> List[str]:
    parts = [w.strip(".,!?:;\"'()").lower() for w in description.split()]
    # keep slightly longer tokens to avoid noise
    return [p for p in parts if len(p) >= 4]


def validate_planner_output(resp: PlannerResponse, case: Case) -> GatekeeperResult:
    reasons: List[str] = []

    # 1. Exactly 5 tasks
    if len(resp.tasks) != 5:
        reasons.append(f"Expected 5 tasks, got {len(resp.tasks)}.")

    # 2. All types present at least once
    seen_types = {task.type for task in resp.tasks}
    missing_types = [
        t
        for t in [
            "VERIFICATION",
            "IMPOSSIBILITY",
            "ENVIRONMENTAL",
            "NEGATIVE_PROOF",
            "RECALL_STRESS",
        ]
        if t not in seen_types
    ]
    if missing_types:
        reasons.append(f"Missing investigative types: {', '.join(missing_types)}.")

    # 3. Vector query quality and metadata filters
    for idx, task in enumerate(resp.tasks):
        tokens = task.vector_query.strip().split()
        if len(tokens) < 5:
            reasons.append(f"Task {idx} vector_query too short; needs a full sentence.")
        if not task.metadata_filter:
            reasons.append(f"Task {idx} missing metadata_filter.")

    # 3b. Metadata filter keys and label values
    allowed_labels = get_case_labels(resp.case_id) or DEFAULT_EVIDENCE_LABELS
    allowed_keys = {"label", "source_document"}
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

    # 4. Peripheral detail requirement
    if not _has_peripheral_task(resp):
        reasons.append("At least one task must probe peripheral details.")

    # 5. Friction focus (heuristic)
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
