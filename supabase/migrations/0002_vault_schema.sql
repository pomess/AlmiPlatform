-- Postgres-canonical vault. One row per tenant on every table; RLS forces
-- `tenant_id = auth.uid()` so cross-tenant reads/writes are impossible at the
-- database layer.
--
-- See docs/adr/0001-postgres-vault.md for the full rationale and the phased
-- migration plan. This file is phase 1: schema only, no code changes — the
-- running services keep using on-disk markdown until phase 2 lands.

-- gen_random_uuid() lives in pgcrypto; Supabase has it but we enable
-- defensively in case this migration is replayed against a fresh project.
create extension if not exists pgcrypto;


-- --- Brains ----------------------------------------------------------------

create table if not exists public.brains (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  name        text not null,
  agents_md   text,
  index_md    text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (tenant_id, name)
);

create index if not exists brains_tenant_idx on public.brains (tenant_id);

alter table public.brains enable row level security;

drop policy if exists "tenant reads own brains" on public.brains;
create policy "tenant reads own brains"
  on public.brains for select to authenticated
  using (tenant_id = auth.uid());

drop policy if exists "tenant writes own brains" on public.brains;
create policy "tenant writes own brains"
  on public.brains for all to authenticated
  using (tenant_id = auth.uid())
  with check (tenant_id = auth.uid());


-- --- Pages -----------------------------------------------------------------

create table if not exists public.pages (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  brain_id    uuid not null references public.brains(id) on delete cascade,
  path        text not null,
  title       text not null,
  body        text not null,
  frontmatter jsonb not null default '{}'::jsonb,
  -- Generated tsvector for full-text search. Title weighted A, body B; matches
  -- the FTS5 weighting used in the legacy services/memory/data/fts.sqlite.
  tsv tsvector generated always as (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(body, '')), 'B')
  ) stored,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (brain_id, path)
);

create index if not exists pages_tenant_idx on public.pages (tenant_id);
create index if not exists pages_brain_idx  on public.pages (brain_id);
create index if not exists pages_tsv_gin    on public.pages using gin (tsv);

alter table public.pages enable row level security;

drop policy if exists "tenant reads own pages" on public.pages;
create policy "tenant reads own pages"
  on public.pages for select to authenticated
  using (tenant_id = auth.uid());

drop policy if exists "tenant writes own pages" on public.pages;
create policy "tenant writes own pages"
  on public.pages for all to authenticated
  using (tenant_id = auth.uid())
  with check (tenant_id = auth.uid());


-- --- Hot cache (one row per brain) -----------------------------------------

create table if not exists public.hot_cache (
  brain_id    uuid primary key references public.brains(id) on delete cascade,
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  body        text not null default '# Hot cache' || E'\n\n',
  updated_at  timestamptz not null default now()
);

create index if not exists hot_cache_tenant_idx on public.hot_cache (tenant_id);

alter table public.hot_cache enable row level security;

drop policy if exists "tenant reads own hot" on public.hot_cache;
create policy "tenant reads own hot"
  on public.hot_cache for select to authenticated
  using (tenant_id = auth.uid());

drop policy if exists "tenant writes own hot" on public.hot_cache;
create policy "tenant writes own hot"
  on public.hot_cache for all to authenticated
  using (tenant_id = auth.uid())
  with check (tenant_id = auth.uid());


-- --- Raw captures (immutable inbox) ----------------------------------------

create table if not exists public.raw_captures (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  brain_id    uuid not null references public.brains(id) on delete cascade,
  filename    text not null,
  body        text not null,
  created_at  timestamptz not null default now()
);

create index if not exists raw_captures_tenant_idx on public.raw_captures (tenant_id);
create index if not exists raw_captures_brain_idx  on public.raw_captures (brain_id);

alter table public.raw_captures enable row level security;

drop policy if exists "tenant reads own raw" on public.raw_captures;
create policy "tenant reads own raw"
  on public.raw_captures for select to authenticated
  using (tenant_id = auth.uid());

