# ADR 0001 — Postgres-canonical vault

**Status:** Accepted (2026-05-24)
**Supersedes:** Phase 1 filesystem vault layout; commit `cf0da22` (directory-shaped tenant scoping) is preserved as a reference but not the final shape.
**Amends:** [`docs/09-locked-decisions.md`](../09-locked-decisions.md) — adds decision #12, reopens the markdown-source-of-truth implication.

## Context

Phase 1 stores the vault as markdown files under `vault/<brain>/` (per-brain folders with `wiki/`, `raw/`, `hot.md`, `index.md`). The cockpit talks only to the harness; the harness talks to the memory service over HTTP; the memory service is the only process that touches disk.

The commercialization wedge is fractional CFOs juggling 4–8 client engagements. The buyer's specific fear is **cross-client cross-contamination** ("we accidentally sent Acme's number to Beacon"). Single-tenant `vault/` is the #1 productization blocker on `docs/business/state.md`.

A first attempt (commit `cf0da22`) added directory-shaped tenancy: `vault/<tenant_id>/<brain>/`, FTS5 SQLite per tenant, `tenant_id` column on the approvals SQLite, every memory route prefixed `/tenant/{tenant_id}/`. This works locally but doesn't get us to a hosted SaaS:

- No row-level enforcement — a bug in URL routing leaks across tenants.
- SQLite-per-tenant doesn't scale to a hosted deploy (file locks, no replication, no backup).
- Approvals SQLite + audit JSONL still need their own multi-tenant story.
- The deploy story (Fly.io / VPS) still needs persistent volumes per tenant.

Supabase is already in the repo for Google OAuth + the `allowed_users` waitlist gate (`apps/web/src/lib/supabase.ts`, `supabase/migrations/0001_allowed_users.sql`). We get RLS, hosted Postgres, FTS, and a verified `tenant_id` from the JWT for free.

## Decision

The vault is **Postgres-canonical**. Tenants are Supabase auth users; `tenant_id := auth.uid()`. Every vault row has a `tenant_id` column with an RLS policy `tenant_id = auth.uid()`. The harness uses the user's JWT to talk to Postgres; the memory service is rewritten to wrap Postgres queries instead of filesystem operations.

Markdown becomes an **export format**, not a source. A `kairos vault export` command (CLI) writes the user's vault to disk in the legacy directory shape for Obsidian-style local browsing. The running system never reads from those files.

The approval queue and audit log move to Postgres alongside the vault — they're per-tenant data and need the same RLS treatment.

## Schema sketch

All tables carry `tenant_id uuid not null references auth.users(id) on delete cascade` and have RLS enabled with `using (tenant_id = auth.uid())`.

```sql
-- Brains: a tenant's named knowledge containers (e.g. "Bruno's Brain", "Acme SaaS Inc")
create table brains (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  name        text not null,
  agents_md   text,                         -- per-brain wiki contract
  index_md    text,                         -- TOC, agent-managed
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (tenant_id, name)
);

-- Pages: wiki/*.md content
create table pages (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  brain_id    uuid not null references brains(id) on delete cascade,
  path        text not null,                -- e.g. "wiki/notes/foo.md"
  title       text not null,
  body        text not null,                -- markdown body
  frontmatter jsonb not null default '{}',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (brain_id, path)
);

-- Hot cache: ~500-token working set per brain
create table hot_cache (
  brain_id    uuid primary key references brains(id) on delete cascade,
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  body        text not null default '# Hot cache\n\n',
  updated_at  timestamptz not null default now()
);

-- Raw captures: immutable inbox before ingest
create table raw_captures (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  brain_id    uuid not null references brains(id) on delete cascade,
  filename    text not null,
  body        text not null,
  created_at  timestamptz not null default now()
);

-- Wikilink edges: derived, refreshed on page upsert
create table wikilinks (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  brain_id    uuid not null references brains(id) on delete cascade,
  source_page uuid not null references pages(id) on delete cascade,
  target_slug text not null,                -- the "[[slug]]" target; may not exist yet
  alias       text,
  anchor      text
);

-- Approval queue
create table approvals (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references auth.users(id) on delete cascade,
  thread_id    text not null,
  tool         text not null,
  args         jsonb not null,
  rationale    text,
  status       text not null,               -- pending|approved|denied|expired|dnd_held
  created_at   timestamptz not null default now(),
  expires_at   timestamptz not null,
  resolved_at  timestamptz,
  resolved_by  text
);

-- Audit log: append-only event stream
create table audit_events (
  id          bigserial primary key,
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  ts          timestamptz not null default now(),
  kind        text not null,                -- tool_call|tool_result|approval_created|approval_resolved
  thread_id   text,
  tool        text,
  payload     jsonb not null
);
```

