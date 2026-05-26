# Supabase setup runbook

One-time setup for Kairos sign-in (Google OAuth) and the allowlist gate. Read this once, do it, never read it again unless you recreate the project.

The frontend lives in `apps/web/`. The Supabase artifacts live in `supabase/`.

## 1. Create the project

1. Sign in at [supabase.com](https://supabase.com), create a new project. Region: closest to Madrid (e.g. `eu-west-2`).
2. Note the **Project URL** and **anon key** (Settings → API). These go into `apps/web/.env.local`:

   ```
   VITE_SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
   VITE_SUPABASE_ANON_KEY=eyJ...
   VITE_CALENDLY_URL=https://calendly.com/signkairos/30min
   ```

3. Note the **service role key** (same page, server-side only). This goes into the edge function secrets in step 4 — never commit it, never expose it to the frontend.

## 2. Enable Google OAuth

1. Authentication → Providers → Google → Enable.
2. Follow the Google Cloud Console steps Supabase links to:
   - Create an OAuth 2.0 client (Web application).
   - Authorized JavaScript origins: `http://localhost:5173`, `https://app.signkairos.com`.
   - Authorized redirect URIs: the URL Supabase shows (looks like `https://YOUR-PROJECT-REF.supabase.co/auth/v1/callback`).
3. Paste the Google client ID + secret back into Supabase.
4. Authentication → URL Configuration → add to **Redirect URLs**:
   - `http://localhost:5173/app`
   - `https://app.signkairos.com/app`

## 3. Apply the migration

In the Supabase SQL editor, paste and run [`supabase/migrations/0001_allowed_users.sql`](../../supabase/migrations/0001_allowed_users.sql).

Then seed Bruno's row so dev access doesn't break the moment auth is on. Replace the email and run:

```sql
insert into public.allowed_users (user_id, email, granted_access, note)
select id, email, true, 'owner'
from auth.users
where email = 'bruno@signkairos.com'
on conflict (user_id) do update set granted_access = true;
```

If Bruno hasn't signed in yet there's no `auth.users` row to copy from — sign in once first, then run the seed.

## 4. Deploy the notify-signup edge function

Install the [Supabase CLI](https://supabase.com/docs/guides/cli) if you haven't.

```bash
supabase link --project-ref YOUR-PROJECT-REF
supabase secrets set \
  RESEND_API_KEY=re_... \
  BRUNO_EMAIL=bruno@signkairos.com \
  CALENDLY_URL=https://calendly.com/signkairos/30min \
  EMAIL_FROM="Kairos <noreply@signkairos.com>"
supabase functions deploy notify-signup --no-verify-jwt
```

`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are injected automatically by the runtime — do not set them manually.

`--no-verify-jwt` is required because the database webhook calls the function with a webhook signature, not a user JWT. Restrict access another way (see step 5).

## 5. Wire up Resend

1. Sign up at [resend.com](https://resend.com), add the `signkairos.com` domain, set the DNS records they show.
2. Once verified, create an API key with **Sending** scope. Paste into the `RESEND_API_KEY` secret in step 4.
3. The `EMAIL_FROM` address (`noreply@signkairos.com`) must use the verified domain.

## 6. Database webhook on auth.users

Database → Webhooks → Create a new hook:

- Name: `notify-signup`
- Table: `auth.users`
- Events: **Insert**
- Type: **Supabase Edge Functions**
- Function: `notify-signup`
- HTTP method: POST

Save. The first signup with a fresh Google account will trigger it.

## 7. Verify end-to-end

1. `cd apps/web && npm run dev`.
2. Open `http://localhost:5173`, click **Sign in →**, complete Google OAuth.
3. Expected: redirect to `/app` → waitlist screen (because `granted_access = false`).
4. Bruno's inbox: a `Kairos signup: …` notification.
5. Test account inbox: a `Kairos — you're on the list` welcome with the Calendly link.
6. Flip `granted_access = true` for the test row in the Supabase dashboard, refresh `/app` → cockpit loads.

## 8. Granting access to a new pilot

1. They click "Sign in →" on the landing page and complete Google OAuth.
2. After their first sign-in, a row appears in `public.allowed_users` with `granted_access = false`.
3. Edit the row, set `granted_access = true`, save.
4. Tell them to refresh `/app`.

That's the whole onboarding flow until Stripe is wired up.
