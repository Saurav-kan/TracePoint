"""Unit tests for planner and judge gatekeepers.

All tests run in-memory — no LLM calls, no database.
The planner gatekeeper validates investigative heuristics;
the judge gatekeeper validates grounding, relevance, and consistency.
"""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

import pytest

from app.agents.gatekeeper import validate_planner_output
from app.agents.judge_gatekeeper import validate_judge_output
from app.db.models import Case
from app.schemas.judge import (
    JudgeOverallVerdict,
    JudgeResponse,
    JudgeTaskAssessment,
    JudgeTaskFact,
)
from app.schemas.planner import (
    FrictionSummary,
    MetadataFilterItem,
    PlannerResponse,
    PlannerTask,
)
from app.schemas.research import EvidenceSnippet, ResearchResponse, ResearchTaskResult

from tests.conftest import CASE_ID

pytestmark = pytest.mark.unit


# ===================================================================
# Planner gatekeeper tests
# ===================================================================


class TestPlannerGatekeeperValid:
    @patch("app.agents.gatekeeper.get_case_labels", return_value=[])
    def test_valid_passes(self, _mock_labels, mock_planner_response, mock_case):
        gate = validate_planner_output(mock_planner_response, mock_case)
        assert gate.valid is True
        assert gate.reasons == []
        assert gate.needs_regeneration is False


class TestPlannerGatekeeperTaskCount:
    @patch("app.agents.gatekeeper.get_case_labels", return_value=[])
    def test_wrong_count_fails(self, _mock_labels, mock_planner_response, mock_case):
        resp = mock_planner_response.model_copy(
            update={"tasks": mock_planner_response.tasks[:3]}
        )
        gate = validate_planner_output(resp, mock_case)
        assert gate.valid is False
        assert any("Expected 10" in r for r in gate.reasons)


class TestPlannerGatekeeperMissingType:
    @patch("app.agents.gatekeeper.get_case_labels", return_value=[])
    def test_missing_type_fails(self, _mock_labels, mock_planner_response, mock_case):
        tasks = deepcopy(mock_planner_response.tasks)
        # Replace both RECALL_STRESS tasks (indices 4 and 9) with VERIFICATION
        tasks[4] = tasks[4].model_copy(update={"type": "VERIFICATION"})
        tasks[9] = tasks[9].model_copy(update={"type": "VERIFICATION"})
        resp = mock_planner_response.model_copy(update={"tasks": tasks})
        gate = validate_planner_output(resp, mock_case)
        assert gate.valid is False
        assert any("RECALL_STRESS" in r for r in gate.reasons)


class TestPlannerGatekeeperShortQuery:
    @patch("app.agents.gatekeeper.get_case_labels", return_value=[])
    def test_short_vector_query(self, _mock_labels, mock_planner_response, mock_case):
        tasks = deepcopy(mock_planner_response.tasks)
        tasks[0] = tasks[0].model_copy(update={"vector_query": "short query"})
        resp = mock_planner_response.model_copy(update={"tasks": tasks})
        gate = validate_planner_output(resp, mock_case)
        assert gate.valid is False
        assert any("vector_query too short" in r for r in gate.reasons)


class TestPlannerGatekeeperInvalidLabel:
    @patch(
        "app.agents.gatekeeper.get_case_labels",
        return_value=["forensic_log", "witness"],
    )
    def test_invalid_label_fails(self, _mock_labels, mock_planner_response, mock_case):
        tasks = deepcopy(mock_planner_response.tasks)
        tasks[0] = tasks[0].model_copy(
            update={
                "metadata_filter": [
                    MetadataFilterItem(key="label", value="nonexistent_type")
                ]
            }
        )
        resp = mock_planner_response.model_copy(update={"tasks": tasks})
        gate = validate_planner_output(resp, mock_case)
        assert gate.valid is False
        assert any("unknown label" in r for r in gate.reasons)


