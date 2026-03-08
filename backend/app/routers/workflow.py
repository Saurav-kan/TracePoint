"""Workflow API routes: LangGraph-based planner -> research -> judge pipeline.

Provides:
  POST /workflow/run          — legacy synchronous endpoint (returns JudgeResponse)
  POST /workflow/run-stream   — SSE streaming endpoint (streams pipeline events)
  GET  /workflow/logs/{case_id}           — list past investigations
  GET  /workflow/logs/{case_id}/{log_id}  — retrieve a single investigation
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Case, CaseBrief, InvestigationLog
from app.db.session import get_session
from app.graph.graph import compiled_graph
from app.graph.state import PipelineState
from app.schemas.judge import JudgeResponse
from app.schemas.planner import PlannerRequest
from app.schemas.workflow import (
    EFFORT_ITERATIONS,
    InvestigationLogSummary,
    WorkflowRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow", tags=["workflow"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_brief(session: Session, case_id: str, brief_id: int | None) -> tuple[Case, str | None]:
    """Look up case + optional brief. Raises HTTPException on not-found."""
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    brief_text_override: str | None = None
    if brief_id is not None:
        brief = session.get(CaseBrief, brief_id)
        if brief is None or str(brief.case_id) != case_id:
            raise HTTPException(status_code=404, detail="Brief not found")
        brief_text_override = brief.brief_text

    return case, brief_text_override


def _build_initial_state(
    case: Case,
    req: WorkflowRequest | PlannerRequest,
    brief_text_override: str | None,
    prior_iterations_summary: str | None = None,
) -> PipelineState:
    """Build the initial PipelineState for the LangGraph invocation."""
    # The graph expects PlannerRequest; convert if needed
    if isinstance(req, WorkflowRequest):
        planner_req = PlannerRequest(
            case_id=req.case_id,
            fact_to_check=req.fact_to_check,
            brief_id=req.brief_id,
        )
    else:
        planner_req = req

    state: PipelineState = {
        "case": case,
        "request": planner_req,
        "brief_text_override": brief_text_override,
        "planner_response": None,
        "planner_attempts": 0,
        "planner_gate": None,
        "research_response": None,
        "judge_response": None,
        "judge_refinement_attempts": 0,
        "refinement_context": None,
        "planner_supplemental_response": None,
    }
    if prior_iterations_summary is not None:
        state["prior_iterations_summary"] = prior_iterations_summary
    return state


def _sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


def _format_prior_iterations_summary(all_iterations: list[dict]) -> str:
    """Format prior iterations' verdicts and findings for the planner."""
    parts: list[str] = []
    for i, it in enumerate(all_iterations, 1):
        judge = it.get("judge") or {}
        ov = judge.get("overall_verdict") or {}
        verdict = ov.get("verdict", "unknown")
        rationale = ov.get("rationale", "")
        parts.append(
            f"Pass {i}: Verdict={verdict}\n"
            f"Rationale: {rationale[:500]}{'...' if len(rationale) > 500 else ''}"
        )
    return (
        "PRIOR INVESTIGATION PASSES (use these to inform your task design;\n"
        "probe gaps, challenge weak verdicts, or strengthen confidence):\n\n"
        + "\n\n".join(parts)
    )


# Results directory lives alongside the backend source
_RESULTS_DIR = Path(__file__).resolve().parents[2] / "tests" / "results"