### Full-text search

Use Postgres `tsvector` indexes on `pages.body` and `pages.title`:

```sql
alter table pages add column tsv tsvector
  generated always as (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(body, '')), 'B')
  ) stored;
create index pages_tsv_gin on pages using gin(tsv);
```

Search becomes `where tsv @@ websearch_to_tsquery('english', $1) order by ts_rank(tsv, ...)`. RLS still applies, so cross-tenant leaks are impossible at the database layer.

### Why RLS over app-layer scoping

The current diff scopes by URL prefix (`/tenant/{tenant_id}/...`). A bug anywhere in URL parsing breaks isolation. RLS pushes the invariant to the database: even if the harness builds the wrong query, Postgres returns zero rows. This is the moat copy ("cross-contamination is impossible by design") becoming actually true instead of vapor.

## Migration approach

Phase the work so the system stays runnable:

1. **Schema + RLS** — write the migration, apply locally and to a dev Supabase project. No code changes yet; existing services keep using disk.
2. **Memory service rewrite** — port `vault.py`, `index_db.py`, `graph.py`, `atlas.py`, `wiki_agent.py` to talk to Postgres via `asyncpg` (or supabase-py for RLS-via-JWT). Keep the same HTTP surface so the harness doesn't change.
3. **Approval store + audit move** — port `approval_store.py` and `audit.py` to Postgres. The CLI's "read approvals SQLite directly" path becomes an HTTP read.
4. **Auth wiring** — harness extracts `tenant_id` from the Supabase JWT (already available in the cockpit). CLI gets a service-role token for Bruno's tenant during local dev.
5. **Migration script** — `scripts/migrate_vault_to_postgres.py` walks `vault/<brain>/`, inserts rows under Bruno's tenant. Run once per environment.
6. **Markdown export** — `kairos vault export` CLI command writes a tenant's vault back to disk for archive / Obsidian browsing.
7. **Delete the filesystem code paths** — only after the export command works and a manual round-trip is verified.

Each phase ships behind a feature flag (`KAIROS_VAULT_BACKEND=disk|postgres`) so we can roll back if a phase breaks production. The flag is removed at the end of phase 7.

## Consequences

**Wins:**
- Cross-tenant isolation enforced at the database, not in URL routing.
- Approval queue and audit log get the same multi-tenant safety as the vault.
- Hosted deploy story collapses: one Supabase project per environment, no per-tenant disk volumes.
- Postgres FTS replaces FTS5 SQLite — same query model, hosted, replicated.
- The "cross-contamination is impossible by design" line in copy stops being vapor.

**Costs:**
- Bruno loses direct Obsidian editing of the live vault. Mitigated by `kairos vault export` for archive workflows; the cockpit becomes the canonical edit surface.
- ~2–3 weeks of focused work per the migration phases above.
- The 13-file directory-shaped tenancy diff (`cf0da22`) is largely superseded — kept as a stepping stone reference, not a foundation.
- New runtime dependency on Supabase availability. Acceptable trade for a SaaS deploy; the local-only mode for Bruno is preserved via a self-hosted Postgres + Supabase Studio if needed.

**Open questions:**
- Where do checkpoints (`langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver`) live? Probably stay on local disk per harness instance — they're per-thread runtime state, not vault content. Revisit if we go horizontal.
- Storing large raw captures (PDFs, audio) — Supabase Storage with a `raw_captures.storage_path` column rather than inline `body`. Defer until first capture exceeds the 1 MB row threshold.
- Markdown round-trip fidelity — frontmatter ordering, trailing newlines, YAML edge cases. Tests in the migration script must verify a disk → Postgres → disk round trip matches byte-for-byte.

## References

- Locked decision #12 — [`docs/09-locked-decisions.md`](../09-locked-decisions.md)
- Existing audit-log moat claims — [`docs/business/state.md`](../business/state.md) §Vapor
- Productization blockers — [`docs/business/state.md`](../business/state.md) §Productization blockers
- Current Supabase footprint — [`docs/dev/supabase-setup.md`](../dev/supabase-setup.md)
- Stepping-stone commit — `cf0da22`