class TestPlannerGatekeeperContraryBalance:
    @patch("app.agents.gatekeeper.get_case_labels", return_value=[])
    def test_too_few_contrary_tasks_fails(
        self, _mock_labels, mock_planner_response, mock_case
    ):
        """When all 10 tasks are confirmational (no contrary keywords),
        the gatekeeper should fail with a contrary-balance warning."""
        tasks = deepcopy(mock_planner_response.tasks)
        # Overwrite all non-confirmational tasks (slots 5-9) with
        # purely confirmational text that has no contrary keywords
        for i in range(5, 10):
            tasks[i] = tasks[i].model_copy(
                update={
                    "question_text": "What direct logs confirm the breach occurred at 23:45?",
                    "vector_query": "Direct server logs confirming unauthorized access during the breach window on March 4th",
                }
            )
        resp = mock_planner_response.model_copy(update={"tasks": tasks})
        gate = validate_planner_output(resp, mock_case)
        assert gate.valid is False
        assert any("non-confirmational" in r.lower() for r in gate.reasons)


class TestPlannerGatekeeperFriction:
    @patch("app.agents.gatekeeper.get_case_labels", return_value=[])
    def test_friction_needs_two_tasks(
        self, _mock_labels, mock_planner_response, mock_case
    ):
        """When friction is described, at least two tasks must target it."""
        tasks = deepcopy(mock_planner_response.tasks)
        # Remove all friction-related keywords from all tasks
        for i in range(len(tasks)):
            tasks[i] = tasks[i].model_copy(
                update={
                    "question_text": "Completely unrelated placeholder question about weather patterns",
                    "vector_query": "Generic unrelated query about atmospheric conditions and climate data patterns",
                }
            )
        resp = mock_planner_response.model_copy(
            update={
                "tasks": tasks,
                "friction_summary": FrictionSummary(
                    has_friction=True,
                    description="Identity/Credential Mismatch: aris_admin was used but Vane is the suspect",
                ),
            }
        )
        gate = validate_planner_output(resp, mock_case)
        assert any("friction" in r.lower() for r in gate.reasons)


# ===================================================================
# Judge gatekeeper tests
# ===================================================================


def _make_judge_and_research(
    fact: str,
    tasks: list[JudgeTaskAssessment],
    research_tasks: list[ResearchTaskResult],
    verdict: JudgeOverallVerdict | None = None,
) -> tuple[JudgeResponse, ResearchResponse]:
    if verdict is None:
        verdict = JudgeOverallVerdict(
            claim=fact,
            verdict="likely_true",
            rationale="test rationale",
            supporting_facts=[],
            contradicting_facts=[],
        )
    judge_resp = JudgeResponse(
        case_id=CASE_ID,
        fact_to_check=fact,
        tasks=tasks,
        overall_verdict=verdict,
        refinement_performed=False,
    )
    research_resp = ResearchResponse(
        case_id=CASE_ID,
        fact_to_check=fact,
        tasks=research_tasks,
    )
    return judge_resp, research_resp


class TestJudgeGatekeeperValid:
    def test_valid_passes(self, mock_judge_response, mock_research_response):
        gate = validate_judge_output(mock_judge_response, mock_research_response)
        assert gate.valid is True
        assert gate.reasons == []


class TestJudgeGatekeeperAnswerRelevance:
    def test_irrelevant_answer_flagged(self, fact_to_check):
        task = JudgeTaskAssessment(
            question_text="What access control logs show server room entry?",
            answer="Banana peels are typically yellow when ripe and green when unripe.",
            sufficient_evidence=True,
            confidence=0.8,
            key_facts=[],
        )
        research_task = ResearchTaskResult(
            question_text=task.question_text,
            vector_query="test",
            metadata_filter=[],
            evidence=[],
        )
        judge_resp, research_resp = _make_judge_and_research(
            fact_to_check, [task], [research_task]
        )
        gate = validate_judge_output(judge_resp, research_resp)
        assert any("overlap" in r.lower() for r in gate.reasons)


