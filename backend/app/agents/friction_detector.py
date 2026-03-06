"""Friction detection between case overview and fact-to-check.

Uses a lightweight LLM call (Gemini Flash) to summarize any glaring
inconsistencies and classify whether friction is present. Falls back
to SiliconFlow (Qwen) if the primary model fails.
"""
import asyncio

from google import genai
from google.genai import types
from openai import OpenAI

from app.config import (
    FRICTION_MODEL,
    GOOGLE_API_KEY2,
    SILICONFLOW_API_KEY,
    SILICONFLOW_BASE_URL,
    SILICONFLOW_JUDGE_MODEL,
)
from app.schemas.planner import FrictionSummary


def _parse_friction_response(text: str) -> FrictionSummary:
    """Parse LLM response into FrictionSummary."""
    text = (text or "").strip()
    if not text or text.lower() == "none":
        return FrictionSummary(has_friction=False, description=None)
    return FrictionSummary(has_friction=True, description=text)


def _call_siliconflow_friction(system_prompt: str, user_content: str) -> str:
    """Call SiliconFlow for friction detection. Returns raw text."""
    client = OpenAI(api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_BASE_URL)
    completion = client.chat.completions.create(
        model=SILICONFLOW_JUDGE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )
    return completion.choices[0].message.content or ""


async def detect_friction(case_brief_text: str, fact_to_check: str) -> FrictionSummary:
    """Detect obvious contradictions between case brief and claim.

    Returns a FrictionSummary that is later embedded into the planner
    prompt. Tries primary model (Gemini) first; on failure, falls back
    to SiliconFlow (Qwen) if configured.
    """
    system_prompt = (
        "You are an Elite Forensic Auditor. Identify glaring contradictions "
        "between the claim and overview. CRITICAL: If a claim says "
        "'Person A is guilty' but the overview  says 'Account B was used,' "
        "flag this as 'Identity/Credential Mismatch Friction.' Describe "
        "the friction in one sentence or respond 'none"
    )
    user_content = f"CASE OVERVIEW:\n{case_brief_text}\n\nCLAIM:\n{fact_to_check}"

    # Try primary model (Gemini) first
    if GOOGLE_API_KEY2:
        client = genai.Client(api_key=GOOGLE_API_KEY2)
        try:
            response = await client.aio.models.generate_content(
                model=FRICTION_MODEL,
                contents=[system_prompt, user_content],
                config=types.GenerateContentConfig(temperature=0.1),
            )
            await client.aio.aclose()
            return _parse_friction_response(getattr(response, "text", None) or "")
        except Exception:
            await client.aio.aclose()

    # Fallback to SiliconFlow if primary failed or no Gemini key
    if SILICONFLOW_API_KEY:
        try:
            text = await asyncio.to_thread(
                _call_siliconflow_friction, system_prompt, user_content
            )
            return _parse_friction_response(text)
        except Exception:
            pass

    return FrictionSummary(has_friction=False, description=None)
