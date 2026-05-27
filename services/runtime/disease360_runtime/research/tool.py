"""LangChain tool wrapper for deep_research.

Exposes the research pipeline as a single async tool that the Disease360
agent can call when it detects a query needs in-depth research.
"""

from __future__ import annotations

import logging
import threading
import traceback
from typing import Literal

from langchain_core.tools import StructuredTool

log = logging.getLogger(__name__)


# --- Per-turn budget ---------------------------------------------------------
# A research run takes 5-15 minutes. If the chat agent isn't satisfied with
# the first run's output (e.g. an "Insufficient grounded data" notice), it
# will sometimes re-invoke deep_research with a rephrased query and waste
# another 10 minutes producing the same notice. Cap at one run per user turn.

MAX_RESEARCH_CALLS_PER_TURN = 1

_budget_lock = threading.Lock()
_calls_this_turn = 0


def reset_research_budget() -> None:
    """Called by the harness at the start of each user turn."""
    global _calls_this_turn
    with _budget_lock:
        _calls_this_turn = 0


def _consume_or_block() -> str | None:
    """Reserve a research slot for this turn. Returns None on success, or a
    short markdown message to return to the agent if the budget is exhausted.
    """
    global _calls_this_turn
    with _budget_lock:
        if _calls_this_turn >= MAX_RESEARCH_CALLS_PER_TURN:
            return (
                "## deep_research budget exhausted\n\n"
                "You have already run `deep_research` once in this turn. The "
                "report from that call is in your tool-result history above. "
                "Render it to the user — quoting the markdown verbatim, "
                "including any '## Insufficient grounded data' notice and the "
                "list of ungrounded claims. Do NOT invoke deep_research again. "
                "Do NOT replace the report with an answer drawn from your "
                "training data. If the prior report says the pipeline could "
                "not ground the question, that is the answer the user gets.\n"
            )
        _calls_this_turn += 1
        return None


def deep_research_tool() -> StructuredTool:
    """Create the deep_research LangChain tool for use in the harness agent."""

    async def _deep_research(
        query: str,
        depth_tier: Literal["standard", "deep", "exhaustive"] = "standard",
    ) -> str:
        """Conduct multi-agent deep research on a complex topic.

        Deploys a team of specialist researchers (code, academic, market, news,
        general) in parallel, verifies all citations, and synthesizes a
        comprehensive report with inline sources.

        USE THIS TOOL WHEN:
        - The user asks for in-depth analysis, comparisons, or literature reviews
        - The question would require 5+ web searches to answer well
        - The user explicitly asks for "research", "deep dive", "comprehensive analysis"
        - Market opportunity scans, competitive analysis, technology comparisons
        - Academic synthesis or state-of-the-art surveys

        DO NOT USE WHEN:
        - Simple factual lookups ("what version is X?")
        - Questions answerable from the user's brain/wiki
        - Casual conversation or opinions
        - Tasks that don't require web research

        Args:
            query: The research question or topic to investigate.
                CRITICAL: Pass the user's intent using ONLY generic/categorical
                terms. NEVER expand the query with specific entity names (model
                names, product names, version numbers, company names) that the
                user did not explicitly mention. Your training data has a
                knowledge cutoff — you do NOT know what models, products, or
                versions are current. The research pipeline will discover the
                correct current entities via live web search.
                BAD:  "tokens per second for GPT-5, Claude 4, Gemini 2.0"
                GOOD: "tokens per second benchmarks for latest frontier LLMs"
            depth_tier: How thorough the research should be:
                - "standard": ~8 min, 3-5 subagents, ~1500 word report (default)
                - "deep": ~15 min, 6-10 subagents, ~4000 word report
                - "exhaustive": ~25 min, 8-10 subagents, ~10000+ word report
              The "quick" tier is intentionally excluded — if the query
              didn't warrant >= standard research, the agent shouldn't
              have called this tool.

        Returns:
            The research report as clean markdown text, ready to show to the user.
        """
        blocked = _consume_or_block()
        if blocked is not None:
            log.warning(
                "[deep_research_tool] budget exceeded — refusing repeat call query=%r",
                query[:80],
            )
            return blocked
        try:
            from langgraph.config import get_stream_writer

            from .runner import deep_research

            log.info(
                "[deep_research_tool] starting query=%r tier=%s",
                query[:80],
                depth_tier,
            )

            try:
                writer = get_stream_writer()
            except Exception:
                writer = None
                log.warning("get_stream_writer unavailable — progress events will not stream")

            async def _on_progress(event):
                log.info(
                    "[deep_research_tool] dispatching %s: %s",
                    event.stage,
                    event.message,
                )
                if writer is None:
                    return
                try:
                    writer({
                        "name": "research_progress",
                        "data": {
                            "stage": event.stage,
                            "message": event.message,
                            "detail": event.detail or {},
                        },
                    })
                except Exception:
                    log.exception("progress writer failed")

            report = await deep_research(query, depth_tier=depth_tier, on_progress=_on_progress)

            if not report.markdown or report.markdown.strip() == "":
                return (
                    f"Research completed but produced no findings for: {query}\n\n"
                    "This may be due to a connectivity issue with Google Search. "
                    "Try again or rephrase the query."
                )

            # Append compact metadata footer
            footer = (
                f"\n\n---\n*Research complete — "
                f"{len(report.citations)} sources, "
                f"{report.budget.used:,} tokens "
                f"({report.budget.pct_used:.0%} of budget)*"
            )
            if report.budget.early_stopped:
                footer = footer[:-1] + " *[partial — budget limit reached]*"

            return report.markdown + footer

        except Exception as exc:
            log.error("deep_research tool failed: %s\n%s", exc, traceback.format_exc())
            return (
                f"Deep research failed for: {query}\n\n"
                f"Error: {type(exc).__name__}: {exc}\n\n"
                "The research pipeline encountered an error. "
                "This is likely a temporary issue. Try again or use a simpler query."
            )

    return StructuredTool.from_function(
        coroutine=_deep_research,
        func=None,
        name="deep_research",
        description=(
            "Conduct multi-agent deep research with parallel specialist researchers, "
            "citation verification, and synthesized report. Use for complex questions "
            "requiring 5+ web searches: comparisons, literature reviews, market scans, "
            "technology deep-dives. NOT for simple lookups. "
            "IMPORTANT: The 'query' arg must use only generic/categorical terms — "
            "NEVER inject specific entity names (models, products, versions) that the "
            "user did not explicitly say. Let the research discover what's current."
        ),
    )