class TestJudgeGatekeeperBadEvidenceIndex:
    def test_out_of_range_index_flagged(self, fact_to_check):
        bad_fact = JudgeTaskFact(
            description="Forensic logs confirm USB device was mounted during the breach",
            supports_claim=True,
            source_task_index=0,
            evidence_indices=[99],  # out of range
        )
        task = JudgeTaskAssessment(
            question_text="What forensic logs exist for the breach?",
            answer="Forensic logs confirm USB mount at 23:45",
            sufficient_evidence=True,
            confidence=0.7,
            key_facts=[bad_fact],
        )
        snippet = EvidenceSnippet(
            source_document="forensic_log.txt",
            case_id=CASE_ID,
            score=0.1,
            chunk="Root access via aris_admin at 23:45",
        )
        research_task = ResearchTaskResult(
            question_text=task.question_text,
            vector_query="test",
            metadata_filter=[],
            evidence=[snippet],
        )
        judge_resp, research_resp = _make_judge_and_research(
            fact_to_check, [task], [research_task]
        )
        gate = validate_judge_output(judge_resp, research_resp)
        assert any("invalid evidence index" in r.lower() for r in gate.reasons)


class TestJudgeGatekeeperUngroundedFact:
    def test_ungrounded_fact_flagged(self, fact_to_check):
        """Fact text shares zero significant tokens with linked evidence."""
        ungrounded = JudgeTaskFact(
            description="Xylophone quartets performed diminuendo",
            supports_claim=True,
            source_task_index=0,
            evidence_indices=[0],
        )
        task = JudgeTaskAssessment(
            question_text="What forensic logs exist for the breach?",
            answer="Forensic logs confirm USB device mount during breach window",
            sufficient_evidence=True,
            confidence=0.7,
            key_facts=[ungrounded],
        )
        snippet = EvidenceSnippet(
            source_document="forensic_log.txt",
            case_id=CASE_ID,
            score=0.1,
            chunk="Root access via aris_admin at 23:45. USB device mounted at /dev/sdb1.",
        )
        research_task = ResearchTaskResult(
            question_text=task.question_text,
            vector_query="test",
            metadata_filter=[],
            evidence=[snippet],
        )
        judge_resp, research_resp = _make_judge_and_research(
            fact_to_check, [task], [research_task]
        )
        gate = validate_judge_output(judge_resp, research_resp)
        assert any("overlap" in r.lower() for r in gate.reasons)


class TestJudgeGatekeeperOverallConsistency:
    def test_overall_fact_not_in_tasks_flagged(self, fact_to_check):
        """Overall verdict references a fact not traceable to any per-task fact."""
        task_fact = JudgeTaskFact(
            description="Forensic logs confirm USB device mounted during breach",
            supports_claim=True,
            source_task_index=0,
            evidence_indices=[0],
        )
        task = JudgeTaskAssessment(
            question_text="What forensic logs exist for the breach?",
            answer="Forensic logs confirm USB mount at 23:45",
            sufficient_evidence=True,
            confidence=0.7,
            key_facts=[task_fact],
        )
        snippet = EvidenceSnippet(
            source_document="forensic_log.txt",
            case_id=CASE_ID,
            score=0.1,
            chunk="Root access via aris_admin at 23:45. USB device mounted.",
        )
        research_task = ResearchTaskResult(
            question_text=task.question_text,
            vector_query="test",
            metadata_filter=[],
            evidence=[snippet],
        )
        # Overall verdict has a supporting fact with zero overlap to per-task facts
        orphan_fact = JudgeTaskFact(
            description="Xylophone quartets performed diminuendo crescendo",
            supports_claim=True,
            source_task_index=0,
            evidence_indices=[],
        )
        verdict = JudgeOverallVerdict(
            claim=fact_to_check,
            verdict="likely_true",
            rationale="Evidence supports claim",
            supporting_facts=[orphan_fact],
            contradicting_facts=[],
        )
        judge_resp, research_resp = _make_judge_and_research(
            fact_to_check, [task], [research_task], verdict=verdict
        )
        gate = validate_judge_output(judge_resp, research_resp)
        assert any("does not overlap" in r.lower() for r in gate.reasons)
