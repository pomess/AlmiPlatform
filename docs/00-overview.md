# Personal AI / "JARVIS" — Research Overview

> Goal: build the closest possible thing to **JARVIS** — a long-running, voice-and-text personal AI that knows you, remembers things, and *takes actions* on your behalf (email, calendar, files, browser, smart home, code, messaging…).
> This `docs/` folder is the research dossier. Read these in order:

| # | File | Purpose |
|---|------|---------|
| 00 | [00-overview.md](00-overview.md) | This file. North-star goal, design principles, summary of options. |
| 01 | [01-openclaw.md](01-openclaw.md) | OpenClaw — the de-facto open-source JARVIS framework (Peter Steinberger). |
| 02 | [02-nemoclaw.md](02-nemoclaw.md) | NVIDIA NemoClaw — security/sandbox layer for OpenClaw. |
| 03 | [03-openjarvis-stanford.md](03-openjarvis-stanford.md) | Stanford OpenJarvis — local-first agent stack (Hazy / Scaling Intelligence Lab). |
| 04 | [04-karpathy-llm-wiki.md](04-karpathy-llm-wiki.md) | Karpathy's Obsidian + LLM Wiki pattern (the "second brain"). |
| 05 | [05-existing-project-audit.md](05-existing-project-audit.md) | Audit of the existing `Obsidian-Knowledge-Graphs` project — what to reuse. |
| 06 | [06-jarvis-architecture-proposal.md](06-jarvis-architecture-proposal.md) | Proposed architecture for our system, combining all of the above. |
| 07 | [07-roadmap.md](07-roadmap.md) | Phased roadmap from MVP voice agent to full JARVIS. |
| 08 | [08-decision-points.md](08-decision-points.md) | Open decisions that need your input before we start building. |

---

## What "JARVIS-like" actually means in 2026

Tony Stark's JARVIS, distilled into engineering primitives:

1. **Always-on**, persistent process — survives reboots, remembers across sessions.
2. **Voice-native** — wake word, low-latency STT/TTS, can be interrupted mid-sentence.
3. **Agentic** — not a chatbot. It uses tools, takes multi-step actions, and reports back.
4. **Knows you** — has a persistent identity for *you* (preferences, calendar, files, projects, people you talk to).
5. **Has a "soul"** — a stable identity for *itself* (personality, values, operating principles) that doesn't drift.
6. **Multi-surface** — desktop, phone, messaging (Telegram/WhatsApp/iMessage), maybe a wearable.
7. **Action-capable** — can read/send email, create calendar events, control devices, browse the web, run code, edit files.
8. **Sandboxed** — should not be able to wipe your disk because it hallucinated `rm -rf /`.
9. **Local-first** — your most personal data should not have to leave your machine.

No single open-source project nails all 9 yet. But three projects collectively cover ~95% of the surface area, and our existing Obsidian project covers a 10th critical capability the others lack: **structured long-term memory**.

---

## The four pillars we're combining

```
                        ┌─────────────────────────────────┐
                        │            JARVIS               │
                        │    (our personal AI system)     │
                        └────────────────┬────────────────┘
                                         │
        ┌──────────────────┬─────────────┼─────────────┬──────────────────┐
        ▼                  ▼             ▼             ▼                  ▼
   ┌─────────┐       ┌──────────┐  ┌──────────┐  ┌──────────┐      ┌────────────┐
   │OpenClaw │       │NemoClaw  │  │OpenJarvis│  │ Karpathy │      │ Our existing│
   │         │       │ (NVIDIA) │  │(Stanford)│  │ LLM Wiki │      │  Obsidian   │
   │ Action  │       │ Security │  │ Local    │  │ Memory   │      │  KG project │
   │ engine  │       │ sandbox  │  │ runtime  │  │ pattern  │      │ (impl. of  │
   │         │       │          │  │          │  │          │      │  Karpathy) │
   └─────────┘       └──────────┘  └──────────┘  └──────────┘      └────────────┘
        │                  │             │             │                  │
   "Take actions"     "Don't blow      "Run the      "Remember         "We already
   email/calendar/    up the host"    LLM on YOUR    everything,        built this.
   shell/browser                       hardware"     don't relearn"     Reuse it."
```

