# Kairos — orientation for Claude

This file is loaded into context every session. Read it before touching code or copy.

## What Kairos is

A long-running personal AI cockpit for **one user (Bruno)**, being commercialized as a **per-client AI workspace for fractional CFOs**. Three independent services, markdown-backed memory, an approval gate on every mutating tool. Not a chatbot — closer to a chief of staff.

- **Internal name (legacy):** JARVIS. **External / product name:** Kairos.
- **Domain:** signkairos.com (marketing), app.signkairos.com (product).
- **Status:** Phase 1 works end-to-end on Windows; ~5–7 weeks of plumbing block multi-tenant SaaS.

Read first if you need the full picture: `docs/MASTER.md` → `CONTEXT.md` (glossary) → `docs/09-locked-decisions.md` → `docs/business/state.md` (honest moat + vapor).

## Architecture

Three processes, each restartable independently. **The cockpit never talks to memory directly.**

| Service | Port | Package | Role |
|---|---|---|---|
| memory  | 8001 | `kairos_memory`  | Vault I/O over Supabase Postgres (tenant-scoped via RLS), FTS, wikilink graph, lint, ingest/solve planner. **No LLM, no secrets.** *(Migration in progress — Phase 1 still uses on-disk markdown; see locked decision #12.)* |
| harness | 8002 | `kairos_harness` | Deep Agent runtime, SSE chat, approval queue, audit log. **Only process with API keys.** |
| web     | 5173 | `apps/web`       | Vite + React 19 + TS cockpit. |

CLI: `kairos_cli` (Typer, spawn-and-exit). Shared runtime: `kairos_runtime` (LLM client, deep-research pipeline, env loader).

Vite proxies: `/api/memory/*` → 8001, `/api/harness/*` → 8002 (both with `ws: true`).

## Domain language (use these terms; avoid the synonyms in CONTEXT.md)

**Cockpit** (the React UI), **Channel** (web/cli/gesture), **Memory** / **Harness** / **Web** (the services), **Tenant** (Supabase auth user, RLS scope), **Vault** (Postgres rows under one tenant; was `vault/` directory pre-migration) → **Brain** (a row in `brains`) → **Page** (a row in `pages`), **Wikilink** (`[[slug]]`), **Hot cache** (a row in `hot_cache`, ~500 tokens), **Raw capture** (immutable rows in `raw`), **AGENTS.md** (per-brain wiki contract), **Agent** (the runtime; singular), **Wiki agent** (same runtime in vault-editing role), **Tool**, **Approval gate** (`HumanInTheLoopMiddleware`), **Approval** (a paused tool call), **Ingest plan** (proposed brain mutation), **Solve cycle** (lint → plan → approve → apply), **Thread** (one chat, bound to one brain), **Heartbeat** (07:00 Madrid), **DND window** (01:00–07:00 Madrid).

Read `CONTEXT.md` before writing copy or new code that introduces terms.

## Locked decisions (do not relitigate)

From `docs/09-locked-decisions.md`:

1. **Greenfield.** No code reuse from Obsidian-Knowledge-Graphs / de-warp. Inspiration only.
2. **Cloud-first LLM** with `gemini-flash-latest` alias; **Ollama + `gemma4:4b`** as local fallback. Single `LLMClient` abstraction. Override via `KAIROS_MODEL_OVERRIDE`.
3. **LangChain 1.x + Deep Agents** on LangGraph. Approval persistence via SQLite, 5-minute default in-session timeout, persists across restarts.
4. **Pragmatic sandbox**: read silently, ask before send/write/exec, refuse destructive. Editable in `policies/actions.yaml`.
5. **Locale Europe/Madrid.** DND **01:00–07:00** (queue silently, drain at 07:00). Morning digest 08:00.
6. **Channels:** CLI + custom web cockpit only. Telegram/iMessage deferred. Voice push-to-talk in Phase 3, wake-word + full gesture set in Phase 4.
7. **Identity:** all brains visible; user is "Bruno"; principal brain = Bruno's Brain; cross-brain hops via `[[Other Brain/page]]`.
8. **Vault is Postgres-canonical** (Supabase, RLS scoped by tenant). Markdown is an export, not a source. *(Amended 2026-05-24 — see locked decision #12 + ADR `docs/adr/0001-postgres-vault.md`. Phase 1 disk vault is being migrated.)*

## Approval policy (`policies/actions.yaml`)

- **Allow silently:** `search_wiki`, `get_page`, `get_graph`, `run_lint`, `update_hot_cache.append`, `read_file` (allowlisted roots), `list_dir`, `http_get` (allowlisted hosts in `policies/network.yaml`), `get_calendar`, `get_inbox`.
- **Require approval:** `send_email`, `send_message`, calendar create/update/delete, `file_write` outside sandbox, `http_post`, `shell_command`, `ingest_text`, `install_skill`, `update_hot_cache.delete_section` / `.replace_section`, plus `apply_ingest`, `apply_solve`, `replace_hot`, `write_note`.
- **Never:** `rm_rf`, `format_disk`, `curl_pipe_bash`, `move_money`, `delete_brain`.

Approvals live in `services/harness/data/approvals.db`, auditable in `logs/audit.jsonl`. Every channel sees the same queue.

## Per-turn budgets (don't fish)

Hard caps enforced in code — match these when writing new tools:

- Memory tools: **≤ 2 searches, ≤ 4 page reads** per turn.
- Deep research: **≤ 1 call** per turn.
- Soft ceiling: **5–8 tool calls total** per turn (per `identity/SOUL.md`).

## Repo layout (key paths)

```
apps/web/                  Vite + React 19 + TS cockpit (no Tailwind, no UI lib; tokenized CSS in src/styles)
docs/                      MASTER.md is the index; 00–11 = research dossier; business/, investor/, external/
identity/                  SOUL.md (agent), USER.md (Bruno), HEARTBEAT.md (cron schedule)
policies/                  actions.yaml, network.yaml, secrets.env(.example)
scripts/                   run.py (used by run.ps1), build_docs.py, bench_*.py, grounding_chat.py
services/
  channels/cli/            kairos_cli (Typer)
  harness/kairos_harness/  agent.py, system_prompt.py, approval_store.py, audit.py, news.py, voice.py, tools/
  memory/kairos_memory/    main.py, vault.py, index_db.py (FTS5), registry.py, schemas.py, wiki_agent.py, atlas.py, graph.py
  runtime/kairos_runtime/  llm.py, config.py, prompt_cache.py, research/{runner,classifier,lead,verifier,synthesizer,fetch,cache,...}
tests/                     conftest.py + test_{audit,approval_store,vault,registry,index_db,graph,atlas}.py
vault/                     Brains: "Bruno's Brain" (primary), "Deloitte's Brain", "Acme SaaS Inc", "Beacon Logistics"
logs/audit.jsonl           Append-only audit trail (one event per line; args redacted)
run.ps1, stop.ps1          Launch all three / kill anything on 8001/8002/5173/5174
CONTEXT.md                 Glossary — read before introducing new terms
```

Python packages on the path: `kairos_memory`, `kairos_harness`, `kairos_cli`, `kairos_runtime`. Console script: `kairos`.

## Dev workflow

```powershell
.\run.ps1                                  # launches memory + harness + web with colored prefixes
.\stop.ps1                                 # frees 8001 / 8002 / 5173 / 5174

ruff check .                               # lint (line-length 100, target py311, rules E F I B UP RUF)
mypy services                              # not strict; ignore_missing_imports
pytest                                     # asyncio_mode=auto; tests under tests/

cd apps\web && npx tsc --noEmit            # frontend type check
```

Tests use a `kairos_home` fixture that points `KAIROS_HOME` at a tmp dir with `policies/`, `identity/`, `vault/` scaffolding — keep new tests on this pattern, never touch the real vault.

Docs: `python scripts/build_docs.py` regenerates `docs/exports/*.docx` from canonical markdown and `*.pdf` from HTML decks via headless Chrome/Edge (set `KAIROS_CHROME` if not auto-detected).

## How to work in this repo

- **Edit existing files.** Don't add new abstractions or files unless the task requires them. The architecture is small and deliberate.
- **No code reuse from prior projects.** Locked decision #1 — even if it would save time.
- **Match the audit-log invariant.** Any new mutating tool must be intercept-able by `HumanInTheLoopMiddleware` and emit `tool_call` / `tool_result` events through `kairos_harness.audit`. Add it to `policies/actions.yaml` under `require_approval` unless it's read-only.
- **Memory writes are two-phase.** `plan_*` proposes a diff (silent), `apply_*` writes to disk (gated). Don't add a one-shot write tool that bypasses the planner.
- **Cockpit talks to harness, never to memory.** If the UI needs vault data, route through a harness endpoint or extend `apps/web/src/lib/api.ts` against `/api/memory/*` (which the dev proxy handles, but keep this constraint visible).
- **Read `vault/<brain>/AGENTS.md`** before any change that writes wiki pages — that's the contract the wiki agent follows, brain-local.
- **Hot cache is ground truth.** Items >7 days move to wiki via approval; file >1500 tokens triggers compaction. Don't write to `hot.md` outside the sanctioned tools.
- **Keep `CONTEXT.md` and `docs/MASTER.md` in sync** when domain language or doc structure changes.

## Known vapor (don't claim these work)

From `docs/business/state.md` and the existing-project audit (`docs/05-existing-project-audit.md`):

1. **"Tamper-evident audit log"** — JSONL is wired but **not cryptographically hash-chained**. Don't describe it as tamper-evident in copy.
2. **"Cross-contamination is impossible by design"** — vault is **single-tenant**. Multi-tenant scoping is the #1 productization blocker.
3. **"No model ever trains on your client's data"** — true under current Google Gemini paid-tier terms; lock the version in the DPA.
4. **Gmail send / Calendar write / HEARTBEAT scheduler** — referenced in identity files but not wired end-to-end.
5. **Gestures** — settings page exists; recognition pipeline is UI-shell only.
6. **Voice STT/TTS** — works on dashboard routes, not standalone.
7. **No CI, no telemetry, no billing, no auth** — all blockers for SaaS.

When asked to "ship X," check `docs/business/state.md` first to see if X is already vapor masquerading as done.

## Commercial constraints (shape the work)

- **Solo / lifestyle business.** Bruno stays solo through ~$30k MRR; at most one part-time contractor after that.
- **Wedge:** fractional CFOs juggling 4–8 clients. Buyer fear: cross-client send disaster. Pricing: $199 Solo / $399 Practice / $1,500 setup. Target by month 4: 6–8 logos, $3–4k MRR.
- **Off-limits markets** (don't suggest pivoting toward them): D2C personal AI, prosumer "chief of staff," OSS-with-paid-hosting, OEM/white-label, single-family offices, healthcare (HIPAA tax), VC deal memos, AI-engineering-team tooling.
- **Moat is approval-gate persistence + tenant-scoped Postgres vault (RLS) + multi-channel queue.** (Amended 2026-05-24 — was "markdown source-of-truth"; vault is now Postgres-canonical with markdown as an export. See locked decision #12 + `docs/adr/0001-postgres-vault.md`.) Commodity layers (LangChain, Gemini, FastAPI, React) are swappable — defensibility lives where regulated buyers will pay.

## When in doubt

- Glossary disagreement → `CONTEXT.md` wins.
- Architecture question → `docs/06-jarvis-architecture-proposal.md`.
- "Is this decided?" → `docs/09-locked-decisions.md`.
- "Does this work?" → `docs/business/state.md` (honest) before `README.md` (aspirational).
- Identity / personality / tone → `identity/SOUL.md` + `identity/USER.md`.
- Approval question → `policies/actions.yaml`.
