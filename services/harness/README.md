# Harness

The connective tissue between channels, the runtime, and the policy/audit layer. Built on **LangChain 1.0 + Deep Agents** (LangGraph underneath).

## Responsibilities

- **Boot** — load `identity/SOUL.md`, `identity/USER.md`, active brain's `hot.md` + `index.md`, `policies/*`, `secrets.env`.
- **System prompt order**: `SOUL.md` → `USER.md` → active brain `hot.md` → active brain `index.md` excerpt → tool descriptions. See [docs/11-hot-cache.md](../../docs/11-hot-cache.md).
- **Agent assembly** — `create_deep_agent(model, tools, middleware=[HumanInTheLoopMiddleware(...), ...], instructions=...)`.
- **Approval gate** — `HumanInTheLoopMiddleware` config matches `policies/actions.yaml`. Tools in `require_approval` are intercepted; the agent pauses (LangGraph `interrupt`), the request is persisted to the SQLite **approval queue**, and the channel layer surfaces it. On approve/deny, the agent resumes via `Command(resume=...)`.
- **Approval queue** — SQLite at `data/approvals.db`, schema:
  ```
  approvals(id TEXT PK, thread_id TEXT, tool TEXT, args_json TEXT,
            rationale TEXT, status TEXT, -- pending|approved|denied|expired|dnd_held
            created_at TEXT, expires_at TEXT, resolved_at TEXT, resolved_by TEXT)
  ```
  - Default in-session timeout: **5 minutes** (`expires_at = created_at + 5m`). Expired items are skipped, never executed.
  - DND window (01:00–07:00 Europe/Madrid): items land as `dnd_held`; drained by the 07:00 heartbeat job into `pending` for the user.
  - Persisted across process restarts; survives spawn-and-exit CLI cycles.
- **Scheduler** — tick `HEARTBEAT.md` blocks (07:00 drain, 08:00 digest, 22:30 day-close).
- **Audit** — every tool call → `logs/audit.jsonl` with `{ts, thread_id, tool, args_redacted, result_summary, rationale}`.
- **REST shim** (`api.py`) — `/chat` (SSE), `/approvals`, `/approvals/{id}/{approve|deny}`. Used by the web app and by the CLI's approve/deny commands.

## Modules

- `disease360_harness/agent.py`          — Deep Agent factory
- `disease360_harness/system_prompt.py`  — SOUL+USER+hot+index assembler
- `disease360_harness/approval_store.py` — SQLite queue (sync via `sqlite3`, simple)
- `disease360_harness/middleware.py`     — HITL config + audit middleware
- `disease360_harness/tools/`            — memory_tools, web_search, email_read (stubs P1), calendar_read (stubs P1)
- `disease360_harness/api.py`            — FastAPI REST shim (port 8002)

Status: **scaffolded — implement in Phase 1**.
