"""Deep research orchestrator — wraps langchain-ai/open_deep_research.

Replaces the custom 5-stage pipeline with open_deep_research's LangGraph-based
multi-agent researcher (supervisor → parallel sub-agents → compression → report).
Keeps the same interface that tool.py expects: `deep_research(query, depth_tier, on_progress)`.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import platform
import uuid
from datetime import datetime
from typing import Any, Callable

from .config import DepthTier
from .state import (
    BudgetReport,
    Citation,
    ProgressEvent,
    ResearchReport,
    VerificationReport,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patch: open_deep_research uses %-d in strftime which is Linux-only.
# On Windows it must be %#d. Patch at import time.
# ---------------------------------------------------------------------------
if platform.system() == "Windows":
    try:
        import open_deep_research.utils as _odr_utils

        def _get_today_str_win() -> str:
            return datetime.now().strftime("%a %b %#d, %Y")

        _odr_utils.get_today_str = _get_today_str_win
    except Exception:
        pass

log = logging.getLogger(__name__)

# Model to use across all open_deep_research stages.
_MODEL = os.environ.get("DISEASE360_RESEARCH_MODEL", "google_genai:gemini-flash-latest")


def _content_to_text(content: Any) -> str:
    """Coerce a LangChain message `content` to a plain string.

    Gemini 3 / flash models return `content` as a list of content blocks
    (e.g. ``[{"type": "text", "text": "..."}]``) rather than a bare string.
    `ResearchReport.markdown` is typed as `str`, so passing the raw list
    crashes Pydantic validation. Flatten any list of blocks into text.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


# ---------------------------------------------------------------------------
# Progress emitter (same interface as before)
# ---------------------------------------------------------------------------


