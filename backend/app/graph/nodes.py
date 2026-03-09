"""Graph nodes for the cyclic planner/research/judge workflow."""

from __future__ import annotations

import asyncio
import logging

from app.agents.gatekeeper import GatekeeperResult, validate_planner_output
from app.agents.judge_agent import run_judge
from app.agents.planner_agent import run_planner
from app.agents.research_agent import run_research
from app.graph.state import PipelineState, WorkflowIteration

logger = logging.getLogger(__name__)

_PLANNER_MAX_ATTEMPTS = 3


def _iteration_number(state: PipelineState) -> int:
    """Return the 1-based iteration currently being executed."""

    return len(state.get("iterations", [])) + 1


def _build_prior_iterations_summary(state: PipelineState) -> str | None:
    """Summarize earlier passes so refinement planning has context."""

    iterations = state.get("iterations", [])
    if not iterations:
        return None

    lines = [
        "PRIOR INVESTIGATION PASSES:",
    ]
    for item in iterations:
        judge = item["judge"]
        lines.append(
            f"- Iteration {item['iteration']}: verdict={judge.overall_verdict.verdict}; "
            f"needs_refinement={judge.needs_refinement}; "
            f"rationale={judge.overall_verdict.rationale}"
        )
        if judge.refinement_questions:
            lines.append(
                "  Outstanding questions: "
                + "; ".join(judge.refinement_questions)
            )

    return "\n".join(lines)


def _build_refinement_context(state: PipelineState) -> str:
    """Format judge follow-up questions for the next planner pass."""

    judge = state["judge_result"]
    questions = judge.refinement_questions or []

    lines = [
        "The previous judge pass reported insufficient evidence for these questions:",
    ]
    lines.extend(f"- {question}" for question in questions)

    if judge.refinement_suggestion:
        lines.append("")
        lines.append(f"Additional judge guidance: {judge.refinement_suggestion}")

    return "\n".join(lines)


async def planner_node(state: PipelineState) -> dict:
    """Run planner generation, including gatekeeper retries for the first pass."""

    case = state["case"]
    request = state["request"]
    brief_text_override = state.get("brief_text_override")
    refinement_context = state.get("refinement_context")
    prior_iterations_summary = _build_prior_iterations_summary(state)

    if refinement_context:
        planner_result = await run_planner(
            case,
            request,
            brief_text_override=brief_text_override,
            refinement_context=refinement_context,
            prior_iterations_summary=prior_iterations_summary,
        )
        gatekeeper_result = GatekeeperResult(
            valid=True,
            reasons=["Refinement pass bypassed the full 10-task gatekeeper checks."],
            needs_regeneration=False,
        )
        return {
            "planner_result": planner_result,
            "gatekeeper_result": gatekeeper_result,
        }

    planner_result = None
    gatekeeper_result = None
    for attempt in range(1, _PLANNER_MAX_ATTEMPTS + 1):
        planner_result = await run_planner(
            case,
            request,
            brief_text_override=brief_text_override,
            prior_iterations_summary=prior_iterations_summary,
        )
        gatekeeper_result = validate_planner_output(planner_result, case)
        if gatekeeper_result.valid:
            break
        logger.warning(
            "Planner output failed gatekeeper validation (attempt %s): %s",
            attempt,
            "; ".join(gatekeeper_result.reasons),
        )

    if planner_result is None or gatekeeper_result is None:
        raise RuntimeError("Planner node failed to produce a result.")

    if not gatekeeper_result.valid:
        detail = "Planner output failed validation: " + "; ".join(
            gatekeeper_result.reasons
        )
        raise RuntimeError(detail)

    return {
        "planner_result": planner_result,
        "gatekeeper_result": gatekeeper_result,
        "refinement_context": None,
    }


async def gatekeeper_node(state: PipelineState) -> dict:
    """Emit the gatekeeper result as a distinct graph step."""

    return {"gatekeeper_result": state["gatekeeper_result"]}


async def research_node(state: PipelineState) -> dict:
    """Run vector research for the current planner output."""

    research_result = await asyncio.to_thread(run_research, state["planner_result"])
    return {"research_result": research_result}


async def judge_node(state: PipelineState) -> dict:
    """Judge the current research pass and decide whether to refine."""

    iteration_number = _iteration_number(state)
    judge_result = await run_judge(
        state["research_result"],
        case=state["case"],
        case_brief_override=state.get("brief_text_override"),
        refinement_performed=iteration_number > 1,
    )

    iteration_record: WorkflowIteration = {
        "iteration": iteration_number,
        "planner": state["planner_result"],
        "gatekeeper": state["gatekeeper_result"],
        "research": state["research_result"],
        "judge": judge_result,
    }

    updates: dict = {
        "judge_result": judge_result,
        "iterations": [iteration_record],
    }

    max_iterations = state.get("max_iterations", 1)
    if judge_result.needs_refinement and iteration_number < max_iterations:
        updates["refinement_context"] = _build_refinement_context(
            {
                **state,
                "judge_result": judge_result,
            }
        )
    else:
        updates["final_verdict"] = judge_result
        updates["refinement_context"] = None

    return updates
