"""System prompt assembly: SOUL.md → USER.md → atlas → active brain hot.md → index.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx

from kairos_runtime.config import get, repo_root

DEFAULT_BRAIN = "Bruno's Brain"


# ---------------------------------------------------------------------------
# Surface notes
#
# The langgraph thread is shared across surfaces (chat + voice on the
# dashboard). On a fresh turn, the LLM sees the FULL message history --
# including assistant turns produced by a *different* surface's agent
# with a different toolset and persona. Without a surface anchor on the
# system prompt, the LLM tends to mirror the most recent assistant
# persona it sees (persona-persistence > system-instruction in practice),
# which leaks dashboard-style "I can only stash in hot cache, switch to
# Chat" replies into chat turns.
#
# These blocks are appended to the assembled system prompt. They quote
# back the exact leaked phrases and forbid them, which is the strongest
# pure-prompt counter we have without restructuring threads.
# ---------------------------------------------------------------------------

CHAT_SURFACE_NOTE = (
    "On chat you have FULL write tools: `plan_ingest`, `apply_ingest`, "
    "`write_note`, `replace_hot`, `append_hot`. The wiki-edit policy "
    "below applies here.\n"
    "\n"
    "This thread is shared with the dashboard's voice assistant. Earlier "
    "turns in the visible history may have come from voice on the "
    "dashboard, where the toolset is intentionally read-only + "
    "`append_hot`. Those turns say things like:\n"
    "- \"On this dashboard surface I only have access to ...\"\n"
    "- \"switch over to Chat to ingest / write / update\"\n"
    "- \"I've stashed it in your hot cache for now\"\n"
    "\n"
    "That was the dashboard speaking. THIS turn is on Chat. Therefore:\n"
    "- Do NOT echo phrases like \"on this dashboard\", \"switch over to "
    "Chat\", \"I can only stash in hot cache\" -- you ARE chat, with "
    "full tools.\n"
    "- If a prior turn deferred a write to chat (\"we'll do this in "
    "chat\"), this is that chat. Execute the deferred write now, "
    "subject to the WIKI EDIT POLICY -- it still requires an explicit "
    "user verb in the CURRENT turn.\n"
    "- Default capture path is `plan_ingest` -> `apply_ingest`. Do not "
    "pick `append_hot` just because a prior dashboard turn used it; "
    "that was the dashboard being constrained, not a style choice."
)

DASHBOARD_SURFACE_NOTE = (
    "On the dashboard you have read tools + `append_hot` only. For any "
    "persistent write the user wants, point them at Chat once and stop "
    "-- do not keep repeating the hand-off across follow-up turns."
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
    memory_url = get("KAIROS_MEMORY_URL", "http://127.0.0.1:8001")
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
    surface_note = (
        CHAT_SURFACE_NOTE if surface_norm == "chat" else DASHBOARD_SURFACE_NOTE
    )

    return (
        f"# NOW\n{_now_block()}\n\n"
        f"# SURFACE\n"
        f"You are currently replying on the **{surface_label}** surface.\n"
        f"{surface_note}\n\n"
        f"# IDENTITY (SOUL.md)\n{soul}\n\n"
        f"# USER (USER.md)\n{user}\n\n"
        f"# WIKI EDIT POLICY\n"
        "Writes to the brain (`plan_ingest`, `apply_ingest`, `write_note`, "
        "`replace_hot`, `append_hot`) require an EXPLICIT, in-this-turn "
        "instruction from the user. Default is OFF -- when in doubt, do "
        "not write.\n"
        "\n"
        "DO NOT write for any of these:\n"
        "- Recall / status / resume questions: 'what were we doing', 'where "
        "were we', 'what's the status', 'continue', 'go on', 'and?'. ANSWER "
        "NARRATIVELY in past tense ('We were drafting your mentorship plan; "
        "I sent it to your approvals 4 minutes ago. Want me to keep going?'). "
        "DO NOT re-fire `apply_ingest` / `write_note` / `plan_ingest` to "
        "'make progress'. The conversation having a paused approval is "
        "NOT a directive to apply again.\n"
        "- Greetings, small talk, casual chat.\n"
        "- General-knowledge questions, opinions, brainstorming, reasoning "
        "out loud. Thinking aloud is not a save request.\n"
        "- Read-only requests: 'what did I write about X', 'pull up my Y', "
        "'summarise my Z'. Use the read tools, never the write ones.\n"
        "- Anything ambiguous. ASK before writing: 'Want me to capture that?'\n"
        "\n"
        "ONLY write when the user gives an unambiguous capture verb in THIS "
        "turn: save, record, capture, note, remember, ingest, write down, "
        "store, log, jot down, put this in my brain, add a page about, "
        "correct my Y page, fix the date on Z, update X. Same content "
        "covered by an existing pending approval should NOT be re-ingested "
        "-- if you see a pending approval for what the user is asking "
        "about, point them at the Approvals page instead.\n"
        "\n"
        "When the user IS asking you to write:\n"
        "- Default to `plan_ingest` -> `apply_ingest`. `plan_ingest` proposes "
        "the full multi-file change (page edits + hot/index/overview/log "
        "updates) in ONE LLM call and ONE approval card showing the diff.\n"
        "- Use `write_note` ONLY when the change is a single isolated page "
        "and the user explicitly asked for that page. NEVER call "
        "`write_note` more than once per turn -- if you find yourself "
        "wanting a second one, stop and call `plan_ingest` instead.\n"
        "- For tiny corrections (a date, a name): still prefer `plan_ingest` "
        "-- it handles the index/hot updates too. `append_hot` is the only "
        "exception, for one-liner ephemeral memos under `## notes`.\n"
        "- After firing an apply/write tool, do NOT claim the change "
        "succeeded until the approval is resolved. While paused, the "
        "right phrasing is 'queued for approval', not 'saved' / 'added' / "
        "'stored'.\n\n"
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
