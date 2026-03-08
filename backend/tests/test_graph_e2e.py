"""End-to-end tests for the compiled LangGraph investigation pipeline.

These tests exercise the full graph topology with mocked LLM/DB calls
to verify node sequencing, retry logic, refinement feedback loop,
and output schema compliance.
"""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.agents.gatekeeper import GatekeeperResult
from app.graph.graph import build_graph
from app.graph.state import PipelineState
from app.schemas.judge import JudgeResponse

pytestmark = pytest.mark.integration


def _initial_state(mock_case, mock_planner_request) -> PipelineState:
    return PipelineState(
        case=mock_case,
        request=mock_planner_request,
        brief_text_override=None,
        planner_response=None,
        planner_attempts=0,
        planner_gate=None,
        research_response=None,
        judge_response=None,
        judge_refinement_attempts=0,
        refinement_context=None,
        planner_supplemental_response=None,
    )


class TestHappyPath:
    @patch("app.graph.nodes.run_judge", new_callable=AsyncMock)
    @patch("app.graph.nodes.run_research")
    @patch("app.graph.nodes.validate_planner_output")
    @patch("app.graph.nodes.run_planner", new_callable=AsyncMock)
    async def test_full_pipeline(
        self,
        mock_planner,
        mock_gate,
        mock_research,
        mock_judge,
        mock_case,
        mock_planner_request,
        mock_planner_response,
        mock_research_response,
        mock_judge_response,
    ):
        mock_planner.return_value = mock_planner_response
        mock_gate.return_value = GatekeeperResult(
            valid=True, reasons=[], needs_regeneration=False
        )
        mock_research.return_value = mock_research_response
        mock_judge.return_value = mock_judge_response

        graph = build_graph().compile()
        state = _initial_state(mock_case, mock_planner_request)

        result = await graph.ainvoke(state)

        assert result["judge_response"] is not None
        assert result["planner_attempts"] == 1
        mock_planner.assert_called_once()
        mock_research.assert_called_once()
        mock_judge.assert_called_once()


class TestPlannerRetryThenPass:
    @patch("app.graph.nodes.run_judge", new_callable=AsyncMock)
    @patch("app.graph.nodes.run_research")
    @patch("app.graph.nodes.validate_planner_output")
    @patch("app.graph.nodes.run_planner", new_callable=AsyncMock)
    async def test_retry_then_pass(
        self,
        mock_planner,
        mock_gate,
        mock_research,
        mock_judge,
        mock_case,
        mock_planner_request,
        mock_planner_response,
        mock_research_response,
        mock_judge_response,
    ):
        mock_planner.return_value = mock_planner_response
        # First call fails, second passes
        mock_gate.side_effect = [
            GatekeeperResult(
                valid=False,
                reasons=["Missing RECALL_STRESS."],
                needs_regeneration=True,
            ),
            GatekeeperResult(
                valid=True, reasons=[], needs_regeneration=False
            ),
        ]
        mock_research.return_value = mock_research_response
        mock_judge.return_value = mock_judge_response

        graph = build_graph().compile()
        state = _initial_state(mock_case, mock_planner_request)

        result = await graph.ainvoke(state)

        assert result["judge_response"] is not None
        assert result["planner_attempts"] == 2
        assert mock_planner.call_count == 2
        mock_research.assert_called_once()


