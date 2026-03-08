"""Graph node functions for the LangGraph investigation pipeline.

Each node is a thin wrapper around an existing agent or gatekeeper function.
Nodes read from and write to the shared PipelineState TypedDict.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.agents.gatekeeper import validate_planner_output
from app.agents.judge_agent import run_judge
from app.agents.planner_agent import run_planner
from app.agents.research_agent import run_research
from app.graph.state import PipelineState


async def planner_node(state: PipelineState) -> PipelineState:
    """Run the planner agent.

    In normal mode: generates 5 investigative tasks, increments attempt counter.
    In refinement mode (refinement_context present): produces 1-3 supplemental
    tasks written to planner_supplemental_response.
    """
    refinement_context = state.get("refinement_context")

    if refinement_context is not None:
        # Refinement mode — produce supplemental tasks, skip attempt counting
        response = await run_planner(
            state["case"],
            state["request"],
            brief_text_override=state.get("brief_text_override"),
            refinement_context=refinement_context,
        )
        return {"planner_supplemental_response": response}

    # Normal mode
    attempts = state.get("planner_attempts", 0) + 1
    response = await run_planner(
        state["case"],
        state["request"],
        brief_text_override=state.get("brief_text_override"),
    )
    return {
        "planner_response": response,
        "planner_attempts": attempts,
    }


async def planner_gatekeeper_node(state: PipelineState) -> PipelineState:
    """Validate the planner output against investigative heuristics."""
    gate = validate_planner_output(state["planner_response"], state["case"])
    return {"planner_gate": gate}


async def research_node(state: PipelineState) -> PipelineState:
    """Run the research agent to retrieve evidence for each planner task."""
    response = run_research(state["planner_response"])
    return {"research_response": response}


async def judge_node(state: PipelineState) -> PipelineState:
    """Run the judge agent to synthesize evidence into a verdict.

    The judge internally runs its own gatekeeper (judge_gatekeeper)
    and attaches the validation result to the response.
    """
    refinement_performed = state.get("judge_refinement_attempts", 0) > 0
    response = await run_judge(
        state["research_response"],
        case=state["case"],
        case_brief_override=state.get("brief_text_override"),
        refinement_performed=refinement_performed,
    )
    return {"judge_response": response}


async def prepare_refinement_node(state: PipelineState) -> PipelineState:
    """Prepare the refinement context from the judge's refinement questions.

    Reads judge_response.refinement_questions, formats them into a string
    for the planner, and sets judge_refinement_attempts to 1 so the loop
    cannot trigger again.
    """
    judge_resp = state["judge_response"]
    questions = judge_resp.refinement_questions
    formatted = "\n".join(f"- {q}" for q in questions)
    return {
        "refinement_context": formatted,
        "judge_refinement_attempts": 1,
    }


async def research_supplemental_node(state: PipelineState) -> PipelineState:
    """Run research on supplemental planner tasks and merge with original results.

    Calls run_research on planner_supplemental_response, then appends
    the supplemental tasks to the existing research_response.
    """
    supplemental_planner = state["planner_supplemental_response"]
    supplemental_research = run_research(supplemental_planner)

    original_research = state["research_response"]
    merged_tasks = list(original_research.tasks) + list(supplemental_research.tasks)

    # Build merged response preserving original case_id and fact_to_check
    from app.schemas.research import ResearchResponse

    merged = ResearchResponse(
        case_id=original_research.case_id,
        fact_to_check=original_research.fact_to_check,
        tasks=merged_tasks,
    )
    return {
        "research_response": merged,
        # Clear refinement_context so planner routing works correctly
        # if the planner node is visited again (it won't be, but defensive)
        "refinement_context": None,
        "planner_supplemental_response": None,
    }


async def error_node(state: PipelineState) -> PipelineState:
    """Terminal node: raises HTTP 500 with gatekeeper failure reasons."""
    gate = state.get("planner_gate")
    reasons = gate.reasons if gate else ["unknown error"]
    detail = "Planner output failed validation: " + "; ".join(reasons)
    raise HTTPException(status_code=500, detail=detail)
