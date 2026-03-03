"""Planner agent: generate investigative tasks for a case and claim."""
from typing import Optional

from google import genai
from google.genai import types

from app.config import GOOGLE_API_KEY, PLANNER_MODEL
from app.agents.friction_detector import detect_friction
from app.agents import planner_templates
from app.db.models import Case
from app.schemas.planner import (
    FrictionSummary,
    PlannerRequest,
    PlannerResponse,
    SearchBoundary,
)


def _build_system_prompt() -> str:
    """Build the system prompt using canonical templates."""
    parts = [
        "You are a planner agent for a law-enforcement fact-checking system.",
        "You receive a case overview and a single fact to check.",
        "Your job is to propose exactly five investigative tasks.",
        "Each task must include: type, question_text, vector_query, metadata_filter.",
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
    return "\n\n".join(parts)


def _derive_search_boundary(case: Case) -> SearchBoundary:
    """Use case crime timestamps as a default search boundary if present."""
    return SearchBoundary(
        start_time=case.crime_timestamp_start,
        end_time=case.crime_timestamp_end,
    )


async def run_planner(case: Case, req: PlannerRequest) -> PlannerResponse:
    """Run the planner LLM with friction detection and return a response.

    This function does not perform gatekeeper validation; that is handled
    by a separate component.
    """
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is required for the planner agent.")

    client = genai.Client(api_key=GOOGLE_API_KEY)

    friction: FrictionSummary = await detect_friction(
        case_brief_text=case.case_brief_text,
        fact_to_check=req.fact_to_check,
    )
    search_boundary = _derive_search_boundary(case)

    system_prompt = _build_system_prompt()

    user_content = (
        f"CASE OVERVIEW:\n{case.case_brief_text}\n\n"
        f"FACT TO CHECK:\n{req.fact_to_check}\n\n"
        f"FRICTION SUMMARY:\n{friction.description or 'none'}\n\n"
        f"SEARCH BOUNDARY (start={search_boundary.start_time}, "
        f"end={search_boundary.end_time})."
    )

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