class TestMaxRetriesErrors:
    @patch("app.graph.nodes.run_judge", new_callable=AsyncMock)
    @patch("app.graph.nodes.run_research")
    @patch("app.graph.nodes.validate_planner_output")
    @patch("app.graph.nodes.run_planner", new_callable=AsyncMock)
    async def test_max_retries_falls_back_to_research(
        self,
        mock_planner,
        mock_gate,
        mock_research,
        mock_judge,
        mock_case,
        mock_planner_request,
        mock_planner_response,
        mock_research_response,
        mock_judge_response,
    ):
        """After MAX_PLANNER_ATTEMPTS the graph should fall through to research
        with the best available plan rather than crashing with HTTP 500."""
        mock_planner.return_value = mock_planner_response
        # Gatekeeper always fails
        mock_gate.return_value = GatekeeperResult(
            valid=False,
            reasons=["Missing investigative types: ENVIRONMENTAL."],
            needs_regeneration=True,
        )
        mock_research.return_value = mock_research_response
        mock_judge.return_value = mock_judge_response

        graph = build_graph().compile()
        state = _initial_state(mock_case, mock_planner_request)

        result = await graph.ainvoke(state)

        # Pipeline completes — no exception raised
        assert result["judge_response"] is not None
        # Planner ran exactly MAX_PLANNER_ATTEMPTS times
        assert mock_planner.call_count == 3
        # Research and judge still ran once (best-effort fallback)
        mock_research.assert_called_once()
        mock_judge.assert_called_once()


class TestResponseSchemaMatch:
    @patch("app.graph.nodes.run_judge", new_callable=AsyncMock)
    @patch("app.graph.nodes.run_research")
    @patch("app.graph.nodes.validate_planner_output")
    @patch("app.graph.nodes.run_planner", new_callable=AsyncMock)
    async def test_output_validates_as_judge_response(
        self,
        mock_planner,
        mock_gate,
        mock_research,
        mock_judge,
        mock_case,
        mock_planner_request,
        mock_planner_response,
        mock_research_response,
        mock_judge_response,
    ):
        mock_planner.return_value = mock_planner_response
        mock_gate.return_value = GatekeeperResult(
            valid=True, reasons=[], needs_regeneration=False
        )
        mock_research.return_value = mock_research_response
        mock_judge.return_value = mock_judge_response

        graph = build_graph().compile()
        state = _initial_state(mock_case, mock_planner_request)

        result = await graph.ainvoke(state)

        judge_resp = result["judge_response"]
        # Validate it can round-trip through Pydantic
        json_str = judge_resp.model_dump_json()
        restored = JudgeResponse.model_validate_json(json_str)
        assert restored.case_id == judge_resp.case_id
        assert restored.overall_verdict.verdict == judge_resp.overall_verdict.verdict


# ---------------------------------------------------------------------------
# Refinement feedback loop tests
# ---------------------------------------------------------------------------


