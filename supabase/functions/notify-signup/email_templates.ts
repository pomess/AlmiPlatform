// Email bodies for the notify-signup edge function.
// Two templates: internal notification (Bruno) + welcome (the new signup).

export type SignupInfo = {
  email: string;
  fullName: string | null;
  userId: string;
  createdAt: string;
  calendlyUrl: string;
};

export type EmailPayload = { subject: string; html: string; text: string };

export function brunoNotificationEmail(info: SignupInfo): EmailPayload {
  const subject = `Kairos signup: ${info.email}`;
  const text = [
    `New Kairos signup`,
    ``,
    `Email:    ${info.email}`,
    `Name:     ${info.fullName ?? "—"}`,
    `User ID:  ${info.userId}`,
    `Time:     ${info.createdAt}`,
    ``,
    `They are on the waitlist (granted_access = false).`,
    `Flip granted_access in the Supabase dashboard once onboarded.`,
  ].join("\n");
  const html = `
    <div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;color:#111;">
      <h2 style="margin:0 0 12px;font-size:15px;">New Kairos signup</h2>
      <table style="border-collapse:collapse;">
        <tr><td style="padding:2px 12px 2px 0;color:#666;">Email</td><td>${escapeHtml(info.email)}</td></tr>
        <tr><td style="padding:2px 12px 2px 0;color:#666;">Name</td><td>${escapeHtml(info.fullName ?? "—")}</td></tr>
        <tr><td style="padding:2px 12px 2px 0;color:#666;">User ID</td><td>${escapeHtml(info.userId)}</td></tr>
        <tr><td style="padding:2px 12px 2px 0;color:#666;">Time</td><td>${escapeHtml(info.createdAt)}</td></tr>
      </table>
      <p style="margin-top:14px;">They're on the waitlist. Flip <code>granted_access</code> in the Supabase dashboard once onboarded.</p>
    </div>`.trim();
  return { subject, html, text };
}

export function userWelcomeEmail(info: SignupInfo): EmailPayload {
  const greeting = info.fullName ? `Hi ${info.fullName.split(" ")[0]},` : "Hi,";
  const subject = "Kairos — you're on the list";
  const text = [
    greeting,
    ``,
    `Thanks for signing up for Kairos. We're invite-only right now while we onboard the first cohort of fractional CFOs.`,
    ``,
    `The fastest way to get access is a 30-minute walkthrough — pick a slot here:`,
    info.calendlyUrl,
    ``,
    `On the call we'll set up your workspace, walk through the approval gate, and get your first client engagement loaded.`,
    ``,
    `— Bruno`,
    `Kairos · signkairos.com`,
  ].join("\n");
  const html = `
    <div style="font-family:Inter,system-ui,-apple-system,sans-serif;font-size:15px;line-height:1.55;color:#111;max-width:560px;">
      <a href="https://signkairos.com" style="display:inline-block;margin:0 0 28px;text-decoration:none;">
        <img src="https://signkairos.com/logos/kairos_logo_navy.png"
             alt="Kairos"
             width="120"
             style="display:block;border:0;max-width:120px;height:auto;" />
      </a>
      <p style="margin:0 0 14px;">${escapeHtml(greeting)}</p>
      <p style="margin:0 0 14px;">Thanks for signing up for Kairos. We're invite-only right now while we onboard the first cohort of fractional CFOs.</p>
      <p style="margin:0 0 18px;">The fastest way to get access is a 30-minute walkthrough — pick a slot below:</p>
      <p style="margin:0 0 22px;">
        <a href="${escapeHtml(info.calendlyUrl)}" style="display:inline-block;background:#3a52d1;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:500;">Book a 30-min walkthrough →</a>
      </p>
      <p style="margin:0 0 14px;">On the call we'll set up your workspace, walk through the approval gate, and get your first client engagement loaded.</p>
      <p style="margin:18px 0 0;color:#666;">— Bruno<br/>Kairos · <a href="https://signkairos.com" style="color:#666;">signkairos.com</a></p>
    </div>`.trim();
  return { subject, html, text };
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
