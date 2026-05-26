# Locked decisions (Phase 0 → Phase 1)

> Answers from Bruno on 2026-04-27. These supersede [08-decision-points.md](08-decision-points.md).

| # | Decision | Locked value |
|---|---|---|
| 1 | Repo strategy | **Independent, greenfield, everything from scratch.** No submodules, no copied modules. `Obsidian-Knowledge-Graphs` and `de-warp` are inspiration only. |
| 2 | Hardware target | **PC now, portable later.** No host-specific code paths. Configure via env vars / config files. |
| 3 | LLM strategy | **Cloud-first** with **`gemini-flash-latest`** alias (Google hot-swaps it; currently resolves to Gemini 3 Flash). **Local fallback** via Ollama + `gemma4:4b`. Single `LLMClient` abstraction. Pin override via `JARVIS_MODEL_OVERRIDE`. |
| 4 | Top capabilities | (1) Email digest, (2) Calendar, (3) Web search, (4) Multi-brain markdown vault access — graph-traversal, wikilink-aware, nuance-preserving (not flat RAG). |
| 5 | Voice / multimodal | Built **from scratch**, `de-warp` only as inspiration. Web push-to-talk first (Phase 3); wake-word desktop later (Phase 4). Camera gestures (MediaPipe Hands) — slim 👍/👎 port in Phase 1, full set in Phase 4. |
| 6 | Identity | All brains visible. User addressed as **"Bruno"**. Principal brain = Bruno's Brain (entry point); hop to other brains via cross-brain wikilinks. |
| 7 | First channels | **CLI** (spawn-and-exit, Phase 1; daemon Phase 4) + **fresh custom web app** (Vite + React + TS, built from scratch). Telegram/iMessage deferred. |
| 8 | Sandbox posture | **Pragmatic**: read silently, ask before send/write/exec, refuse destructive. Editable in `policies/actions.yaml`. |
| 9 | Framework | **LangChain 1.0 + Deep Agents** (on LangGraph). Gives TodoList / Filesystem / SubAgent / Skills / Memory / HumanInTheLoop middleware. |
| 10 | Approval queue | **Stateful, SQLite-backed**, 5-minute default in-session timeout, persists across sessions. |
| 11 | Locale | **Europe/Madrid**. DND **01:00–07:00** (queue silently, drain at 07:00). Morning digest **08:00**. |
| 12 | Vault storage (amended 2026-05-24) | **Postgres-canonical vault** (Supabase). Pages, hot cache, raw, wikilinks, approvals, audit live in tenant-scoped tables under RLS. Markdown is an export format, no longer the source of truth. Phase 1's filesystem vault is superseded; the directory-shaped tenant scoping in commit `cf0da22` is a stepping stone, not the final shape. See ADR in `docs/adr/0001-postgres-vault.md`. |

## Implications for the architecture

- **Zero code reuse.** Every line of code in this repo is written for JARVIS. `Obsidian-Knowledge-Graphs` and `de-warp` inform the *design*, not the implementation.
- **Portability**: every secret, path, and host name lives in config — never hardcoded.
- **Multi-brain**: built fresh. Principal = Bruno's Brain. Cross-brain hops via `[[Deloitte's Brain/some-page]]` wikilinks at key boundary nodes.
- **Gemini Flash**: alias `gemini-flash-latest` for daily, override env `JARVIS_MODEL_OVERRIDE=gemini-3-flash-preview` to pin during demos.
- **Gemma 4 (4B)** via Ollama for private/offline fallback (health, finance, intimate context).
- **Voice + gesture**: `services/perception/` (Phase 3+). Web push-to-talk first; gestures slim (👍 approve / 👎 deny) in Phase 1, full 7-gesture set Phase 4.
- **CLI**: spawn-and-exit Python (`jarvis ask|status|approvals|brains|switch`). Reads approvals SQLite directly; POSTs approve/deny to harness REST so the paused agent can resume.
- **Web**: fresh Vite + React + TypeScript app under `apps/web/`.
- **Vault**: rows in Supabase Postgres, RLS scoped by `tenant_id` from the verified JWT. Markdown export remains available via a `kairos vault export` command for Obsidian-style local browsing, but the running system reads/writes Postgres. Approval queue and audit log move to Postgres alongside the vault.
