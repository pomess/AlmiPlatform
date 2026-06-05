"""System prompt assembly: SOUL.md → USER.md → atlas → active brain hot.md → index.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx
from atlas_runtime.config import get, repo_root

DEFAULT_BRAIN = "BioMCP Brain"


# ---------------------------------------------------------------------------
# Surface notes — read-only cockpit
#
# The cockpit reads the vault. There are no write tools on any surface.
# Both Chat and the Dashboard share the same read-only toolset; the
# surface label is kept so page-specific addendums (e.g. dashboard map
# narration) can still anchor the reply.
# ---------------------------------------------------------------------------

READ_ONLY_SURFACE_NOTE = (
    "This cockpit is read-only. You can search and read the vault but "
    "cannot write to it. If the user asks to save, capture, record, "
    "ingest, or write something, tell them plainly the cockpit is "
    "read-only right now and continue helping with what you can do."
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _now_block() -> str:
    now = datetime.now().astimezone()
    pretty = f"{now:%A}, {now:%B} {now.day}, {now.year}"
    tz = f"{now:%Z}" or f"UTC{now:%z}"
    return (
        f"Today is {pretty} ({now:%Y-%m-%d}). "
        f"Local time is {now:%H:%M} {tz}. "
        "When the user says 'today', 'tomorrow', 'next Monday', etc., resolve "
        "the date from this reference — never guess and never assume a stale date."
    )


def _format_atlas(atlas: dict | None, active_brain: str) -> str:
    """Render the cross-brain atlas as a compact KNOWLEDGE LANDSCAPE block.

    Atlas comes from the memory service (`GET /atlas`) and lists, per brain,
    its `purpose`, top entities, and top concepts. We collapse each brain to
    three lines — purpose, entity titles, concept titles — so the model gets
    the *vocabulary* it needs to (a) route directly to the right brain when
    a topic is named here, and (b) speak natural connector lines like
    "Let me check your Deloitte notes." while the lookup is in flight.

    Returns "" when the atlas is missing/empty so the caller can skip the
    section entirely.
    """
    brains = (atlas or {}).get("brains") or []
    if not brains:
        return ""
    lines: list[str] = [
        "# KNOWLEDGE LANDSCAPE",
        "Here is what each of your brains holds. Use this to route lookups:",
        "- If a topic is already named below, call `get_page(path, brain=...)` "
        "DIRECTLY — skip `search_wiki`. Cross-brain search reindexes both "
        "vaults and is much slower than reading a single page.",
        "- Only fall back to `search_wiki` when the topic is NOT named here.",
        "",
    ]
    for b in brains:
        bid = b.get("id", "")
        purpose = (b.get("purpose") or "").strip()
        active_marker = "  *(active brain)*" if bid == active_brain else ""
        if purpose:
            lines.append(f"## {bid} — {purpose}{active_marker}")
        else:
            lines.append(f"## {bid}{active_marker}")

        entities = b.get("key_entities") or []
        if entities:
            ent_strs = [f"{e['title']} (`{e['path']}`)" for e in entities if e.get("title")]
            if ent_strs:
                lines.append("Entities: " + "; ".join(ent_strs))

        concepts = b.get("key_concepts") or []
        if concepts:
            con_strs = [f"{c['title']} (`{c['path']}`)" for c in concepts if c.get("title")]
            if con_strs:
                lines.append("Concepts: " + "; ".join(con_strs))

        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def assemble(
    active_brain: str = DEFAULT_BRAIN,
    *,
    fetch_remote: bool = True,
    surface: str = "chat",
    tenant_id: str = "local",
) -> str:
    """Build the system prompt.

    Order: NOW → SURFACE → SOUL → USER → wiki edit policy →
    KNOWLEDGE LANDSCAPE (atlas) → active brain hot.md → index.md head.

    `fetch_remote=True` pulls hot/index/atlas from the memory service over
    HTTP; `False` reads hot/index from disk and skips the atlas (used when
    memory service is offline).

    `surface` is "chat" (default) or "dashboard". It controls the SURFACE
    block which anchors the agent to the current reply surface and
    immunises it against persona-bleed from prior turns produced on a
    different surface in the same shared thread.
    """
    root = repo_root()
    soul = _read(root / "identity" / "SOUL.md")
    user = _read(root / "identity" / "USER.md")

    hot, index = "", ""
    atlas: dict | None = None
    memory_url = get("atlas_memory_URL", "http://127.0.0.1:8001")
    tenant_prefix = f"/tenant/{tenant_id}"
    if fetch_remote and memory_url:
        try:
            with httpx.Client(timeout=2.0) as client:
                hot = (
                    client.get(f"{memory_url}{tenant_prefix}/brain/{active_brain}/hot")
                    .json()
                    .get("body", "")
                )
                index = (
                    client.get(f"{memory_url}{tenant_prefix}/brain/{active_brain}/index")
                    .json()
                    .get("body", "")
                )
                # Atlas is a perf hint, not a correctness requirement — if
                # the call fails we silently omit the section.
                try:
                    atlas = client.get(f"{memory_url}{tenant_prefix}/atlas").json()
                except Exception:
                    atlas = None
        except Exception:
            hot, index = "", ""
    if not hot:
        hot = _read(root / "vault" / tenant_id / active_brain / "hot.md")
    if not index:
        index = _read(root / "vault" / tenant_id / active_brain / "index.md")

    # Trim index to head (first ~120 lines) to keep prompt size sane
    index_head = "\n".join(index.splitlines()[:120])
    atlas_block = _format_atlas(atlas, active_brain)

    surface_norm = (surface or "chat").strip().lower()
    surface_label = surface_norm.upper()

    return (
        f"# NOW\n{_now_block()}\n\n"
        f"# SURFACE\n"
        f"You are currently replying on the **{surface_label}** surface.\n"
        f"{READ_ONLY_SURFACE_NOTE}\n\n"
        f"# IDENTITY (SOUL.md)\n{soul}\n\n"
        f"# USER (USER.md)\n{user}\n\n"
        "# TOOL ARGUMENT GROUNDING\n"
        "When calling any tool that takes a free-text query argument (e.g. "
        "`deep_research`, `search_wiki`), you MUST pass ONLY the terms the "
        "user actually said. NEVER expand, elaborate, or add specific entity "
        "names (model names, product names, company names, version numbers, "
        "hardware names) from your own knowledge. Your training data is stale "
        "— you do not know what is current. The tool's search layer will "
        "discover current entities.\n"
        "- User says 'new frontier LLMs' → pass 'new frontier LLMs', NOT "
        "'GPT-5, Claude 4, Gemini 2.0, Llama 4'\n"
        "- User says 'best React frameworks' → pass 'best React frameworks', "
        "NOT 'Next.js 15, Remix 3, Astro 5'\n"
        "Violation of this rule poisons research with hallucinated entities.\n\n"
        "# RENDERING `deep_research` OUTPUT — STRICT\n"
        "When `deep_research` returns, its markdown is the GROUND TRUTH for "
        "your reply. You MUST:\n"
        "- Present the tool's markdown to the user with at most light "
        "trimming/reformatting. Do NOT replace it with a confident-sounding "
        "answer drawn from your own training data.\n"
        "- If the tool returns '## Insufficient grounded data', tell the user "
        "exactly that — quote the report, including the list of claims that "
        "could not be grounded if present. Do NOT 'help' by filling in the "
        "missing facts from memory. Your training data is stale and the "
        "research pipeline already determined that no current sources support "
        "those specific claims.\n"
        "- NEVER name a specific model, product, version, benchmark number, "
        "company, hardware part, paper, or URL in your reply that does not "
        "appear in the tool's returned markdown. If you find yourself wanting "
        "to write 'GPT-X', 'Claude Y', 'Llama Z', 'NVIDIA <chip>', a TPS "
        "number, or any version string that is not in the tool's report — "
        "STOP and remove it. The user can re-run with a different query if "
        "they want more.\n"
        "- An honest 'the research could not ground this' beats a "
        "confidently-wrong list of 2024-era models every time.\n\n"
        f"{atlas_block}\n"
        f"# ACTIVE BRAIN: {active_brain}\n\n"
        f"## Hot cache (hot.md)\n{hot}\n\n"
        f"## Index (head of index.md)\n{index_head}\n"
    )
