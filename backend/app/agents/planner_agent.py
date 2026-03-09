"""Planner agent: generate investigative tasks for a case and claim."""
import asyncio
import json
from typing import List, Optional

from google import genai
from google.genai import types
from openai import OpenAI

from app.config import (
    DEFAULT_EVIDENCE_LABELS,
    GOOGLE_API_KEY,
    PLANNER_MODEL,
    OPENAI_API_KEY,
    OPENAI_PLANNER_MODEL,
    PLANNER_PROVIDER,
    GROQ_API_KEY,
    GROQ_PLANNER_MODEL,
    GROQ_BASE_URL,
    SILICONFLOW_API_KEY,
    SILICONFLOW_BASE_URL,
    SILICONFLOW_JUDGE_MODEL,
)
from app.agents.friction_detector import detect_friction
from app.agents import planner_templates
from app.db.models import Case
from app.db.queries import get_case_labels, get_case_evidence_types
from app.schemas.planner import (
    FrictionSummary,
    PlannerRequest,
    PlannerResponse,
    SearchBoundary,
)

_DISCONFIRMING_HINTS = (
    "Search for an alibi, an alternative suspect, exonerating evidence, "
    "contradictory evidence, proof the subject was not involved, or signs the "
    "claim is false."
)


def _build_system_prompt(
    allowed_labels: Optional[List[str]] = None,
    allowed_evidence_types: Optional[List[str]] = None,
) -> str:
    """Build the system prompt using canonical templates.

    If allowed_labels is provided, constrain metadata_filter label values
    to that set for the current case; otherwise fall back to a small
    global taxonomy.
    """
    parts = [
        "You are a planner agent for a law-enforcement fact-checking system.",
        "You receive a case overview and a single fact to check.",
        "Your job is to propose exactly TEN investigative tasks, split into two",
        "halves of five: the first five are CONFIRMATIONAL (seeking evidence that",
        "supports the claim), and the second five are NON-CONFIRMATIONAL (seeking",
        "evidence that weakens, disproves, or provides alternatives to the claim).",
        "Each task must include: type, question_text, vector_query, metadata_filter.",
        "metadata_filter must be a list of {key, value} objects (e.g. {\"key\": \"label\", \"value\": \"forensic_log\"}), not a raw object.",
        "Types must be one of: VERIFICATION, IMPOSSIBILITY, ENVIRONMENTAL,",
        "NEGATIVE_PROOF, RECALL_STRESS, PHYSICAL_ARTIFACT_AUTHORSHIP.",
        "Vector queries must be full descriptive sentences suitable for an",
        "embedding model, not single keywords.",
        "Prefer concrete, objective evidence (logs, device traces, receipts,",
        "timestamps, CCTV) over subjective recollections when designing",
        "vector queries.",
        "Should vs Could — critical framing rule: Never design tasks that assume",
        "the 'authorized' user of a credential IS the actor. Always design tasks",
        "to find who PHYSICALLY DID the action (fingerprints, biometrics, physical",
        "access traces, code signatures) vs who SHOULD have had access (role,",
        "authorization). Authorization level is irrelevant if another person has",
        "physical evidence tying them to the act.",
        "Physical Artifact Authorship Task (mandatory when a physical artifact is",
        "central to the case): Always include at least one task specifically searching",
        "for forensic traces on the principal crime artifact (e.g., a USB drive, a",
        "weapon, a device). Target: fingerprints, DNA, embedded code strings like",
        "'property_of_X', developer tags, serial numbers linked to individuals.",
        "Identify Actor-Credential Mismatch: If the case involves a specific",
        "account (e.g., an Admin), do not assume the owner of that account is",
        "the one who used it. Propose a task to verify the physical location",
        "of the account owner vs. the suspect during the breach.",
        "Credential Probing Pattern: Always include a task investigating whether",
        "the privileged credential was acquired through theft. Look for failed",
        "login attempts, keyloggers, password harvesting tools, or physical access",
        "to the credential owner's devices before the breach.",
        "Network Origin Analysis: Always include a task to identify the physical",
        "device or workstation associated with a specific IP or login event.",
        "Ask: 'Who was physically at the machine assigned to IP X?'",
        "Balanced-Direction Requirement: The first five tasks (slots 1-5) must each",
        "be CONFIRMATIONAL — one per type (VERIFICATION, IMPOSSIBILITY, ENVIRONMENTAL,",
        "NEGATIVE_PROOF, RECALL_STRESS), each seeking evidence that supports the claim.",
        "The second five tasks (slots 6-10) must each be NON-CONFIRMATIONAL — one per",
        "type, each actively seeking DISCONFIRMING evidence: alibis, alternative",
        "suspects, exonerating records, contradictory physical evidence, or proof of",
        "innocence. The non-confirmational vector_query must search for evidence AGAINST",
        "the claim, not for the claim itself. This ensures equal investigative effort",
        "in both directions.",
        "Formatting rule for slots 6-10: start question_text with '[DISCONFIRMING]'",
        "and write vector_query so it explicitly includes at least one contrary idea",
        "such as 'alibi', 'alternative suspect', 'exonerating evidence',",
        "'contradictory evidence', 'not involved', 'ruled out', or 'false claim'.",
        "Do not use vague neutral wording for slots 6-10. Make the disconfirming",
        "intent obvious from the text alone.",
        "Always include at least one peripheral-detail question that probes",
        "minor contextual details that would be hard to fabricate.",
        "If a major inconsistency (friction) is described, at least two of",
        "the five tasks must directly target that inconsistency.",
        "Here are canonical descriptions of the investigative types:",
        planner_templates.VERIFICATION_TEMPLATE,
        planner_templates.IMPOSSIBILITY_TEMPLATE,
        planner_templates.ENVIRONMENTAL_TEMPLATE,
        planner_templates.NEGATIVE_PROOF_TEMPLATE,
        planner_templates.RECALL_STRESS_TEMPLATE,
        planner_templates.PHYSICAL_ARTIFACT_AUTHORSHIP_TEMPLATE,
    ]

    labels = allowed_labels or DEFAULT_EVIDENCE_LABELS
    evidence_types = allowed_evidence_types or []

    if evidence_types:
        et_instructions = [
            "PREFERRED: For metadata_filter, filter by clerk-extracted evidence_type:",
            "  {\"key\": \"evidence_type\", \"value\": \"<one of the types below>\"}.",
            "These types were automatically extracted from evidence content and are",
            "more accurate than user-assigned labels. Available evidence_type values:",
        ]
        for et in evidence_types:
            et_instructions.append(f"- {et}")
        et_instructions.append(
            "Prefer evidence_type over label when both are available."
        )
        parts.extend(et_instructions)

    if labels:
        label_instructions = [
            "FALLBACK: You may also filter by user-assigned label:",
            "  {\"key\": \"label\", \"value\": \"<one of the allowed labels below>\"}.",
            "Do NOT invent new label values. Only choose from this list:",
        ]
        for lbl in labels:
            label_instructions.append(f"- {lbl}")
        parts.extend(label_instructions)

    parts.append(
        "Every task's metadata_filter must include at least one filter "
        "(either evidence_type or label)."
    )

    parts.extend(
        [
            "You must return ONLY a JSON object with a single top-level key 'tasks'.",
            "'tasks' must be a list of exactly TEN objects, each with fields: type, question_text, vector_query, metadata_filter.",
            "Return the tasks in order: slots 1-5 confirmational, slots 6-10 disconfirming.",
        ]
    )
    return "\n\n".join(parts)


