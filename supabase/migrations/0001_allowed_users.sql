-- Allowlist for Kairos /app access. One row per signed-in user.
-- Bruno flips granted_access manually for each pilot during the invite-only phase.

create table if not exists public.allowed_users (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  granted_access boolean not null default false,
  created_at timestamptz not null default now(),
  note text
);

create index if not exists allowed_users_email_idx on public.allowed_users (email);

alter table public.allowed_users enable row level security;

-- Authenticated users can read only their own row. The frontend uses this to
-- render the cockpit vs. the waitlist screen.
drop policy if exists "users read own row" on public.allowed_users;
create policy "users read own row"
  on public.allowed_users
  for select
  to authenticated
  using (auth.uid() = user_id);

-- Inserts/updates happen only from server contexts (the notify-signup edge
-- function with the service role key, or the Supabase dashboard). No client
-- write policy is granted on purpose.