drop policy if exists "tenant writes own raw" on public.raw_captures;
create policy "tenant writes own raw"
  on public.raw_captures for all to authenticated
  using (tenant_id = auth.uid())
  with check (tenant_id = auth.uid());


-- --- Wikilinks (derived edges) ---------------------------------------------

create table if not exists public.wikilinks (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  brain_id    uuid not null references public.brains(id) on delete cascade,
  source_page uuid not null references public.pages(id) on delete cascade,
  target_slug text not null,
  alias       text,
  anchor      text
);

create index if not exists wikilinks_tenant_idx on public.wikilinks (tenant_id);
create index if not exists wikilinks_brain_idx  on public.wikilinks (brain_id);
create index if not exists wikilinks_source_idx on public.wikilinks (source_page);
create index if not exists wikilinks_target_idx on public.wikilinks (brain_id, target_slug);

alter table public.wikilinks enable row level security;

drop policy if exists "tenant reads own wikilinks" on public.wikilinks;
create policy "tenant reads own wikilinks"
  on public.wikilinks for select to authenticated
  using (tenant_id = auth.uid());

drop policy if exists "tenant writes own wikilinks" on public.wikilinks;
create policy "tenant writes own wikilinks"
  on public.wikilinks for all to authenticated
  using (tenant_id = auth.uid())
  with check (tenant_id = auth.uid());


-- --- Approvals -------------------------------------------------------------

create table if not exists public.approvals (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references auth.users(id) on delete cascade,
  thread_id    text not null,
  tool         text not null,
  args         jsonb not null,
  rationale    text,
  status       text not null,
  created_at   timestamptz not null default now(),
  expires_at   timestamptz not null,
  resolved_at  timestamptz,
  resolved_by  text
);

create index if not exists approvals_tenant_idx on public.approvals (tenant_id);
create index if not exists approvals_status_idx on public.approvals (status);
create index if not exists approvals_thread_idx on public.approvals (thread_id);

alter table public.approvals enable row level security;

drop policy if exists "tenant reads own approvals" on public.approvals;
create policy "tenant reads own approvals"
  on public.approvals for select to authenticated
  using (tenant_id = auth.uid());

drop policy if exists "tenant writes own approvals" on public.approvals;
create policy "tenant writes own approvals"
  on public.approvals for all to authenticated
  using (tenant_id = auth.uid())
  with check (tenant_id = auth.uid());


-- --- Audit events (append-only) --------------------------------------------

create table if not exists public.audit_events (
  id          bigserial primary key,
  tenant_id   uuid not null references auth.users(id) on delete cascade,
  ts          timestamptz not null default now(),
  kind        text not null,
  thread_id   text,
  tool        text,
  payload     jsonb not null
);

create index if not exists audit_events_tenant_idx on public.audit_events (tenant_id, ts desc);
create index if not exists audit_events_thread_idx on public.audit_events (thread_id);

alter table public.audit_events enable row level security;

-- Audit log is read-only from the client. The harness writes via the service
-- role key (server-side); end users can only read their own events.
drop policy if exists "tenant reads own audit" on public.audit_events;
create policy "tenant reads own audit"
  on public.audit_events for select to authenticated
  using (tenant_id = auth.uid());


-- --- updated_at trigger ----------------------------------------------------

create or replace function public.touch_updated_at() returns trigger as $$
begin
  new.updated_at := now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists brains_touch_updated_at on public.brains;
create trigger brains_touch_updated_at
  before update on public.brains
  for each row execute function public.touch_updated_at();

drop trigger if exists pages_touch_updated_at on public.pages;
create trigger pages_touch_updated_at
  before update on public.pages
  for each row execute function public.touch_updated_at();

drop trigger if exists hot_cache_touch_updated_at on public.hot_cache;
create trigger hot_cache_touch_updated_at
  before update on public.hot_cache
  for each row execute function public.touch_updated_at();
