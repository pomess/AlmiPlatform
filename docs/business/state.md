# Kairos — Technical state, sales-readiness audit

_As of 2026-05-17. Source: deep-audit subagent on the full repo._

## Phase 1 working end-to-end

- **SSE streaming chat** (Gemini Flash + Ollama fallback) via FastAPI in `services/harness/`.
- **Persisted SQLite approval queue** across CLI + web (`HumanInTheLoopMiddleware` on LangGraph interrupts — survives process restarts).
- **Markdown vault I/O** with FTS5 + wikilink graph + lint (`services/memory/`).
- **Ingest / solve cycle** — plan → approve → apply, with multi-file atomic updates.
- **Multi-brain support** — registry bootstraps Bruno's Brain + Deloitte's Brain on startup; cross-brain wikilinks work.
- **Typer CLI** — `kairos ask`, `kairos approvals`, `kairos brains`, `kairos switch`.
- **Force-directed graph view** with click-to-peek 3D flashcard.
- **Hot.md cache** — ~500-token working set loaded into every prompt.
- **Partial voice endpoints** — STT + TTS plumbing in `voice.py`, dashboard client tools.
- **Audit log** ✅ — `logs/audit.jsonl` now wired (added 2026-05-17). Tool calls, tool results, approval lifecycle.

## Vapor — claims that don't match the code

Caught during the audit. Don't demo or promise these until they ship.

- **Gmail / Calendar tools** — placeholders in `policies/actions.yaml`, no bodies in `memory_tools.py`.
- **HEARTBEAT.md scheduler** — identity file exists, no daemon. The 07:00 DND drain and morning digest are doc concepts.
- **Telegram channel** — deferred to Phase 2.
- **NemoClaw sandbox** — Phase 4. Approval gates are policy-soft, no kernel isolation.
- **Credential stripping** — secrets load straight into LLM prompts.
- **Full gesture pipeline** — MediaPipe skeleton, but approval gestures aren't wired end-to-end.
- **Network proxy / `policies/network.yaml` enforcement** — not implemented.

## Productization blockers (~5–7 weeks of work for sale to anyone-but-Bruno)

1. **Hardcoded paths.** `repo_root()` walks for `policies/` + `identity/`. No multi-tenant data isolation.
2. **No auth on backend services.** Memory:8001 and harness:8002 both have CORS but no JWT check (Supabase auth on the cockpit only). The backend doesn't yet read the verified `tenant_id` off the token.
3. **Single-tenant assumption.** `vault/` is shared globally; no `tenant_id` scoping. *(In progress: directory-shaped tenancy landed in commit `cf0da22`; superseded by Postgres-canonical vault per ADR `docs/adr/0001-postgres-vault.md` — locked decision #12.)*
4. **Secrets handling.** API keys load directly into prompts; no redaction at the model boundary.
5. **Windows-only deploy.** `run.ps1` is PowerShell. No Docker, no systemd, no health checks.
6. **Frontend hardcodes.** `apps/web/src/lib/api.ts` pins localhost:5173 / 8001 / 8002.
7. **No telemetry / billing.** No structured logs, no cost attribution, no usage metering.
8. **No CI.** No GitHub Actions, no automated test runs on push.
9. **Onboarding.** USER.md is a static file; timezone + DND hours are hardcoded as Europe/Madrid / 01:00–07:00.

## Genuine moat (defensible)

- **Approval gate on persisted LangGraph interrupts** — most agent stacks pause in memory or freeze the whole thread. Kairos persists the interrupt to SQLite, allows any channel (web/CLI/gesture) to resolve it, and resumes the same thread with full state. Hard to bolt on retroactively.
- **Tenant-scoped Postgres vault under RLS** *(target architecture, Phase 2 — was "markdown-as-source-of-truth" through Phase 1)*. Cross-tenant isolation enforced at the database, not in URL routing. Markdown export remains for archive/Obsidian workflows. See ADR `docs/adr/0001-postgres-vault.md`.
- **Wikilink graph + lint** — orphans, broken links, schema violations. Drives both navigation and integrity checks. Harder than flat-document search, harder than generic knowledge graphs.
- **Multi-channel approval queue** — same DB visible from web + CLI + (future) gesture/Telegram. No channel amnesia.
- **Hot cache pattern** — ~500-token always-loaded working memory, editable, compactable. Cheaper than fine-tuning, more robust than RAG.

## Commodity layers (not a moat)

LangChain 1.x, Deep Agents, Gemini Flash, FastAPI, React 19, SQLite, Vite, Typer. Replace any of these and the product still works.

## Vault / brain examples already in the repo

- **Bruno's Brain** — research / career intellectual history. AI forecasts, intellectual contacts, project history. Useful for self-demo but **not** for sales — talks to a CFO about Daniel Kokotajlo and Vannevar Bush.
- **Deloitte's Brain** — work-relationship manager. Colleague names, client engagements (Almirall, Vera, Disease360), Deloitte career ladder. Closer to a sales demo but Deloitte-flavored.
- **Missing for the wedge demo** — fractional-CFO-shaped brains. See [`marketing/loom-script.md`](../../marketing/loom-script.md) for the Acme SaaS Inc + Beacon Logistics scaffold.

## Verdict in one paragraph

Phase 1 is more complete than the roadmap implies. The approval gate, markdown vault, FTS5, wikilink graph, multi-brain registry, and CLI all work end-to-end. The audit log gap is closed (2026-05-17). What's missing is everything between "works on Bruno's Windows machine" and "a fractional CFO can sign up and pay" — multi-tenant scoping, auth, hosted deploy, billing. ~5–7 weeks of plumbing. The moat is real and the demo can be honest if we don't oversell Gmail, voice, or gesture features that haven't shipped.

## Related docs

- [`docs/business/strategy.md`](strategy.md) — wedge, ACV, GTM.
- [`docs/07-roadmap.md`](../07-roadmap.md) — the original (pre-commercialization) phase plan.
