"""Per-run isolated virtual filesystem (artifact pattern).

Each research run gets its own VirtualFS instance. Subagents write findings
to it via LangChain tools; the lead only sees pointers (one-line summaries).
The verifier and synthesizer read from it to produce the final report.
"""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import StructuredTool

from .url_whitelist import (
    URLWhitelist,
    extract_urls,
    format_violation_message,
)


class VirtualFS:
    """In-memory filesystem scoped to a single research run."""

    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    def write(self, path: str, content: str) -> str:
        """Write content and return a pointer summary for the lead."""
        self._files[path] = content
        lines = content.strip().splitlines()
        citation_count = content.count("http://") + content.count("https://")
        summary_line = lines[0][:120] if lines else "(empty)"
        return f"[artifact:{path}] {summary_line} ({citation_count} sources)"

    def read(self, path: str) -> str:
        """Read a file by path. Returns empty string if not found."""
        return self._files.get(path, "")

    def list_files(self) -> list[str]:
        return list(self._files.keys())

    def has(self, path: str) -> bool:
        return path in self._files

    @property
    def files(self) -> dict[str, str]:
        return dict(self._files)


def make_write_file_tool(
    vfs: VirtualFS,
    *,
    agent_name: str = "subagent",
    on_write: Callable[[str, int], None] | None = None,
    whitelist: URLWhitelist | None = None,
) -> StructuredTool:
    """Create a write_file LangChain tool bound to a specific VirtualFS instance.

    `on_write` is called with (path, approx_tokens) after each write for
    budget tracking.

    `whitelist` enforces URL provenance: any URL in the body that is NOT in
    the whitelist (i.e. not seen via web_search or fetch_url) causes the
    write to be rejected with a guidance message. Pass ``None`` to disable
    the guard (useful in tests or for the lead's own write tool which
    doesn't author findings).
    """

    def _write_file(name: str, content: str) -> str:
        """Write a findings file to the shared research filesystem.

        Args:
            name: Filename (e.g. 'findings_react_frameworks.md')
            content: Full markdown content including:
                - "Queries Made" section
                - "Findings" section (preserve facts/numbers/quotes verbatim)
                - "Sources" section (deduplicated URLs with access timestamps)

        Returns:
            A pointer string the lead can use to reference this artifact.
        """
        if not name.endswith(".md"):
            name = f"{name}.md"
        path = f"/{name}"

        if whitelist is not None:
            urls_in_body = extract_urls(content)
            offending = sorted(whitelist.diff(urls_in_body))
            if offending:
                return format_violation_message(name, offending)

        pointer = vfs.write(path, content)
        if on_write:
            approx_tokens = len(content) // 4
            on_write(path, approx_tokens)
        return pointer

    return StructuredTool.from_function(
        func=_write_file,
        name="write_file",
        description=(
            "Write a findings markdown file to the shared research filesystem. "
            f"Called by {agent_name}. Returns a pointer string (filename + summary + "
            "source count) that the lead researcher sees instead of the full content."
        ),
    )


def make_read_file_tool(vfs: VirtualFS) -> StructuredTool:
    """Create a read_file LangChain tool bound to a specific VirtualFS instance."""

    def _read_file(path: str) -> str:
        """Read a file from the research filesystem by path.

        Args:
            path: File path (e.g. '/findings_react_frameworks.md')

        Returns:
            The file content, or an error message if not found.
        """
        if not path.startswith("/"):
            path = f"/{path}"
        content = vfs.read(path)
        if not content:
            available = vfs.list_files()
            return f"File not found: {path}. Available: {available}"
        return content

    return StructuredTool.from_function(
        func=_read_file,
        name="read_file",
        description="Read a file from the shared research filesystem by path.",
    )
