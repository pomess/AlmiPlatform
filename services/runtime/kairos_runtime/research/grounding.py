"""Gemini Google Search grounding wrapper with DuckDuckGo fallback.

Uses google.genai directly for structured grounding chunks + supports.
Falls back to DuckDuckGo when Google grounding is unavailable (503, 499, etc).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from kairos_runtime.config import require

from .config import get_model
from .quota import acquire_google_slot

log = logging.getLogger(__name__)


@dataclass
class GroundingChunk:
    url: str
    title: str = ""


@dataclass
class GroundingSupport:
    text: str
    chunk_indices: list[int] = field(default_factory=list)


@dataclass
class SearchResult:
    answer: str
    chunks: list[GroundingChunk] = field(default_factory=list)
    supports: list[GroundingSupport] = field(default_factory=list)
    queries_run: list[str] = field(default_factory=list)
    # Which provider actually served this search. "google" = Gemini Google
    # Search grounding (success path). "ddg" = DuckDuckGo fallback after a
    # transient error or empty grounding response. "none" = both failed.
    provider: str = "google"


def _get_client() -> genai.Client:
    # Google grounding (GoogleSearch tool) routinely takes 30-90s for
    # multi-query searches; the SDK's default timeout (~60s) was firing
    # 503 "Deadline expired" errors and forcing a fallback to DDG.
    return genai.Client(
        api_key=require("GOOGLE_API_KEY"),
        http_options=types.HttpOptions(timeout=180_000),
    )


async def _ddg_search(query: str, max_results: int = 5) -> SearchResult:
    """DuckDuckGo fallback when Google grounding is unavailable."""
    from ddgs import DDGS

    try:
        results = await asyncio.to_thread(DDGS().text, query, max_results=max_results)
        if not results:
            return SearchResult(
                answer="", chunks=[], supports=[], queries_run=[query], provider="none"
            )

        chunks = [
            GroundingChunk(url=r.get("href", ""), title=r.get("title", ""))
            for r in results
            if r.get("href")
        ]
        answer = "\n\n".join(
            f"{r.get('title', '')}: {r.get('body', '')}" for r in results
        )
        return SearchResult(
            answer=answer, chunks=chunks, supports=[], queries_run=[query], provider="ddg"
        )
    except Exception as exc:
        log.warning("DDG fallback also failed query=%r err=%s", query[:80], exc)
        return SearchResult(
            answer="", chunks=[], supports=[], queries_run=[], provider="none"
        )


async def grounded_search(
    query: str,
    *,
    model: str | None = None,
) -> SearchResult:
    """Run a grounded Google Search via Gemini and return structured results.

    Uses google.genai's native GoogleSearch tool to get real-time web results
    with grounding metadata (source URLs, support spans, queries issued).
    """
    model_id = model or get_model("subagent")

    # Daily quota gate: Google's grounded-search free tier is ~5000/day.
    # Cap our usage at a configurable threshold (default 4000) and fall
    # back to DDG once exhausted, so we don't start incurring charges.
    ok, used, limit = await acquire_google_slot()
    if not ok:
        log.info(
            "[grounded_search] daily google quota exhausted (%d/%d) — using DDG",
            used,
            limit,
        )
        result = await _ddg_search(query)
        log.info(
            "[grounded_search] DDG (quota fallback) returned %d chunks, answer_len=%d",
            len(result.chunks),
            len(result.answer),
        )
        return result

    client = _get_client()

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.0,
    )

    log.info(
        "[grounded_search] start model=%s query=%r quota=%d/%d",
        model_id,
        query[:120],
        used,
        limit,
    )
    resp = None
    last_exc: Exception | None = None
    for attempt in (1, 2):
        try:
            resp = await client.aio.models.generate_content(
                model=model_id,
                contents=query,
                config=config,
            )
            break
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            transient = "503" in msg or "UNAVAILABLE" in msg or "Deadline" in msg
            if attempt == 1 and transient:
                log.warning(
                    "[grounded_search] attempt %d transient error (%s) — retrying after backoff",
                    attempt,
                    type(exc).__name__,
                )
                await asyncio.sleep(2.0)
                continue
            break

    if resp is None:
        log.warning(
            "[grounded_search] generate_content failed after retries: %s: %s — falling back to DDG",
            type(last_exc).__name__ if last_exc else "Unknown",
            last_exc,
        )
        result = await _ddg_search(query)
        log.info(
            "[grounded_search] DDG fallback returned %d chunks, answer_len=%d",
            len(result.chunks),
            len(result.answer),
        )
        return result

    answer = resp.text or ""
    chunks: list[GroundingChunk] = []
    supports: list[GroundingSupport] = []
    queries_run: list[str] = []

    candidate = resp.candidates[0] if resp.candidates else None
    if candidate:
        gm = candidate.grounding_metadata
        if gm:
            for chunk in gm.grounding_chunks or []:
                if chunk.web:
                    chunks.append(
                        GroundingChunk(url=chunk.web.uri or "", title=chunk.web.title or "")
                    )
            for support in gm.grounding_supports or []:
                seg_text = ""
                if support.segment:
                    seg_text = support.segment.text or ""
                indices = list(support.grounding_chunk_indices or [])
                supports.append(GroundingSupport(text=seg_text, chunk_indices=indices))
            queries_run = list(gm.web_search_queries or [])
        else:
            log.info("[grounded_search] candidate had no grounding_metadata")
    else:
        log.info("[grounded_search] no candidates in response")

    log.info(
        "[grounded_search] result: answer_len=%d chunks=%d supports=%d queries_issued=%s",
        len(answer),
        len(chunks),
        len(supports),
        queries_run or "[]",
    )

    if not answer and not chunks:
        log.info("[grounded_search] empty result — falling back to DDG")
        result = await _ddg_search(query)
        log.info(
            "[grounded_search] DDG fallback returned %d chunks, answer_len=%d",
            len(result.chunks),
            len(result.answer),
        )
        return result

    return SearchResult(
        answer=answer,
        chunks=chunks,
        supports=supports,
        queries_run=queries_run,
    )
