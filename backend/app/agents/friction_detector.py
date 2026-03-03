"""Friction detection between case overview and fact-to-check.

Uses a lightweight LLM call (Gemini Flash) to summarize any glaring
inconsistencies and classify whether friction is present.
"""
from typing import Tuple

from google import genai
from google.genai import types

from app.config import FRICTION_MODEL, GOOGLE_API_KEY2
from app.schemas.planner import FrictionSummary


async def detect_friction(case_brief_text: str, fact_to_check: str) -> FrictionSummary:
    """Detect obvious contradictions between case brief and claim.

    Returns a FrictionSummary that is later embedded into the planner
    prompt. For now, we treat any non-empty description as friction.
    """
    if not GOOGLE_API_KEY2:
        # Fall back to "no friction" if secondary key is unavailable
        return FrictionSummary(has_friction=False, description=None)

    client = genai.Client(api_key=GOOGLE_API_KEY2)

    system_prompt = (
        "You are assisting a fact-checking pipeline. Given a case overview "
        "and a single claim, identify any glaring contradictions between "
        "them (for example impossible times, locations, or conditions). "
        "Respond with a short sentence describing the friction if it is "
        "significant, or the word 'none' if there is no obvious issue."
    )

    try:
        response = await client.aio.models.generate_content(
            model=FRICTION_MODEL,
            contents=[
                system_prompt,
                f"CASE OVERVIEW:\n{case_brief_text}\n\nCLAIM:\n{fact_to_check}",
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
            ),
        )
    finally:
        await client.aio.aclose()

    text = (getattr(response, "text", None) or "").strip()
    if not text or text.lower() == "none":
        return FrictionSummary(has_friction=False, description=None)

    return FrictionSummary(has_friction=True, description=text)