def _dump_results_to_file(
    case_title: str,
    claim: str,
    effort_level: str,
    final_verdict: dict | None,
    iterations: list[dict],
) -> Path | None:
    """Write a human-readable results file for debugging/testing."""
    try:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_claim = claim[:40].replace(" ", "_").replace("?", "").replace("'", "")
        filename = f"{ts}_{safe_claim}.txt"
        filepath = _RESULTS_DIR / filename

        lines: list[str] = []
        lines.append("=" * 70)
        lines.append(f"TRACEPOINT INVESTIGATION RESULT")
        lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
        lines.append("=" * 70)
        lines.append(f"\nCase:          {case_title}")
        lines.append(f"Claim:         {claim}")
        lines.append(f"Effort Level:  {effort_level.upper()}")
        lines.append(f"Iterations:    {len(iterations)}")

        if final_verdict:
            ov = final_verdict.get("overall_verdict") or {}
            verdict_str = str(ov.get("verdict", "N/A")).upper()
            lines.append(f"\n{'─' * 70}")
            lines.append("FINAL VERDICT")
            lines.append(f"{'─' * 70}")
            lines.append(f"Overall:       {verdict_str}")
            lines.append(f"Fact Checked:  {final_verdict.get('fact_to_check', 'N/A')}")

            tasks = final_verdict.get("tasks", [])
            if tasks:
                lines.append(f"\n{'─' * 70}")
                lines.append(f"TASK-LEVEL ASSESSMENTS ({len(tasks)} tasks)")
                lines.append(f"{'─' * 70}")
                for i, task in enumerate(tasks, 1):
                    lines.append(f"\n  [{i}] {task.get('question_text', 'N/A')}")
                    lines.append(f"      Answer:     {task.get('answer', 'N/A')}")
                    conf = task.get("confidence")
                    lines.append(f"      Confidence: {conf if conf is not None else 'N/A'}")
                    key_facts = task.get("key_facts", [])
                    if key_facts:
                        lines.append("      Key Facts:")
                        for kf in key_facts:
                            direction = "↑" if kf.get("supports_claim", False) else "↓"
                            lines.append(f"        {direction} {kf.get('description', 'N/A')}")

        # Include planner tasks from first iteration for context
        if iterations and iterations[0].get("planner"):
            planner = iterations[0]["planner"]
            ptasks = planner.get("tasks", [])
            if ptasks:
                lines.append(f"\n{'─' * 70}")
                lines.append(f"PLANNER TASKS ({len(ptasks)} tasks)")
                lines.append(f"{'─' * 70}")
                for i, pt in enumerate(ptasks, 1):
                    lines.append(f"  [{i}] [{pt.get('type', 'N/A')}] {pt.get('question_text', 'N/A')}")
                    lines.append(f"      Vector Query: {pt.get('vector_query', 'N/A')}")

        # Include research evidence from first iteration
        if iterations and iterations[0].get("research"):
            research = iterations[0]["research"]
            rtasks = research.get("tasks", [])
            if rtasks:
                lines.append(f"\n{'─' * 70}")
                lines.append(f"RESEARCH EVIDENCE")
                lines.append(f"{'─' * 70}")
                for i, rt in enumerate(rtasks, 1):
                    lines.append(f"\n  [{i}] {rt.get('question_text', 'N/A')}")
                    evidence = rt.get("evidence", [])
                    if evidence:
                        for ev in evidence[:3]:  # Top 3 per task
                            lines.append(f"      📄 {ev.get('source_document', 'unknown')} (score: {ev.get('score', 0):.2f})")
                            chunk = ev.get("chunk", "")[:150]
                            lines.append(f"         {chunk}...")
                    else:
                        lines.append("      (no evidence retrieved)")

        lines.append(f"\n{'=' * 70}")
        lines.append("END OF REPORT")
        lines.append("=" * 70)

        filepath.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Results written to %s", filepath)
        return filepath
    except Exception as e:
        logger.error("Failed to dump results to file: %s", e)
        return None


# ---------------------------------------------------------------------------
# POST /workflow/run  (legacy synchronous)
# ---------------------------------------------------------------------------

@router.post("/run", response_model=JudgeResponse)
async def run_workflow(req: PlannerRequest) -> JudgeResponse:
    """Run the full pipeline synchronously. Returns JudgeResponse."""
    session: Session = get_session()
    try:
        case, brief_text_override = _resolve_brief(
            session, str(req.case_id), req.brief_id
        )
    finally:
        session.close()

    initial_state = _build_initial_state(case, req, brief_text_override)
    result = await compiled_graph.ainvoke(initial_state)
    return result["judge_response"]


# ---------------------------------------------------------------------------
# POST /workflow/run-stream  (SSE streaming)
# ---------------------------------------------------------------------------