async def _emit(
    callback: Callable[[ProgressEvent], Any] | None,
    stage: str,
    message: str,
    **detail: Any,
) -> None:
    log.info("[research] %s | %s", stage, message)
    if callback:
        event = ProgressEvent(stage=stage, message=message, detail=detail)
        try:
            result = callback(event)
            if inspect.isawaitable(result):
                await result
        except Exception:
            log.exception("progress emit failed for stage=%s", stage)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def deep_research(
    query: str,
    *,
    depth_tier: DepthTier | None = None,
    on_progress: Callable[[ProgressEvent], Any] | None = None,
    run_id: str | None = None,
) -> ResearchReport:
    """Execute deep research via langchain-ai/open_deep_research.

    Args:
        query: The research question
        depth_tier: Controls concurrency/iterations (standard/deep/exhaustive)
        on_progress: Optional callback for streaming progress events
        run_id: Optional run identifier

    Returns:
        ResearchReport with markdown, citations, and budget info
    """
    from langchain_core.messages import HumanMessage
    from open_deep_research.deep_researcher import deep_researcher_builder
    from open_deep_research.configuration import Configuration, SearchAPI

    run_id = run_id or str(uuid.uuid4())[:8]
    started_at = datetime.now()

    await _emit(on_progress, "start", f"Research run {run_id} started", query=query)

    # Map depth tier to concurrency/iteration settings.
    tier = depth_tier or "standard"
    if tier == "exhaustive":
        max_concurrent = 8
        max_iterations = 8
        max_tool_calls = 15
    elif tier == "deep":
        max_concurrent = 6
        max_iterations = 6
        max_tool_calls = 12
    else:
        max_concurrent = 5
        max_iterations = 4
        max_tool_calls = 8

    log.info("=" * 70)
    log.info("[research] RUN %s — deep research starting", run_id)
    log.info("[research]   query        : %s", query)
    log.info("[research]   depth tier   : %s", tier)
    log.info("[research]   model        : %s", _MODEL)
    log.info(
        "[research]   limits       : %d concurrent units · %d iterations · %d tool calls",
        max_concurrent,
        max_iterations,
        max_tool_calls,
    )
    log.info("=" * 70)

    config = {
        "configurable": {
            "search_api": SearchAPI.TAVILY.value,
            "research_model": _MODEL,
            "summarization_model": _MODEL,
            "compression_model": _MODEL,
            "final_report_model": _MODEL,
            "max_concurrent_research_units": max_concurrent,
            "max_researcher_iterations": max_iterations,
            "max_react_tool_calls": max_tool_calls,
            "allow_clarification": False,
        }
    }

    graph = deep_researcher_builder.compile()

    await _emit(on_progress, "planning", "Generating research brief...")

    # Stream the graph to capture intermediate events.
    final_report = ""
    sources_seen: list[str] = []
    subagent_count = 0
    search_count = 0

    # Every progress event carries the running tallies so the UI can render
    # a single, self-contained status line (e.g. "Sub-agents dispatched: 13 |
    # Researching") without having to accumulate counts itself.
    def _counts() -> dict[str, int]:
        return {
            "subagents": subagent_count,
            "searches": search_count,
            "sources": len(sources_seen),
        }

    try:
        async for event in graph.astream_events(
            {"messages": [HumanMessage(content=query)]},
            config=config,
            version="v2",
        ):
            kind = event.get("event", "")
            name = event.get("name", "")

            if kind == "on_chain_start" and "write_research_brief" in name:
                log.info("[research] %s · PLAN — writing research brief", run_id)
                await _emit(on_progress, "planning", "Research brief generated", **_counts())

            elif kind == "on_chain_start" and "supervisor" in name:
                log.info("[research] %s · SUPERVISOR — dispatching sub-agents", run_id)
                await _emit(
                    on_progress, "researching", "Supervisor dispatching sub-agents...",
                    **_counts(),
                )

            elif kind == "on_chain_start" and "researcher" in name:
                subagent_count += 1
                log.info("[research] %s · SUB-AGENT #%d — researching", run_id, subagent_count)
                await _emit(on_progress, "researching", "Sub-agent researching...", **_counts())

            elif kind == "on_tool_start":
                tool_name = event.get("data", {}).get("input", {}).get("query", "")
                if tool_name:
                    short = tool_name[:80]
                    search_count += 1
                    log.info("[research] %s · SEARCH #%d — %s", run_id, search_count, short)
                    await _emit(
                        on_progress, "searching", f"Searching: {short}",
                        query=short, **_counts(),
                    )

            elif kind == "on_tool_end":
                data = event.get("data", {})
                output = data.get("output", "")
                if isinstance(output, str) and "http" in output:
                    for line in output.split("\n"):
                        if line.startswith("http"):
                            url = line.strip()
                            if url not in sources_seen:
                                sources_seen.append(url)
                                log.info(
                                    "[research] %s · SOURCE [%d] %s",
                                    run_id,
                                    len(sources_seen),
                                    url[:80],
                                )
                                await _emit(
                                    on_progress, "fetching",
                                    f"Source [{len(sources_seen)}]: {url[:60]}",
                                    url=url, **_counts(),
                                )

            elif kind == "on_chain_start" and "compress_research" in name:
                log.info("[research] %s · COMPRESS — distilling findings", run_id)
                await _emit(
                    on_progress, "compressing", "Compressing research findings...",
                    **_counts(),
                )

            elif kind == "on_chain_start" and "final_report" in name:
                log.info("[research] %s · SYNTHESIZE — writing final report", run_id)
                await _emit(
                    on_progress, "synthesizing", "Writing final report...", **_counts(),
                )

            elif kind == "on_chain_end" and "final_report" in name:
                data = event.get("data", {})
                output = data.get("output", {})
                if isinstance(output, dict):
                    msgs = output.get("messages", [])
                    if msgs:
                        last_msg = msgs[-1]
                        if hasattr(last_msg, "content"):
                            final_report = _content_to_text(last_msg.content)

    except Exception as exc:
        log.error("[research] %s · FAILED — %s", run_id, exc)
        await _emit(on_progress, "error", f"Research failed: {exc}")
        raise

    # If we didn't capture the report from events, try invoking directly.
    if not final_report:
        await _emit(on_progress, "synthesizing", "Finalizing report...", **_counts())
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=query)]},
            config=config,
        )
        messages = result.get("messages", [])
        if messages:
            final_report = (
                _content_to_text(messages[-1].content)
                if hasattr(messages[-1], "content")
                else ""
            )

    completed_at = datetime.now()
    elapsed = (completed_at - started_at).total_seconds()

    log.info("=" * 70)
    log.info(
        "[research] RUN %s — complete in %.0fs · %d sub-agents · %d searches · "
        "%d sources · %d chars",
        run_id,
        elapsed,
        subagent_count,
        search_count,
        len(sources_seen),
        len(final_report),
    )
    log.info("=" * 70)

    await _emit(
        on_progress, "done",
        f"Research complete ({elapsed:.0f}s, {len(sources_seen)} sources)",
        elapsed_s=round(elapsed), **_counts(),
    )

    # Build citations from sources seen.
    citations = [
        Citation(index=i + 1, url=url, verified=True, live=True)
        for i, url in enumerate(sources_seen)
    ]

    return ResearchReport(
        markdown=final_report,
        citations=citations,
        verification=VerificationReport(),
        tokens_used={},
        budget=BudgetReport(
            ceiling=0,
            used=0,
            early_stopped=False,
            pct_used=0.0,
            stages_completed=["planning", "researching", "compressing", "synthesizing"],
            note=f"open_deep_research ({tier}), {elapsed:.0f}s",
        ),
        started_at=started_at,
        completed_at=completed_at,
        run_id=run_id,
    )
