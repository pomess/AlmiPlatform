// Supabase Edge Function — fires on auth.users insert via a database webhook.
// Inserts the allowed_users row (granted_access=false) and sends two Resend emails:
// one to Bruno (notification), one to the new user (welcome + Calendly link).
//
// Deploy:    supabase functions deploy notify-signup
// Webhook:   Database → Webhooks → "On insert in auth.users" → POST to this function
// Secrets:   supabase secrets set RESEND_API_KEY=... BRUNO_EMAIL=... CALENDLY_URL=... \
//                                 SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
//                                 EMAIL_FROM="Kairos <noreply@signkairos.com>"

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import {
  brunoNotificationEmail,
  userWelcomeEmail,
  type SignupInfo,
} from "./email_templates.ts";

const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") ?? "";
const BRUNO_EMAIL = Deno.env.get("BRUNO_EMAIL") ?? "";
const CALENDLY_URL = Deno.env.get("CALENDLY_URL") ?? "https://calendly.com/signkairos/30min";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const EMAIL_FROM = Deno.env.get("EMAIL_FROM") ?? "Kairos <noreply@signkairos.com>";

type WebhookPayload = {
  type: string;
  table: string;
  record: {
    id: string;
    email: string | null;
    raw_user_meta_data?: { full_name?: string; name?: string } | null;
    created_at: string;
  };
};

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  let body: WebhookPayload;
  try {
    body = (await req.json()) as WebhookPayload;
  } catch {
    return jsonError("invalid_json", 400);
  }

  if (body.type !== "INSERT" || body.table !== "users") {
    return new Response(JSON.stringify({ skipped: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }

  const record = body.record;
  if (!record?.id || !record?.email) {
    return jsonError("missing_user_fields", 400);
  }

  const fullName =
    record.raw_user_meta_data?.full_name ?? record.raw_user_meta_data?.name ?? null;

  // 1. Insert allowed_users row (idempotent — webhook may retry).
  const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
  const { error: insertErr } = await admin.from("allowed_users").upsert(
    {
      user_id: record.id,
      email: record.email,
      granted_access: false,
    },
    { onConflict: "user_id" },
  );
  if (insertErr) {
    console.error("allowed_users upsert failed", insertErr);
    return jsonError("allowlist_insert_failed", 500);
  }

  // 2. Send both emails. Failures are logged but don't fail the webhook
  // (the row is what matters for access control).
  const info: SignupInfo = {
    email: record.email,
    fullName,
    userId: record.id,
    createdAt: record.created_at,
    calendlyUrl: CALENDLY_URL,
  };
  await Promise.all([
    BRUNO_EMAIL ? sendEmail(BRUNO_EMAIL, brunoNotificationEmail(info)) : Promise.resolve(),
    sendEmail(record.email, userWelcomeEmail(info)),
  ]).catch((err) => console.error("email send error", err));

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
});

async function sendEmail(
  to: string,
  payload: { subject: string; html: string; text: string },
): Promise<void> {
  if (!RESEND_API_KEY) {
    console.warn("RESEND_API_KEY not set; skipping send to", to);
    return;
  }
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${RESEND_API_KEY}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      from: EMAIL_FROM,
      to,
      subject: payload.subject,
      html: payload.html,
      text: payload.text,
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    console.error(`resend ${res.status} for ${to}: ${detail}`);
  }
}

function jsonError(code: string, status: number): Response {
  return new Response(JSON.stringify({ error: code }), {
    status,
    headers: { "content-type": "application/json" },
  });
}