class TestRefinementLoop:
    """Tests for the judge → prepare_refinement → planner → research_supplemental → judge path."""

    @patch("app.graph.nodes.run_judge", new_callable=AsyncMock)
    @patch("app.graph.nodes.run_research")
    @patch("app.graph.nodes.validate_planner_output")
    @patch("app.graph.nodes.run_planner", new_callable=AsyncMock)
    async def test_refinement_triggered_when_needed(
        self,
        mock_planner,
        mock_gate,
        mock_research,
        mock_judge,
        mock_case,
        mock_planner_request,
        mock_planner_response,
        mock_research_response,
        mock_judge_response,
    ):
        """When judge returns needs_refinement=True and attempts < 1,
        the graph should take the refinement path and run judge a second time."""
        # First judge call: signal refinement needed
        first_judge_resp = mock_judge_response.model_copy(
            update={
                "needs_refinement": True,
                "refinement_questions": [
                    "What physical evidence places the suspect at the server room?",
                ],
            }
        )
        # Second judge call: no more refinement (loop done)
        second_judge_resp = mock_judge_response.model_copy(
            update={
                "refinement_performed": True,
                "needs_refinement": False,
                "refinement_questions": [],
            }
        )
        mock_judge.side_effect = [first_judge_resp, second_judge_resp]

        # Planner called twice: 1st normal, 2nd refinement mode
        mock_planner.return_value = mock_planner_response
        mock_gate.return_value = GatekeeperResult(
            valid=True, reasons=[], needs_regeneration=False
        )
        mock_research.return_value = mock_research_response

        graph = build_graph().compile()
        state = _initial_state(mock_case, mock_planner_request)

        result = await graph.ainvoke(state)

        # Judge called twice (initial + after refinement)
        assert mock_judge.call_count == 2
        # Planner called twice (normal + refinement)
        assert mock_planner.call_count == 2
        # Research called twice (normal + supplemental)
        assert mock_research.call_count == 2
        # Gatekeeper called only once (bypassed on refinement)
        assert mock_gate.call_count == 1
        # Final judge response should be the second one
        assert result["judge_response"].refinement_performed is True
        assert result["judge_response"].needs_refinement is False
        # Refinement attempts counter should be 1
        assert result["judge_refinement_attempts"] == 1

    @patch("app.graph.nodes.run_judge", new_callable=AsyncMock)
    @patch("app.graph.nodes.run_research")
    @patch("app.graph.nodes.validate_planner_output")
    @patch("app.graph.nodes.run_planner", new_callable=AsyncMock)
    async def test_no_second_refinement_when_attempts_exhausted(
        self,
        mock_planner,
        mock_gate,
        mock_research,
        mock_judge,
        mock_case,
        mock_planner_request,
        mock_planner_response,
        mock_research_response,
        mock_judge_response,
    ):
        """When needs_refinement=True but judge_refinement_attempts is already 1,
        the graph should go directly to END (no second refinement loop)."""
        # Judge still wants refinement on second pass (should be ignored)
        first_judge_resp = mock_judge_response.model_copy(
            update={
                "needs_refinement": True,
                "refinement_questions": ["More info needed"],
            }
        )
        second_judge_resp = mock_judge_response.model_copy(
            update={
                "refinement_performed": True,
                "needs_refinement": True,  # Still wanting more, but should be capped
                "refinement_questions": ["Even more info needed"],
            }
        )
        mock_judge.side_effect = [first_judge_resp, second_judge_resp]
        mock_planner.return_value = mock_planner_response
        mock_gate.return_value = GatekeeperResult(
            valid=True, reasons=[], needs_regeneration=False
        )
        mock_research.return_value = mock_research_response

        graph = build_graph().compile()
        state = _initial_state(mock_case, mock_planner_request)

        result = await graph.ainvoke(state)

        # Judge called exactly twice — second pass goes to END even with needs_refinement=True
        assert mock_judge.call_count == 2
        assert result["judge_refinement_attempts"] == 1
        # No third judge call (refinement capped at 1)
        assert mock_planner.call_count == 2

    @patch("app.graph.nodes.run_judge", new_callable=AsyncMock)
    @patch("app.graph.nodes.run_research")
    @patch("app.graph.nodes.validate_planner_output")
    @patch("app.graph.nodes.run_planner", new_callable=AsyncMock)
    async def test_research_merge_combines_tasks(
        self,
        mock_planner,
        mock_gate,
        mock_research,
        mock_judge,
        mock_case,
        mock_planner_request,
        mock_planner_response,
        mock_research_response,
        mock_judge_response,
    ):
        """After refinement, research_response should contain merged tasks
        (original + supplemental) in the expected order."""
        first_judge_resp = mock_judge_response.model_copy(
            update={
                "needs_refinement": True,
                "refinement_questions": ["Need more evidence"],
            }
        )
        second_judge_resp = mock_judge_response.model_copy(
            update={
                "refinement_performed": True,
                "needs_refinement": False,
                "refinement_questions": [],
            }
        )
        mock_judge.side_effect = [first_judge_resp, second_judge_resp]
        mock_planner.return_value = mock_planner_response
        mock_gate.return_value = GatekeeperResult(
            valid=True, reasons=[], needs_regeneration=False
        )

        # Original research has N tasks, supplemental adds more
        original_task_count = len(mock_research_response.tasks)
        mock_research.return_value = mock_research_response

        graph = build_graph().compile()
        state = _initial_state(mock_case, mock_planner_request)

        result = await graph.ainvoke(state)

        # research_response should be merged (original + supplemental tasks)
        final_research = result["research_response"]
        # Merged tasks = original tasks + supplemental tasks (same mock returns same count)
        assert len(final_research.tasks) == original_task_count * 2
        # First N tasks should be from original research
        for i in range(original_task_count):
            assert final_research.tasks[i].question_text == mock_research_response.tasks[i].question_text
