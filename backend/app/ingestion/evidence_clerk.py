"""Evidence clerk: extract structured metadata using Gemini Flash.

Uses a secondary Gemini API key to avoid rate limits on the main
embedding key and returns strictly-typed JSON validated by Pydantic.
"""
from typing import List, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import EVIDENCE_CLERK_MODEL, GOOGLE_API_KEY2


class EvidenceClerkDetails(BaseModel):
    """Structured metadata extracted from an evidence document or chunk."""

    summary: str = Field(..., description="Short factual summary of the evidence")
    parties: List[str] = Field(
        default_factory=list,
        description="People or entities mentioned (e.g., suspect, witness, officer)",
    )
    locations: List[str] = Field(
        default_factory=list,
        description="Relevant locations mentioned in the evidence",
    )
    times: List[str] = Field(
        default_factory=list,
        description="Key times or time ranges mentioned (raw text)",
    )
    evidence_type: Optional[str] = Field(
        default=None,
        description="Model's guess of evidence type (e.g., witness_statement, gps_log)",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model's overall confidence in this extraction (0-1)",
    )


async def extract_evidence_details(text: str) -> EvidenceClerkDetails:
    """Call Gemini Flash to extract structured evidence metadata.

    The response is constrained to JSON and validated against
    `EvidenceClerkDetails` using the google-genai response_schema
    integration.
    """
    if not GOOGLE_API_KEY2:
        raise RuntimeError("GOOGLE_API_KEY2 is required for the evidence clerk.")

    client = genai.Client(api_key=GOOGLE_API_KEY2)

    system_prompt = (
        "You are an evidence clerk helping law enforcement. "
        "Given a single piece of evidence (statement, log, report), "
        "extract only factual, directly stated details. Do not infer beyond "
        "what is written. Return JSON matching the EvidenceClerkDetails schema."
    )

    try:
        response = await client.aio.models.generate_content(
            model=EVIDENCE_CLERK_MODEL,
            contents=[
                system_prompt,
                text,
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=EvidenceClerkDetails,
            ),
        )
    finally:
        await client.aio.aclose()

    # With response_schema + application/json, google-genai populates
    # `parsed` with a Pydantic model instance when possible.
    if hasattr(response, "parsed") and isinstance(response.parsed, EvidenceClerkDetails):
        return response.parsed

    # Fallback: parse JSON text manually if `parsed` is not set
    if hasattr(response, "text") and response.text:
        return EvidenceClerkDetails.model_validate_json(response.text)

    raise RuntimeError("Evidence clerk returned no usable JSON payload.")
