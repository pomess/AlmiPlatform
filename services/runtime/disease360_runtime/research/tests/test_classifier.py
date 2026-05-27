"""Tests for the query classifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from disease360_runtime.research.classifier import (
    classify_and_brief,
    classify_query,
    write_research_brief,
)
from disease360_runtime.research.state import Classification, Domain, QueryType, ResearchBrief


@pytest.fixture
def mock_classifier_response():
    """Mock LLM response returning valid classification JSON."""
    return (
        '{"query_type": "comparison", "domain": "software_eng", '
        '"depth_tier": "standard", "ambiguity_score": 0.2, '
        '"suggested_clarifications": [], "estimated_subagents": 3, '
        '"estimated_tokens": 200000}'
    )


@pytest.fixture
def mock_brief_response():
    """Mock LLM response returning valid brief JSON."""
    return (
        '{"title": "LangGraph vs CrewAI Comparison", '
        '"objective": "Compare architecture, performance, and adoption", '
        '"scope": "Multi-agent frameworks released 2024-2026", '
        '"constraints": ["Focus on Python ecosystem"], '
        '"output_format": "markdown"}'
    )


@pytest.mark.asyncio
async def test_classify_query_parses_valid_json(mock_classifier_response):
    mock_msg = MagicMock()
    mock_msg.content = mock_classifier_response

    with patch(
        "disease360_runtime.research.classifier.ChatGoogleGenerativeAI"
    ) as MockLLM:
        instance = MockLLM.return_value
        instance.ainvoke = AsyncMock(return_value=mock_msg)

        result = await classify_query("Compare LangGraph and CrewAI")

    assert isinstance(result, Classification)
    assert result.query_type == QueryType.COMPARISON
    assert result.domain == Domain.SOFTWARE_ENG
    assert result.depth_tier == "standard"
    assert result.ambiguity_score == 0.2
    assert result.estimated_subagents == 3


@pytest.mark.asyncio
async def test_classify_query_handles_code_fences():
    mock_msg = MagicMock()
    mock_msg.content = (
        "```json\n"
        '{"query_type": "specific_fact", "domain": "ai_ml", '
        '"depth_tier": "quick", "ambiguity_score": 0.1, '
        '"suggested_clarifications": [], "estimated_subagents": 1, '
        '"estimated_tokens": 50000}\n'
        "```"
    )

    with patch(
        "disease360_runtime.research.classifier.ChatGoogleGenerativeAI"
    ) as MockLLM:
        instance = MockLLM.return_value
        instance.ainvoke = AsyncMock(return_value=mock_msg)

        result = await classify_query("What is the latest version of LangGraph?")

    assert result.query_type == QueryType.SPECIFIC_FACT
    assert result.depth_tier == "quick"


@pytest.mark.asyncio
async def test_classify_query_falls_back_on_invalid_json():
    mock_msg = MagicMock()
    mock_msg.content = "This is not JSON at all"

    with patch(
        "disease360_runtime.research.classifier.ChatGoogleGenerativeAI"
    ) as MockLLM:
        instance = MockLLM.return_value
        instance.ainvoke = AsyncMock(return_value=mock_msg)

        result = await classify_query("Some query")

    # Should fall back to defaults
    assert isinstance(result, Classification)
    assert result.query_type == QueryType.BROAD_SURVEY
    assert result.domain == Domain.GENERAL
    assert result.depth_tier == "standard"


@pytest.mark.asyncio
async def test_write_research_brief(mock_brief_response):
    mock_msg = MagicMock()
    mock_msg.content = mock_brief_response

    classification = Classification(
        query_type=QueryType.COMPARISON,
        domain=Domain.SOFTWARE_ENG,
        depth_tier="standard",
        ambiguity_score=0.2,
        suggested_clarifications=[],
        estimated_subagents=3,
        estimated_tokens=200000,
    )

    with patch(
        "disease360_runtime.research.classifier.ChatGoogleGenerativeAI"
    ) as MockLLM:
        instance = MockLLM.return_value
        instance.ainvoke = AsyncMock(return_value=mock_msg)

        result = await write_research_brief("Compare LangGraph and CrewAI", classification)

    assert isinstance(result, ResearchBrief)
    assert "LangGraph" in result.title
    assert result.output_format == "markdown"


@pytest.mark.asyncio
async def test_classify_and_brief_single_call_returns_both():
    """The merged path makes one LLM call and returns both objects."""
    mock_msg = MagicMock()
    mock_msg.content = (
        '{"classification": {"query_type": "comparison", "domain": "software_eng", '
        '"depth_tier": "standard", "ambiguity_score": 0.15, '
        '"suggested_clarifications": [], "estimated_subagents": 4, '
        '"estimated_tokens": 250000}, '
        '"brief": {"title": "Compare A and B", "objective": "Compare A and B", '
        '"scope": "All sources", "constraints": [], "output_format": "markdown"}}'
    )

    ainvoke_mock = AsyncMock(return_value=mock_msg)
    with patch(
        "disease360_runtime.research.classifier.ChatGoogleGenerativeAI"
    ) as MockLLM:
        instance = MockLLM.return_value
        instance.ainvoke = ainvoke_mock
        instance.with_config = MagicMock(return_value=instance)

        classification, brief = await classify_and_brief("Compare A and B")

    assert ainvoke_mock.call_count == 1
    assert isinstance(classification, Classification)
    assert isinstance(brief, ResearchBrief)
    assert classification.query_type == QueryType.COMPARISON
    assert classification.estimated_subagents == 4
    assert brief.title == "Compare A and B"


@pytest.mark.asyncio
async def test_classify_and_brief_falls_back_on_bad_json():
    mock_msg = MagicMock()
    mock_msg.content = "not json"

    with patch(
        "disease360_runtime.research.classifier.ChatGoogleGenerativeAI"
    ) as MockLLM:
        instance = MockLLM.return_value
        instance.ainvoke = AsyncMock(return_value=mock_msg)

        classification, brief = await classify_and_brief("query")

    assert classification.query_type == QueryType.BROAD_SURVEY
    assert classification.depth_tier == "standard"
    assert brief.objective == "query"
