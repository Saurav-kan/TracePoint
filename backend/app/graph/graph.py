"""LangGraph definition for the cyclic investigation workflow."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.nodes import gatekeeper_node, judge_node, planner_node, research_node
from app.graph.state import PipelineState


def _route_after_judge(state: PipelineState) -> str:
    """Loop when the judge asks for more evidence, otherwise end."""

    judge_result = state.get("judge_result")
    completed_iterations = len(state.get("iterations", []))
    max_iterations = state.get("max_iterations", 1)

    if (
        judge_result is not None
        and judge_result.needs_refinement
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

    graph.set_entry_point("planner_node")

    graph.add_edge("planner_node", "gatekeeper_node")
    graph.add_edge("gatekeeper_node", "research_node")
    graph.add_edge("research_node", "judge_node")

    graph.add_conditional_edges(
        "judge_node",
        _route_after_judge,
        {
            "planner_node": "planner_node",
            "__end__": END,
        },
    )

    return graph


compiled_graph = build_graph().compile()
