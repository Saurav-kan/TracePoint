"""Corroboration Clustering Layer for Adversarial effort mode."""

import json
from typing import List
from pydantic import BaseModel, Field
from app.schemas.research import ResearchResponse
from app.agents.judge_llm import judge_llm_completion
from app.agents.judge_agent import _format_chunks_for_overall

class CorroborationCluster(BaseModel):
    description: str = Field(..., description="Description of the suspiciously synchronized evidence.")
    evidence_indices: List[int] = Field(..., description="Indices of the evidence involved.")

class CorroborationResult(BaseModel):
    suspicious_clusters: List[CorroborationCluster] = Field(default_factory=list)
    has_suspicious_coordination: bool = Field(False)

CORROBORATION_PROMPT = """
You are a Corroboration Clustering Layer for a forensic investigation system.
Given the raw evidence chunks, identify "perfectly synchronized" evidence. 
This includes multiple witness accounts using identical unique phrases, or multiple 
independent system logs timestamped within an impossibly narrow window, suggesting 
coordination, log tampering, or a frame job rather than independent truths.

RAW EVIDENCE CHUNKS:
{chunks}

Return a JSON object with this shape:
{
  "has_suspicious_coordination": true/false,
  "suspicious_clusters": [
    {
      "description": "<Why this evidence set looks tampered/coordinated>",
      "evidence_indices": []
    }
  ]
}
"""

async def run_corroboration(research_resp: ResearchResponse) -> CorroborationResult:
    chunks = _format_chunks_for_overall(research_resp)
    prompt = CORROBORATION_PROMPT.format(chunks=chunks)
    try:
        raw = await judge_llm_completion(
            "You are a forensic corroboration cluster analyzer. Output strictly JSON.",
            prompt,
            response_format={"type": "json_object"}
        )
        data = json.loads(raw)
        has_coord = bool(data.get("has_suspicious_coordination", False))
        clusters = []
        for c in data.get("suspicious_clusters", []):
            clusters.append(CorroborationCluster(
                description=str(c.get("description", "")),
                evidence_indices=[]
            ))
        return CorroborationResult(has_suspicious_coordination=has_coord, suspicious_clusters=clusters)
    except Exception:
        return CorroborationResult(has_suspicious_coordination=False, suspicious_clusters=[])
