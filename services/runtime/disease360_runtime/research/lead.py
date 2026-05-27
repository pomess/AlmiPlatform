"""Lead researcher agent factory.

Builds the top-level deep agent that orchestrates subagents but cannot
search the web directly — forcing compression at every level.
"""

from __future__ import annotations

import asyncio
from typing import Any

from deepagents import create_deep_agent
from langchain_core.tools import StructuredTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph.state import CompiledStateGraph

from disease360_runtime.config import require

from .cache import RunCache
from .config import TierConfig, get_model
from .filesystem import VirtualFS, make_read_file_tool, make_write_file_tool
from .prompts import format_lead_prompt
from .state import ResearchBrief
from .subagents import build_all_subagents
from .url_whitelist import URLWhitelist
from .usage import attach as _attach_usage


def _make_think_tool() -> StructuredTool:
    """No-op scratchpad for the lead to plan before/after each delegation."""

    def _think(thought: str) -> str:
        """Plan your approach, assess subagent findings, or reason about gaps.

        REQUIRED before and after each delegation round.

        Args:
            thought: Your reasoning about what to delegate next or what gaps remain.
        """
        return f"[thought recorded: {len(thought)} chars]"

    return StructuredTool.from_function(
        func=_think,
        name="think_tool",
        description=(
            "Think through your delegation strategy, assess returned findings, "
            "and identify research gaps. REQUIRED before and after each delegation round."
        ),
    )


def build_lead_agent(
    *,
    brief: ResearchBrief,
    vfs: VirtualFS,
    cache: RunCache,
    tier_config: TierConfig,
    tool_invocations: dict[str, int] | None = None,
    meter: Any = None,
    whitelist: URLWhitelist | None = None,
) -> CompiledStateGraph:
    """Construct the lead researcher deep agent.

    The lead has ONLY think_tool + read_file (no direct web access).
    It delegates all searches to domain-specialist subagents.
    """
    # Build the lead model directly so we can attach a usage callback. Pass a
    # BaseChatModel instance through to ``create_deep_agent`` — its
    # ``resolve_model`` returns it unchanged.
    lead_model = ChatGoogleGenerativeAI(
        model=get_model("lead"),
        google_api_key=require("GOOGLE_API_KEY"),
        temperature=0.0,
    )
    lead_model = _attach_usage(lead_model, meter, "lead")

    # Subagents share one whitelist that grows as they observe URLs via
    # web_search / fetch_url. write_file rejects bodies whose URLs aren't
    # in this set. The lead's own write tool (it doesn't author findings,
    # but inherits the same tool here) shares the same guarded path.
    write_tool = make_write_file_tool(
        vfs, agent_name="lead", whitelist=whitelist
    )
    read_tool = make_read_file_tool(vfs)

    # Build the formatted lead prompt with brief and limits
    brief_text = (
        f"Title: {brief.title}\n"
        f"Objective: {brief.objective}\n"
        f"Scope: {brief.scope}\n"
        f"Constraints: {', '.join(brief.constraints) if brief.constraints else 'None'}"
    )
    system_prompt = format_lead_prompt(
        brief_text,
        max_rounds=tier_config.max_rounds,
        max_concurrent=tier_config.max_concurrent,
    )

    # Shared semaphore: throttles total concurrent web_search + fetch_url
    # calls across all subagents. This is what `MAX_CONCURRENT_SUBAGENTS`
    # is actually meant to enforce — gating network-bound work.
    search_sem = asyncio.Semaphore(tier_config.max_concurrent)

    # Build all specialist subagents with shared VFS and cache. Pass the
    # brief so subagent prompts have non-empty Topic/Objective slots.
    subagents = build_all_subagents(
        write_file_tool=write_tool,
        read_file_tool=read_tool,
        cache=cache,
        tool_invocations=tool_invocations,
        meter=meter,
        semaphore=search_sem,
        whitelist=whitelist,
        topic=brief.title,
        objective=brief.objective,
        max_tool_calls=tier_config.max_tool_calls,
    )

    # Lead tools: only think + read (no search, no write — subagents write)
    lead_tools: list[Any] = [_make_think_tool(), read_tool]

    agent = create_deep_agent(
        model=lead_model,
        tools=lead_tools,
        system_prompt=system_prompt,
        subagents=subagents,
    )
    return agent
