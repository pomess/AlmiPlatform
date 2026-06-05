"""Domain-specialist subagent factories.

Each factory returns a DeepAgents SubAgent TypedDict configured with the
appropriate prompt, model, and tool allowlist for its domain.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.tools import StructuredTool

from .config import get_model
from .url_whitelist import URLWhitelist


_BUDGET_THRESHOLD = 0.80


def _budget_message(meter: Any) -> str:
    pct = getattr(meter, "pct_used", 0.0) or 0.0
    ceiling = getattr(meter, "ceiling", 0) or 0
    return (
        f"Budget exceeded ({pct:.0%} of {ceiling:,} tokens used). "
        f"Stop researching now: write your current findings to file with "
        f"write_file, then return. Do NOT issue any more searches or fetches."
    )


def _budget_blocked(meter: Any) -> bool:
    """True iff the meter exists and has crossed the early-stop threshold."""
    if meter is None:
        return False
    try:
        return bool(meter.should_early_stop(_BUDGET_THRESHOLD))
    except Exception:
        return False


def _make_think_tool() -> StructuredTool:
    """No-op scratchpad tool that forces the model to reason between actions."""

    def _think(thought: str) -> str:
        """Use this tool to think through your approach, assess findings, and plan next steps.

        REQUIRED before and after every search. Write your reasoning here.

        Args:
            thought: Your reasoning, assessment of progress, or plan for next steps.
        """
        return f"[thought recorded: {len(thought)} chars]"

    return StructuredTool.from_function(
        func=_think,
        name="think_tool",
        description=(
            "Think through your approach, assess findings, or plan next steps. "
            "REQUIRED before and after every search call. "
            "Argument: your reasoning text."
        ),
    )


def _emit_progress(stage: str, message: str, detail: dict[str, Any]) -> None:
    """Best-effort write to the LangGraph stream so the chat UI can show
    live subagent activity. No-op outside a streaming run."""
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        return
    try:
        writer({
            "name": "research_progress",
            "data": {"stage": stage, "message": message, "detail": detail},
        })
    except Exception:
        pass


def _make_search_tool(
    search_fn: Any,
    cache: Any | None = None,
    tool_invocations: dict[str, int] | None = None,
    semaphore: asyncio.Semaphore | None = None,
    whitelist: URLWhitelist | None = None,
    meter: Any = None,
) -> StructuredTool:
    """Create a web_search async tool that wraps grounded_search for subagents."""
    from .grounding import grounded_search

    async def _search_async(query: str) -> str:
        """Search the web for information on a topic.

        Args:
            query: The search query. Be specific and include key terms.

        Returns:
            Search results with source URLs and relevant excerpts.
        """
        if _budget_blocked(meter):
            return _budget_message(meter)

        if tool_invocations is not None:
            tool_invocations["web_search"] = tool_invocations.get("web_search", 0) + 1
        if cache and cache.has("search", query):
            _emit_progress(
                "search",
                f"Cached: {query[:80]}",
                {"query": query, "cached": True},
            )
            return cache.get("search", query)

        if semaphore is not None:
            async with semaphore:
                result = await grounded_search(query)
        else:
            result = await grounded_search(query)

        if whitelist is not None and result.chunks:
            whitelist.add_many(c.url for c in result.chunks if c.url)

        # Track which provider served the search so we can compute the
        # Google-vs-DDG-vs-empty rate per run.
        if tool_invocations is not None:
            key = f"search_provider_{result.provider}"
            tool_invocations[key] = tool_invocations.get(key, 0) + 1

        urls = [c.url for c in result.chunks if c.url][:8]
        titles = [c.title for c in result.chunks if c.url][:8]
        _emit_progress(
            "search",
            f"Searched [{result.provider}]: {query[:80]}",
            {
                "query": query,
                "provider": result.provider,
                "queries_run": list(result.queries_run or []),
                "urls": urls,
                "titles": titles,
                "result_count": len(result.chunks),
            },
        )

        output_parts = [result.answer]
        if result.chunks:
            output_parts.append("\n\nSources:")
            for chunk in result.chunks:
                output_parts.append(f"- [{chunk.title}]({chunk.url})")

        output = "\n".join(output_parts)
        if cache:
            cache.put("search", query, output)
        return output

    return StructuredTool.from_function(
        coroutine=_search_async,
        func=None,
        name="web_search",
        description=(
            "Search the web using Google Search grounding. Returns synthesized "
            "answer with source URLs. Use specific, targeted queries."
        ),
    )


def _make_fetch_tool(
    cache: Any | None = None,
    tool_invocations: dict[str, int] | None = None,
    semaphore: asyncio.Semaphore | None = None,
    whitelist: URLWhitelist | None = None,
    meter: Any = None,
) -> StructuredTool:
    """Create an async fetch_url tool for subagents."""
    from .fetch import fetch_url

    async def _fetch_async(url: str) -> str:
        """Fetch the content of a URL as clean markdown.

        Args:
            url: Full URL to fetch (must start with http:// or https://)

        Returns:
            The page content as markdown, or an error message.
        """
        if _budget_blocked(meter):
            return _budget_message(meter)

        if tool_invocations is not None:
            tool_invocations["fetch_url"] = tool_invocations.get("fetch_url", 0) + 1
        if cache and cache.has("fetch", url):
            _emit_progress("fetch", f"Cached: {url[:120]}", {"url": url, "cached": True})
            if whitelist is not None:
                whitelist.add(url)
            return cache.get("fetch", url)

        if semaphore is not None:
            async with semaphore:
                content = await fetch_url(url)
        else:
            content = await fetch_url(url)

        if content and whitelist is not None:
            whitelist.add(url)

        if not content:
            _emit_progress("fetch", f"Failed: {url[:120]}", {"url": url, "ok": False})
            return f"Failed to fetch {url}"

        _emit_progress(
            "fetch",
            f"Fetched: {url[:120]}",
            {"url": url, "ok": True, "bytes": len(content)},
        )

        if cache:
            cache.put("fetch", url, content)
        return content

    return StructuredTool.from_function(
        coroutine=_fetch_async,
        func=None,
        name="fetch_url",
        description=(
            "Fetch a URL and extract its content as clean markdown. "
            "Use to read the full text of a source after finding it via web_search."
        ),
    )


def build_subagent(
    agent_type: str,
    *,
    write_file_tool: StructuredTool,
    read_file_tool: StructuredTool,
    cache: Any | None = None,
    topic: str = "",
    objective: str = "",
    max_tool_calls: int = 15,
    boundaries: str = "None specified",
    tool_invocations: dict[str, int] | None = None,
    meter: Any = None,
    semaphore: asyncio.Semaphore | None = None,
    whitelist: URLWhitelist | None = None,
) -> dict[str, Any]:
    """Build a SubAgent TypedDict for use with create_deep_agent.

    Args:
        agent_type: One of code_researcher, academic_researcher,
                    market_researcher, news_researcher, general_researcher
        write_file_tool: VFS write tool bound to the run's filesystem
        read_file_tool: VFS read tool bound to the run's filesystem
        cache: Optional RunCache for deduplicating searches
        topic: Research topic for the prompt
        objective: Specific objective for this subagent
        max_tool_calls: Tool call budget
        boundaries: What this subagent should NOT research
        meter: Optional TokenMeter; receives subagent token usage via callback
        semaphore: Optional asyncio.Semaphore that gates concurrent
            web_search/fetch_url calls across subagents
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    from atlas_runtime.config import require

    from .prompts import format_subagent_prompt
    from .usage import attach as _attach_usage

    # Build the chat model directly (instead of passing a "google_genai:..."
    # string) so we can attach a usage callback before deepagents wraps it.
    model = ChatGoogleGenerativeAI(
        model=get_model("subagent"),
        google_api_key=require("GOOGLE_API_KEY"),
        temperature=0.0,
    )
    model = _attach_usage(model, meter, f"subagent_{agent_type}")

    prompt = format_subagent_prompt(
        agent_type,
        topic=topic,
        objective=objective,
        max_tool_calls=max_tool_calls,
        boundaries=boundaries,
    )

    tools: list[Any] = [
        _make_think_tool(),
        _make_search_tool(
            None,
            cache=cache,
            tool_invocations=tool_invocations,
            semaphore=semaphore,
            whitelist=whitelist,
            meter=meter,
        ),
        _make_fetch_tool(
            cache=cache,
            tool_invocations=tool_invocations,
            semaphore=semaphore,
            whitelist=whitelist,
            meter=meter,
        ),
        write_file_tool,
        read_file_tool,
    ]

    descriptions = {
        "code_researcher": (
            "Research codebases, APIs, libraries, frameworks, official docs, "
            "GitHub repos, and technical implementation details."
        ),
        "academic_researcher": (
            "Research academic papers, arXiv preprints, peer-reviewed publications, "
            "citation graphs, and scientific findings."
        ),
        "market_researcher": (
            "Research companies, funding rounds, competitors, market sizing, "
            "product comparisons, and business intelligence."
        ),
        "news_researcher": (
            "Research current events, recent announcements, press releases, "
            "breaking news, and time-sensitive information."
        ),
        "general_researcher": (
            "Research general topics using Wikipedia, government data, "
            "reference sources, and anything not covered by specialist agents."
        ),
    }

    return {
        "name": agent_type,
        "description": descriptions.get(agent_type, descriptions["general_researcher"]),
        "system_prompt": prompt,
        "tools": tools,
        "model": model,
    }


def build_all_subagents(
    *,
    write_file_tool: StructuredTool,
    read_file_tool: StructuredTool,
    cache: Any | None = None,
    tool_invocations: dict[str, int] | None = None,
    meter: Any = None,
    semaphore: asyncio.Semaphore | None = None,
    whitelist: URLWhitelist | None = None,
    topic: str = "",
    objective: str = "",
    max_tool_calls: int = 15,
) -> list[dict[str, Any]]:
    """Build all five specialist subagents with shared FS and cache.

    ``topic`` and ``objective`` come from the research brief and fill the
    ``<Topic>`` / ``<Objective>`` slots in each subagent's system prompt so
    the carefully-written scaffolding isn't empty at runtime.
    """
    agent_types = [
        "code_researcher",
        "academic_researcher",
        "market_researcher",
        "news_researcher",
        "general_researcher",
    ]
    return [
        build_subagent(
            t,
            write_file_tool=write_file_tool,
            read_file_tool=read_file_tool,
            cache=cache,
            tool_invocations=tool_invocations,
            meter=meter,
            semaphore=semaphore,
            whitelist=whitelist,
            topic=topic,
            objective=objective,
            max_tool_calls=max_tool_calls,
        )
        for t in agent_types
    ]
