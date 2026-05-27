# Disease360 — Security & data handling overview

_Customer-facing. Last updated: 2026-05-18._

This page summarizes how Disease360 handles your engagement data. It is written for **fractional CFOs** evaluating whether to put their clients' financials, board materials, and investor correspondence into the platform.

If you need a Data Processing Agreement (DPA), email **hello@signkairos.com** — we provide a GDPR Art. 28-compliant DPA on request, including SCCs for international transfers.

---

## What Disease360 stores

For each engagement (each of your client relationships), Disease360 stores:

- **Markdown pages** you (or the assistant, with your approval) write. These hold meeting notes, variance commentary, draft board updates, runway models, and other engagement context.
- **An approval queue.** Every outbound action the assistant proposes is recorded with its inputs, your decision, and a timestamp.
- **An audit log** (`audit.jsonl`). Every tool call, tool result, and approval lifecycle event is appended here. Exportable to PDF.

We do **not** store: connected mailbox contents beyond what you explicitly ingest, raw financial system credentials (these live with you, not us), or recordings of your meetings.

---

## What Disease360 does *not* do with your data

- **No model training on your client data.** Your client data is never used to train, fine-tune, or evaluate any model — ours, our LLM provider's, or any third party's.
- **No secondary use.** We don't aggregate, anonymize-and-resell, or analyze across customers.
- **No cross-tenant access.** Your data is only accessible by your account.

The "no training" guarantee is contractually backed by our LLM provider's paid-tier terms (currently Google for the Gemini API). The exact provider terms version is captured in your DPA's subprocessor annex. If we change LLM provider or tier, you are notified 30 days in advance.

---

## Approval gate (the core control)

Every action that *sends, writes, or spends* is paused for your approval before it executes:

- Every email or board pack draft.
- Every Slack/DM the assistant proposes to send.
- Every ingest of new content into a client space.

A pending action surfaces in the cockpit, the CLI, and (eventually) on your phone. Defaults are conservative: a 5-minute decision window, then the action expires unexecuted. You can deny without explanation. Nothing reaches your client until you tap approve.

This is enforced in code, not policy. The runtime literally cannot send an outbound message without an approval row.

---

## Audit log

Every interaction is appended to an append-only log:

- **What was logged:** tool call, tool input, tool result, approval created, approval resolved, approval expired.
- **Where it lives:** per-tenant log file. Exportable as JSONL or PDF on demand, including after you cancel.
- **What it gives your malpractice carrier:** a complete chain of who-asked-what, what-was-drafted, what-you-approved, when. Engagement-end review becomes a query, not an archaeology project.

The log is append-only by design. We are working on cryptographic chaining (each row references the previous row's hash) — when shipped, this will be added here.

---

## Data location and transfers

- **Hosting:** EU-based (current target: Fly.io fra/cdg).
- **LLM calls:** Routed via Google Gemini paid-tier API. Google may process data in regions outside the EU under SCCs. Listed as a sub-processor in your DPA.
- **No analytics tools** that fingerprint or track. Operational telemetry is internal-only and never includes engagement content.

---

## Subprocessor list

The current subprocessors:

| Subprocessor | Purpose | Data | Region |
|---|---|---|---|
| Google (Gemini API, paid tier) | LLM inference | Engagement content during request | Multi-region under SCCs |
| Fly.io | Hosting | All persisted data | EU (fra, cdg) |
| Stripe | Payments | Billing data only — never engagement content | EU |

Changes to this list are notified 30 days in advance. The current canonical list is kept inside your DPA and at this URL.

---

## Encryption

- **In transit:** TLS 1.2+ on every API and the cockpit.
- **At rest:** Provider-managed disk encryption on hosting volumes. Backups encrypted at rest.
- **Secrets:** API keys live in environment configuration, never inside markdown files or model prompts.

---

## Access controls

- One account per practice. Sub-users are not yet available — when added, role-based access (admin / member) will land at the same time.
- No employee of Disease360 accesses customer data except for explicit support requests, and only with your written authorization.
- Production access is logged.

---

## What we don't claim (and why)

We deliberately *don't* claim:

- **SOC 2 Type 1 or Type 2.** Not required for the fractional-CFO use case at this scale. We will pursue SOC 2 Type 1 once we begin selling to boutique M&A advisors who need it for FINRA Rule 2210 / SEC Marketing Rule alignment.
- **HIPAA / BAA.** We don't store PHI and don't sign BAAs.
- **24/7 incident response.** Solo operator coverage is best-effort during EU business hours; SLA is 99.5% uptime with service-credit remedy.
- **"Air-gapped" or "fully on-prem."** Not on the public tier. If you're at a firm that requires it, email Bruno directly.

---

## How to report a security issue

Email **hello@signkairos.com** with subject `[security]`. We acknowledge within one business day. We do not run a paid bug bounty.

---

## What this page is not

- A legal document. The binding instruments are the **Privacy Policy**, **Terms of Service**, and **Data Processing Agreement** (request via email).
- A guarantee of a specific feature roadmap. Items here describe what the product does **today**.