def _normalize_main_pass_tasks(resp: PlannerResponse) -> PlannerResponse:
    """Make the second half of the main task list explicitly disconfirming.

    The planner is instructed to do this already, but we normalize the wording
    so downstream gatekeeping and debugging are stable across model providers.
    """

    if len(resp.tasks) != 10:
        return resp

    normalized_tasks = []
    second_half_start = len(resp.tasks) // 2
    contrary_markers = (
        "alibi",
        "alternative suspect",
        "exonerating",
        "contradictory",
        "not involved",
        "ruled out",
        "false claim",
        "false",
    )

    for idx, task in enumerate(resp.tasks):
        if idx < second_half_start:
            normalized_tasks.append(task)
            continue

        question_text = task.question_text.strip()
        if "[DISCONFIRMING]" not in question_text.upper():
            question_text = f"[DISCONFIRMING] {question_text}"

        vector_query = task.vector_query.strip()
        lowered = vector_query.lower()
        if not any(marker in lowered for marker in contrary_markers):
            vector_query = f"{vector_query} {_DISCONFIRMING_HINTS}"

        normalized_tasks.append(
            task.model_copy(
                update={
                    "question_text": question_text,
                    "vector_query": vector_query,
                }
            )
        )

    return resp.model_copy(update={"tasks": normalized_tasks})


