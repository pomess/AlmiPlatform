"""Tests for subagent tool factories — semaphore-based concurrency cap,
URL whitelist population, and per-tool budget guard."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from disease360_runtime.research.subagents import _make_fetch_tool, _make_search_tool
from disease360_runtime.research.url_whitelist import URLWhitelist


@pytest.mark.asyncio
async def test_search_semaphore_caps_concurrent_calls():
    """Fire 10 concurrent web_search calls with a semaphore of 2 — at no
    point should more than 2 be in flight.
    """
    sem = asyncio.Semaphore(2)
    in_flight = 0
    peak = 0

    async def _fake_grounded_search(query):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1

        class _R:
            answer = "ok"
            chunks: list = []
            queries_run: list = []
            provider = "google"

        return _R()

    with patch(
        "disease360_runtime.research.grounding.grounded_search",
        side_effect=_fake_grounded_search,
    ):
        tool = _make_search_tool(None, semaphore=sem)
        await asyncio.gather(*(tool.coroutine(query=f"q{i}") for i in range(10)))

    assert peak <= 2, f"Semaphore breached — {peak} concurrent searches"


@pytest.mark.asyncio
async def test_fetch_semaphore_caps_concurrent_calls():
    """Same check for fetch_url."""
    sem = asyncio.Semaphore(3)
    in_flight = 0
    peak = 0

    async def _fake_fetch(url):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return "page body"

    with patch("disease360_runtime.research.fetch.fetch_url", side_effect=_fake_fetch):
        tool = _make_fetch_tool(semaphore=sem)
        await asyncio.gather(*(tool.coroutine(url=f"https://x/{i}") for i in range(10)))

    assert peak <= 3, f"Semaphore breached — {peak} concurrent fetches"


@pytest.mark.asyncio
async def test_search_no_semaphore_runs_unbounded():
    """Without a semaphore the search tool runs all calls concurrently."""
    in_flight = 0
    peak = 0

    async def _fake_grounded_search(query):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1

        class _R:
            answer = "ok"
            chunks: list = []
            queries_run: list = []
            provider = "google"

        return _R()

    with patch(
        "disease360_runtime.research.grounding.grounded_search",
        side_effect=_fake_grounded_search,
    ):
        tool = _make_search_tool(None, semaphore=None)
        await asyncio.gather(*(tool.coroutine(query=f"q{i}") for i in range(8)))

    assert peak >= 4, f"Expected unbounded concurrency, got peak={peak}"


# ---------------------------------------------------------------------------
# URL whitelist population
# ---------------------------------------------------------------------------


def _fake_search_result(urls: list[str]):
    class _Chunk:
        def __init__(self, url):
            self.url = url
            self.title = url

    class _R:
        def __init__(self, urls):
            self.answer = "Synthesised answer"
            self.chunks = [_Chunk(u) for u in urls]
            self.queries_run = []
            self.provider = "google"

    return _R(urls)


@pytest.mark.asyncio
async def test_search_tool_populates_whitelist_with_chunk_urls():
    """After a successful web_search, every chunk.url is in the whitelist."""
    whitelist = URLWhitelist()

    async def _fake(query):
        return _fake_search_result(
            ["https://a.example.com/1", "https://b.example.com/2"]
        )

    with patch(
        "disease360_runtime.research.grounding.grounded_search",
        side_effect=_fake,
    ):
        tool = _make_search_tool(None, whitelist=whitelist)
        await tool.coroutine(query="anything")

    assert whitelist.contains("https://a.example.com/1")
    assert whitelist.contains("https://b.example.com/2")
    assert whitelist.size == 2


@pytest.mark.asyncio
async def test_fetch_tool_populates_whitelist_with_input_url_on_success():
    whitelist = URLWhitelist()

    async def _fake_fetch(url):
        return f"page body for {url}"

    with patch("disease360_runtime.research.fetch.fetch_url", side_effect=_fake_fetch):
        tool = _make_fetch_tool(whitelist=whitelist)
        await tool.coroutine(url="https://verified.example.com/page")

    assert whitelist.contains("https://verified.example.com/page")
    assert whitelist.size == 1


@pytest.mark.asyncio
async def test_fetch_tool_does_not_whitelist_on_failure():
    """A fetch that returns empty content should NOT add the URL to the whitelist."""
    whitelist = URLWhitelist()

    async def _fake_fetch(url):
        return ""  # simulate failed fetch

    with patch("disease360_runtime.research.fetch.fetch_url", side_effect=_fake_fetch):
        tool = _make_fetch_tool(whitelist=whitelist)
        await tool.coroutine(url="https://broken.example.com/")

    assert whitelist.size == 0


# ---------------------------------------------------------------------------
# Per-tool budget guard
# ---------------------------------------------------------------------------


class _FakeMeter:
    def __init__(self, used, ceiling):
        self.used = used
        self.ceiling = ceiling
        self.pct_used = used / ceiling if ceiling else 0

    def should_early_stop(self, threshold):
        return self.pct_used >= threshold


@pytest.mark.asyncio
async def test_search_tool_short_circuits_when_over_budget():
    """When the meter is at >=80% the search tool returns the budget message
    WITHOUT calling grounded_search. The tool fn should never be invoked."""
    meter = _FakeMeter(used=85_000, ceiling=100_000)  # 85% used
    grounded = AsyncMock()

    with patch(
        "disease360_runtime.research.grounding.grounded_search",
        new=grounded,
    ):
        tool = _make_search_tool(None, meter=meter)
        result = await tool.coroutine(query="anything")

    assert "Budget exceeded" in result
    assert grounded.await_count == 0


@pytest.mark.asyncio
async def test_fetch_tool_short_circuits_when_over_budget():
    meter = _FakeMeter(used=90_000, ceiling=100_000)
    fetch_mock = AsyncMock()

    with patch("disease360_runtime.research.fetch.fetch_url", new=fetch_mock):
        tool = _make_fetch_tool(meter=meter)
        result = await tool.coroutine(url="https://x.com/y")

    assert "Budget exceeded" in result
    assert fetch_mock.await_count == 0


@pytest.mark.asyncio
async def test_search_tool_does_not_short_circuit_under_budget():
    meter = _FakeMeter(used=10_000, ceiling=100_000)  # 10% used

    async def _fake(query):
        return _fake_search_result(["https://a.com/x"])

    with patch(
        "disease360_runtime.research.grounding.grounded_search",
        side_effect=_fake,
    ):
        tool = _make_search_tool(None, meter=meter)
        result = await tool.coroutine(query="anything")

    assert "Budget exceeded" not in result
    assert "Sources:" in result or "Synthesised answer" in result
