"""Schema round-trip and validation tests.

Pure Pydantic tests — no I/O, no mocks.
"""

import pytest
from pydantic import ValidationError

from app.schemas.judge import (
    JudgeOverallVerdict,
    JudgeResponse,
    JudgeTaskAssessment,
    JudgeTaskFact,
)
from app.schemas.planner import PlannerResponse
from app.schemas.research import ResearchResponse

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Round-trip serialization
# ---------------------------------------------------------------------------


class TestPlannerResponseRoundTrip:
    def test_serialize_deserialize(self, mock_planner_response: PlannerResponse):
        json_str = mock_planner_response.model_dump_json()
        restored = PlannerResponse.model_validate_json(json_str)

        assert restored.case_id == mock_planner_response.case_id
        assert restored.fact_to_check == mock_planner_response.fact_to_check
        assert len(restored.tasks) == len(mock_planner_response.tasks)
        assert restored.friction_summary.has_friction is True
        assert restored.search_boundary.start_time is not None


class TestResearchResponseRoundTrip:
    def test_serialize_deserialize(self, mock_research_response: ResearchResponse):
        json_str = mock_research_response.model_dump_json()
        restored = ResearchResponse.model_validate_json(json_str)

        assert restored.case_id == mock_research_response.case_id
        assert len(restored.tasks) == len(mock_research_response.tasks)
        for original, restored_task in zip(
            mock_research_response.tasks, restored.tasks
        ):
            assert len(restored_task.evidence) == len(original.evidence)


class TestJudgeResponseRoundTrip:
    def test_serialize_deserialize(self, mock_judge_response: JudgeResponse):
        json_str = mock_judge_response.model_dump_json()
        restored = JudgeResponse.model_validate_json(json_str)

        assert restored.case_id == mock_judge_response.case_id
        assert restored.overall_verdict.verdict == "likely_true"
        assert len(restored.tasks) == len(mock_judge_response.tasks)
        assert restored.gatekeeper_passed is True


# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------


class TestVerdictValidation:
    def test_invalid_verdict_rejected(self, fact_to_check: str):
        with pytest.raises(ValidationError):
            JudgeOverallVerdict(
                claim=fact_to_check,
                verdict="maybe",  # not in the Literal set
                rationale="test",
                supporting_facts=[],
                contradicting_facts=[],
            )

    @pytest.mark.parametrize(
        "verdict",
        ["true", "likely_true", "uncertain", "likely_false", "false"],
    )
    def test_valid_verdicts_accepted(self, fact_to_check: str, verdict: str):
        ov = JudgeOverallVerdict(
            claim=fact_to_check,
            verdict=verdict,
            rationale="test",
            supporting_facts=[],
            contradicting_facts=[],
        )
        assert ov.verdict == verdict


class TestConfidenceRange:
    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            JudgeTaskAssessment(
                question_text="test",
                answer="test",
                sufficient_evidence=True,
                confidence=1.5,
                key_facts=[],
            )

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            JudgeTaskAssessment(
                question_text="test",
                answer="test",
                sufficient_evidence=True,
                confidence=-0.1,
                key_facts=[],
            )

    def test_confidence_at_boundary_accepted(self):
        a = JudgeTaskAssessment(
            question_text="test",
            answer="test",
            sufficient_evidence=True,
            confidence=0.0,
            key_facts=[],
        )
        b = JudgeTaskAssessment(
            question_text="test",
            answer="test",
            sufficient_evidence=True,
            confidence=1.0,
            key_facts=[],
        )
        assert a.confidence == 0.0
        assert b.confidence == 1.0
