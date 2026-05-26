"""Tests for the verifier module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from kairos_runtime.research.filesystem import VirtualFS
from kairos_runtime.research.verifier import (
    _get_wayback_url,
    check_urls_batch,
    extract_citations_from_findings,
    verify_findings,
)


@pytest.fixture
def vfs_with_findings():
    """VFS with a sample findings file containing URLs."""
    vfs = VirtualFS()
    vfs.write(
        "/findings_test.md",
        "## Findings\n\n"
        "LangGraph supports 1M+ concurrent runs per deployment [source](https://langchain.com/langgraph).\n"
        "The framework was released in 2024 according to https://github.com/langchain-ai/langgraph.\n"
        "\n## Sources\n"
        "- https://langchain.com/langgraph\n"
        "- https://github.com/langchain-ai/langgraph\n"
        "- https://this-url-is-dead.example.com/page\n",
    )
    return vfs


def test_extract_citations_from_findings(vfs_with_findings):
    pairs = extract_citations_from_findings(vfs_with_findings)
    urls = [url for _, url in pairs]

    assert len(pairs) >= 3
    assert "https://langchain.com/langgraph" in urls
    assert "https://github.com/langchain-ai/langgraph" in urls
    assert "https://this-url-is-dead.example.com/page" in urls


def test_extract_citations_empty_vfs():
    vfs = VirtualFS()
    pairs = extract_citations_from_findings(vfs)
    assert pairs == []


@pytest.mark.asyncio
async def test_check_urls_batch_live_and_dead():
    """Mock httpx to simulate one live and one dead URL."""

    async def _mock_check(url):
        if "dead" in url:
            return (url, False, "https://web.archive.org/web/cached")
        return (url, True, None)

    with patch(
        "kairos_runtime.research.verifier._check_url_liveness",
        side_effect=_mock_check,
    ):
        results = await check_urls_batch(
            ["https://live.example.com", "https://dead.example.com/page"]
        )

    assert len(results) == 2
    assert results["https://live.example.com"] == (True, None)
    assert results["https://dead.example.com/page"] == (
        False,
        "https://web.archive.org/web/cached",
    )


@pytest.mark.asyncio
async def test_wayback_fallback():
    """Test Wayback Machine API response parsing."""

    async def _mock_get(url, **kwargs):
        from unittest.mock import MagicMock

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "archived_snapshots": {
                "closest": {
                    "available": True,
                    "url": "https://web.archive.org/web/20240101/https://example.com",
                }
            }
        }
        return resp

    with patch("kairos_runtime.research.verifier.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.get = _mock_get
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await _get_wayback_url("https://example.com")

    assert result == "https://web.archive.org/web/20240101/https://example.com"


@pytest.mark.asyncio
async def test_verify_findings_empty_vfs():
    """Verify that an empty VFS produces no citations."""
    vfs = VirtualFS()
    citations, report = await verify_findings(vfs, skip_nli=True)

    assert citations == []
    assert report.total_citations == 0


def test_extract_citations_uses_real_claim_sentences():
    """[n] markers in the body should pull the surrounding sentence as the
    claim, not the Sources list. This prevents NLI from being asked to
    verify ``"## Sources [1] foo [2] bar"`` against the actual source
    content — the bug that produced the DSPy "insufficient grounded data"
    failure on 2026-05-13.
    """
    vfs = VirtualFS()
    vfs.write(
        "/findings.md",
        "## Findings\n\n"
        "DSPy is a framework developed by Stanford NLP [1, 4].\n"
        "It treats prompts as code and uses optimizers like BootstrapFewShot [2].\n"
        "\n## Sources\n"
        "[1] https://dspy.ai\n"
        "[2] https://example.com/dspy-optimizers\n"
        "[4] https://github.com/stanfordnlp/dspy\n",
    )
    pairs = extract_citations_from_findings(vfs)
    by_url = {url: claim for claim, url in pairs}

    # The claim attached to dspy.ai should be the actual sentence, not the
    # Sources block.
    claim_for_dspy = by_url.get("https://dspy.ai", "")
    assert "Stanford NLP" in claim_for_dspy
    assert "Sources" not in claim_for_dspy

    claim_for_optimizers = by_url.get("https://example.com/dspy-optimizers", "")
    assert "BootstrapFewShot" in claim_for_optimizers


@pytest.mark.asyncio
async def test_verify_findings_batches_nli_per_url(monkeypatch):
    """Three claims attached to two URLs should produce ONE NLI call per URL.

    Pre-batch the verifier silently dropped claims 2..N for each URL via a
    seen-urls dedupe; the new path issues one batched NLI call per URL with
    all that URL's claims.
    """
    from kairos_runtime.research import verifier as v

    vfs = VirtualFS()
    # Two URLs: dspy.ai gets two claims, github gets one.
    vfs.write(
        "/findings.md",
        "## Findings\n\n"
        "DSPy is a framework developed by Stanford [1].\n"
        "DSPy treats prompts as code [1].\n"
        "It is hosted on GitHub [2].\n\n"
        "## Sources\n"
        "[1] https://dspy.ai\n"
        "[2] https://github.com/stanfordnlp/dspy\n",
    )

    # Stub liveness + fetch
    async def _live(urls, cache=None):
        return {u: (True, None) for u in urls}

    async def _fetch(urls, cache):
        return {u: f"page body for {u}" for u in urls}

    monkeypatch.setattr(v, "check_urls_batch", _live)
    monkeypatch.setattr(v, "_fetch_pages_batch", _fetch)

    # Track calls. Batch path takes (claims, source_text); single path takes
    # (claim, source_text). Both should be exercised — but `nli_check_batch`
    # exactly once per URL.
    batch_calls: list[tuple[list[str], str]] = []

    async def _batch(claims, source_text, *, meter=None):
        batch_calls.append((claims, source_text))
        return ["entails"] * len(claims)

    single_calls = []

    async def _single(claim, source_text, *, meter=None):
        single_calls.append((claim, source_text))
        return "entails"

    monkeypatch.setattr(v, "nli_check_batch", _batch)
    monkeypatch.setattr(v, "nli_check", _single)

    citations, report = await v.verify_findings(vfs)

    # One batched call per URL — not one per claim.
    assert len(batch_calls) == 2
    # The dspy.ai URL gets both claims; github gets one.
    claim_counts = sorted(len(c) for c, _ in batch_calls)
    assert claim_counts == [1, 2]
    # Citation count is per-URL (deduplicated source list).
    assert report.total_citations == 2


def test_parse_batch_verdicts():
    from kairos_runtime.research.verifier import _parse_batch_verdicts

    verdicts = _parse_batch_verdicts(
        "1: ENTAILS\n2: NOT_MENTIONED\n3: CONTRADICTS\n", n_claims=3
    )
    assert verdicts == ["entails", "not_mentioned", "contradicts"]

    # Missing rows fall back to not_mentioned.
    verdicts = _parse_batch_verdicts("1: ENTAILS\n", n_claims=3)
    assert verdicts == ["entails", "not_mentioned", "not_mentioned"]


@pytest.mark.asyncio
async def test_check_urls_batch_uses_cache_as_liveness_signal():
    """If the subagent already fetched a URL successfully, treat it as
    live without re-probing — successful retrieval is the strongest
    possible liveness signal."""
    from kairos_runtime.research.cache import RunCache

    cache = RunCache()
    cache.put("fetch", "https://cached.example.com", "page body content")

    # Even with a mock that says "dead", cache hits should report live.
    async def _mock_dead(url):
        return (url, False, None)

    with patch(
        "kairos_runtime.research.verifier._check_url_liveness",
        side_effect=_mock_dead,
    ):
        results = await check_urls_batch(
            ["https://cached.example.com", "https://uncached.example.com"],
            cache=cache,
        )

    assert results["https://cached.example.com"] == (True, None)
    # Uncached URL still goes through the liveness check.
    assert results["https://uncached.example.com"] == (False, None)
