# JARVIS — Proposed Architecture

> A composition of:
> - **OpenJarvis** (Stanford) — runtime: engine, agents, tools (MCP), local-first inference.
> - **OpenClaw patterns** — identity files, channels, heartbeat scheduler.
> - **NemoClaw patterns** — default-deny, approval gates, credential stripping (run NemoClaw later when stable).
> - **Karpathy LLM Wiki pattern** — already implemented in our existing `Obsidian-Knowledge-Graphs` project. Reuse.
> - **Bruno's "de-warp"** voice pipeline (if available) for low-latency STT/TTS.

---

## Big picture

```
                          ┌──────────────────────────┐
                          │           YOU            │
                          └────┬───────────┬────┬────┘
                               │           │    │
                  ┌────────────┘   ┌───────┘    └─────────┐
                  ▼                ▼                      ▼
            ┌──────────┐    ┌─────────────┐        ┌────────────┐
            │  Voice   │    │  Web UI     │        │ Messaging  │
            │ (wake +  │    │ (the React  │        │ (Telegram, │
            │  STT/TTS)│    │  app, ext.) │        │  WhatsApp, │
            └────┬─────┘    └──────┬──────┘        │  iMessage) │
                 │                 │                └─────┬──────┘
                 └─────────┬───────┴────────────┬─────────┘
                           │                    │
                           ▼                    ▼
                  ┌────────────────────────────────────┐
                  │       Channel Router / API         │
                  │           (FastAPI + SSE)          │
                  └─────────────────┬──────────────────┘
                                    │
                  ┌─────────────────▼──────────────────┐
                  │         JARVIS Harness             │
                  │  ┌──────────────────────────────┐  │
                  │  │ Identity                     │  │
                  │  │  SOUL.md · USER.md           │  │
                  │  │  HEARTBEAT.md (scheduler)    │  │
                  │  └──────────────────────────────┘  │
                  │  ┌──────────────────────────────┐  │
                  │  │ Approval gate                │  │
                  │  │  default-deny actions        │  │
                  │  │  TUI/UI prompts for risky    │  │
                  │  │  ops (email, money, delete)  │  │
                  │  └──────────────────────────────┘  │
                  └─────────────────┬──────────────────┘
                                    │
                  ┌─────────────────▼──────────────────┐
                  │     OpenJarvis runtime             │
                  │  Intelligence │ Engine │ Agents    │
                  │  Tools (MCP)  │ Memory │ Learning  │
                  └─┬───────────────┬───────────────┬──┘
                    │               │               │
       ┌────────────▼──┐  ┌─────────▼──────┐  ┌─────▼────────┐
       │ Inference     │  │ Tools (MCP)    │  │ Memory       │
       │  Local: Ollama│  │ - Gmail/Cal    │  │ ┌──────────┐ │
       │  /vLLM/Apple  │  │ - Filesystem   │  │ │ Our      │ │
       │  Cloud:       │  │ - Shell (gated)│  │ │ Obsidian │ │
       │   Gemini/Claude│  │ - Browser     │  │ │  KG      │ │
       │  /GPT-OSS     │  │ - Skills       │  │ │  project │ │
       │               │  │   (~13.7K from │  │ │  (reuse!) │ │
       │               │  │    OpenClaw)   │  │ └──────────┘ │
       └───────────────┘  └────────────────┘  └──────────────┘
                                    │
                             (later, when stable)
                  ┌─────────────────▼──────────────────┐
                  │      NemoClaw / OpenShell          │
                  │  Landlock + seccomp + netns        │
                  │  default-deny egress               │
                  └────────────────────────────────────┘
```

---

## Component-by-component

### 1. Memory layer — **reuse our Obsidian-KG project**

No new code needed for v0. The existing project handles:
- Karpathy three-layer vault (`raw/` / `wiki/` / `AGENTS.md`).
- `index.md`, `log.md`, `hot.md`.
- Multi-brain support (BrainRegistry).
- Web UI for chat, wiki browser, graph, ingest, lint.

**Mod**: expose it as an **MCP server** so OpenJarvis (and Claude Code, Cursor, etc.) can query it as a native tool. This is straightforward — wrap the existing FastAPI endpoints in MCP tool definitions:

```
mcp tools: search_wiki, get_page, get_graph, ingest_text, run_lint
```

Then any LLM agent — including JARVIS itself — can use the wiki as part of its toolbox.

### 2. Runtime layer — **OpenJarvis**

Use OpenJarvis as the agent runtime:
- `jarvis init` to detect hardware and pick an engine.
- Use the **`orchestrator`** built-in agent for multi-step tasks; **`monitor_operative`** for long-running watchers; **`morning_digest`** for the spoken daily briefing.
- Skills: pull a curated subset from the OpenClaw catalog (`jarvis skill install`).
- MCP tools: register our memory layer, plus standard ones (filesystem, web fetch, shell).

### 3. Identity layer — **OpenClaw pattern**, our implementation

Add a top-level harness directory:

```
~/.jarvis/
├── identity/
│   ├── SOUL.md         ← agent's personality, values, operating principles
│   ├── USER.md         ← Bruno's preferences, timezone, projects, people
│   ├── MEMORY.md       ← agent's working journal (LLM-maintained)
│   └── HEARTBEAT.md    ← cron-like schedule for proactive tasks
├── vaults/             ← memory layer (Obsidian-KG vaults)
│   ├── personal/
│   └── work/
├── policies/
│   ├── network.yaml    ← allowlist of outbound hosts
│   ├── actions.yaml    ← which tool calls require approval
│   └── secrets.env     ← API keys (never seen by the LLM)
└── logs/
    └── audit.jsonl     ← every tool call, every approval decision
```

