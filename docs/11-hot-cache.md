# Hot cache

> The single highest-leverage piece of personal-LLM systems. Karpathy-pattern derivative; popularized by the AgriciDaniel `claude-obsidian` workflow. Reused from the existing Obsidian-Knowledge-Graphs project.

## What it is

A small (target: < 1500 tokens), **always-loaded** markdown file holding the user's *current working context*: what's on top of mind right now. It's prepended to every model call so the LLM doesn't have to re-derive context each turn.

It is **not**:
- A summary of the whole brain (that's `index.md`).
- A journal (that's `log.md`).
- The agent's identity (that's `SOUL.md`).
- Stable user facts (those go in `USER.md`).

It **is**: rolling, ephemeral, hot. Today's projects, this week's problems, names of people in active threads, the file Bruno is editing right now.

## Where it lives

Per brain. Already implemented in the existing project under each vault as `hot.md`, surfaced in the UI by the `HotCache` component.

```
vaults/
├── personal/
│   ├── hot.md          ← personal hot cache
│   ├── index.md
│   ├── log.md
│   └── …
└── work/
    ├── hot.md          ← work hot cache
    └── …
```

## How JARVIS uses it

### Read (every turn)

The harness's system-prompt assembly:

```
SYSTEM PROMPT
├── identity/SOUL.md           ← who you are (rarely changes)
├── identity/USER.md           ← who Bruno is (slow-moving)
├── vaults/<active>/hot.md     ← what's hot RIGHT NOW (this is the new bit)
└── vaults/<active>/index.md (top of file only) ← navigation
```

Order matters. Hot cache goes *after* USER.md so transient context can override stale facts.

When JARVIS spans multiple brains for a query, hot caches are concatenated under headers (`## personal hot`, `## work hot`).

### Write (managed)

Three writers, each gated differently:

| Who writes | When | Approval? |
|---|---|---|
| **Bruno** | Manually in Obsidian or via the web UI | n/a |
| **Day-close job** (HEARTBEAT.md, 22:30) | Compacts hot.md: drop items closed today, promote to wiki pages anything that's been hot for >7 days | Show diff, ask once |
| **Inline by JARVIS** | When user says things like "I'm starting on X today" or "remind me about Y" | `ingest_text` is in `require_approval` — but for hot.md edits we'll add a special action `update_hot_cache` defaulted to `allow_silently` for *appends*, `require_approval` for *deletions*. |

### Pin / freshness budget

Soft rule enforced by the day-close job:
- **Items older than 7 days** and not touched in the last day → propose moving to a real wiki page.
- **File over 1500 tokens** → trigger a compaction pass before next morning.

Both surface as approval prompts in the morning digest.

## hot.md schema (kept loose, but this is the seed)

```markdown
# Hot — personal

_Updated: 2026-04-27_

## Now
- Building JARVIS (this repo)
- Reading: Karpathy LLM wiki gist
- Open question: submodule vs copy for memory service

## This week
- Ship Phase 1: harness skeleton + LLMClient + approvals + slim gesture port
- USER.md TBDs: timezone, DND hours, morning-digest time

## People in active threads
- (none right now)

## Pinned
- Local model: gemma4:4b via Ollama
- All brains visible to JARVIS; addresses me as Bruno
```

(We keep both English and Spanish entries verbatim — JARVIS is bilingual.)

## Implications for the harness

- **Token budget guard**: cap hot.md ingestion at 1500 tokens; if over, truncate with a warning logged to `audit.jsonl` (don't silently drop content).
- **Cache invalidation**: re-read on every chat turn (file is small) and on `update_hot_cache` calls. No in-memory cache that can go stale.
- **MCP tool**: add `update_hot_cache(brain, op, content)` where `op ∈ {append, replace_section, delete_section}`.
- **Web UI**: the existing `HotCache` panel becomes the authoritative editor; mount it in the JARVIS sidebar.

## Why this matters for "JARVIS-feel"

Without hot cache, every conversation starts cold. The agent knows *who you are* (USER.md) but not *where you are* (hot.md). Every JARVIS interaction in the movies skips re-explanation — that's exactly what hot cache buys.

It's also the cheapest way to get the brain-as-second-memory effect: the model "remembers" what you're working on because you (or it) wrote it down, not because it's in the weights.

## Status

- ✅ Concept already in the existing project (`hot.md` + `HotCache` component).
- ⏭ Phase 1 work: wire it into the harness's system-prompt assembly; add `update_hot_cache` tool; honor the 1500-token cap; surface in the JARVIS web sidebar.
- ⏭ Phase 2 work: day-close compaction job in HEARTBEAT.md.
