"""Unit tests for LangGraph node functions.

Each test mocks external calls (LLM, DB) and verifies that nodes
correctly read from and write to the PipelineState.
"""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.agents.gatekeeper import GatekeeperResult
from app.graph.nodes import (
    error_node,
    judge_node,
    planner_gatekeeper_node,
    planner_node,
    research_node,
)
from app.graph.state import PipelineState

pytestmark = pytest.mark.integration


def _base_state(mock_case, mock_planner_request) -> PipelineState:
    return PipelineState(
        case=mock_case,
        request=mock_planner_request,
        brief_text_override=None,
        planner_response=None,
        planner_attempts=0,
        planner_gate=None,
        research_response=None,
        judge_response=None,
    )


class TestPlannerNode:
    @patch("app.graph.nodes.run_planner", new_callable=AsyncMock)
    async def test_increments_attempts(
        self, mock_run, mock_case, mock_planner_request, mock_planner_response
    ):
        mock_run.return_value = mock_planner_response
        state = _base_state(mock_case, mock_planner_request)

        result = await planner_node(state)

        assert result["planner_attempts"] == 1

    @patch("app.graph.nodes.run_planner", new_callable=AsyncMock)
    async def test_stores_response(
        self, mock_run, mock_case, mock_planner_request, mock_planner_response
    ):
        mock_run.return_value = mock_planner_response
        state = _base_state(mock_case, mock_planner_request)

        result = await planner_node(state)

        assert result["planner_response"] is mock_planner_response


class TestPlannerGatekeeperNode:
    @patch("app.graph.nodes.validate_planner_output")
    async def test_passes_valid(
        self, mock_validate, mock_case, mock_planner_request, mock_planner_response
    ):
        gate = GatekeeperResult(
            valid=True, reasons=[], needs_regeneration=False
        )
        mock_validate.return_value = gate

        state = _base_state(mock_case, mock_planner_request)
        state["planner_response"] = mock_planner_response

        result = await planner_gatekeeper_node(state)

        assert result["planner_gate"].valid is True
        assert result["planner_gate"].needs_regeneration is False

    @patch("app.graph.nodes.validate_planner_output")
    async def test_fails_invalid(
        self, mock_validate, mock_case, mock_planner_request, mock_planner_response
    ):
        gate = GatekeeperResult(
            valid=False,
            reasons=["Expected 5 tasks, got 3."],
            needs_regeneration=True,
        )
        mock_validate.return_value = gate

        state = _base_state(mock_case, mock_planner_request)
        state["planner_response"] = mock_planner_response

        result = await planner_gatekeeper_node(state)

        assert result["planner_gate"].valid is False
        assert result["planner_gate"].needs_regeneration is True


class TestResearchNode:
    @patch("app.graph.nodes.run_research")
    async def test_stores_response(
        self,
        mock_run,
        mock_case,
        mock_planner_request,
        mock_planner_response,
        mock_research_response,
    ):
        mock_run.return_value = mock_research_response

        state = _base_state(mock_case, mock_planner_request)
        state["planner_response"] = mock_planner_response

        result = await research_node(state)

        assert result["research_response"] is mock_research_response


class TestJudgeNode:
    @patch("app.graph.nodes.run_judge", new_callable=AsyncMock)
    async def test_stores_response(
        self,
        mock_run,
        mock_case,
        mock_planner_request,
        mock_research_response,
        mock_judge_response,
    ):
        mock_run.return_value = mock_judge_response

        state = _base_state(mock_case, mock_planner_request)
        state["research_response"] = mock_research_response

        result = await judge_node(state)

        assert result["judge_response"] is mock_judge_response


class TestErrorNode:
    async def test_raises_http_exception(self, mock_case, mock_planner_request):
        gate = GatekeeperResult(
            valid=False,
            reasons=["Expected 5 tasks, got 3.", "Missing RECALL_STRESS."],
            needs_regeneration=True,
        )
        state = _base_state(mock_case, mock_planner_request)
        state["planner_gate"] = gate

        with pytest.raises(HTTPException) as exc_info:
            await error_node(state)

        assert exc_info.value.status_code == 500
        assert "Expected 5 tasks" in exc_info.value.detail
        assert "Missing RECALL_STRESS" in exc_info.value.detail
