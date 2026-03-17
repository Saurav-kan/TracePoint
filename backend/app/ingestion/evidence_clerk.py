"""Evidence clerk: extract structured metadata using Gemini Flash.

Uses a secondary Gemini API key to avoid rate limits on the main
embedding key and returns strictly-typed JSON validated by Pydantic.

Also scores all evidence labels 1-10 for auto-labeling.
"""
import json
import logging
import asyncio
import re
from typing import List, Optional

from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.config import (
    DEFAULT_EVIDENCE_LABELS,
    DEFAULT_EVIDENCE_TYPES,
    EVIDENCE_CLERK_MODEL,
    EVIDENCE_CLERK_PROVIDER,
    GOOGLE_API_KEY2,
    SILICONFLOW_API_KEY,
    SILICONFLOW_BASE_URL,
    SILICONFLOW_EVIDENCE_CLERK_MODEL,
)

logger = logging.getLogger(__name__)

# Cutoff and max for auto-label selection
LABEL_SCORE_CUTOFF = 6
LABEL_MAX_COUNT = 3


class LabelScore(BaseModel):
    """A single label with its relevance score."""

    label: str = Field(..., description="Evidence label (snake_case)")
    score: int = Field(
        ...,
        ge=1,
        le=10,
        description="Relevance score 1-10 (10 = perfect match)",
    )


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
    canonical_evidence_type: Optional[str] = Field(
        default=None,
        description=(
            "Normalized evidence type chosen from the controlled taxonomy. "
            "This field is post-processed by the application for retrieval and validation."
        ),
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model's overall confidence in this extraction (0-1)",
    )
    label_scores: List[LabelScore] = Field(
        default_factory=list,
        description="Relevance score (1-10) for every evidence label",
    )


def select_top_labels(
    scores: List[LabelScore],
    cutoff: int = LABEL_SCORE_CUTOFF,
    max_labels: int = LABEL_MAX_COUNT,
) -> list[str]:
    """Pick the top 1-3 labels that score >= cutoff.

    Returns at most `max_labels` labels sorted by score descending.
    If no label meets the cutoff, returns ['unclassified'].
    """
    if not scores:
        return ["unclassified"]

    sorted_scores = sorted(scores, key=lambda s: s.score, reverse=True)
    selected = [s.label for s in sorted_scores if s.score >= cutoff][:max_labels]

    # Fallback: if nothing meets cutoff, mark as unclassified instead of forcing
    # a misleading label.
    if not selected:
        selected = ["unclassified"]

    return selected


def _slugify_type(value: str) -> str:
    """Normalize arbitrary evidence type text into a loose snake_case slug."""
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized


def canonicalize_evidence_type(
    raw_evidence_type: Optional[str],
    label_scores: List[LabelScore],
) -> str:
    """Map freeform AI output into a controlled canonical evidence type."""
    allowed = set(DEFAULT_EVIDENCE_TYPES)
    raw = (raw_evidence_type or "").strip()
    slug = _slugify_type(raw) if raw else ""

    alias_map = {
        "witness_interview": "witness_statement",
        "witness_testimony": "witness_statement",
        "interview_transcript": "security_interview",
        "security_report": "security_interview",
        "camera_footage": "surveillance",
        "cctv": "surveillance",
        "video": "surveillance",
        "video_log": "surveillance",
        "biometric_log": "access_log",
        "badge_log": "access_log",
        "audit_log": "access_log",
        "wifi_log": "network_log",
        "gps_log": "sensor_data",
        "telemetry": "sensor_data",
        "sensor_log": "sensor_data",
        "maintenance_record": "maintenance_log",
        "repair_log": "maintenance_log",
        "email": "communications",
        "chat_log": "communications",
        "message_log": "communications",
        "personnel_record": "hr_record",
        "employee_record": "hr_record",
        "invoice": "financial_record",
        "transaction_log": "financial_record",
    }

    if slug in allowed:
        return slug
    if slug in alias_map:
        return alias_map[slug]

    heuristics = [
        (("forensic", "fingerprint", "dna", "ballistic"), "forensic_log"),
        (("witness", "statement", "testimony"), "witness_statement"),
        (("interview", "interrogation", "debrief", "security"), "security_interview"),
        (("badge", "door", "entry", "exit", "biometric", "access"), "access_log"),
        (("wifi", "network", "ip", "dns", "firewall", "packet"), "network_log"),
        (("sensor", "telemetry", "gps", "rfid", "temperature", "hvac"), "sensor_data"),
        (("camera", "cctv", "video", "surveillance"), "surveillance"),
        (("maintenance", "repair", "service", "work_order"), "maintenance_log"),
        (("hr", "human_resources", "personnel", "employee"), "hr_record"),
        (("finance", "invoice", "expense", "payment", "transaction"), "financial_record"),
        (("email", "chat", "message", "sms", "call"), "communications"),
        (("ransom", "extortion"), "ransom_note"),
        (("osint", "public", "social", "news"), "osint"),
        (("inventory", "checkout", "schedule", "policy", "administrative"), "administrative"),
        (("artifact", "physical", "object", "device"), "physical"),
    ]
    for keywords, canonical in heuristics:
        if any(keyword in slug for keyword in keywords):
            return canonical

    sorted_scores = sorted(label_scores, key=lambda s: s.score, reverse=True)
    if sorted_scores and sorted_scores[0].score >= LABEL_SCORE_CUTOFF:
        top_label = sorted_scores[0].label
        if top_label in allowed:
            return top_label

    return "unclassified"