`SOUL.md` is the most important file. Write it once, edit rarely. Defines:
- Name, voice, style.
- Values and refusal conditions.
- Operating principles (e.g., "always confirm before sending email", "never spend money without explicit approval").

This file becomes the system prompt prefix on every invocation. **It's what prevents drift across model upgrades.**

### 4. Voice surface — **reuse "de-warp" pipeline (if usable)**

If your existing voice agent gives <500 ms latency with Gemini, use it as the front-end. The voice service speaks to the JARVIS harness over the same FastAPI endpoints the React UI uses.

If it's not reusable, the MVP voice stack is:
- **Wake word**: `openWakeWord` (open source, runs on CPU).
- **STT**: `whisper.cpp` or `faster-whisper` locally; `Deepgram` cloud as fallback.
- **TTS**: `Piper` (local, fast) or `ElevenLabs` (cloud, better quality).
- **Barge-in / interruption**: VAD + cancel-and-resume on the LLM stream.

### 5. Channels — **OpenClaw-style bridges**

Start with **one** channel to keep complexity down: **Telegram**. It's the easiest, has a clean bot API, and works from anywhere.

Add later in priority order: web UI (already built), iMessage (macOS only), WhatsApp Business, Discord.

### 6. Approval gate — **NemoClaw pattern, lightweight version**

We probably don't run NemoClaw itself yet (alpha, Linux-primary, 8 GB sandbox image). But adopt the concept:

```yaml
# policies/actions.yaml
default: deny

allow_silently:
  - read_file
  - search_wiki
  - http_get        # to allowlist hosts only
  - run_lint

require_approval:
  - send_email
  - send_message
  - create_calendar_event
  - shell_command
  - file_write       # outside ~/.jarvis/sandbox/
  - http_post

never:
  - rm -rf
  - format
  - curl piped to bash
```

Approval prompts surface in:
- The web UI (a banner / modal).
- Telegram (inline keyboard "approve / deny / explain").
- Voice ("I want to send an email to X. Should I?").

Every decision logged to `audit.jsonl` with rationale.

### 7. Sandboxing — **defer to NemoClaw v1.0**

Don't build a kernel-level sandbox. NemoClaw will. Until then:
- Run the agent process with `firejail` or a Docker container with the workspace bind-mounted.
- Filesystem-scope to `~/.jarvis/sandbox/`.
- Outbound network via a Squid proxy with the allowlist.

When NemoClaw stabilizes, swap in.

---

## What lives where (file layout for the new repo)

```
Personal AI/
├── docs/                       ← THIS folder (research)
├── identity/                   ← SOUL.md, USER.md, HEARTBEAT.md
├── vaults/                     ← memory (existing Obsidian-KG project)
│   └── …
├── services/
│   ├── memory/                 ← FastAPI from existing project, exposed as MCP
│   ├── runtime/                ← OpenJarvis config, presets, skills
│   ├── voice/                  ← STT/TTS pipeline (or reuse de-warp)
│   ├── channels/
│   │   ├── telegram/
│   │   ├── web/                ← existing React app, extended
│   │   └── …
│   └── harness/                ← scheduler, approval gate, audit log
├── policies/                   ← network.yaml, actions.yaml
├── skills/                     ← curated/custom skills (OpenJarvis spec)
└── scripts/                    ← install, onboard, doctor
```

---

## Why this composition (and not just install OpenClaw)

| Want | Could we get from OpenClaw alone? | What our composition adds |
|---|---|---|
| Take actions on email/cal/files | ✅ yes | same |
| Local LLM by default | ⚠️ partial via Ollama | OpenJarvis's hardware-aware engine selection + 8 backends |
| Structured personal knowledge | ❌ MEMORY.md is flat | Our Obsidian-KG (Karpathy-pattern wiki, graph, queries) |
| Self-improving from traces | ❌ none | OpenJarvis's Learning primitive (DSPy, GRPO) |
| Already-built UI we like | ❌ TUI/menubar only | Our React app |
| Voice with sub-second latency | ❌ thin | Bruno's de-warp pipeline |
| Provider-agnostic | ✅ yes | OpenJarvis is also provider-agnostic; we get cloud failover |

The downside of the composition is **integration work**. Pure OpenClaw would be working in an afternoon; ours is more like 4–6 weeks to MVP. But the result is a system that is *ours*, runs on our hardware, learns from our use, and slots into existing assets.

---

## Risks & open questions

- **Maintenance burden** of OpenJarvis (alpha-ish, fast-moving research framework).
- **NemoClaw is alpha** — security model is solid but we'd be on the bleeding edge.
- **Voice barge-in** is hard to get right; a mediocre voice UI is worse than none.
- **OpenJarvis vs OpenClaw skills compatibility** — claimed to work, needs verification.
- **Multi-brain conflict** — does JARVIS pull from one vault or all of them by default?

These get resolved in [08-decision-points.md](08-decision-points.md).

---

## Next: see [07-roadmap.md](07-roadmap.md) for phasing, and [08-decision-points.md](08-decision-points.md) for what I need from you to start.
