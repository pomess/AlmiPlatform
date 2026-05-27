"""Deep Agent factory.

Builds Disease360 as a read-only deep agent with:
- Gemini Flash (or local Ollama) as the model
- Read-only memory tools (HTTP to services/memory)
- An AsyncSqliteSaver checkpointer (works with both sync .invoke and async .astream)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from disease360_runtime import prompt_cache
from disease360_runtime.config import get as config_get
from disease360_runtime.config import repo_root
from disease360_runtime.llm import get_chat_model

from .system_prompt import DEFAULT_BRAIN, assemble
from .tools import all_memory_tools, research_tools


def _checkpointer_path() -> Path:
    p = repo_root() / "services" / "harness" / "data" / "checkpoints.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def build_agent(
    *,
    profile: str = "chat",
    active_brain: str = DEFAULT_BRAIN,
    extra_tools: list | None = None,
    extra_system_prompt: str | None = None,
    base_tools: list | None = None,
    surface: str = "chat",
) -> Any:
    """Build a Disease360 agent.

    `extra_system_prompt` is appended to the assembled SOUL/USER/brain
    prompt with a blank-line separator. Used to layer a voice-only
    persona (the JARVIS delivery cues) on top of the normal Disease360
    prompt without affecting typed chat.

    `base_tools`, when provided, replaces the default `all_memory_tools()`
    set entirely. Use it to give a page-scoped agent a smaller, curated
    toolset (e.g. read-only memory tools on the dashboard). `extra_tools`
    is still appended on top, so page UI tools layer cleanly.

    `surface` is forwarded to `assemble()` and controls the SURFACE block
    that anchors this agent to its current reply surface (chat or
    dashboard). Default "chat".
    """
    import aiosqlite
    from deepagents import create_deep_agent
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    tools = list(base_tools) if base_tools is not None else list(all_memory_tools())
    if extra_tools:
        tools.extend(extra_tools)
    # Add deep research tool (read-only)
    tools.extend(research_tools())

    system_prompt = assemble(active_brain, surface=surface)
    if extra_system_prompt:
        system_prompt = f"{system_prompt}\n\n{extra_system_prompt.strip()}\n"

    # Optional Gemini context cache for the static system-prompt prefix.
    # Disabled by default (`DISEASE360_USE_CONTEXT_CACHE` flag in
    # `prompt_cache.context_cache_enabled`). When enabled, callers MUST
    # ensure the agent does not later try to bind a different toolset --
    # langchain-google-genai forbids passing tools/system_instruction
    # alongside `cached_content`, and `create_agent` calls `.bind_tools`
    # internally. Safe path right now: enable only on chat-only flows or
    # after the bind-tools coupling is unwound. We compute and try the
    # cache regardless so failures are visible early instead of silently
    # falling back; `get_or_create_cache` returns None unless the flag is
    # set, so the default code path is unchanged.
    cached_content: str | None = None
    if prompt_cache.context_cache_enabled():
        model_name = config_get("DISEASE360_MODEL_OVERRIDE") or config_get(
            "GEMINI_DEFAULT_MODEL", "gemini-flash-latest"
        )
        tool_signatures = [getattr(t, "name", repr(t)) for t in tools]
        cached_content = prompt_cache.get_or_create_cache(
            model=model_name,
            system_prompt=system_prompt,
            tool_signatures=tool_signatures,
        )

    model = get_chat_model(profile, cached_content=cached_content)  # type: ignore[arg-type]

    # Open the aiosqlite connection directly so we own its lifetime — using the
    # `AsyncSqliteSaver.from_conn_string(...)` context manager would close the
    # connection as soon as the manager is GC'd, breaking subsequent requests.
    # AsyncSqliteSaver also satisfies the sync .get_tuple/.put used by
    # `agent.invoke`, so we can use a single checkpointer for both `/chat`
    # (sync) and `/chat/stream` (async).
    conn = aiosqlite.connect(str(_checkpointer_path()))
    checkpointer = AsyncSqliteSaver(conn)

    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )
    return agent
