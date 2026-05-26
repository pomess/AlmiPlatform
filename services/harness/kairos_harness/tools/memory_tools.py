"""HTTP-client tools that talk to the memory FastAPI service."""

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
            "the wiki, say so plainly: \"I don't see that in your brain — want me "
            "to capture it?\""
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
    live in work brains (e.g. "Deloitte's Brain") rather than "Bruno's Brain".
    One cross-brain call is almost always the right first move.

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
def append_hot(text: str, brain: str = "Bruno's Brain", section: str | None = None) -> dict:
    """Append an EPHEMERAL working-memory note to hot.md. Silent — no approval.

    Use ONLY for observations scoped to the current conversation that would help
    over the next few turns. Examples: "user is in a hurry", "current focus:
    debugging X", "user prefers short answers right now".

    DO NOT use for:
    - Identity facts about Bruno (name, role, employer, salary, preferences,
      relationships) — those go through `plan_ingest` → approval.
    - Persistent facts about people, places, decisions, projects — those go
      through `plan_ingest` → approval.
    - Anything the user said with "remember", "save this", "add this to my
      profile", "from now on" — always use `plan_ingest`.

    `section` nests the note under '## <section>' (creates the section if
    missing). Keep notes short (one line).
    """
    with httpx.Client(timeout=10.0) as c:
        return c.post(
            _tenant_url(f"/brain/{brain}/append-hot"),
            json={"text": text, "section": section},
        ).json()


@tool
def replace_hot(full_text: str, brain: str = "Bruno's Brain", rationale: str = "") -> dict:
    """REPLACE the entire hot.md. REQUIRES APPROVAL. Use only at compaction time."""
    with httpx.Client(timeout=10.0) as c:
        return c.post(
            _tenant_url(f"/brain/{brain}/replace-hot"),
            json={"full_text": full_text, "rationale": rationale},
        ).json()


@tool
def write_note(
    path: str,
    title: str,
    body: str,
    brain: str = "Bruno's Brain",
    frontmatter: dict | None = None,
) -> dict:
    """Create or overwrite a SINGLE wiki page. REQUIRES APPROVAL.

    `path` is relative to wiki/. Use this ONLY for a single isolated page edit
    (e.g. creating one new concept page, or rewriting one specific page the
    user named).

    DO NOT call this tool multiple times in a row to propagate one change
    across several pages. For any edit that touches more than one page, or
    that needs to update hot.md / index.md / overview.md alongside the page
    change, call `plan_ingest` instead — it proposes the full multi-file
    change in ONE shot and shows the user a single diff to approve. Using
    `write_note` in a loop is 5-10x slower (one LLM generation per file) and
    creates one approval prompt per page.
    """
    with httpx.Client(timeout=15.0) as c:
        return c.post(
            _tenant_url(f"/brain/{brain}/note"),
            json={
                "path": path,
                "title": title,
                "body": body,
                "frontmatter": frontmatter or {},
            },
        ).json()


@tool
def get_index(brain: str = "Bruno's Brain") -> dict:
    """Read the brain's index.md (TOC of wiki pages)."""
    with httpx.Client(timeout=10.0) as c:
        return c.get(_tenant_url(f"/brain/{brain}/index")).json()


@tool
def plan_ingest(title: str, content: str, brain: str = "Bruno's Brain") -> dict:
    """Propose a wiki ingest WITHOUT writing anything. SILENT — no approval needed.

    Returns a plan dict with `plan_id`, `summary`, `ops` (list of file changes),
    and proposed updates to hot.md / index.md / overview.md / log.md.

    Use this whenever the user shares a meaningful source, decision, or fact
    they want captured. After receiving the plan, summarize it back to the user
    in chat and then call `apply_ingest(plan_id)` to commit (which requires
    approval). Never call `apply_ingest` without first showing the user what
    will change.
    """
    with httpx.Client(timeout=180.0) as c:
        r = c.post(
            _tenant_url(f"/brain/{brain}/ingest/plan"),
            json={"title": title, "content": content},
        )
        r.raise_for_status()
        return r.json()


@tool
def apply_ingest(plan_id: str, brain: str = "Bruno's Brain") -> dict:
    """Apply a previously-planned ingest. REQUIRES APPROVAL.

    `plan_id` must come from a recent `plan_ingest` call. The approval card
    shown to the user will display the full diff (new pages, updated pages,
    hot/index/overview/log changes). Plans expire after 30 minutes.
    """
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            _tenant_url(f"/brain/{brain}/ingest/apply"),
            json={"plan_id": plan_id},
        )
        r.raise_for_status()
        return r.json()


@tool
def lint_brain(brain: str = "Bruno's Brain") -> dict:
    """Run a read-only health check on a brain.

    Returns a list of issues (contradictions, orphans, missing pages, sparse
    pages, index drift, etc.) plus stats. SILENT — no approval needed.
    Pair with `plan_solve` + `apply_solve` to fix issues one at a time.
    """
    with httpx.Client(timeout=120.0) as c:
        r = c.post(_tenant_url(f"/brain/{brain}/lint"))
        r.raise_for_status()
        return r.json()


@tool
def plan_solve(issue: dict, brain: str = "Bruno's Brain") -> dict:
    """Propose edits that fix a single lint issue. SILENT — no writes.

    `issue` should be a dict from `lint_brain`'s issues list with keys
    `type`, `severity`, `description`, `page`, `suggestion`.
    Returns a plan with `plan_id` to feed into `apply_solve`.
    """
    with httpx.Client(timeout=120.0) as c:
        r = c.post(_tenant_url(f"/brain/{brain}/solve/plan"), json=issue)
        r.raise_for_status()
        return r.json()


@tool
def apply_solve(plan_id: str, brain: str = "Bruno's Brain") -> dict:
    """Apply a previously-planned solve. REQUIRES APPROVAL.

    Same shape and approval flow as `apply_ingest`.
    """
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            _tenant_url(f"/brain/{brain}/solve/apply"),
            json={"plan_id": plan_id},
        )
        r.raise_for_status()
        return r.json()


def all_memory_tools() -> list:
    return [
        list_brains,
        search_wiki,
        get_page,
        get_hot,
        get_index,
        append_hot,
        replace_hot,
        write_note,
        plan_ingest,
        apply_ingest,
        lint_brain,
        plan_solve,
        apply_solve,
    ]


# Tools that require approval per policies/actions.yaml
APPROVAL_TOOLS: set[str] = {"replace_hot", "write_note", "apply_ingest", "apply_solve"}