async def _stream_pipeline(
    req: WorkflowRequest,
    case: Case,
    brief_text_override: str | None,
) -> AsyncGenerator[str, None]:
    """Generator that runs the pipeline and yields SSE events."""
    iterations_count = EFFORT_ITERATIONS.get(req.effort_level, 1)
    all_iterations: list[dict] = []
    pipeline_error: str | None = None

    try:
        for iteration in range(1, iterations_count + 1):
            # --- Planner ---
            yield _sse_event("step", {
                "step": "planner", "status": "running",
                "iteration": iteration, "total_iterations": iterations_count,
            })

            # Build prior iterations summary for passes 2+ so the planner can refine
            prior_summary: str | None = None
            if iteration > 1 and all_iterations:
                prior_summary = _format_prior_iterations_summary(all_iterations)

            initial_state = _build_initial_state(
                case, req, brief_text_override, prior_iterations_summary=prior_summary
            )
            try:
                result = await compiled_graph.ainvoke(initial_state)
            except Exception as e:
                logger.error("Pipeline failed on iteration %d: %s", iteration, e)
                pipeline_error = str(e)
                yield _sse_event("error", {"detail": str(e)})
                return

            planner_data = result.get("planner_response")
            yield _sse_event("step", {
                "step": "planner", "status": "complete",
                "iteration": iteration, "total_iterations": iterations_count,
                "data": planner_data.model_dump(mode="json") if planner_data else None,
            })

            # --- Gatekeeper ---
            gate_data = result.get("planner_gate")
            yield _sse_event("step", {
                "step": "gatekeeper", "status": "complete",
                "iteration": iteration, "total_iterations": iterations_count,
                "data": gate_data.model_dump(mode="json") if hasattr(gate_data, "model_dump") else (gate_data if isinstance(gate_data, dict) else None),
            })

            # --- Research ---
            research_data = result.get("research_response")
            yield _sse_event("step", {
                "step": "research", "status": "complete",
                "iteration": iteration, "total_iterations": iterations_count,
                "data": research_data.model_dump(mode="json") if research_data else None,
            })

            # --- Judge ---
            judge_data = result.get("judge_response")
            yield _sse_event("step", {
                "step": "judge", "status": "complete",
                "iteration": iteration, "total_iterations": iterations_count,
                "data": judge_data.model_dump(mode="json") if judge_data else None,
            })

            iteration_result = {
                "iteration": iteration,
                "planner": planner_data.model_dump(mode="json") if planner_data else None,
                "gatekeeper": gate_data.model_dump(mode="json") if hasattr(gate_data, "model_dump") else gate_data,
                "research": research_data.model_dump(mode="json") if research_data else None,
                "judge": judge_data.model_dump(mode="json") if judge_data else None,
            }
            all_iterations.append(iteration_result)

        # Use the last judge result as the final verdict
        final_verdict = all_iterations[-1]["judge"] if all_iterations else None

        # Persist to investigation_logs
        log_id = -1
        try:
            session = get_session()
            log_entry = InvestigationLog(
                case_id=str(req.case_id),
                claim=req.fact_to_check,
                effort_level=req.effort_level,
                verdict=(final_verdict.get("overall_verdict") or {}).get("verdict", "uncertain") if final_verdict else "uncertain",
                result_payload={
                    "effort_level": req.effort_level,
                    "iterations": all_iterations,
                    "final_verdict": final_verdict,
                },
            )
            session.add(log_entry)
            session.commit()
            log_id = log_entry.id
            session.close()
        except Exception as e:
            logger.error("Failed to persist investigation log: %s", e)

        # Final done event
        done_payload = {
            "log_id": log_id,
            "data": {
                "log_id": log_id,
                "effort_level": req.effort_level,
                "iterations": all_iterations,
                "final_verdict": final_verdict,
            },
        }
        yield _sse_event("done", done_payload)

    finally:
        # Always dump results file — even on pipeline failure — so partial
        # data is preserved for debugging.
        final_verdict = all_iterations[-1]["judge"] if all_iterations else None
        _dump_results_to_file(
            case_title=case.title,
            claim=req.fact_to_check,
            effort_level=req.effort_level,
            final_verdict=final_verdict,
            iterations=all_iterations,
        )


@router.post("/run-stream")
async def run_workflow_stream(req: WorkflowRequest):
    """SSE streaming endpoint that emits pipeline step events as they complete."""
    # Resolve case/brief before streaming so HTTPException returns proper 404
    # (once StreamingResponse starts, status 200 is committed and exceptions
    # would cause an abrupt closed stream with no error event)
    session: Session = get_session()
    try:
        case, brief_text_override = _resolve_brief(
            session, str(req.case_id), req.brief_id
        )
    finally:
        session.close()

    return StreamingResponse(
        _stream_pipeline(req, case, brief_text_override),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Investigation log CRUD
# ---------------------------------------------------------------------------

@router.get("/logs/{case_id}")
async def list_investigation_logs(case_id: str) -> list[InvestigationLogSummary]:
    """List all investigation logs for a case."""
    session = get_session()
    try:
        stmt = (
            select(InvestigationLog)
            .where(InvestigationLog.case_id == case_id)
            .order_by(InvestigationLog.created_at.desc())
        )
        logs = session.execute(stmt).scalars().all()
        return [
            InvestigationLogSummary(
                id=log.id,
                claim=log.claim,
                effort_level=log.effort_level,
                verdict=log.verdict,
                created_at=log.created_at,
            )
            for log in logs
        ]
    finally:
        session.close()


@router.get("/logs/{case_id}/{log_id}")
async def get_investigation_log(case_id: str, log_id: int):
    """Retrieve a single investigation log."""
    session = get_session()
    try:
        log = session.get(InvestigationLog, log_id)
        if log is None or str(log.case_id) != case_id:
            raise HTTPException(status_code=404, detail="Investigation log not found")
        return log.result_payload
    finally:
        session.close()
