"""HTTP-client tools that talk to the memory FastAPI service.

Read-only set: the cockpit only reads the vault. No mutating tools are
exposed to the agent — anything that would write to a brain has been
removed alongside the approval/HITL pipeline.
"""

from __future__ import annotations

import threading

import httpx
from kairos_runtime.config import get
from langchain_core.tools import tool

DEFAULT_TENANT_ID = "local"


def _base() -> str:
    return get("KAIROS_MEMORY_URL", "http://127.0.0.1:8001") or "http://127.0.0.1:8001"


# --- Active tenant ---------------------------------------------------------
# Tools call the memory service with a tenant-scoped URL. The harness sets
# the active tenant at the start of every /chat turn before kicking off the
# agent. ContextVars don't propagate to LangGraph's tool-execution threads,
# so we use the same module-level + lock pattern as the budget tracker.

_tenant_lock = threading.Lock()
_active_tenant: str = DEFAULT_TENANT_ID


def set_active_tenant(tenant_id: str) -> None:
    global _active_tenant
    with _tenant_lock:
        _active_tenant = tenant_id or DEFAULT_TENANT_ID


def get_active_tenant() -> str:
    with _tenant_lock:
        return _active_tenant


def _tenant_url(suffix: str) -> str:
    """Build a memory URL under the active tenant. Suffix starts with '/'."""
    return f"{_base()}/tenant/{get_active_tenant()}{suffix}"


# --- Per-turn search budget --------------------------------------------------
# Hard cap on read-tool calls per user turn. Without this the model (Gemini
# Flash especially) tends to fish for synonyms across both brains 10+ times
# when an answer isn't in the vault. The harness resets this state at the
# start of each /chat or /chat/stream invocation. Single-user system, so we
# use a module-level dict guarded by a lock — robust whether tools run on the
# event loop or in a thread executor (ContextVars don't propagate to threads).

MAX_SEARCHES_PER_TURN = 2
MAX_PAGE_READS_PER_TURN = 4

_budget_lock = threading.Lock()
_budget_state: dict = {
    "searches": 0,
    "pages": 0,
    "queries": set(),
}


def reset_turn_budget() -> None:
    """Called by the harness at the start of each user turn."""
    with _budget_lock:
        _budget_state["searches"] = 0
        _budget_state["pages"] = 0
        _budget_state["queries"] = set()


def _budget_msg(kind: str, used: int, cap: int) -> dict:
    return {
        "_budget_exceeded": True,
        "message": (
            f"Search budget exhausted ({kind}: {used}/{cap}). Stop searching and "
            "answer with what you already have. If the user's question is not in "
            "the wiki, say so plainly: \"I don't see that in your brain.\""
        ),
        "results": [],
    }


@tool
def list_brains() -> list[dict]:
    """List all available knowledge brains (vaults)."""
    with httpx.Client(timeout=10.0) as c:
        return c.get(_tenant_url("/brains")).json()


@tool
def search_wiki(query: str, brain: str | None = None, limit: int = 10) -> list | dict:
    """Full-text search across Bruno's brains. Returns hits tagged with their brain.

    By DEFAULT searches ALL brains at once — people, projects, and clients may
    live in work brains rather than "Bruno's Brain". One cross-brain call is
    almost always the right first move.

    Only pass `brain=` when the user has clearly scoped the question to a single
    brain (e.g. "in my personal brain", "in Deloitte").

    Hard limit: AT MOST 2 search_wiki calls per user turn. Repeating the same
    (query, brain) pair returns the cached result. If the cross-brain search
    returns no hits, DO NOT fall back to `ls`/`glob`/`grep`/`read_file` —
    those are sandbox tools that cannot see wiki content.
    """
    key = f"{brain or '*'}::{query.strip().lower()}"
    with _budget_lock:
        if key in _budget_state["queries"]:
            return {
                "_duplicate": True,
                "message": "Same query already issued this turn. Do not retry.",
                "results": [],
            }
        used = _budget_state["searches"]
        if used >= MAX_SEARCHES_PER_TURN:
            return _budget_msg("search_wiki", used, MAX_SEARCHES_PER_TURN)
        _budget_state["searches"] = used + 1
        _budget_state["queries"].add(key)

    with httpx.Client(timeout=10.0) as c:
        if brain is None:
            return c.get(
                _tenant_url("/search"),
                params={"q": query, "limit": limit},
            ).json()
        return c.get(
            _tenant_url(f"/brain/{brain}/search"),
            params={"q": query, "limit": limit},
        ).json()


@tool
def get_page(path: str, brain: str = "Bruno's Brain") -> dict:
    """Read a wiki page by its relative path (e.g. 'wiki/concepts/agency.md').

    Hard limit: AT MOST 4 get_page calls per user turn. Only call paths
    returned by `search_wiki` or listed in `index.md` — do not guess paths.
    """
    with _budget_lock:
        used = _budget_state["pages"]
        if used >= MAX_PAGE_READS_PER_TURN:
            return _budget_msg("get_page", used, MAX_PAGE_READS_PER_TURN)
        _budget_state["pages"] = used + 1

    with httpx.Client(timeout=10.0) as c:
        return c.get(_tenant_url(f"/brain/{brain}/page"), params={"path": path}).json()


@tool
def get_hot(brain: str = "Bruno's Brain") -> dict:
    """Read the active brain's hot.md (current focus / working set)."""
    with httpx.Client(timeout=10.0) as c:
        return c.get(_tenant_url(f"/brain/{brain}/hot")).json()


@tool
def get_index(brain: str = "Bruno's Brain") -> dict:
    """Read the brain's index.md (TOC of wiki pages)."""
    with httpx.Client(timeout=10.0) as c:
        return c.get(_tenant_url(f"/brain/{brain}/index")).json()


def all_memory_tools() -> list:
    return [
        list_brains,
        search_wiki,
        get_page,
        get_hot,
        get_index,
    ]
