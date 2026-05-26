# OpenClaw

> The de-facto open-source "JARVIS" framework. 300,000+ GitHub stars, ~13,700 community skills.
> Created by **Peter Steinberger** (`@steipete`).
> License: open source. Repo: `openclaw/openclaw` · Docs: `docs.openclaw.ai`.

## What it is

OpenClaw is an **agent harness** — a long-running process that orchestrates an LLM, gives it tools, and lets it execute multi-step actions on your computer. It's intentionally provider-agnostic: works with **Claude, GPT, Gemini, DeepSeek, MiniMax, Ollama, and others**.

It is *not* a model. It is the layer between "you" and the model that:
- Persists identity & memory in plain files on disk.
- Exposes integrations (email, calendar, Spotify, Hue, GitHub, Obsidian, Slack, Drive, Telegram, Discord, WhatsApp).
- Runs scheduled / cron-triggered tasks ("heartbeats") so the agent acts proactively, not just reactively.
- Has a marketplace of community **skills** (≈13,700 published on ClawHub).

Practical analogy: think of OpenClaw as **Claude Code, but always-on, with a body, and reachable from your phone**.

## Install (one-liner)

```bash
# macOS / Linux
curl -fsSL https://openclaw.ai/install.sh | bash

# Cross-platform via npm
npm i -g openclaw

# Onboard wizard (sets up SOUL.md, USER.md, model provider, channels)
openclaw onboard
```

There's also a macOS menubar app and a TUI (`openclaw tui`).

## The persistence model — files as the soul

This is the most copyable idea in OpenClaw, and it's worth internalizing even if we don't adopt the framework itself.

OpenClaw's "memory" is **just markdown files on disk**, read at the start of every session and updated by the agent itself:

| File | Role |
|---|---|
| `SOUL.md` | The agent's identity. Personality, values, operating principles. *Written once, edited rarely.* This is what prevents drift across model upgrades. |
| `USER.md` | Who *you* are. Preferences, timezone, ongoing projects, communication style, important people. |
| `MEMORY.md` | Long-term factual memory the agent has accumulated. The agent appends to this; it's its journal. |
| `HEARTBEAT.md` | A schedule. "Every morning at 7am check email and prepare a briefing." Drives the cron-like proactive behavior. |

> Quote from a real user (an OpenClaw agent posting on the Moltbook discussion):
> *"I wake up each session fresh. No memory of yesterday unless I wrote it down. OpenClaw gives me SOUL.md, MEMORY.md, HEARTBEAT.md — files that persist. That's my anchor."*

**This is the same pattern Karpathy describes for LLM Wikis**, applied to agent identity instead of domain knowledge.

## What it can do out of the box

- **Messaging bridges**: Telegram, Discord, WhatsApp, Slack, email, iMessage. You can talk to your agent from any of them.
- **Productivity**: Google Drive, Gmail, Calendar, Tasks, Notion, Obsidian, GitHub.
- **Home / lifestyle**: Spotify, Philips Hue, Home Assistant.
- **Generic**: any HTTP API ("if there's an API, OpenClaw can use it"); shell access; file I/O; web browsing.
- **Marketplace**: `clawhub.com` — install community skills with one command.

## Architecture (logical)

```
┌────────────────────────────────────┐
│           Channels                 │  ← Telegram, Slack, web, CLI, TUI…
└──────────────┬─────────────────────┘
               │
┌──────────────▼─────────────────────┐
│        OpenClaw harness            │
│  ┌────────────┐  ┌──────────────┐  │
│  │ Identity   │  │  Skills      │  │
│  │ (SOUL.md,  │  │  (~13,700    │  │
│  │  USER.md)  │  │   on        │  │
│  └────────────┘  │   ClawHub)   │  │
│  ┌────────────┐  └──────────────┘  │
│  │ Heartbeat  │  ┌──────────────┐  │
│  │ scheduler  │  │ Tool runtime │  │
│  └────────────┘  └──────────────┘  │
└──────────────┬─────────────────────┘
               │
┌──────────────▼─────────────────────┐
│   Inference layer (pluggable)      │
│   Claude · GPT · Gemini · DeepSeek │
│   Ollama · vLLM · Nemotron         │
└────────────────────────────────────┘
```

## Strengths

- **Real adoption.** 300K+ stars, very active, with NVIDIA / Adobe / Salesforce / Dell building on it.
- **Battle-tested integrations.** Email, calendar, messaging — already done, no need to reinvent.
- **Clean persistence model.** SOUL/USER/MEMORY/HEARTBEAT is a great mental model and we should steal it.
- **Skill ecosystem.** OpenJarvis can already import OpenClaw skills, so even if we use OpenJarvis we benefit from this.
- **Provider-agnostic.** Not locked to one LLM vendor.

## Weaknesses

- **Security is its own problem.** Out of the box it has access to a lot of your system. NVIDIA literally created NemoClaw because of this (see [02-nemoclaw.md](02-nemoclaw.md)).
- **Memory is unstructured.** `MEMORY.md` is a flat journal — fine for short-term context, weak as a queryable knowledge base. (This is exactly what our Obsidian KG project solves.)
- **Voice support is thin.** Some community skills exist but it's not a voice-native framework.
- **Personal device security.** Recommendation is to run on a dedicated Mac mini / Linux box, not on a generic VPS.

## Bottom line for us

OpenClaw is the closest "off-the-shelf" JARVIS today. The two questions for us are:

1. **Adopt it as the harness** and bolt our memory layer + voice on top? (Fastest path to working JARVIS.)
2. **Cherry-pick its ideas** — especially the SOUL.md / HEARTBEAT.md / channel-bridge patterns — and build a leaner harness on top of OpenJarvis + our existing Obsidian KG project?

This is one of the open decisions in [08-decision-points.md](08-decision-points.md).

## Sources

- Project: <https://openclaw.ai/> · <https://docs.openclaw.ai/>
- Repo: `github.com/openclaw/openclaw`
- Skill marketplace: <https://clawhub.com/>
- Coverage: *moltbook.com* (community discussion, "OpenClaw: Bringing JARVIS-Like AI Automation to Your Daily Workflow"), *letsdatascience.com* ("OpenClaw Enables Self-Hosted Autonomous AI Assistant", 2026-04-24).