def _finalize_clerk_details(details: EvidenceClerkDetails) -> EvidenceClerkDetails:
    """Fill application-controlled clerk fields after model generation."""
    return details.model_copy(
        update={
            "canonical_evidence_type": canonicalize_evidence_type(
                details.evidence_type, details.label_scores
            )
        }
    )


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Check if an exception is a rate-limit (429) error from the Gemini SDK."""
    exc_type = type(exc).__name__
    if "ResourceExhausted" in exc_type or "TooManyRequests" in exc_type:
        return True
    if "429" in str(exc):
        return True
    return False


def _normalize_clerk_payload(raw: dict) -> dict:
    """Coerce common LLM schema deviations into the expected format.

    Handles:
    - label_scores as flat dict {"forensic_log": 1, ...} → list of LabelScore dicts
    - Missing summary field → derived from evidence_type or set to a default
    """
    # Fix label_scores: dict → list[LabelScore]
    ls = raw.get("label_scores")
    if isinstance(ls, dict):
        raw["label_scores"] = [
            {"label": k, "score": v} for k, v in ls.items()
        ]

    # Fix missing summary
    if "summary" not in raw or not raw["summary"]:
        raw["summary"] = raw.get("evidence_type") or "No summary extracted"

    if "canonical_evidence_type" in raw and not raw["canonical_evidence_type"]:
        raw.pop("canonical_evidence_type", None)

    return raw


def _evidence_clerk_call_siliconflow(system_prompt: str, user_content: str) -> EvidenceClerkDetails:
    """Evaluate evidence details via SiliconFlow (OpenAI-compatible)."""
    if not SILICONFLOW_API_KEY:
        raise RuntimeError("SILICONFLOW_API_KEY is required for SiliconFlow evidence clerk.")

    client = OpenAI(api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_BASE_URL)
    completion = client.chat.completions.create(
        model=SILICONFLOW_EVIDENCE_CLERK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    json_text = completion.choices[0].message.content
    if not json_text:
        raise RuntimeError("SiliconFlow returned empty result.")

    raw = json.loads(json_text)
    raw = _normalize_clerk_payload(raw)
    return _finalize_clerk_details(EvidenceClerkDetails.model_validate(raw))


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
    # Build the label list for the prompt
    label_list = ", ".join(DEFAULT_EVIDENCE_LABELS)

    system_prompt = (
        "You are an evidence clerk helping law enforcement. "
        "Given a single piece of evidence (statement, log, report), "
        "extract only factual, directly stated details. Do not infer beyond "
        "what is written. Return JSON matching the EvidenceClerkDetails schema.\n\n"
        "IMPORTANT: For the `label_scores` field, you MUST rate ALL of the "
        "following labels from 1 to 10 based on how well each label describes "
        "this evidence. 10 = perfect match, 1 = completely irrelevant.\n\n"
        f"Labels to rate: {label_list}\n\n"
        "Return one LabelScore entry for each label above. Be strict: only give "
        "high scores (8-10) if the label genuinely matches the content."
    )

    if EVIDENCE_CLERK_PROVIDER == "siliconflow":
        return await asyncio.to_thread(_evidence_clerk_call_siliconflow, system_prompt, text)

    if not GOOGLE_API_KEY2:
        raise RuntimeError("GOOGLE_API_KEY2 is required for the evidence clerk (Gemini).")

    client = genai.Client(api_key=GOOGLE_API_KEY2)
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
        if _is_rate_limit_error(e):
            logger.warning("Rate limited by Gemini API, will retry: %s", e)
        raise
    finally:
        await client.aio.aclose()

    # With response_schema + application/json, google-genai populates
    # `parsed` with a Pydantic model instance when possible.
    if hasattr(response, "parsed") and isinstance(response.parsed, EvidenceClerkDetails):
        return _finalize_clerk_details(response.parsed)

    # Fallback: parse JSON text manually if `parsed` is not set
    if hasattr(response, "text") and response.text:
        return _finalize_clerk_details(
            EvidenceClerkDetails.model_validate_json(response.text)
        )

    raise RuntimeError("Evidence clerk returned no usable JSON payload.")
