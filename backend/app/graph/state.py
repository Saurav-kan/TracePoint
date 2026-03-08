"""Shared state definition for the LangGraph investigation pipeline.

PipelineState is a TypedDict that flows through every node in the graph.
Each node reads the fields it needs and writes back the fields it produces.
"""

from __future__ import annotations

from typing import Optional, TypedDict

from app.agents.gatekeeper import GatekeeperResult
from app.db.models import Case
from app.schemas.judge import JudgeResponse
from app.schemas.planner import PlannerRequest, PlannerResponse
from app.schemas.research import ResearchResponse


class PipelineState(TypedDict, total=False):
    """Typed state dictionary shared across all graph nodes.

    Fields marked total=False are optional — nodes populate them
    progressively as the graph executes.
    """

    # --- Injected at graph entry (router) ---
    case: Case
    request: PlannerRequest
    brief_text_override: Optional[str]

    # --- Populated by planner_node ---
    planner_response: Optional[PlannerResponse]
    planner_attempts: int

    # --- Populated by planner_gatekeeper_node ---
    planner_gate: Optional[GatekeeperResult]

    # --- Populated by research_node ---
    research_response: Optional[ResearchResponse]

    # --- Populated by judge_node ---
    judge_response: Optional[JudgeResponse]

    # --- Refinement loop ---
    judge_refinement_attempts: int
    refinement_context: Optional[str]
    planner_supplemental_response: Optional[PlannerResponse]
