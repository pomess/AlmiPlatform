"""End-to-end runner test with all stages mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kairos_runtime.research.runner import deep_research
from kairos_runtime.research.state import (
    Classification,
    Domain,
    QueryType,
    ResearchBrief,
    ResearchReport,
    VerificationReport,
)


@pytest.fixture
def mock_classification():
    return Classification(
        query_type=QueryType.COMPARISON,
        domain=Domain.SOFTWARE_ENG,
        depth_tier="quick",
        ambiguity_score=0.1,
        suggested_clarifications=[],
        estimated_subagents=2,
        estimated_tokens=100000,
    )


@pytest.fixture
def mock_brief():
    return ResearchBrief(
        title="Test Research",
        objective="Compare A and B",
        scope="All sources",
        constraints=[],
        output_format="markdown",
    )


def _mock_verify():
    return ([], VerificationReport())


@pytest.mark.asyncio
async def test_deep_research_end_to_end(mock_classification, mock_brief):
    """Full pipeline with all external calls mocked."""
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": []})

    with (
        patch(
            "kairos_runtime.research.runner.classify_and_brief",
            AsyncMock(return_value=(mock_classification, mock_brief)),
        ),
        patch(
            "kairos_runtime.research.runner.build_lead_agent",
            return_value=mock_agent,
        ),
        patch(
            "kairos_runtime.research.runner.verify_findings",
            AsyncMock(return_value=_mock_verify()),
        ),
        patch(
            "kairos_runtime.research.runner.synthesize_report",
            AsyncMock(return_value="# Test Report\n\nThis is a test."),
        ),
    ):
        report = await deep_research("Compare A and B", depth_tier="quick")

    assert isinstance(report, ResearchReport)
    assert "Test Report" in report.markdown
    assert report.run_id != ""
    assert report.started_at is not None
    assert report.completed_at is not None
    assert report.budget.ceiling == 100000


@pytest.mark.asyncio
async def test_deep_research_handles_lead_timeout(mock_classification, mock_brief):
    """Pipeline should gracefully handle lead agent timeout."""
    import asyncio

    async def _hang(*args, **kwargs):
        await asyncio.sleep(9999)

    mock_agent = MagicMock()
    mock_agent.ainvoke = _hang

    with (
        patch(
            "kairos_runtime.research.runner.classify_and_brief",
            AsyncMock(return_value=(mock_classification, mock_brief)),
        ),
        patch(
            "kairos_runtime.research.runner.build_lead_agent",
            return_value=mock_agent,
        ),
        patch(
            "kairos_runtime.research.runner.verify_findings",
            AsyncMock(return_value=_mock_verify()),
        ),
        patch(
            "kairos_runtime.research.runner.synthesize_report",
            AsyncMock(return_value="# Partial Report"),
        ),
        patch(
            "kairos_runtime.research.config.WALL_CLOCK_TIMEOUT_SECONDS",
            {"quick": 1, "standard": 1, "deep": 1, "exhaustive": 1},
        ),
    ):
        report = await deep_research("Test query", depth_tier="quick")

    assert isinstance(report, ResearchReport)
    assert report.budget.early_stopped is True
    assert "lead_timeout" in report.budget.stages_completed


@pytest.mark.asyncio
async def test_deep_research_progress_callback(mock_classification, mock_brief):
    """Progress events are emitted correctly."""
    events = []

    def _on_progress(event):
        events.append(event)

    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": []})

    with (
        patch(
            "kairos_runtime.research.runner.classify_and_brief",
            AsyncMock(return_value=(mock_classification, mock_brief)),
        ),
        patch(
            "kairos_runtime.research.runner.build_lead_agent",
            return_value=mock_agent,
        ),
        patch(
            "kairos_runtime.research.runner.verify_findings",
            AsyncMock(return_value=_mock_verify()),
        ),
        patch(
            "kairos_runtime.research.runner.synthesize_report",
            AsyncMock(return_value="# Report"),
        ),
    ):
        await deep_research("Test", depth_tier="quick", on_progress=_on_progress)

    stages = [e.stage for e in events]
    assert "start" in stages
    assert "classifier" in stages
    assert "brief" in stages
    assert "lead" in stages
    assert "complete" in stages


@pytest.mark.asyncio
async def test_subagent_tokens_recorded_in_meter(mock_classification, mock_brief):
    """When a subagent's LLM emits usage_metadata, the runner should record
    those tokens into the meter under a `subagent_*` stage key.

    The lead agent in this test is mocked, so we simulate the side effect of
    the subagent's UsageCallback firing by directly recording tokens during
    the `ainvoke` mock. This exercises the meter integration path.
    """
    from kairos_runtime.research.runner import TokenMeter

    captured_meters: list[TokenMeter] = []

    def _capture_lead(*args, **kwargs):
        captured_meters.append(kwargs["meter"])
        agent = MagicMock()

        async def _ainvoke(_input):
            # Simulate the subagent's UsageCallback firing during the run.
            kwargs["meter"].record("subagent_code_researcher", 4242)
            kwargs["meter"].record("lead", 1234)
            return {"messages": []}

        agent.ainvoke = _ainvoke
        return agent

    with (
        patch(
            "kairos_runtime.research.runner.classify_and_brief",
            AsyncMock(return_value=(mock_classification, mock_brief)),
        ),
        patch(
            "kairos_runtime.research.runner.build_lead_agent",
            side_effect=_capture_lead,
        ),
        patch(
            "kairos_runtime.research.runner.verify_findings",
            AsyncMock(return_value=_mock_verify()),
        ),
        patch(
            "kairos_runtime.research.runner.synthesize_report",
            AsyncMock(return_value="# Report"),
        ),
    ):
        report = await deep_research("query", depth_tier="quick")

    assert "subagent_code_researcher" in report.tokens_used
    assert report.tokens_used["subagent_code_researcher"] == 4242
    assert report.tokens_used["lead"] == 1234