### TL;DR of each
- **OpenClaw**: the *body* — gives the agent hands (tools, integrations, messaging surfaces).
- **NemoClaw**: the *immune system* — kernel-level sandbox so the body can't hurt you.
- **OpenJarvis**: the *nervous system* — local model serving, agent loop, hardware-aware engine selection, Tools & Memory primitives (MCP, A2A).
- **Karpathy LLM Wiki + our project**: the *brain / memory* — persistent, structured, queryable knowledge of you and your world.

---

## Design principles for our build

1. **Local-first, cloud-optional.** Frontier model only when local can't handle it.
2. **Markdown is the database.** Per Karpathy: structured `.md` files in a git repo. No vector-DB lock-in.
3. **Files are the soul.** `SOUL.md`, `USER.md`, `HEARTBEAT.md`, `MEMORY.md` — identity persists across sessions because it lives on disk.
4. **Default-deny.** Every action a tool can take is blocked unless explicitly approved (NemoClaw model).
5. **Voice is a UI, not a feature.** Bolt voice on top of a strong text agent, don't build the voice agent first.
6. **Reuse > rewrite.** Our Obsidian KG project is already 60–80% of the memory layer.
7. **One brain, many surfaces.** Same agent reachable from VS Code, Telegram, web UI, eventually voice.

---

## Quick comparison

| Capability | OpenClaw | NemoClaw | OpenJarvis | Our Obsidian KG | Karpathy pattern |
|---|---|---|---|---|---|
| Tool/action execution | ✅ core | (wraps OC) | ✅ via MCP | ❌ | ❌ |
| Voice I/O | partial | (inherits) | partial | ❌ | ❌ |
| Local LLM | via Ollama | ✅ Nemotron | ✅ first-class | ❌ (Gemini API) | n/a |
| Sandboxing | weak | ✅ kernel-level | weak | n/a | n/a |
| Persistent memory | file-based | (inherits) | semantic + traces | ✅ structured wiki | ✅ pattern |
| Multi-channel | ✅ TG/Discord/WA | (inherits) | ✅ 26+ channels | web UI only | n/a |
| Identity / "soul" | ✅ SOUL.md | (inherits) | weak | weak | weak |
| Skill ecosystem | ✅ ~13,700 skills | (inherits) | ✅ imports OC | ❌ | n/a |
| Self-improvement | weak | weak | ✅ DSPy/GRPO loop | ❌ | ❌ |

---

## The recommended composition (preview of doc 06)

```
┌─────────────────── JARVIS ───────────────────┐
│                                              │
│  Voice surface    ←→  TTS / STT (later)      │
│  Text surfaces    ←→  Telegram, web, VS Code │
│                                              │
│  ──── OpenClaw harness ────                  │
│  Skills, channels, SOUL.md, HEARTBEAT.md     │
│                                              │
│  ──── OpenJarvis runtime ────                │
│  Engine (Ollama/vLLM), Agents (Orchestrator),│
│  Tools (MCP), Memory (semantic index)        │
│                                              │
│  ──── Memory layer = our Obsidian KG ────    │
│  raw/  wiki/  index.md  hot.md  log.md       │
│  multi-brain registry, lint, ingest, graph   │
│                                              │
│  ──── NemoClaw sandbox (when ready) ────     │
│  Landlock + seccomp + netns +                │
│  default-deny egress + approval TUI          │
│                                              │
└──────────────────────────────────────────────┘
```

Read the linked docs in order, then look at [08-decision-points.md](08-decision-points.md) for the questions I need answered before we start coding.
