"""LangGraph definition for the cyclic investigation workflow."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.nodes import gatekeeper_node, judge_node, planner_node, research_node, challenger_node, reconciliation_node
from app.graph.state import PipelineState


def _route_after_reconciliation(state: PipelineState) -> str:
    """Loop when the challenger asks for more evidence via retrieval gap, otherwise end."""

    challenger_result = state.get("challenger_result")
    completed_iterations = len(state.get("iterations", []))
    max_iterations = state.get("max_iterations", 1)

    if (
        challenger_result is not None
        and challenger_result.retrieval_gap
        and completed_iterations < max_iterations
    ):
        return "planner_node"

    return "__end__"


def build_graph() -> StateGraph:
    """Construct the planner -> research -> judge refinement graph."""

    graph = StateGraph(PipelineState)

    graph.add_node("planner_node", planner_node)
    graph.add_node("gatekeeper_node", gatekeeper_node)
    graph.add_node("research_node", research_node)
    graph.add_node("judge_node", judge_node)
    graph.add_node("challenger_node", challenger_node)
    graph.add_node("reconciliation_node", reconciliation_node)

    graph.set_entry_point("planner_node")

    graph.add_edge("planner_node", "gatekeeper_node")
    graph.add_edge("gatekeeper_node", "research_node")
    graph.add_edge("research_node", "judge_node")
    graph.add_edge("judge_node", "challenger_node")
    graph.add_edge("challenger_node", "reconciliation_node")

    graph.add_conditional_edges(
        "reconciliation_node",
        _route_after_reconciliation,
        {
            "planner_node": "planner_node",
            "__end__": END,
        },
    )

    return graph


compiled_graph = build_graph().compile()
