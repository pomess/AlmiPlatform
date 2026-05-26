# Decisions I need from you before we start coding

> Please answer these (informally is fine — a sentence each) and we'll lock the architecture and start Phase 1 from [07-roadmap.md](07-roadmap.md).

---

## 1. Foundation: greenfield or extend the existing project?

**Option A — Extend `Obsidian-Knowledge-Graphs`.**
Keep working in that repo, evolve it into JARVIS. Adds branches/folders for `identity/`, `services/runtime/`, etc.
*Pro*: no migration cost, your work continues.
*Con*: the repo accumulates concerns; "JARVIS" will share a git history with the original KG project.

**Option B — Greenfield in this `Personal AI/` workspace, pull the KG project in as a git submodule (or copy the relevant modules).**
*Pro*: clean separation, room to grow, the KG project stays a focused tool.
*Con*: small migration tax up front.

**My recommendation: B**, with the existing project pulled in as a submodule under `services/memory/`. But your call.

---

## 2. Hardware target

Where will JARVIS live?

- [ ] **Your daily driver laptop** — fine for development, fine for cloud-LLM mode, marginal for local LLMs.
- [ ] **A dedicated Mac mini** — ideal. M-series silicon runs Qwen3.5/GPT-OSS well via Apple FM / MLX.
- [ ] **A Linux box / NUC / homelab** — best for running 24/7 with cron heartbeats.
- [ ] **DGX Spark or similar** — overkill but works, also unlocks NemoClaw.
- [ ] **None yet, decide later** — start cloud-only and pick hardware in Phase 4.

Knowing this changes the OpenJarvis Engine choice (Apple FM vs Ollama vs vLLM) and whether Phase 4 includes "buy a Mac mini."

---

## 3. LLM strategy

Pick one starting position:

- [ ] **Cloud-first** (Gemini 2.5 Flash like the existing project). Cheapest path, fastest. Privacy is "trust Google."
- [ ] **Hybrid** (default to Gemini/Claude; fall back to local for sensitive content; OpenJarvis Privacy Router style). Most pragmatic.
- [ ] **Local-first** (Qwen3.5 via Ollama; cloud only when local fails). Most aligned with the OpenJarvis thesis. Slowest. Best privacy.

**My recommendation: Hybrid**, with the local model coming online in Phase 2 or 3 once you have hardware decided.

---

## 4. Priority capabilities

Rank or pick top 3 — I'll sequence Phase 2 around your priorities.

- [ ] **Email triage & morning digest** (Gmail read + classify + summary)
- [ ] **Calendar assistant** (read + write events with approval)
- [ ] **File / project assistant** (work with files in `~/Documents`, code repos, etc.)
- [ ] **Web research** (multi-hop, with citations into the wiki)
- [ ] **Smart home / lifestyle** (Hue, Spotify, Home Assistant)
- [ ] **Code companion** (the OpenJarvis `code-assistant` preset)
- [ ] **Messaging bridge** (Telegram first; iMessage/WhatsApp later)
- [ ] **Voice in/out** (Phase 3 anyway, but how high a priority?)
- [ ] **Other**: ___________________________________

---

## 5. The "de-warp" voice pipeline

You mentioned a separate project already does <500 ms voice with Gemini + LangChain Deep Agents.

- [ ] It's reusable, please plug it into JARVIS in Phase 3.
- [ ] It's reusable but I'd rather build a fresh local-first one.
- [ ] It's not really reusable — start fresh.
- [ ] Doesn't exist / I misremembered.

If reusable, point me at the repo and I'll plan the integration.

---

## 6. Identity — what should JARVIS *be*?

This drives `SOUL.md`. Some prompts:

- A name?  ("Jarvis" is fine, but it's identifiable / generic — something more uniquely yours, like a wake word, may be better.)
- Voice? (calm/butler-ish, casual peer, Spanish/English/other, etc.)
- Hard refusals? (e.g., never spend money, never message certain contacts, never act when unsure.)
- Ownership: is this strictly personal, or also a "work brain" that knows about Deloitte work? (You already have two brains in the existing project — does JARVIS see both?)

A 5-line answer is enough; we'll co-evolve `SOUL.md` from there.

---

## 7. Channels — Telegram first, or something else?

- [ ] Telegram (recommended — easiest bot API, works everywhere)
- [ ] iMessage (macOS-only, but most-natural-feeling on iPhone; needs `mac_imessage` bridge)
- [ ] WhatsApp Business (most useful, hardest to set up legally)
- [ ] Discord
- [ ] Just the web UI for now; messaging in Phase 4

---

## 8. Sandboxing posture

How paranoid?

- [ ] **Strict**: every tool call goes through approval until I say otherwise.
- [ ] **Pragmatic** (default-deny network, but read-only operations on the wiki / files run silently). ← my recommendation.
- [ ] **Loose**: trust by default, audit log everything, only approve money-spending or message-sending.

This sets the initial `policies/actions.yaml`.

---

## 9. Anything I missed?

Constraints, weird preferences, things that worked or failed in past attempts at this — drop them here.

---

## When you've answered these

Reply in this chat (informal bullets are perfect) and I'll:
1. Update `docs/00-overview.md` with the locked decisions.
2. Create the new repo structure (or extend the existing one, per your choice).
3. Start Phase 1 from [07-roadmap.md](07-roadmap.md): identity files + MCP-wrap the memory layer + add the Approvals panel.

Then we build.
