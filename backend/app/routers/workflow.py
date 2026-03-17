"""Workflow API routes for the cyclic investigation graph."""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Case, CaseBrief, InvestigationLog, InvestigationTrace
from app.db.session import get_session
from app.graph.graph import compiled_graph
from app.graph.state import PipelineState
from app.schemas.judge import JudgeResponse
from app.schemas.planner import PlannerRequest
from app.schemas.workflow import (
    EFFORT_ITERATIONS,
    InvestigationLogSummary,
    WorkflowResponse,
    WorkflowRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow", tags=["workflow"])
_RESULTS_DIR = Path(__file__).resolve().parents[2] / "tests" / "results"


def _resolve_brief(
    session: Session, case_id: str, brief_id: int | None
) -> tuple[Case, str | None]:
    """Look up case + optional brief."""

    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    brief_text_override = None
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
) -> PipelineState:
    """Build the graph state shared by both sync and streaming endpoints."""

    max_iterations = 1
    if isinstance(req, WorkflowRequest):
        planner_req = PlannerRequest(
            case_id=req.case_id,
            fact_to_check=req.fact_to_check,
            brief_id=req.brief_id,
        )
        max_iterations = EFFORT_ITERATIONS[req.effort_level]
    else:
        planner_req = req

    return {
        "case": case,
        "request": planner_req,
        "brief_text_override": brief_text_override,
        "max_iterations": max_iterations,
        "effort_mode": getattr(req, "effort_level", "standard"),
        "iterations": [],
    }


def _sse_event(event_type: str, data: dict) -> str:
    """Format a server-sent event payload."""

    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


def _model_to_dict(value):
    """Convert Pydantic models in graph state into JSON-safe dictionaries."""

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _build_workflow_response(
    *,
    log_id: int,
    effort_level: str,
    iterations: list[dict],
    final_verdict: JudgeResponse,
) -> WorkflowResponse:
    """Normalize graph state into the API response shape."""

    return WorkflowResponse(
        log_id=log_id,
        effort_level=effort_level,
        iterations=iterations,
        final_verdict=final_verdict,
    )


