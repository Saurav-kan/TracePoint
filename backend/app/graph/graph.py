"""LangGraph StateGraph definition for the investigation pipeline.

Compiles the Planner → Gatekeeper → Research → Judge workflow into a
reusable graph with a conditional retry loop for planner validation
and a one-time judge refinement feedback loop.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.nodes import (
    error_node,
    judge_node,
    planner_gatekeeper_node,
    planner_node,
    prepare_refinement_node,
    research_node,
    research_supplemental_node,
)
from app.graph.state import PipelineState

MAX_PLANNER_ATTEMPTS = 3


def _route_after_gatekeeper(state: PipelineState) -> str:
    """Conditional edge: decide what happens after planner gatekeeper runs."""
    gate = state.get("planner_gate")
    if gate and not gate.needs_regeneration:
        return "research_node"

    attempts = state.get("planner_attempts", 0)
    if attempts >= MAX_PLANNER_ATTEMPTS:
        # Best-effort fallback: use whatever the planner produced rather than
        # crashing with HTTP 500. Gatekeeper reasons are preserved in state.
        return "research_node"

    return "planner_node"


def _route_after_planner(state: PipelineState) -> str:
    """Conditional edge: route planner output based on mode.

    If refinement_context is set, the planner just produced supplemental
    tasks — route to research_supplemental_node (bypassing gatekeeper).
    If a schema validation error already set a failed planner_gate,
    apply retry/error logic directly (no valid response for gatekeeper).
    Otherwise, follow the normal path to the gatekeeper.
    """
    if state.get("refinement_context") is not None:
        return "research_supplemental_node"

    # Schema validation failed in planner_node — gate already set
    gate = state.get("planner_gate")
    if gate and gate.needs_regeneration:
        attempts = state.get("planner_attempts", 0)
        if attempts >= MAX_PLANNER_ATTEMPTS:
            return "error_node"
        return "planner_node"

    return "planner_gatekeeper_node"


def _route_after_judge(state: PipelineState) -> str:
    """Conditional edge: decide whether to refine or finish.

    If the judge signals needs_refinement AND no refinement has been
    performed yet, route to prepare_refinement_node for a supplemental
    research pass. Otherwise, end the pipeline.
    """
    judge_resp = state.get("judge_response")
    if (
        judge_resp
        and judge_resp.needs_refinement
        and state.get("judge_refinement_attempts", 0) < 1
    ):
        return "prepare_refinement_node"
    return "__end__"


def build_graph() -> StateGraph:
    """Construct the investigation pipeline graph."""
    graph = StateGraph(PipelineState)

    graph.add_node("planner_node", planner_node)
    graph.add_node("planner_gatekeeper_node", planner_gatekeeper_node)
    graph.add_node("research_node", research_node)
    graph.add_node("judge_node", judge_node)
    graph.add_node("prepare_refinement_node", prepare_refinement_node)
    graph.add_node("research_supplemental_node", research_supplemental_node)
    graph.add_node("error_node", error_node)

    graph.set_entry_point("planner_node")

    # Planner → route based on mode (normal → gatekeeper, refinement → supplemental research)
    graph.add_conditional_edges(
        "planner_node",
        _route_after_planner,
        {
            "planner_gatekeeper_node": "planner_gatekeeper_node",
            "research_supplemental_node": "research_supplemental_node",
            "planner_node": "planner_node",
            "error_node": "error_node",
        },
    )

    # Gatekeeper → route based on validation result
    graph.add_conditional_edges(
        "planner_gatekeeper_node",
        _route_after_gatekeeper,
        {
            "research_node": "research_node",
            "planner_node": "planner_node",
            "error_node": "error_node",
        },
    )

    graph.add_edge("research_node", "judge_node")

    # Judge → route: refine or end
    graph.add_conditional_edges(
        "judge_node",
        _route_after_judge,
        {
            "prepare_refinement_node": "prepare_refinement_node",
            "__end__": END,
        },
    )

    # Refinement path
    graph.add_edge("prepare_refinement_node", "planner_node")
    graph.add_edge("research_supplemental_node", "judge_node")

    graph.add_edge("error_node", END)

    return graph


compiled_graph = build_graph().compile()