def _build_refinement_system_prompt(
    allowed_labels: Optional[List[str]] = None,
    allowed_evidence_types: Optional[List[str]] = None,
) -> str:
    """Build a system prompt for supplemental (refinement) task generation.

    Unlike the main prompt, this asks for 1-3 targeted follow-up tasks
    instead of the standard five.
    """
    parts = [
        "You are a planner agent for a law-enforcement fact-checking system.",
        "You are running in REFINEMENT MODE. A previous investigation round",
        "found insufficient evidence for certain questions. You receive the",
        "original case overview, claim, and a set of refinement questions",
        "that need more evidence.",
        "",
        "Your job is to propose 1-3 supplemental investigative tasks that",
        "specifically target the evidence gaps identified in the refinement",
        "questions. These tasks should use different search strategies,",
        "metadata filters, or angles than the original investigation.",
        "",
        "Each task must include: type, question_text, vector_query, metadata_filter.",
        "metadata_filter must be a list of {key, value} objects.",
        "Types must be one of: VERIFICATION, IMPOSSIBILITY, ENVIRONMENTAL,",
        "NEGATIVE_PROOF, RECALL_STRESS, PHYSICAL_ARTIFACT_AUTHORSHIP.",
        "Vector queries must be full descriptive sentences suitable for an",
        "embedding model, not single keywords.",
        "Here are canonical descriptions of the investigative types:",
        planner_templates.VERIFICATION_TEMPLATE,
        planner_templates.IMPOSSIBILITY_TEMPLATE,
        planner_templates.ENVIRONMENTAL_TEMPLATE,
        planner_templates.NEGATIVE_PROOF_TEMPLATE,
        planner_templates.RECALL_STRESS_TEMPLATE,
        planner_templates.PHYSICAL_ARTIFACT_AUTHORSHIP_TEMPLATE,
    ]

    labels = allowed_labels or DEFAULT_EVIDENCE_LABELS
    evidence_types = allowed_evidence_types or []

    if evidence_types:
        et_instructions = [
            "PREFERRED: Filter by clerk-extracted evidence_type:",
            "  {\"key\": \"evidence_type\", \"value\": \"<one of the types below>\"}.",
            "Available evidence_type values:",
        ]
        for et in evidence_types:
            et_instructions.append(f"- {et}")
        et_instructions.append(
            "Prefer evidence_type over label when both are available."
        )
        parts.extend(et_instructions)

    if labels:
        label_instructions = [
            "FALLBACK: You may also filter by user-assigned label:",
            "  {\"key\": \"label\", \"value\": \"<one of the allowed labels below>\"}.",
            "Do NOT invent new label values. Only choose from this list:",
        ]
        for lbl in labels:
            label_instructions.append(f"- {lbl}")
        parts.extend(label_instructions)

    parts.append(
        "Every task's metadata_filter must include at least one filter "
        "(either evidence_type or label)."
    )

    parts.extend(
        [
            "You must return ONLY a JSON object with a single top-level key 'tasks'.",
            "'tasks' must be a list of 1-3 objects, each with fields: type, question_text, vector_query, metadata_filter.",
        ]
    )
    return "\n\n".join(parts)


def _derive_search_boundary(case: Case) -> SearchBoundary:
    """Use case crime timestamps as a default search boundary if present."""
    return SearchBoundary(
        start_time=case.crime_timestamp_start,
        end_time=case.crime_timestamp_end,
    )


