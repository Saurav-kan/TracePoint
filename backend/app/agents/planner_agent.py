"""Planner agent: generate investigative tasks for a case and claim."""
from typing import List, Optional
import json

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
)
from app.agents.friction_detector import detect_friction
from app.agents import planner_templates
from app.db.models import Case
from app.db.queries import get_case_labels
from app.schemas.planner import (
    FrictionSummary,
    PlannerRequest,
    PlannerResponse,
    SearchBoundary,
)


def _build_system_prompt(allowed_labels: Optional[List[str]] = None) -> str:
    """Build the system prompt using canonical templates.

    If allowed_labels is provided, constrain metadata_filter label values
    to that set for the current case; otherwise fall back to a small
    global taxonomy.
    """
    parts = [
        "You are a planner agent for a law-enforcement fact-checking system.",
        "You receive a case overview and a single fact to check.",
        "Your job is to propose exactly five investigative tasks.",
        "Each task must include: type, question_text, vector_query, metadata_filter.",
        "metadata_filter must be a list of {key, value} objects (e.g. {\"key\": \"label\", \"value\": \"forensic_log\"}), not a raw object.",
        "Types must be one of: VERIFICATION, IMPOSSIBILITY, ENVIRONMENTAL,",
        "NEGATIVE_PROOF, RECALL_STRESS.",
        "Vector queries must be full descriptive sentences suitable for an",
        "embedding model, not single keywords.",
        "Prefer concrete, objective evidence (logs, device traces, receipts,",
        "timestamps, CCTV) over subjective recollections when designing",
        "vector queries.",
        "Always include at least one peripheral-detail question that probes",
        "minor contextual details that would be hard to fabricate.",
        "If a major inconsistency (friction) is described, at least two of",
        "the five tasks must directly target that inconsistency.",
        "Here are canonical descriptions of the five investigative types:",
        planner_templates.VERIFICATION_TEMPLATE,
        planner_templates.IMPOSSIBILITY_TEMPLATE,
        planner_templates.ENVIRONMENTAL_TEMPLATE,
        planner_templates.NEGATIVE_PROOF_TEMPLATE,
        planner_templates.RECALL_STRESS_TEMPLATE,
    ]

    labels = allowed_labels or DEFAULT_EVIDENCE_LABELS
    if labels:
        label_instructions = [
            "For metadata_filter, when you filter by evidence type, you MUST use:",
            "  {\"key\": \"label\", \"value\": \"<one of the allowed labels below>\"}.",
            "Do NOT invent new label values. Only choose from this list:",
        ]
        for lbl in labels:
            label_instructions.append(f"- {lbl}")
        label_instructions.append(
            "Every task's metadata_filter must include at least one such label filter."
        )
        parts.extend(label_instructions)

    parts.extend(
        [
            "You must return ONLY a JSON object with a single top-level key 'tasks'.",
            "'tasks' must be a list of exactly five objects, each with fields: type, question_text, vector_query, metadata_filter.",
        ]
    )
    return "\n\n".join(parts)


def _derive_search_boundary(case: Case) -> SearchBoundary:
    """Use case crime timestamps as a default search boundary if present."""
    return SearchBoundary(
        start_time=case.crime_timestamp_start,
        end_time=case.crime_timestamp_end,
    )


async def run_planner(
    case: Case, req: PlannerRequest, brief_text_override: Optional[str] = None
) -> PlannerResponse:
    """Run the planner LLM with friction detection and return a response.

    This function does not perform gatekeeper validation; that is handled
    by a separate component.
    If brief_text_override is provided, use it instead of case.case_brief_text.
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

    system_prompt = _build_system_prompt(allowed_labels)

    user_content = (
        f"CASE OVERVIEW:\n{brief_text}\n\n"
        f"FACT TO CHECK:\n{req.fact_to_check}\n\n"
        f"FRICTION SUMMARY:\n{friction.description or 'none'}\n\n"
        f"SEARCH BOUNDARY (start={search_boundary.start_time}, "
        f"end={search_boundary.end_time})."
    )

    # If configured, use OpenAI as the planner provider
    if PLANNER_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is required when PLANNER_PROVIDER=openai.")

        client = OpenAI(api_key=OPENAI_API_KEY)

        completion = client.chat.completions.create(
            model=OPENAI_PLANNER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        try:
            json_text = completion.choices[0].message.content
            raw = json.loads(json_text or "{}")
            tasks = raw.get("tasks", [])
        except (AttributeError, IndexError, KeyError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
            raise RuntimeError("OpenAI planner response missing or invalid JSON 'tasks'") from exc

        data = {
            "case_id": req.case_id,
            "fact_to_check": req.fact_to_check,
            "friction_summary": friction.model_dump(),
            "search_boundary": search_boundary.model_dump(),
            "tasks": tasks,
        }
        return PlannerResponse.model_validate(data)

    # If configured, use Groq (OpenAI-compatible) as the planner provider
    if PLANNER_PROVIDER == "groq":
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is required when PLANNER_PROVIDER=groq.")

        client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)

        completion = client.chat.completions.create(
            model=GROQ_PLANNER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        try:
            json_text = completion.choices[0].message.content
            raw = json.loads(json_text or "{}")
            tasks = raw.get("tasks", [])
        except (AttributeError, IndexError, KeyError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
            raise RuntimeError("Groq planner response missing or invalid JSON 'tasks'") from exc

        data = {
            "case_id": req.case_id,
            "fact_to_check": req.fact_to_check,
            "friction_summary": friction.model_dump(),
            "search_boundary": search_boundary.model_dump(),
            "tasks": tasks,
        }
        return PlannerResponse.model_validate(data)

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
    finally:
        await client.aio.aclose()

    if hasattr(response, "parsed") and isinstance(response.parsed, PlannerResponse):
        return response.parsed

    if hasattr(response, "text") and response.text:
        return PlannerResponse.model_validate_json(response.text)

    raise RuntimeError("Planner agent returned no usable JSON payload.")
