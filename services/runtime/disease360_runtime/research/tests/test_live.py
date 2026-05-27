"""Live smoke test — only runs when RUN_LIVE_TESTS=1 is set.

Requires GOOGLE_API_KEY in the environment (loaded via secrets.env).
Actually hits Gemini API so costs tokens and takes time.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS", "0") != "1",
    reason="Live tests disabled (set RUN_LIVE_TESTS=1 to enable)",
)


@pytest.mark.asyncio
async def test_live_classify_query():
    """Hit the real Gemini Flash-Lite API for classification."""
    from disease360_runtime.research.classifier import classify_query
    from disease360_runtime.research.state import Classification

    result = await classify_query("What is the latest version of Python?")

    assert isinstance(result, Classification)
    assert result.depth_tier in ("quick", "standard", "deep", "exhaustive")
    assert result.estimated_subagents >= 1


@pytest.mark.asyncio
async def test_live_grounded_search():
    """Hit the real Gemini API with Google Search grounding."""
    from disease360_runtime.research.grounding import grounded_search

    result = await grounded_search("What is LangGraph?")

    assert result.answer != ""
    assert len(result.chunks) > 0


@pytest.mark.asyncio
async def test_live_deep_research_quick():
    """Full pipeline at 'quick' tier — should complete in ~2 minutes."""
    from disease360_runtime.research.runner import deep_research
    from disease360_runtime.research.state import ResearchReport

    report = await deep_research(
        "What is the current stable version of LangGraph?",
        depth_tier="quick",
    )

    assert isinstance(report, ResearchReport)
    assert len(report.markdown) > 100
    assert report.run_id != ""