def _planner_call_siliconflow(
    system_prompt: str,
    user_content: str,
    friction: FrictionSummary,
    search_boundary: SearchBoundary,
    req: PlannerRequest,
) -> PlannerResponse:
    """Fallback: call SiliconFlow (Qwen) for planner when primary provider fails."""
    client = OpenAI(api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_BASE_URL)
    completion = client.chat.completions.create(
        model=SILICONFLOW_JUDGE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    json_text = completion.choices[0].message.content
    raw = json.loads(json_text or "{}")
    tasks = raw.get("tasks", [])
    data = {
        "case_id": req.case_id,
        "fact_to_check": req.fact_to_check,
        "friction_summary": friction.model_dump(),
        "search_boundary": search_boundary.model_dump(),
        "tasks": tasks,
    }
    return PlannerResponse.model_validate(data)


def _call_llm_provider(
    system_prompt: str,
    user_content: str,
    friction: FrictionSummary,
    search_boundary: SearchBoundary,
    req: PlannerRequest,
    provider: str,
) -> PlannerResponse:
    """Shared LLM call logic for OpenAI-compatible providers (openai, groq)."""
    if provider == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is required when PLANNER_PROVIDER=openai.")
        client = OpenAI(api_key=OPENAI_API_KEY)
        model = OPENAI_PLANNER_MODEL
    elif provider == "groq":
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is required when PLANNER_PROVIDER=groq.")
        client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
        model = GROQ_PLANNER_MODEL
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        json_text = completion.choices[0].message.content
        raw = json.loads(json_text or "{}")
        tasks = raw.get("tasks", [])
    except Exception:
        if SILICONFLOW_API_KEY:
            return _planner_call_siliconflow(
                system_prompt, user_content, friction, search_boundary, req
            )
        raise

    data = {
        "case_id": req.case_id,
        "fact_to_check": req.fact_to_check,
        "friction_summary": friction.model_dump(),
        "search_boundary": search_boundary.model_dump(),
        "tasks": tasks,
    }
    return PlannerResponse.model_validate(data)


async def run_planner(
    case: Case,
    req: PlannerRequest,
    brief_text_override: Optional[str] = None,
    refinement_context: Optional[str] = None,
    prior_iterations_summary: Optional[str] = None,
) -> PlannerResponse:
    """Run the planner LLM with friction detection and return a response.

    This function does not perform gatekeeper validation; that is handled
    by a separate component.
    If brief_text_override is provided, use it instead of case.case_brief_text.
    If refinement_context is provided, run in supplemental-task mode: produce
    1-3 targeted tasks addressing refinement questions (gatekeeper bypassed).
    If prior_iterations_summary is provided (multi-pass medium/high effort),
    the planner uses prior verdicts to inform task design for subsequent passes.
    """
    brief_text = brief_text_override if brief_text_override is not None else case.case_brief_text
    friction: FrictionSummary = await detect_friction(
        case_brief_text=brief_text,
        fact_to_check=req.fact_to_check,
    )
    search_boundary = _derive_search_boundary(case)

    # Case-scoped evidence labels for metadata_filter guidance
    case_labels: List[str] = get_case_labels(req.case_id)
    allowed_labels: List[str] = case_labels or DEFAULT_EVIDENCE_LABELS
    allowed_evidence_types: List[str] = get_case_evidence_types(req.case_id)

    # Choose prompt based on whether this is a refinement pass
    if refinement_context is not None:
        system_prompt = _build_refinement_system_prompt(allowed_labels, allowed_evidence_types)
        user_content = (
            f"CASE OVERVIEW:\n{brief_text}\n\n"
            f"FACT TO CHECK:\n{req.fact_to_check}\n\n"
            f"FRICTION SUMMARY:\n{friction.description or 'none'}\n\n"
            f"SEARCH BOUNDARY (start={search_boundary.start_time}, "
            f"end={search_boundary.end_time}).\n\n"
            f"REFINEMENT QUESTIONS (produce supplemental tasks for these):\n"
            f"{refinement_context}"
        )
    else:
        system_prompt = _build_system_prompt(allowed_labels, allowed_evidence_types)
        user_content = (
            f"CASE OVERVIEW:\n{brief_text}\n\n"
            f"FACT TO CHECK:\n{req.fact_to_check}\n\n"
            f"FRICTION SUMMARY:\n{friction.description or 'none'}\n\n"
            f"SEARCH BOUNDARY (start={search_boundary.start_time}, "
            f"end={search_boundary.end_time})."
        )
        if prior_iterations_summary:
            user_content += f"\n\n{prior_iterations_summary}"

    # If configured, use OpenAI or Groq as the planner provider
    if PLANNER_PROVIDER in ("openai", "groq"):
        resp = _call_llm_provider(
            system_prompt, user_content, friction, search_boundary, req, PLANNER_PROVIDER
        )
        return resp if refinement_context is not None else _normalize_main_pass_tasks(resp)

    # Default: use Gemini as the planner provider
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is required for the planner agent.")

    client = genai.Client(api_key=GOOGLE_API_KEY)
    try:
        response = await client.aio.models.generate_content(
            model=PLANNER_MODEL,
            contents=[system_prompt, user_content],
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=PlannerResponse,
            ),
        )
        await client.aio.aclose()
        if hasattr(response, "parsed") and isinstance(
            response.parsed, PlannerResponse
        ):
            resp = response.parsed
            return resp if refinement_context is not None else _normalize_main_pass_tasks(resp)
        if hasattr(response, "text") and response.text:
            resp = PlannerResponse.model_validate_json(response.text)
            return resp if refinement_context is not None else _normalize_main_pass_tasks(resp)
        raise RuntimeError("Planner agent returned no usable JSON payload.")
    except Exception:
        await client.aio.aclose()
        if SILICONFLOW_API_KEY:
            resp = await asyncio.to_thread(
                _planner_call_siliconflow,
                system_prompt,
                user_content,
                friction,
                search_boundary,
                req,
            )
            return resp if refinement_context is not None else _normalize_main_pass_tasks(resp)
        raise
