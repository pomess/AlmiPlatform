"""Deep research pipeline — modular, async, reusable everywhere."""

from .runner import deep_research
from .state import ResearchReport
from .store import get_run, submit_run
from .tool import deep_research_tool

__all__ = [
    "ResearchReport",
    "deep_research",
    "deep_research_tool",
    "get_run",
    "submit_run",
]
