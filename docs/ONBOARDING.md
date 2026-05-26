# Kairos — Contractor onboarding

_For a part-time contractor joining Bruno on Kairos. Half-day to read, run locally, and pick a first ticket._

---

## What you're being hired to help with

Kairos is **a single-user AI cockpit** being repurposed as **a multi-tenant SaaS for fractional CFOs**. The single-user version works end-to-end on Bruno's Windows machine. The SaaS version doesn't exist yet — you're being hired to help cross that gap.

The gap is real. Read [`business/state.md`](business/state.md) before writing any code. It lists ~5–7 weeks of plumbing blockers honestly: hardcoded paths, no auth, single-tenant vault, Windows-only run, no CI, no billing.

---

## Mental model in 30 seconds

Three FastAPI/Vite processes. Each can be restarted without the others.

```
web (5173)  ──▶  harness (8002)  ──▶  memory (8001)
React UI         agent + approvals     vault I/O + FTS + graph
                 + Gemini API key      no LLM, no secrets
```

- **Memory** owns the markdown vault — no LLM, no API keys, no secrets.
- **Harness** runs the LangChain 1.x / Deep Agents runtime, holds the approval queue (SQLite), and is the only process that talks to Gemini.
- **Web** is the React 19 cockpit at port 5173.
- The web cockpit **never** talks to memory directly. Always through the harness.

Domain glossary: [`../CONTEXT.md`](../CONTEXT.md) — read this before naming anything.

---

## Get it running locally

**Prereqs:** Python 3.11+, Node 18+, optionally [`uv`](https://github.com/astral-sh/uv). Currently Windows-only (`run.ps1` is PowerShell). Containerization is on the productization blocker list.

```powershell
# 1. Python env + deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"     # or: uv sync

# 2. Secrets
copy policies\secrets.env.example policies\secrets.env
# Set GOOGLE_API_KEY (required). TAVILY_API_KEY is optional.

# 3. Launch all three
.\run.ps1

# 4. Open the cockpit at http://localhost:5173
```

`run.ps1` streams the three services side by side with colored prefixes. `Ctrl+C` once shuts all three down. If a port is stuck: `.\stop.ps1` frees 8001/8002/5173/5174.

---

## Where things live

```
apps/web/                       Vite + React 19 + TS cockpit
  src/pages/Landing.tsx         signkairos.com landing page
  src/pages/Cockpit.tsx         the /app shell
  src/lib/api.ts                ⚠️ hardcoded localhost — needs config
services/
  memory/                       FastAPI, port 8001 (vault, FTS, graph, lint)
  harness/                      FastAPI, port 8002 (agent, approvals, audit log)
    kairos_harness/audit.py     append-only JSONL log (logs/audit.jsonl)
  channels/cli/                 `kairos` Typer CLI
  perception/                   voice/gesture (Phase 3+, partial)
  runtime/                      shared LLM client config
policies/
  actions.yaml                  which tools require approval
  secrets.env                   API keys (gitignored)
identity/
  SOUL.md, USER.md, HEARTBEAT.md   agent identity files (loaded into prompts)
vault/                          the brains live here as folders of markdown
  Bruno's Brain/                research / career history (self-demo, NOT for sales)
  Deloitte's Brain/             work-relationship manager (closer to sales-shape)
docs/                           all documentation — start at MASTER.md
marketing/                      hero.md (landing copy), loom-script.md
logs/audit.jsonl                runtime audit log (wired 2026-05-17)
```

---

## Conventions Bruno cares about

These are *not* preferences — they've been argued for and locked. Don't relitigate without checking.

1. **Markdown is the source of truth.** The FTS5 SQLite index is rebuilt from disk on demand. Never write a feature that depends on the index existing — if the disk files are right, the system is right.
2. **Approvals route through one queue.** Web, CLI, and (future) gesture all read/write the same `approvals.db`. Don't add a parallel queue.
3. **The harness is the only process with API keys.** Memory must never call an LLM. Web must never call Gemini directly.
4. **Names matter.** Use the exact terms in [`../CONTEXT.md`](../CONTEXT.md) — *cockpit*, not "frontend"; *brain*, not "workspace"; *thread*, not "session". Customer-facing copy uses *client*, *engagement*, *board* — never *brain*, *vault*, *agent*.
5. **Bug fix ≠ refactor.** Fix the bug. Don't reshape the surrounding code unless asked.
6. **No CLAUDE.md/AI-tooling files in commits unless asked.** They're working files for Bruno's local sessions.

---

## Productization blockers (your likely ticket pool)

From [`business/state.md`](business/state.md), in rough priority order for the CFO wedge:

1. **Multi-tenant data isolation.** `vault/` is shared globally. No `tenant_id` scoping anywhere. This is the **#1 ship-blocker** — landing page promises a "wall" between clients that the code doesn't currently enforce.
2. **Auth.** Memory:8001 and harness:8002 have CORS but no token check. Need a per-tenant auth layer (Clerk is the leading candidate per the strategy doc).
3. **Hardcoded paths.** `repo_root()` walks for `policies/` + `identity/`. Won't survive a hosted deploy.
4. **Frontend hardcodes.** `apps/web/src/lib/api.ts` pins localhost. Needs env-driven base URL.
5. **Audit log integrity.** `logs/audit.jsonl` is wired but is a plain JSONL file. The landing page calls it "tamper-evident" — adding a hash chain (each row references prev-hash) is what makes that claim honest.
6. **Hosted deploy.** No Docker, no health checks, Windows-only `run.ps1`. Fly.io is the leading candidate.
7. **Billing.** Stripe integration not present.
8. **CI.** No GitHub Actions. Tests (`pytest`, `npx tsc --noEmit`, `ruff check .`, `mypy services`) need to run on push.

---

## Vapor — claims that don't match the code

Don't demo or promise these to anyone, internal or external, until they ship:

- **Gmail / Calendar tools** — placeholders in `policies/actions.yaml`, no bodies.
- **HEARTBEAT.md scheduler** — file exists, no daemon. The 07:00 DND drain and morning digest are doc concepts.
- **Telegram channel** — Phase 2.
- **NemoClaw sandbox** — Phase 4. Approval gates are policy-soft today.
- **Credential stripping** — secrets load straight into prompts; no redaction at the model boundary.
- **Full gesture pipeline** — MediaPipe skeleton, not wired end-to-end.
- **Network proxy / `policies/network.yaml` enforcement** — not implemented.

---

## How to ship a change

```powershell
# Frontend type check (from apps/web)
cd apps\web; npx tsc --noEmit

# Python lint + types + tests (from repo root)
ruff check .
mypy services
pytest
```

Branch naming: `feat/...`, `fix/...`, `refactor/...`, `chore/...`. PRs squash-merge to `main`. There's a `backup/yellow-previous-frontend` branch holding the pre-redesign UI as a safety net.

---

## When you're stuck

1. Check [`MASTER.md`](MASTER.md) for the right doc.
2. Search the vault — Kairos eats its own dogfood; design notes often live in `vault/Bruno's Brain/wiki/`.
3. Ping Bruno. Solo founder, async, expects clear questions with file paths and line numbers.
