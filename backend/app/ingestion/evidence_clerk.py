"""Evidence clerk: extract structured metadata using Gemini Flash.

Uses a secondary Gemini API key to avoid rate limits on the main
embedding key and returns strictly-typed JSON validated by Pydantic.
"""
import logging
from typing import List, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.config import EVIDENCE_CLERK_MODEL, GOOGLE_API_KEY2

logger = logging.getLogger(__name__)


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


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Check if an exception is a rate-limit (429) error from the Gemini SDK."""
    exc_type = type(exc).__name__
    # google-genai raises ClientError or similar with status 429
    if "ResourceExhausted" in exc_type or "TooManyRequests" in exc_type:
        return True
    # Catch generic errors with 429 in the message
    if "429" in str(exc):
        return True
    return False


@retry(
    retry=retry_if_exception_type((Exception,)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def extract_evidence_details(text: str) -> EvidenceClerkDetails:
    """Call Gemini Flash to extract structured evidence metadata.

    The response is constrained to JSON and validated against
    `EvidenceClerkDetails` using the google-genai response_schema
    integration.

    Retries automatically on 429 rate-limit errors with exponential backoff.
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
    except Exception as e:
        # Let tenacity handle retries for rate-limit errors
        if _is_rate_limit_error(e):
            logger.warning("Rate limited by Gemini API, will retry: %s", e)
        raise
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
