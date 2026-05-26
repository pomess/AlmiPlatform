# Roadmap

> Five phases from "no JARVIS" to "JARVIS-as-promised."
> Each phase is independently useful — you get value at the end of every step.

---

## Phase 0 — Foundation (decision phase)

**Goal**: agree on the architecture and the constraints. No code yet.

- [ ] Read all of `docs/`.
- [ ] Answer the questions in [08-decision-points.md](08-decision-points.md).
- [ ] Decide: greenfield repo *or* extend `Obsidian-Knowledge-Graphs`?
- [ ] Decide: hardware target (laptop / Mac mini / Linux box / DGX Spark…).
- [ ] Decide: cloud-first vs local-first vs hybrid LLM.

**Output**: a one-page constraints doc + a green light to start Phase 1.

---

## Phase 1 — MVP text agent on top of the existing memory layer

**Goal**: text-only JARVIS in the existing web UI that can *do things*, not just chat.

- [ ] Stand up a new repo (or branch) that imports the Obsidian-KG project.
- [ ] Add `identity/` directory with `SOUL.md`, `USER.md`, `HEARTBEAT.md`.
- [ ] Wire SOUL.md into the system prompt of every chat / agent call.
- [ ] Install OpenJarvis as the runtime (`uv run jarvis init`, pick the `orchestrator` agent).
- [ ] Wrap the existing memory backend as an **MCP server** exposing `search_wiki`, `get_page`, `ingest_text`, `run_lint`.
- [ ] Connect 3 starter MCP tools: filesystem (scoped to `~/.jarvis/sandbox/`), web fetch (allowlisted), and a simple shell tool (gated by approval).
- [ ] Add an **Approvals** panel to the React UI — modal + audit log view.
- [ ] Build the `policies/actions.yaml` allow/deny/approve config.

**Acceptance**: from the web UI, you can say "summarize my latest meeting note, then save the summary as a new wiki page" and watch it happen with one approval prompt.

---

## Phase 2 — Real-world integrations

**Goal**: agent does the boring useful stuff.

- [ ] Connect **Gmail** (read + draft, never auto-send without approval).
- [ ] Connect **Google Calendar** (read freely, write with approval).
- [ ] Connect **filesystem** (scoped, with file-write approval outside sandbox).
- [ ] Add the **HEARTBEAT.md** scheduler:
  - Every morning at 7:00, generate a *morning digest* (email triage + calendar + open todos), file it as a wiki page, optionally TTS-narrate it.
- [ ] Add `monitor_operative` agent for one specific watch (e.g., "alert me when an email about X arrives").
- [ ] Add **Telegram bridge** so you can chat with JARVIS from your phone.

**Acceptance**: you wake up, your phone shows a Telegram message with a 5-bullet morning digest. Replying "what's on for tomorrow?" works.

---

## Phase 3 — Voice surface

**Goal**: low-latency talk-to-JARVIS.

- [ ] Decide: reuse "de-warp" voice pipeline or build fresh?
- [ ] If fresh: openWakeWord + faster-whisper (STT) + Piper (TTS) locally.
- [ ] Add VAD-based barge-in.
- [ ] Build a small "voice service" that streams audio in/out and talks to the harness over the same API the web UI uses.
- [ ] Add visual feedback in the React UI when voice is active (a "listening" indicator + live transcript).

**Acceptance**: "Hey Jarvis, what's my next meeting?" replies in <2 s, interruptible.

---

## Phase 4 — Hardening & multi-channel

**Goal**: survive being used daily.

- [ ] Move outbound network through a proxy (e.g., Squid) with `policies/network.yaml` allowlist.
- [ ] Containerize the runtime; bind-mount only `~/.jarvis/`.
- [ ] Encrypt secrets at rest; never put them into prompts (credential-stripping pattern).
- [ ] Add iMessage / WhatsApp channel as appropriate.
- [ ] Backup/restore for the vault and identity files (it's git already, just push to a private remote).
- [ ] Lint pass schedules (weekly).
- [ ] Health dashboard (energy use per query, $ cost per query, latency p50/p95).

**Acceptance**: you trust JARVIS with your real Gmail.

---

## Phase 5 — Self-improvement & NemoClaw

**Goal**: it gets better with use, and you can trust it to run unattended.

- [ ] Capture interaction traces locally (OpenJarvis already does this).
- [ ] Run `jarvis optimize skills --policy dspy` periodically; A/B against the current.
- [ ] Optional: small LoRA on local model from your traces (OpenJarvis Learning primitive).
- [ ] When NemoClaw goes stable, wrap the harness in NemoClaw + OpenShell for kernel-level sandboxing.
- [ ] Add multi-stakeholder mode (separate "personal" vs "work" SOULs sharing one vault structure).

**Acceptance**: in a week of normal use, latency drops, costs drop, and you've never had to repeat yourself about the same preference twice.

---

## Stretch — research goals

- Integrate `OpenCrab`-style trajectory distillation: capture corrections, fine-tune a small local model that handles them invisibly next time.
- Multi-agent: a "deep research" agent that runs overnight while a "monitor" agent watches your inbox.
- Custom wake-word ("Jarvis" is taken; pick something more uniquely yours).

---

## Honest scope estimate

| Phase | Scope |
|---|---|
| 0 — Foundation | a sitting-at-a-table conversation |
| 1 — MVP text agent | small but real |
| 2 — Integrations | the longest phase; one integration at a time |
| 3 — Voice | small if "de-warp" is reusable; otherwise medium |
| 4 — Hardening | cross-cutting; touches everything |
| 5 — Self-improvement | research-y, open-ended |

(I'm deliberately not giving time estimates per the project conventions.)