def _result_filename(claim: str) -> str:
    """Build a stable, filesystem-safe result filename."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", claim).strip("_")[:80]
    return f"{timestamp}_{slug or 'workflow_result'}.txt"


def _write_result_snapshot(req: WorkflowRequest, response: WorkflowResponse) -> None:
    """Persist a completed workflow response under backend/tests/results."""
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _RESULTS_DIR / _result_filename(req.fact_to_check)
    output_path.write_text(
        "\n".join(
            [
                "======================================================================",
                "TRACEPOINT WORKFLOW RESULT",
                f"Generated: {datetime.now(timezone.utc).isoformat()}",
                "======================================================================",
                "",
                "REQUEST",
                json.dumps(req.model_dump(mode="json"), indent=2),
                "",
                "RESPONSE",
                json.dumps(response.model_dump(mode="json"), indent=2),
                "",
            ]
        ),
        encoding="utf-8",
    )


@router.post("/run", response_model=JudgeResponse)
async def run_workflow(req: PlannerRequest) -> JudgeResponse:
    """Run the workflow synchronously and return the final judge response."""

    session: Session = get_session()
    try:
        case, brief_text_override = _resolve_brief(session, str(req.case_id), req.brief_id)
    finally:
        session.close()

    try:
        result = await compiled_graph.ainvoke(
            _build_initial_state(case, req, brief_text_override)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    final_verdict = result.get("final_verdict")
    if final_verdict is None:
        raise RuntimeError("Workflow completed without a final verdict.")
    return final_verdict


async def _stream_pipeline(
    req: WorkflowRequest,
    case: Case,
    brief_text_override: str | None,
) -> AsyncGenerator[str, None]:
    """Stream planner, gatekeeper, research, and judge steps over SSE."""

    initial_state = _build_initial_state(case, req, brief_text_override)
    total_iterations = initial_state["max_iterations"]
    completed_iterations = 0
    final_verdict: JudgeResponse | None = None
    iterations: list[dict] = []
    all_traces: list[dict] = []

    try:
        async for chunk in compiled_graph.astream(initial_state, stream_mode="updates"):
            active_iteration = completed_iterations + 1
            
            for node_name, outputs in chunk.items():
                if "investigation_traces" in outputs:
                    all_traces.extend(outputs["investigation_traces"])

            if "planner_node" in chunk:
                outputs = chunk["planner_node"]
                yield _sse_event(
                    "step",
                    {
                        "step": "planner",
                        "status": "complete",
                        "iteration": active_iteration,
                        "total_iterations": total_iterations,
                        "data": _model_to_dict(outputs["planner_result"]),
                    },
                )

            if "gatekeeper_node" in chunk:
                outputs = chunk["gatekeeper_node"]
                yield _sse_event(
                    "step",
                    {
                        "step": "gatekeeper",
                        "status": "complete",
                        "iteration": active_iteration,
                        "total_iterations": total_iterations,
                        "data": _model_to_dict(outputs["gatekeeper_result"]),
                    },
                )

            if "research_node" in chunk:
                outputs = chunk["research_node"]
                yield _sse_event(
                    "step",
                    {
                        "step": "research",
                        "status": "complete",
                        "iteration": active_iteration,
                        "total_iterations": total_iterations,
                        "data": _model_to_dict(outputs["research_result"]),
                    },
                )

            if "judge_node" in chunk:
                outputs = chunk["judge_node"]
                judge_result = outputs["judge_result"]
                yield _sse_event(
                    "step",
                    {
                        "step": "judge",
                        "status": "complete",
                        "iteration": completed_iterations or active_iteration,
                        "total_iterations": total_iterations,
                        "data": _model_to_dict(judge_result),
                    },
                )
            
            if "challenger_node" in chunk:
                outputs = chunk["challenger_node"]
                challenger_result = outputs["challenger_result"]
                yield _sse_event(
                    "step",
                    {
                        "step": "challenger",
                        "status": "complete",
                        "iteration": completed_iterations or active_iteration,
                        "total_iterations": total_iterations,
                        "data": _model_to_dict(challenger_result),
                    },
                )
                
            if "reconciliation_node" in chunk:
                outputs = chunk["reconciliation_node"]
                reconciliation_result = outputs["reconciliation_result"]
                if outputs.get("iterations"):
                    latest_iteration = outputs["iterations"][0]
                    iterations.append(
                        {
                            "iteration": latest_iteration["iteration"],
                            "planner": _model_to_dict(latest_iteration["planner"]),
                            "gatekeeper": _model_to_dict(latest_iteration["gatekeeper"]),
                            "research": _model_to_dict(latest_iteration["research"]),
                            "judge": _model_to_dict(latest_iteration["judge"]),
                            "challenger": _model_to_dict(latest_iteration.get("challenger")),
                            "reconciliation": _model_to_dict(latest_iteration.get("reconciliation")),
                        }
                    )
                    completed_iterations = latest_iteration["iteration"]
                    
                yield _sse_event(
                    "step",
                    {
                        "step": "reconciliation",
                        "status": "complete",
                        "iteration": completed_iterations or active_iteration,
                        "total_iterations": total_iterations,
                        "data": _model_to_dict(reconciliation_result),
                    },
                )
                final_verdict = outputs.get("final_verdict") or reconciliation_result
    except Exception as exc:
        logger.exception("Workflow stream failed")
        yield _sse_event(
            "error",
            {
                "detail": str(exc),
                "iteration": completed_iterations + 1,
                "total_iterations": total_iterations,
            },
        )
        return

    if final_verdict is None:
        raise RuntimeError("Workflow stream completed without a final verdict.")

    workflow_response = _build_workflow_response(
        log_id=-1,
        effort_level=req.effort_level,
        iterations=iterations,
        final_verdict=final_verdict,
    )

    log_id = -1
    session = get_session()
    try:
        log_entry = InvestigationLog(
            case_id=str(req.case_id),
            claim=req.fact_to_check,
            effort_level=req.effort_level,
            verdict=final_verdict.overall_verdict.verdict,
            result_payload=workflow_response.model_dump(mode="json"),
        )
        session.add(log_entry)
        session.flush() # get log_entry.id
        
        trace_entry = InvestigationTrace(
            case_id=str(req.case_id),
            run_id=f"run_{log_entry.id}",
            trace_payload={"traces": _model_to_dict(all_traces)}
        )
        session.add(trace_entry)
        session.commit()
        log_id = log_entry.id
    except Exception as exc:
        logger.error("Failed to persist log: %s", exc)
    finally:
        session.close()

    done_response = workflow_response.model_copy(update={"log_id": log_id})
    try:
        _write_result_snapshot(req, done_response)
    except Exception:
        logger.exception("Failed to write workflow result snapshot")
    yield _sse_event(
        "done",
        {
            "log_id": log_id,
            "data": done_response.model_dump(mode="json"),
        },
    )


@router.post("/run-stream")
async def run_workflow_stream(req: WorkflowRequest):
    """Run the workflow as an SSE stream."""

    session: Session = get_session()
    try:
        case, brief_text_override = _resolve_brief(session, str(req.case_id), req.brief_id)
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


@router.get("/logs/{case_id}")
async def list_investigation_logs(case_id: str) -> list[InvestigationLogSummary]:
    """List stored investigation logs for a case."""

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
    """Return a persisted workflow result."""

    session = get_session()
    try:
        log = session.get(InvestigationLog, log_id)
        if log is None or str(log.case_id) != case_id:
            raise HTTPException(status_code=404, detail="Investigation log not found")
        return log.result_payload
    finally:
        session.close()
