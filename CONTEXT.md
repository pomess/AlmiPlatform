# Disease360

A long-running personal AI cockpit for a single user. Markdown-backed memory, approval-gated tools, three services (memory, harness, web) that can be restarted independently.

## Language

### Surfaces

**Cockpit**:
The React web UI at port 5173. The single screen the user drives Disease360 from.
_Avoid_: Frontend, dashboard, app, client

**Channel**:
A surface through which the user reads or acts on Disease360 — `web`, `cli`, `gesture`, future `telegram`. All channels see the same approval queue.
_Avoid_: Interface, client, frontend

**CLI**:
The `disease360` Typer command. One-shot — spawns, hits the harness over HTTP, exits.
_Avoid_: Terminal, console, shell tool

### Services

**Memory** (the service):
The FastAPI process on port 8001 that owns vault I/O — pages, wikilink graph, FTS5 search, lint, ingest planning. Holds no secrets, calls no LLM.
_Avoid_: Backend, store, db service

**Harness**:
The FastAPI process on port 8002 that runs the agent, holds the approval queue, and streams chat over SSE. The only process with API keys.
_Avoid_: Server, backend, agent service, runner

**Web** (the service):
The Vite dev server on port 5173 that serves the cockpit.
_Avoid_: Frontend, UI server

### Memory model

**Vault**:
The on-disk root (`vault/`) that holds every brain. Markdown is the source of truth.
_Avoid_: Workspace, store, library

**Brain**:
One knowledge graph — a folder directly under `vault/`. Each brain is self-contained: its own `hot.md`, `index.md`, `wiki/`, `raw/`, `AGENTS.md`.
_Avoid_: Knowledge base, notebook, workspace, project

**Page**:
A single markdown file inside a brain's `wiki/` tree. Pages link to each other via wikilinks.
_Avoid_: Note, document, doc, file

**Wikilink**:
The `[[slug]]` syntax that joins pages. Drives both navigation and the graph view.
_Avoid_: Link, reference, backlink

**Hot cache** (or `hot.md`):
The ~500-token working set loaded into every prompt. One per brain.
_Avoid_: Context window, scratchpad, system prompt

**Raw capture**:
A file under a brain's `raw/`. Immutable — the agent reads it but never rewrites it.
_Avoid_: Source, input, attachment

**AGENTS.md**:
The per-brain contract the wiki agent follows when writing pages. Brain-local, not global.
_Avoid_: Schema, instructions, prompt file

### Agent + tooling

**Agent**:
The LangChain 1.x / Deep Agents runtime inside the harness. Singular — there is one agent, configured with tools and middleware.
_Avoid_: Bot, assistant, AI

**Wiki agent**:
The agent acting in its vault-editing role, following a brain's `AGENTS.md`. Same runtime, different hat.
_Avoid_: Writer, scribe, vault agent

**Tool**:
A function the agent can call. Read-only tools run inline; mutating tools route through the approval gate.
_Avoid_: Action, command, function

**Approval gate**:
The `HumanInTheLoopMiddleware` that intercepts any tool listed under `require_approval` in `policies/actions.yaml` and pauses the agent via a LangGraph `interrupt`.
_Avoid_: Permission check, gate, guard

**Approval**:
A paused tool call awaiting a human decision. Lives in `approvals.db`, visible on every channel, resolved with `Command(resume=...)`.
_Avoid_: Permission, request, prompt, confirmation

**Ingest plan**:
The diff the memory service proposes when new content is being added to a brain. Approved before any file is written.
_Avoid_: Patch, changeset, draft

**Solve cycle**:
The plan → approve → apply loop that mutates a brain. Lint findings feed into the same cycle.
_Avoid_: Workflow, pipeline, edit flow

**Lint**:
Vault-integrity checks run by the memory service — broken wikilinks, schema violations, orphans.
_Avoid_: Validation, audit, check

### Time + lifecycle

**Thread**:
One chat conversation, scoped to the active brain. Switching brains starts a new thread.
_Avoid_: Conversation, session, chat

**Heartbeat**:
The daily 07:00 Europe/Madrid trigger that drains `dnd_held` approvals back to `pending`.
_Avoid_: Cron, tick, scheduler

**DND window**:
01:00–07:00 Europe/Madrid. Approval requests arriving in this window land as `dnd_held` instead of `pending`.
_Avoid_: Quiet hours, sleep mode, off hours

**Audit log**:
`logs/audit.jsonl` — append-only record of every tool call.
_Avoid_: History, journal, trace

## Relationships

- The **Cockpit** talks to the **Harness**; the **Harness** talks to **Memory**. The cockpit never talks to memory directly.
- A **Brain** lives inside the **Vault**. A **Page** lives inside a **Brain**. **Wikilinks** join **Pages** within a **Brain**.
- The **Agent** runs inside the **Harness**. When it calls a mutating **Tool**, the **Approval gate** creates an **Approval** that every **Channel** can resolve.
- An **Ingest plan** is one kind of **Approval** — proposed mutations to a **Brain** before any **Page** is written.
- A **Thread** is bound to exactly one **Brain**. Switching brains ends the thread.

## Example dialogue

> **Dev:** "When the user types in the cockpit, does the request go to memory?"
> **Domain expert:** "No — the **Cockpit** only talks to the **Harness**. The **Harness** is the only thing that holds API keys and the only thing that can call the **Agent**. If the **Agent** needs to read a **Page**, *it* calls **Memory**."
>
> **Dev:** "And if the agent wants to write a page?"
> **Domain expert:** "Then memory builds an **Ingest plan** and the **Approval gate** pauses the agent. The plan shows up as an **Approval** on every **Channel** — web, CLI, gesture. Until someone approves, no file on disk changes."

## Flagged ambiguities

- "agent" was being used for both the runtime and the wiki-editing role — resolved: **Agent** is the runtime, **Wiki agent** is the same runtime in its vault-editing capacity.
- "memory" was being used for both the service and the concept of long-term recall — resolved: **Memory** (capitalised) refers to the service; the broader idea of persistent recall is just "the vault" or "what Disease360 remembers".
- "session" was being used for both a chat thread and a container/process lifetime — resolved: a chat conversation is a **Thread**; "session" is reserved for process lifetime and should not appear as a domain term.
