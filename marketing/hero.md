# signkairos.com — Homepage copy

_Domain: `signkairos.com`. Buyer: fractional CFO with 4–8 clients. Banned words: "personal AI," "second brain," "knowledge graph," "agent." Voice: a CFO writing to another, not a founder pitching AI._

---

## Hero (above the fold)

**Eyebrow tag (small, all caps, muted):**

> **AI WORKSPACE FOR FRACTIONAL CFOs**

**Headline (60–72pt):**

> # Six clients. One brain. Zero crossed wires.

**Subhead (20–22pt, max 2 lines):**

> The AI workspace that remembers every client engagement, drafts your board packs, and queues every send for your sign-off. With an audit log your malpractice carrier will actually like.

**Primary CTA:** `Book a 20-min walkthrough` _(Calendly link — not "Get started," not "Try free")_

**Secondary CTA:** `Watch the 90-sec demo` _(plays the Loom inline)_

**Trust strip immediately under the CTAs (small, muted):**

> Built for portfolio practices · Per-client memory · Approve every send · Export the audit log

**Hero visual:**
A real screenshot — split panel:
- **Left:** the Approvals view, showing one pending board-pack email _"To: CFO @ Acme Co · Q1 Board Update — DRAFT"_, with **Approve** / **Edit** / **Deny** buttons.
- **Right:** a snippet of `audit.jsonl` rendered as a clean timeline (3 lines: tool call → approval created → resolved).

The graph view does **not** appear here. Save it for the demo Loom.

---

## Section 2 — How it works (3 columns)

| **Per-client memory** | **Approve before every send** | **A record that holds up** |
|---|---|---|
| Every meeting, every variance note, every investor-update draft lives in a separate space per client. Cross-contamination is impossible by design. | Drafts the email. Drafts the board pack. Drafts the Slack reply. Then waits. Nothing leaves your account until you tap approve. | Every action — drafted, approved, denied, sent — is appended to a tamper-evident log. Export to PDF for any engagement-end review. |

One tiny screenshot per column. No animation, no gradient backgrounds.

---

## Section 3 — The single demo

> ## Watch a board pack go out the door

Inline 90-second Loom. No bullets. The video is the demo.

Script: [`marketing/loom-script.md`](loom-script.md).

---

## Section 4 — Built for the practice you actually run

> **You're managing 4–8 clients.** Not 1. Not 50. Each one needs its own context, its own narrative, its own paper trail.
>
> **Compliance is a feature, not a meeting.** Marketing Rule, FINRA-adjacent, engagement-end. The log is exportable from day one, in plain JSONL or PDF.
>
> **Your data stays yours.** Plain-text files. Export anytime. No model training on your client's books — ever.

The third line is the closer.

---

## Section 5 — Pricing

| **Solo** | **Practice** |
|---|---|
| **$199 / mo** | **$399 / mo** |
| 1 user, up to 6 client brains | 1 user, unlimited client brains |
| Email support | Slack support, audit log PDF export |
| `Start a 14-day trial` | `Book a walkthrough` |

> **Concierge onboarding** — $1,500 one-time. We sit with you for 90 minutes and ingest your last three engagements together. Most practices skip this; the ones that don't stop using it within a month.

---

## Section 6 — FAQ (4 questions, no more)

> **Is my client data used to train models?**
> No. Ever. Your brain is a folder of plain markdown files on your hosted instance. Models read it; nothing trains on it.
>
> **Can I export everything?**
> Yes. Every brain is a folder of `.md` files; every action is a line in `audit.jsonl`. Both are downloadable any time, including after you cancel.
>
> **What if I don't want it sending email?**
> Then it doesn't. Every outbound action queues for your approval. You can also disable any tool entirely per client.
>
> **Is there a self-hosted option?**
> Not for the public tier. If you're at a firm that needs it, email me directly.

---

## Footer

```
signkairos.com
Built by Bruno · 2026
hello@signkairos.com
```

Nothing else. No social icons unless actively posting. No "Made with ❤️."

---

## Deliberately missing (do not add)

- "Personal AI" — banned word
- Logo strip / "Trusted by" — no fakes; add real ones once 3 customers grant permission
- Force-graph viz on hero — shifts buyer category; lives in the Loom
- Founder photo — `/about` page, not the hero
- Animations / gradient mesh / glass morphism — quiet white space is the credibility signal in 2026
- "Free trial" as the primary CTA — the primary CTA is a call until logo #10

## Risk to test

The line _"audit log your malpractice carrier will actually like"_ is great peer-to-peer; on a homepage a careful CFO might read it as flippant. **Test against the neutral fallback:** _"With an exportable audit log for every engagement-end review."_ Run both past the first 3 discovery calls. If anyone frowns, swap.
