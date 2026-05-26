# OpenJarvis (Stanford)

> **The local-first personal AI stack.** Apache 2.0, 3.2K stars, 694 forks.
> Built at **Stanford SAIL — Hazy Research + Scaling Intelligence Lab**.
> Authors: Saad-Falcon, Narayan, Shandilya, Akengin, Manihani, Bo, Hennessy, Christopher Ré, Mirhoseini.
> Repo: [`github.com/open-jarvis/OpenJarvis`](https://github.com/open-jarvis/OpenJarvis) · Project page: <https://scalingintelligence.stanford.edu/blogs/openjarvis/>

> **Important**: Despite the name, OpenJarvis is *not* trying to be JARVIS-the-product. It's the **runtime/research framework** that makes building one practical. Think "PyTorch for personal AI agents."

## The thesis

From the paper:
> *"Local language models already handle 88.7% of single-turn chat and reasoning queries… intelligence efficiency improving 5.3× from 2023 to 2025. The models and hardware are ready. **What has been missing is the software stack.**"*

OpenClaw runs on cloud APIs by default. OpenJarvis is the answer to "what if the brain ran on your laptop?"

## The five primitives

OpenJarvis is structured as five composable primitives — each can be benchmarked, swapped, or optimized independently.

```
┌────────────────────────────────────────────────────┐
│   1. Intelligence  — on-device language models     │
│      (Qwen, GPT-OSS, Gemma, Granite, GLM, Kimi…)   │
├────────────────────────────────────────────────────┤
│   2. Engine        — hardware-aware inference      │
│      (Ollama, vLLM, SGLang, llama.cpp,             │
│       Apple FM, Exo, Nexa, Mirai Uzu, cloud)       │
├────────────────────────────────────────────────────┤
│   3. Agents        — composable reasoning          │
│      (ReAct, OpenHands/CodeAct,                    │
│       Orchestrator, Operative, simple)             │
├────────────────────────────────────────────────────┤
│   4. Tools & Memory — grounding to the real world  │
│      (MCP, Google A2A, semantic indexing,          │
│       26+ messaging channels, webhooks)            │
├────────────────────────────────────────────────────┤
│   5. Learning      — self-improving systems        │
│      (DSPy, GEPA, SFT, GRPO, DPO,                  │
│       LoRA, bandit routing)                        │
└────────────────────────────────────────────────────┘
```

### 1. Intelligence
A unified model catalog over a fast-moving ecosystem. You declare *capability*, OpenJarvis picks the model that fits your hardware. `jarvis init` auto-detects.

### 2. Engine
The most fragmented layer in local AI. OpenJarvis provides one interface over 8+ inference backends. `jarvis doctor` keeps the setup healthy.

### 3. Agents
Built-in agent roles:
- `simple` — single-turn chat, no tools.
- `native_react` — Thought-Action-Observation loop.
- `native_openhands` (CodeAct) — generates and runs Python.
- `orchestrator` — decomposes tasks, delegates to sub-agents.
- `operative` — persistent autonomous agent with state.
- `monitor_operative` — long-horizon monitoring with memory compression.
- `deep_research` — multi-hop research with citations across web + local docs.
- `morning_digest` — scheduled daily briefing from email/calendar/health/news, with TTS.

### 4. Tools & Memory
- **MCP** (Model Context Protocol) for tool use.
- **Google A2A** for agent-to-agent communication.
- **Semantic index** for local retrieval over papers/notes.
- **26+ channels**: iMessage, Telegram, WhatsApp, Slack, Discord, web, webhooks…
- **Skills system** — can import directly from **OpenClaw's ~13,700-skill catalog** *and* from Hermes Agent (~150 skills).

### 5. Learning
Closed-loop optimization across four layers:
- Model weights (SFT, GRPO, DPO, LoRA)
- LM prompts (DSPy)
- Agentic logic (GEPA)
- Inference engine (quantization, batching, kernels)

All driven by *local trace data* — your interactions become training signal without leaving your device.

## Efficiency as a first-class metric

OpenJarvis tracks **energy, FLOPs, latency, and dollar cost** alongside accuracy. Hardware-agnostic telemetry: NVIDIA via NVML, AMD natively, Apple Silicon via `powermetrics`. Sampling at 50 ms intervals. There's a leaderboard and an "ENERGY" prize (Mac mini giveaway promotion).

This is unique. Nobody else in the agent-framework space treats wattage as a first-class metric.

## Install & quickstart

Prereqs: Python 3.10+, `uv`, Rust, Git, plus a local inference backend.

```bash
git clone https://github.com/open-jarvis/OpenJarvis.git
cd OpenJarvis
uv sync                     # core
uv sync --extra server      # + FastAPI server

# Detect hardware, recommend engine
uv run jarvis init

# (in another shell)
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull qwen3.5:4b      # CPU-friendly default

uv run jarvis ask "What is the capital of France?"
```

### Starter presets — install with one command

```bash
jarvis init --preset morning-digest-mac        # daily spoken briefing
jarvis init --preset morning-digest-linux      # GPU server version
jarvis init --preset morning-digest-minimal    # Gmail+Cal only, any machine
jarvis init --preset deep-research             # multi-hop research w/ citations
jarvis init --preset code-assistant            # code exec + file I/O + shell
jarvis init --preset scheduled-monitor         # stateful scheduled agent
jarvis init --preset chat-simple               # lightweight chat
```

The `morning-digest` preset is the most JARVIS-like out of the box.

### Skills

```bash
jarvis skill install hermes:arxiv
jarvis skill sync hermes --category research
jarvis ask "Use the code-explainer skill to explain this code: …"
jarvis optimize skills --policy dspy
jarvis bench skills --max-samples 5 --seeds 42
```

Skills follow the [`agentskills.io`](https://agentskills.io/specification) open standard.

## Surfaces

- **CLI**: `jarvis ask`, `jarvis chat`, `jarvis digest`.
- **Web dashboard** with built-in webchat + energy/cost dashboards.
- **Tauri desktop app** (macOS / Linux / Windows).
- **26+ messaging channels** (iMessage, Telegram, etc.).

## Strengths (for our use case)

1. **Local-first by design** — exactly what we want for privacy.
2. **Already imports OpenClaw skills** — no need to choose.
3. **MCP-native** — interoperates with Claude Code, Cursor, Codex out of the box.
4. **Real research lab behind it** — Stanford / Christopher Ré. Not a hobby project.
5. **Engine abstraction is genuinely useful** — solves a real fragmentation problem.
6. **Learning loop is unique** — closes the gap between "use" and "improve" without sending data to the cloud.

## Weaknesses

- **Younger** than OpenClaw (3.2K stars vs 300K). Smaller ecosystem of integrations *outside* what's imported from OpenClaw.
- **No equivalent of `SOUL.md`** — identity layer is weaker.
- **Voice is partial.** TTS for digest, but not a wake-word always-listening voice agent.
- **Memory primitive is "semantic index"** — useful, but our Obsidian KG project's structured-wiki memory is *better* for personal context.

## Where it slots into our build

OpenJarvis is the strongest candidate for the **runtime layer** of our system:

- ✅ Engine + Agents primitives — let it pick the model and run the agent loop.
- ✅ Tools (MCP) primitive — give it tool access.
- 🔁 Memory primitive — replace its semantic index with **our Obsidian KG / wiki layer** as the memory backend (or run both side by side).
- ➕ Add SOUL.md / HEARTBEAT.md harness on top, OpenClaw-style.
- ➕ Add voice pipeline on top.

## Sources

- Project page: <https://scalingintelligence.stanford.edu/blogs/openjarvis/>
- Repo: <https://github.com/open-jarvis/OpenJarvis>
- Docs: <https://open-jarvis.github.io/OpenJarvis/>
- Citation: Saad-Falcon et al., *OpenJarvis: Personal AI, On Personal Devices*, 2026.
- Underlying research: *Intelligence Per Watt* — <https://www.intelligence-per-watt.ai/>, arXiv:2511.07885.
