"""ReAct agent: dynamic iterative investigation and evidence synthesis."""

import json
from typing import List, Dict, Optional, Any
from uuid import UUID

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.config import (
    PLANNER_PROVIDER,
    OPENAI_PLANNER_MODEL,
    OPENAI_API_KEY,
    GROQ_PLANNER_MODEL,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GOOGLE_API_KEY,
    PLANNER_MODEL,
    SILICONFLOW_API_KEY,
    SILICONFLOW_BASE_URL,
    SILICONFLOW_JUDGE_MODEL
)
from app.schemas.planner import PlannerResponse, ResearchTask, MetadataFilterItem
from app.schemas.research import ResearchResponse
from app.agents.research_agent import run_research


INVESTIGATOR_SYSTEM_PROMPT = """You are an investigative ReAct agent for TracePoint, a law-enforcement fact-checking system.
Your job is to determine the absolute truth of a claim based on evidence.

You have access to the `search_evidence` tool which lets you query the vector database for evidence.
You must explicitly evaluate the burden of proof. Do not make assumptions. 
If the retrieved evidence is insufficient or contradictory, you MUST call the tool again with different queries or metadata filters.
Only stop when you have absolute confidence in your answer, or have exhausted reasonable searches.

When designing vector queries for the tool, use full descriptive sentences suitable for an embedding model, not single keywords.
Be balanced: actively search for confirming AND disconfirming evidence (alibis, alternative suspects, exonerating records, etc).

Use the tool as many times as necessary.

If you are ready to conclude the investigation, DO NOT call `search_evidence`. Instead, call `submit_verdict` with your final rationale and verdict.
"""

class MetadataFilterDict(BaseModel):
    key: str = Field(description="The metadata property to filter on, e.g., 'label' or 'evidence_type'")
    value: str = Field(description="The target value for the property, e.g., 'forensic_log'")

@tool
def search_evidence(query: str, case_id: str, metadata_filters: Optional[List[MetadataFilterDict]] = None) -> str:
    """Search for evidence related to the case.
    
    Args:
        query: A descriptive sentence for similarity search.
        case_id: The UUID of the case (must be provided).
        metadata_filters: Optional list of filters. Use to narrow evidence types.
    """
    m_filters = []
    if metadata_filters:
        m_filters = [MetadataFilterItem(key=f.key, value=f.value) for f in metadata_filters]
    
    task = ResearchTask(
        type="VERIFICATION",
        question_text=query,
        vector_query=query,
        metadata_filter=m_filters
    )
    
    plan_resp = PlannerResponse(
        case_id=UUID(case_id),
        fact_to_check=query,
        tasks=[task]
    )
    
    result: ResearchResponse = run_research(plan_resp)
    
    evidence_texts = []
    if result.tasks and result.tasks[0].evidence:
        for snip in result.tasks[0].evidence:
            source = snip.source_document or "unknown"
            evidence_texts.append(f"[{source}] {snip.chunk.strip()}")
            
    if not evidence_texts:
        return "No relevant evidence found for this query."
        
    return "\n".join(evidence_texts)

class JudgeTaskFactInput(BaseModel):
    description: str
    supports_claim: bool

@tool
def submit_verdict(verdict: str, rationale: str, supporting_facts: List[JudgeTaskFactInput], contradicting_facts: List[JudgeTaskFactInput]) -> str:
    """Submit the final verdict for the case.
    
    Args:
        verdict: One of: "true", "likely_true", "uncertain", "likely_false", "false".
        rationale: Explains how the evidence led to this verdict.
        supporting_facts: Highlights from the evidence that support the claim.
        contradicting_facts: Highlights from the evidence that contradict the claim.
    """
    return "VERDICT_SUBMITTED"

def get_react_llm():
    """Instantiate the LLM bound with tools."""
    if PLANNER_PROVIDER == "openai" and OPENAI_API_KEY:
        llm = ChatOpenAI(model=OPENAI_PLANNER_MODEL, api_key=OPENAI_API_KEY)
    elif PLANNER_PROVIDER == "groq" and GROQ_API_KEY:
        llm = ChatOpenAI(model=GROQ_PLANNER_MODEL, api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
    elif PLANNER_PROVIDER == "gemini" and GOOGLE_API_KEY:
        try:
            llm = ChatGoogleGenerativeAI(model=PLANNER_MODEL, api_key=GOOGLE_API_KEY)
        except ImportError:
            llm = ChatOpenAI(model=SILICONFLOW_JUDGE_MODEL, api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_BASE_URL)
    else:
        llm = ChatOpenAI(model=SILICONFLOW_JUDGE_MODEL, api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_BASE_URL)
        
    return llm.bind_tools([search_evidence, submit_verdict])
