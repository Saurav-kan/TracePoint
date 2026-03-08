"""Shared pytest fixtures for TracePoint backend tests.

All fixtures use synthetic data derived from tests/cases/digitalArtRobbery
so that tests run without a live database or LLM provider.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from app.schemas.judge import (
    JudgeOverallVerdict,
    JudgeResponse,
    JudgeTaskAssessment,
    JudgeTaskFact,
)
from app.schemas.planner import (
    FrictionSummary,
    MetadataFilterItem,
    PlannerRequest,
    PlannerResponse,
    PlannerTask,
    SearchBoundary,
)
from app.schemas.research import EvidenceSnippet, ResearchResponse, ResearchTaskResult

CASE_DIR = Path(__file__).parent / "cases" / "digitalArtRobbery"
CASE_ID = UUID("00000000-0000-0000-0000-000000000001")


def _read_case_file(filename: str) -> str:
    return (CASE_DIR / filename).read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def case_summary_text() -> str:
    return _read_case_file("case_summary.txt")


@pytest.fixture()
def fact_to_check() -> str:
    return _read_case_file("question.txt")


@pytest.fixture()
def mock_case(case_summary_text: str) -> MagicMock:
    """Mock Case object (avoids SQLAlchemy ORM instrumentation)."""
    case = MagicMock()
    case.case_id = str(CASE_ID)
    case.title = "The Midnight Glitch"
    case.case_brief_text = case_summary_text
    case.brief_embedding = None
    case.target_subject_name = "Sarah Vane"
    case.crime_timestamp_start = datetime(2025, 3, 4, 23, 0, tzinfo=timezone.utc)
    case.crime_timestamp_end = datetime(2025, 3, 5, 1, 0, tzinfo=timezone.utc)
    case.created_at = datetime.now(timezone.utc)
    case.updated_at = datetime.now(timezone.utc)
    case.status = "active"
    return case


@pytest.fixture()
def mock_planner_request(fact_to_check: str) -> PlannerRequest:
    return PlannerRequest(case_id=CASE_ID, fact_to_check=fact_to_check)


# ---------------------------------------------------------------------------
# Planner response fixture
# ---------------------------------------------------------------------------

_TASK_DEFS = [
    # --- Confirmational tasks (slots 1-5) ---
    (
        "VERIFICATION",
        "What access control logs show who used aris_admin credentials to enter the server room on March 4th?",
        "Access control logs showing badge entry and aris_admin credential usage in the server room on March 4th around 23:00",
        [MetadataFilterItem(key="label", value="forensic_log")],
    ),
    (
        "IMPOSSIBILITY",
        "Was it physically impossible for Sarah Vane to have used aris_admin credentials given her known whereabouts?",
        "Evidence of Sarah Vane location and credential access during the server breach at 23:45 on March 4th",
        [MetadataFilterItem(key="label", value="security_interview")],
    ),
    (
        "ENVIRONMENTAL",
        "What were the surveillance camera conditions in the server room during the breach?",
        "Security camera footage and loop anomalies in the server room on March 4th night",
        [MetadataFilterItem(key="label", value="forensic_log")],
    ),
    (
        "NEGATIVE_PROOF",
        "Are there any missing access logs or alerts that should have been triggered by the breach?",
        "Missing intrusion detection alerts or absent audit trail entries during the AETHER-01 breach",
        [MetadataFilterItem(key="label", value="forensic_log")],
    ),
    (
        "RECALL_STRESS",
        "What peripheral details does the security guard recall about sounds or smells near the server room?",
        "Background details such as sounds smells or minor observations reported by security guard Marcus Thorne",
        [MetadataFilterItem(key="label", value="security_interview")],
    ),
    # --- Non-confirmational / contrary tasks (slots 6-10) ---
    (
        "VERIFICATION",
        "Is there evidence that could disprove Sarah Vane's involvement or exonerate her from the breach?",
        "Evidence that could exonerate or clear Sarah Vane from the server room breach and contradict the claim of her guilt",
        [MetadataFilterItem(key="label", value="forensic_log")],
    ),
    (
        "IMPOSSIBILITY",
        "Could an alternative suspect other than Sarah Vane have physically accessed the server room?",
        "Evidence of alternative suspects or other individuals who could have accessed the server room to disprove Vane involvement",
        [MetadataFilterItem(key="label", value="security_interview")],
    ),
    (
        "ENVIRONMENTAL",
        "Are there environmental conditions that contradict the claim that Sarah Vane was in the server room?",
        "Environmental evidence that would weaken or contradict the claim that Vane was present in the server room",
        [MetadataFilterItem(key="label", value="forensic_log")],
    ),
    (
        "NEGATIVE_PROOF",
        "Is there an alibi or evidence of innocence that shows Sarah Vane was elsewhere during the breach?",
        "Alibi evidence or records showing Sarah Vane was not at the server room and is innocent of the breach",
        [MetadataFilterItem(key="label", value="security_interview")],
    ),
    (
        "RECALL_STRESS",
        "Do witness accounts contain details that exclude Sarah Vane or frame an alternative narrative?",
        "Witness peripheral details that could exclude Sarah Vane or suggest she was framed by another party",
        [MetadataFilterItem(key="label", value="security_interview")],
    ),
]


@pytest.fixture()
def mock_planner_response(fact_to_check: str) -> PlannerResponse:
    tasks = [
        PlannerTask(
            type=t, question_text=q, vector_query=v, metadata_filter=m
        )
        for t, q, v, m in _TASK_DEFS
    ]
    return PlannerResponse(
        case_id=CASE_ID,
        fact_to_check=fact_to_check,
        friction_summary=FrictionSummary(
            has_friction=True,
            description="Identity/Credential Mismatch: aris_admin credentials were used but claim targets Sarah Vane",
        ),
        search_boundary=SearchBoundary(
            start_time=datetime(2025, 3, 4, 23, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 3, 5, 1, 0, tzinfo=timezone.utc),
        ),
        tasks=tasks,
    )


# ---------------------------------------------------------------------------
# Research response fixture
# ---------------------------------------------------------------------------


def _make_snippet(source: str, chunk: str) -> EvidenceSnippet:
    return EvidenceSnippet(
        source_document=source,
        case_id=CASE_ID,
        score=0.15,
        chunk_before=None,
        chunk=chunk,
        chunk_after=None,
    )


@pytest.fixture()
def mock_research_response(
    mock_planner_response: PlannerResponse,
) -> ResearchResponse:
    task_results = []
    for task in mock_planner_response.tasks:
        task_results.append(
            ResearchTaskResult(
                question_text=task.question_text,
                vector_query=task.vector_query,
                metadata_filter=task.metadata_filter,
                evidence=[
                    _make_snippet(
                        "forensic_log_server.txt",
                        "Root access via aris_admin at 23:45. USB device mounted at /dev/sdb1.",
                    ),
                    _make_snippet(
                        "interview_security_guard.txt",
                        "Thorne reports seeing Vane near server room at approximately 23:30.",
                    ),
                ],
            )
        )
    return ResearchResponse(
        case_id=CASE_ID,
        fact_to_check=mock_planner_response.fact_to_check,
        tasks=task_results,
    )


# ---------------------------------------------------------------------------
# Judge response fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_judge_response(fact_to_check: str) -> JudgeResponse:
    supporting = JudgeTaskFact(
        description="Forensic logs confirm USB device mounted during breach window",
        supports_claim=True,
        source_task_index=0,
        evidence_indices=[0],
    )
    # Contradicting fact must share tokens with a per-task key fact
    # so the judge gatekeeper's overall-consistency check passes.
    contradicting = JudgeTaskFact(
        description="Forensic logs show aris_admin credentials used during breach",
        supports_claim=False,
        source_task_index=0,
        evidence_indices=[0],
    )
    task_assessment = JudgeTaskAssessment(
        question_text="What access control logs show who entered the server room?",
        answer="Forensic logs confirm root access via aris_admin and a USB device mount at 23:45.",
        sufficient_evidence=True,
        confidence=0.75,
        key_facts=[supporting, contradicting],
    )
    return JudgeResponse(
        case_id=CASE_ID,
        fact_to_check=fact_to_check,
        tasks=[task_assessment],
        overall_verdict=JudgeOverallVerdict(
            claim=fact_to_check,
            verdict="likely_true",
            rationale="Evidence supports Vane's physical access to the server room.",
            supporting_facts=[supporting],
            contradicting_facts=[contradicting],
        ),
        refinement_performed=False,
        refinement_suggestion=None,
        needs_refinement=False,
        refinement_questions=[],
        gatekeeper_passed=True,
        gatekeeper_reasons=[],
    )
