# Audit of `Obsidian-Knowledge-Graphs` — inspiration only

> Repo: `c:\Users\Bruno\Desktop\Obsidian-Knowledge-Graphs`
> **STATUS (per locked decision #1): inspiration only — NO code reuse.** Read this doc to understand the design space; rebuild every component fresh in JARVIS. No submodules, no copy/paste, no port-by-replace.
>
> The architecture below is a *reference* for what greenfield JARVIS modules should look like, not a list of files to import.

## Stack at a glance

| Layer | Tech |
|---|---|
| Backend | **FastAPI** (Python) |
| Inference | **Gemini 2.5 Flash** via `google-genai`, async streaming |
| Frontend | **React 19 + Vite + TypeScript** |
| Graph viz | **D3-force** |
| Streaming | **Server-Sent Events (SSE)** |
| Storage | Plain markdown + YAML frontmatter on disk |

## Architecture

```
┌────────────────────────────────────────────────────┐
│   React 19 + Vite + TS frontend                    │
│   ┌─────────────┐  ┌──────────────┐                │
│   │ ChatPanel   │  │ WikiBrowser  │                │
│   ├─────────────┤  ├──────────────┤                │
│   │ GraphView   │  │ IngestPanel  │                │
│   ├─────────────┤  ├──────────────┤                │
│   │ LintPanel   │  │ HotCache     │                │
│   ├─────────────┤  ├──────────────┤                │
│   │ Sidebar     │  │ ChatMessage  │                │
│   └─────────────┘  └──────────────┘                │
│        ▲                ▲                          │
│        │ useStreamChat hook (SSE)                  │
│        │ lib/api.ts                                │
└────────┼────────────────────────────────────────────┘
         │
         ▼ (HTTP + SSE)
┌────────────────────────────────────────────────────┐
│   FastAPI backend (main.py)                        │
│   ┌──────────────────────────────────────────────┐ │
│   │   BrainRegistry  (multi-brain support)       │ │
│   │   ├─ Bruno's Brain                           │ │
│   │   └─ Deloitte's Brain                        │ │
│   └──────────────────────────────────────────────┘ │
│   ┌────────────┐  ┌─────────────┐  ┌────────────┐  │
│   │VaultManager│  │ WikiAgent   │  │GeminiClient│  │
│   │            │  │             │  │            │  │
│   │ disk I/O   │  │ context     │  │ async      │  │
│   │ frontmatter│  │ gathering   │  │ streaming  │  │
│   │ wikilinks  │  │ ingest_text │  │            │  │
│   │ graph (D3) │  │ JSON extract│  │            │  │
│   └────────────┘  └─────────────┘  └────────────┘  │
└────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────┐
│   Vault on disk (Karpathy three-layer pattern)     │
│   ├ raw/{*.md, assets/}        ← layer 1: sources  │
│   ├ wiki/                       ← layer 2: LLM-gen │
│   │  ├ overview.md                                 │
│   │  ├ concepts/                                   │
│   │  ├ entities/                                   │
│   │  ├ sources/                                    │
│   │  └ analyses/                                   │
│   ├ index.md                                       │
│   ├ log.md                                         │
│   ├ hot.md                                         │
│   ├ AGENTS.md                  ← layer 3: schema   │
│   └ CLAUDE.md                                      │
└────────────────────────────────────────────────────┘
```

## API surface (already implemented)

- `GET  /api/brains`            — list available brains
- `POST /api/chat`              — streaming chat (SSE)
- `POST /api/ingest/text`       — ingest a text source, update wiki
- `POST /api/ingest/file`       — same, for uploads
- `POST /api/lint`              — run lint pass
- `POST /api/lint/solve`        — apply lint fixes

## Backend module breakdown

### `vault.py` — `VaultManager`
Disk-level operations on a vault:
- `read_file`, `write_file`
- `parse_frontmatter` (uses `python-frontmatter`)
- `parse_wikilinks` — regex `\[\[([^\]|]+)(?:\|[^\]]+)?\]\]`
- `list_pages`
- `get_graph` — produces D3-force compatible nodes/edges

### `wiki_agent.py` — `WikiAgent`
The brain of the operation:
- `_gather_context` — keyword-scoring over the index to pick relevant pages
- `query` (async) — streaming chat with cited context
- `ingest_text` (async) — full Karpathy ingest workflow with the AGENTS.md schema in the prompt
- `_extract_json` — robust JSON extraction handling markdown fences

### `gemini_client.py` — `GeminiClient`
Thin async wrapper over `google.genai`. Separate prompt templates for ingest vs chat. Streaming.

### `main.py` — FastAPI app
- `BrainRegistry` for multi-vault support
- Routes for chat, ingest, lint
- SSE streaming

## Vault structure (Karpathy-compliant)

```
AGENTS.md       ← "schema" layer (Codex flavor)
CLAUDE.md       ← "schema" layer (Claude flavor)
hot.md          ← working-context cache (the "hot cache" pattern)
index.md        ← LLM-maintained content catalog
log.md          ← append-only operation log
raw/
  ├─ *.md       ← source documents
  └─ assets/    ← images & attachments
wiki/
  ├─ overview.md
  ├─ concepts/
  ├─ entities/
  ├─ sources/
  └─ analyses/
```

## Reusability matrix

| Component | Reuse as-is | Reuse with mods | Replace | Notes |
|---|---|---|---|---|
| `VaultManager` | ✅ | | | Solid, generic, pure I/O. Move into a shared `core/` package. |
| `BrainRegistry` | ✅ | | | Already supports the multi-brain idea. Extend to register a "JARVIS brain" alongside personal/work. |
| Vault layout (raw/wiki/AGENTS.md) | ✅ | | | Already Karpathy-compliant. |
| `index.md`, `log.md`, `hot.md` | ✅ | | | Keep. |
| `GeminiClient` | | ⚠️ | | Provider should become pluggable (Gemini, Claude, GPT-OSS, local Ollama via OpenJarvis). The streaming pattern stays. |
| `WikiAgent` | | ⚠️ | | Logic stays (gather → query/ingest), but plumbing should become an OpenJarvis "agent" or sit behind MCP so other agents can call it as a tool. |
| Frontend (Chat / Wiki / Graph / Ingest / Lint) | ✅ | | | Excellent. Becomes the JARVIS web UI. Add a "Voice" tab and an "Actions/Approvals" tab. |
| `useStreamChat` SSE hook | ✅ | | | Generic, reusable. |
| Action / tool execution | | | ❌ none | Needs to be added — this is the OpenClaw / OpenJarvis layer. |
| Voice I/O | | | ❌ none | Needs to be added. |
| Sandboxing / approval gates | | | ❌ none | Needs to be added (NemoClaw-inspired). |
| Identity layer (`SOUL.md`, `USER.md`, `HEARTBEAT.md`) | | | ❌ none | Adopt OpenClaw pattern. |

## What's missing for it to be JARVIS

This is the gap analysis driving the architecture proposal in [06-jarvis-architecture-proposal.md](06-jarvis-architecture-proposal.md):

1. **Action layer** — the agent can read the wiki and answer questions, but can't *do* things. No email, calendar, shell, browser, smart home.
2. **Identity layer** — there's `AGENTS.md`/`CLAUDE.md` per-vault, but no `SOUL.md` for the agent's own persona, and no `USER.md` for who Bruno is.
3. **Heartbeat / scheduler** — no proactive behavior (cron / morning digest).
4. **Voice surface** — chat-only.
5. **Multi-channel** — web only. No Telegram / WhatsApp / iMessage.
6. **Sandbox / approvals** — Gemini API gets handed prompts directly; nothing gates dangerous actions.
7. **Local LLM option** — currently Gemini-only. Should support Ollama / vLLM via the OpenJarvis Engine primitive.
8. **Self-improvement loop** — no traces, no fine-tuning. (Stretch goal.)

## Bonus context

The vault references a separate **"de-warp"** project of Bruno's that is reportedly already a voice agent with **<500 ms latency** using Gemini + LangChain Deep Agents. If true, that's the voice frontend — we don't need to build STT/TTS/wake-word from scratch either. Worth surfacing and confirming.

## Recommendation

**Reuse the existing project as the memory & web-UI layer of JARVIS.**

Concretely:
- Promote `backend/` to `services/memory/` in the new repo (or pull it in as a git submodule).
- Add **OpenJarvis** as the agent runtime (Engine + Agents + Tools/MCP primitives).
- Add an **OpenClaw-style identity & channels harness** (SOUL/USER/HEARTBEAT, Telegram bridge first).
- Add a **voice service** (probably reusing your "de-warp" pipeline).
- Keep the FastAPI + React UI as the local control panel — extend with Voice tab, Actions/Approvals tab, Skills tab.

A more detailed proposal is in [06-jarvis-architecture-proposal.md](06-jarvis-architecture-proposal.md).
