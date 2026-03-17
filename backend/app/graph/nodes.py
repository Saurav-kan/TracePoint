"""Graph nodes for the cyclic planner/research/judge workflow."""

from __future__ import annotations

import asyncio
import logging

from app.agents.gatekeeper import GatekeeperResult, validate_planner_output
from app.agents.judge_agent import run_judge
from app.agents.challenger import run_challenger
from app.agents.reconciliation import run_reconciliation
from app.agents.corroboration import run_corroboration
from app.agents.planner_agent import run_planner
from app.agents.research_agent import run_research
from app.graph.state import PipelineState, WorkflowIteration

logger = logging.getLogger(__name__)

_PLANNER_MAX_ATTEMPTS = 3


def _iteration_number(state: PipelineState) -> int:
    """Return the 1-based iteration currently being executed."""

    return len(state.get("iterations", [])) + 1

def _append_trace(node_name: str, payload: dict) -> dict:
    """Helper to append a trace record to the state."""
    return {"investigation_traces": [{"node": node_name, "payload": payload}]}


def _build_prior_iterations_summary(state: PipelineState) -> str | None:
    """Summarize earlier passes so refinement planning has context."""

    iterations = state.get("iterations", [])
    if not iterations:
        return None

    lines = [
        "PRIOR INVESTIGATION PASSES:",
    ]
    for item in iterations:
        recon = item.get("reconciliation")
        if recon:
            lines.append(
                f"- Iteration {item['iteration']}: verdict={recon.verdict}; "
                f"rationale={recon.rationale}"
            )

    return "\n".join(lines)


def _build_refinement_context(state: PipelineState) -> str:
    """Format challenger follow-up questions for the next planner pass."""
    challenger = state.get("challenger_result")
    effort_mode = state.get("effort_mode", "standard")
    completed_iterations = len(state.get("iterations", []))

    lines = []
    
    if effort_mode == "deep" and completed_iterations == 1 and challenger and challenger.has_disagreement:
        lines.append("[DEEP MODE ACTIVATED: SECOND PASS OVERRIDE]")
        lines.append("The following opposing narrative emerged during the first pass but was not definitively resolved:")
        if challenger.structured_disagreement:
            lines.append(f"Narrative: {challenger.structured_disagreement.narrative}")
        lines.append("Your sole objective for this entire pass is to forcefully query for evidence that specifically confirms or falsifies this alternative narrative.")
        return "\n".join(lines)

    questions = challenger.missed_queries if challenger else []
    lines.append("The previous Challenger pass identified missing evidence and requested these queries:")
    lines.extend(f"- {question}" for question in questions)

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
    regeneration_feedback = None
    for attempt in range(1, _PLANNER_MAX_ATTEMPTS + 1):
        planner_result = await run_planner(
            case,
            request,
            brief_text_override=brief_text_override,
            prior_iterations_summary=prior_iterations_summary,
            regeneration_feedback=regeneration_feedback,
        )
        gatekeeper_result = await validate_planner_output(planner_result, case)
        if gatekeeper_result.valid:
            break
        logger.warning(
            "Planner output failed gatekeeper validation (attempt %s): %s",
            attempt,
            "; ".join(gatekeeper_result.reasons),
        )
        regeneration_feedback = "\n".join(
            f"- {reason}" for reason in gatekeeper_result.reasons
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
        **_append_trace("planner_and_gatekeeper", {
            "planner": planner_result.model_dump() if hasattr(planner_result, "model_dump") else planner_result.dict(),
            "gatekeeper": gatekeeper_result.model_dump() if hasattr(gatekeeper_result, "model_dump") else gatekeeper_result.dict()
        })
    }

async def gatekeeper_node(state: PipelineState) -> dict:
    """Emit the gatekeeper result as a distinct graph step."""
    return {"gatekeeper_result": state["gatekeeper_result"]}


async def research_node(state: PipelineState) -> dict:
    """Run vector research for the current planner output."""

    research_result = await run_research(state["planner_result"])
    return {
        "research_result": research_result,
        **_append_trace("research", research_result.model_dump() if hasattr(research_result, "model_dump") else research_result.dict())
    }


async def judge_node(state: PipelineState) -> dict:
    """Judge the current research pass (without routing logic)."""

    iteration_number = _iteration_number(state)
    judge_result = await run_judge(
        state["research_result"],
        case=state["case"],
        case_brief_override=state.get("brief_text_override"),
        refinement_performed=iteration_number > 1,
    )
    return {
        "judge_result": judge_result,
        **_append_trace("judge", judge_result.model_dump() if hasattr(judge_result, "model_dump") else judge_result.dict())
    }

async def challenger_node(state: PipelineState) -> dict:
    """Adversarially evaluate the Judge's preliminary verdict."""
    adversarial_injection = None
    if state.get("effort_mode", "standard") == "adversarial":
        corrob_res = await run_corroboration(state["research_result"])
        if corrob_res.has_suspicious_coordination:
            cluster_text = "\n".join(c.description for c in corrob_res.suspicious_clusters)
            adversarial_injection = (
                "[ADVERSARIAL MODE: CORROBORATION CLUSTERING HAS IDENTIFIED SUSPICIOUS SYNCHRONIZATION]\n"
                f"{cluster_text}\n"
                "You MUST heavily weight theories of coordination, log tampering, or frame jobs over face-value truths."
            )

    challenger_result = await run_challenger(
        state["judge_result"],
        state["research_result"],
        case=state["case"],
        case_brief_override=state.get("brief_text_override"),
        adversarial_injection=adversarial_injection
    )
    
    trace_payload = challenger_result.model_dump() if hasattr(challenger_result, "model_dump") else challenger_result.dict()
    if adversarial_injection:
        trace_payload["adversarial_injection"] = adversarial_injection
        
    return {
        "challenger_result": challenger_result,
        **_append_trace("challenger", trace_payload)
    }

async def reconciliation_node(state: PipelineState) -> dict:
    """Reconcile Judge and Challenger conflict and perform routing logic."""
    iteration_number = _iteration_number(state)
    reconciliation_result = await run_reconciliation(
        state["judge_result"],
        state["challenger_result"],
        case=state["case"],
        case_brief_override=state.get("brief_text_override"),
    )

    iteration_record: WorkflowIteration = {
        "iteration": iteration_number,
        "planner": state["planner_result"],
        "gatekeeper": state["gatekeeper_result"],
        "research": state["research_result"],
        "judge": state["judge_result"],
        "challenger": state["challenger_result"],
        "reconciliation": reconciliation_result,
    }

    updates: dict = {
        "reconciliation_result": reconciliation_result,
        "iterations": [iteration_record],
    }

    challenger_result = state["challenger_result"]
    max_iterations = state.get("max_iterations", 1)
    effort_mode = state.get("effort_mode", "standard")

    needs_rerun = False
    
    # 1. Standard retrieval gap refinement
    if challenger_result.retrieval_gap and iteration_number < max_iterations:
        needs_rerun = True

    # 2. Deep mode second pass override
    if effort_mode == "deep" and iteration_number == 1 and challenger_result.has_disagreement:
        needs_rerun = True

    if needs_rerun:
        updates["refinement_context"] = _build_refinement_context(state)
    else:
        updates["final_verdict"] = reconciliation_result
        updates["refinement_context"] = None

    updates.update(_append_trace("reconciliation", reconciliation_result.model_dump() if hasattr(reconciliation_result, "model_dump") else reconciliation_result.dict()))
    return updates
