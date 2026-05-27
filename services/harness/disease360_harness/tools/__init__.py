"""Tool registry exported to the Deep Agent."""

from .memory_tools import all_memory_tools
from .page_tools import (
    PAGE_BASE_TOOLS,
    PAGE_PROMPTS,
    PAGE_TOOLS,
    base_tools_for_page,
    prompt_for_page,
    tools_for_page,
)


def research_tools() -> list:
    """Return the deep research tool(s) for inclusion in the agent toolset."""
    from disease360_runtime.research import deep_research_tool

    return [deep_research_tool()]


__all__ = [
    "PAGE_BASE_TOOLS",
    "PAGE_PROMPTS",
    "PAGE_TOOLS",
    "all_memory_tools",
    "base_tools_for_page",
    "prompt_for_page",
    "research_tools",
    "tools_for_page",
]
