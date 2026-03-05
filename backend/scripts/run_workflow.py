#!/usr/bin/env python3
"""Run the TracePoint pipeline (ingest, planner, research, judge) in a modular way.

Supports running a single stage, a segment (from X to Y), or the full pipeline.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

# Add backend to path so app imports work when run from project root
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from app.agents.gatekeeper import GatekeeperResult, validate_planner_output
from app.agents.planner_agent import run_planner
from app.agents.research_agent import run_research
from app.agents.judge_agent import run_judge
from app.db.models import Case
from app.db.session import get_session
from app.ingestion.evidence_clerk import EvidenceClerkDetails, extract_evidence_details
from app.ingestion.pipeline import ingest_document
from app.ingestion.chunker import chunk_file
from app.schemas.ingest import IngestResponse
from app.schemas.planner import PlannerRequest, PlannerResponse
from app.schemas.research import ResearchResponse
from app.schemas.judge import JudgeResponse

STAGES = ["ingest", "planner", "research", "judge"]


def _stage_index(stage: str) -> int:
    """Return index of stage in STAGES. Raises ValueError if unknown."""
    try:
        return STAGES.index(stage)
    except ValueError:
        raise ValueError(f"Unknown stage: {stage}. Must be one of: {', '.join(STAGES)}")


def _get_text_from_file(path: Path) -> str:
    """Get document text from a file. For .txt/.md read directly; else use chunker and join."""
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    chunks = chunk_file(path)
    return "\n\n".join(chunks) if chunks else ""


async def run_ingest_stage(
    *,
    text: str,
    label: str,
    case_id: UUID,
    source_document: str | None = None,
    quiet: bool = False,
) -> IngestResponse:
    """Run ingest: evidence clerk + chunk/embed/store. Returns IngestResponse."""
    if not quiet:
        print("Running evidence clerk...", file=sys.stderr)
    try:
        clerk_details: EvidenceClerkDetails = await extract_evidence_details(text)
    except Exception as e:
        print(f"Evidence clerk error: {e}", file=sys.stderr)
        sys.exit(1)

    merged_metadata: dict = {}
    merged_metadata.setdefault("evidence_clerk", clerk_details.model_dump())

    try:
        count = ingest_document(
            text=text,
            label=label,
            source_document=source_document,
            additional_metadata=merged_metadata,
            case_id=case_id,
        )
    except ValueError as e:
        print(f"Ingest error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Ingest error: {e}", file=sys.stderr)
        sys.exit(1)

    if not quiet:
        print(f"Ingested {count} chunk(s) for case {case_id}.", file=sys.stderr)
    return IngestResponse(case_id=case_id, chunks_created=count)


async def run_planner_stage(
    *,
    case_id: UUID,
    fact_to_check: str,
    quiet: bool = False,
) -> PlannerResponse:
    """Run planner + gatekeeper loop. Returns PlannerResponse."""
    session = get_session()
    try:
        case = session.get(Case, str(case_id))
        if case is None:
            print(f"Case not found: {case_id}", file=sys.stderr)
            sys.exit(1)
    finally:
        session.close()

    if not quiet:
        print("Running planner...", file=sys.stderr)

    req = PlannerRequest(case_id=case_id, fact_to_check=fact_to_check)
    max_attempts = 3
    last_result: PlannerResponse | None = None
    last_gate: GatekeeperResult | None = None

    for _ in range(max_attempts):
        resp = await run_planner(case, req)
        gate = validate_planner_output(resp, case)
        last_result = resp
        last_gate = gate
        if not gate.needs_regeneration:
            return resp

    detail = "Planner output failed validation: " + "; ".join(
        last_gate.reasons if last_gate else ["unknown error"]
    )
    print(detail, file=sys.stderr)
    sys.exit(1)


def run_research_stage(planner_resp: PlannerResponse, *, quiet: bool = False) -> ResearchResponse:
    """Run research agent. Returns ResearchResponse."""
    if not quiet:
        print("Running research...", file=sys.stderr)
    return run_research(planner_resp)


def run_judge_stage(
    research_resp: ResearchResponse, *, quiet: bool = False
) -> JudgeResponse:
    """Run judge agent. Returns JudgeResponse."""
    if not quiet:
        print("Running judge...", file=sys.stderr)
    session = get_session()
    try:
        case = session.get(Case, str(research_resp.case_id))
    finally:
        session.close()
    return run_judge(research_resp, case=case)


def _validate_args(args: argparse.Namespace) -> None:
    """Validate --from/--to and stage-specific requirements. Exit on error."""
    from_idx = _stage_index(args.from_stage)
    to_idx = _stage_index(args.to_stage)
    if from_idx > to_idx:
        print(
            f"Invalid range: --from {args.from_stage} must not be after --to {args.to_stage}.",
            file=sys.stderr,
        )
        sys.exit(1)

    stages_in_run = STAGES[from_idx : to_idx + 1]

    if "ingest" in stages_in_run:
        if not args.case_id:
            print("--case-id is required when ingest is in the run.", file=sys.stderr)
            sys.exit(1)
        if not args.ingest_label:
            print("--ingest-label is required when ingest is in the run.", file=sys.stderr)
            sys.exit(1)
        if args.ingest_file and args.ingest_text:
            print(
                "Provide only one of --ingest-file, --ingest-text, or stdin.",
                file=sys.stderr,
            )
            sys.exit(1)

    if "planner" in stages_in_run:
        if not args.case_id:
            print("--case-id is required when planner is in the run.", file=sys.stderr)
            sys.exit(1)
        if not args.fact_to_check:
            print("--fact-to-check is required when planner is in the run.", file=sys.stderr)
            sys.exit(1)

    if "research" in stages_in_run and "planner" not in stages_in_run:
        if not args.planner_json:
            print(
                "--planner-json is required when running research without running planner.",
                file=sys.stderr,
            )
            sys.exit(1)
        path = Path(args.planner_json)
        if not path.exists():
            print(f"Planner JSON file not found: {path}", file=sys.stderr)
            sys.exit(1)

    if "judge" in stages_in_run and "research" not in stages_in_run:
        if not args.research_json:
            print(
                "--research-json is required when running judge without running research.",
                file=sys.stderr,
            )
            sys.exit(1)
        path = Path(args.research_json)
        if not path.exists():
            print(f"Research JSON file not found: {path}", file=sys.stderr)
            sys.exit(1)


async def _main_async(args: argparse.Namespace) -> None:
    _validate_args(args)

    from_idx = _stage_index(args.from_stage)
    to_idx = _stage_index(args.to_stage)
    case_id: UUID | None = args.case_id

    result = None

    for i in range(from_idx, to_idx + 1):
        stage = STAGES[i]

        if stage == "ingest":
            if args.ingest_file:
                path = Path(args.ingest_file)
                if not path.exists():
                    print(f"File not found: {path}", file=sys.stderr)
                    sys.exit(1)
                text = _get_text_from_file(path)
                source_document = args.ingest_source or path.name
            elif args.ingest_text:
                text = args.ingest_text
                source_document = args.ingest_source or "text"
            else:
                text = sys.stdin.read()
                if not text.strip():
                    print("No ingest text from stdin.", file=sys.stderr)
                    sys.exit(1)
                source_document = args.ingest_source or "stdin"

            result = await run_ingest_stage(
                text=text,
                label=args.ingest_label,
                case_id=case_id,
                source_document=source_document,
                quiet=args.quiet,
            )

        elif stage == "planner":
            result = await run_planner_stage(
                case_id=case_id,
                fact_to_check=args.fact_to_check,
                quiet=args.quiet,
            )

        elif stage == "research":
            planner_resp: PlannerResponse
            if result is not None and isinstance(result, PlannerResponse):
                planner_resp = result
            elif args.planner_json:
                raw = Path(args.planner_json).read_text(encoding="utf-8")
                planner_resp = PlannerResponse.model_validate_json(raw)
            else:
                print("No PlannerResponse available for research stage.", file=sys.stderr)
                sys.exit(1)
            result = run_research_stage(planner_resp, quiet=args.quiet)

        elif stage == "judge":
            research_resp: ResearchResponse
            if result is not None and isinstance(result, ResearchResponse):
                research_resp = result
            elif args.research_json:
                raw = Path(args.research_json).read_text(encoding="utf-8")
                research_resp = ResearchResponse.model_validate_json(raw)
            else:
                print("No ResearchResponse available for judge stage.", file=sys.stderr)
                sys.exit(1)

            result = run_judge_stage(research_resp, quiet=args.quiet)

    if result is not None:
        out = result.model_dump_json(indent=2)
        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
            if not args.quiet:
                print(f"Wrote output to {args.output}", file=sys.stderr)
        else:
            print(out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the TracePoint pipeline (ingest, planner, research, judge) in a modular way.",
    )
    parser.add_argument(
        "--from",
        dest="from_stage",
        required=True,
        choices=STAGES,
        help="Start stage",
    )
    parser.add_argument(
        "--to",
        dest="to_stage",
        required=True,
        choices=STAGES,
        help="End stage (inclusive)",
    )
    parser.add_argument(
        "--case-id",
        type=lambda s: UUID(s),
        default=None,
        help="Case UUID (required when ingest or planner is in the run)",
    )
    parser.add_argument(
        "--ingest-file",
        type=str,
        default=None,
        help="Path to document to ingest (when ingest is in the run)",
    )
    parser.add_argument(
        "--ingest-text",
        type=str,
        default=None,
        help="Raw text to ingest (when ingest is in the run)",
    )
    parser.add_argument(
        "--ingest-label",
        type=str,
        default=None,
        help="Evidence type label, e.g. witness, gps (required when ingest is in the run)",
    )
    parser.add_argument(
        "--ingest-source",
        type=str,
        default=None,
        help="Optional source_document name",
    )
    parser.add_argument(
        "--fact-to-check",
        type=str,
        default=None,
        help="Natural language claim to verify (required when planner is in the run)",
    )
    parser.add_argument(
        "--planner-json",
        type=str,
        default=None,
        help="Path to PlannerResponse JSON (required when --from research and planner not run)",
    )
    parser.add_argument(
        "--research-json",
        type=str,
        default=None,
        help="Path to ResearchResponse JSON (required when --from judge and research not run)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Write final output JSON to file; otherwise stdout",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only print the final output JSON, no progress messages",
    )

    args = parser.parse_args()
    asyncio.run(_main_async(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
