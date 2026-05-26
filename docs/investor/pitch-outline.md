# Kairos — Pitch outline

_For the rare strategic conversation. **Bruno is not raising.** This exists for acquirer/partner discussions and as a discipline for keeping the narrative tight._

10 slides. Each one earns its place or gets cut.

---

## 1 — Title

**Kairos**
The AI workspace for fractional CFOs.
*Per-client memory. Approve every send. Exportable audit log.*

Domain: signkairos.com · Built by Bruno · 2026

---

## 2 — The problem

Fractional CFOs juggle 4–8 clients in parallel. Their #1 fear is **the cross-client send disaster** — Client A's runway numbers ending up in Client B's inbox.

Existing AI tools (ChatGPT, Gemini-in-Workspace, Apple Intelligence) blur memory across contexts, send without supervision, and leave no record an engagement-end review can use.

---

## 3 — The wedge

**Fractional CFOs**, not consumers, not engineers, not boutique M&A (yet).

- ACV $2.4–4.8k/seat/yr
- Reachable: LinkedIn, CFO Connect (Spendesk-run), r/fractionalCFO, Pilot/Paro alumni
- Buyer fear maps perfectly to product: per-client isolation + approval gate + exportable log

ICP is small, public, and wealthy enough to pay $399/mo without a procurement loop.

---

## 4 — The product

Three primitives the buyer cares about:

1. **Per-client workspaces** — meeting notes, variance commentary, drafts live in *one space per engagement*. Cross-contamination is structural.
2. **Approve every send** — every outbound action pauses in a queue with a 5-minute countdown. Defaults are conservative.
3. **Exportable audit log** — every tool call, every approval, every send → JSONL, exportable to PDF for any engagement-end review.

The cockpit is the only surface. CLI/voice/gesture exist but are not the product.

---

## 5 — Why this wins

The three commodity layers — LLM, vector DB, agent framework — converge fast. The defensible layers are:

- **Approval gate on persisted LangGraph interrupts.** Most agent stacks pause in memory or freeze the whole thread. Kairos persists the interrupt to SQLite, lets *any* channel resolve it, and resumes the same thread with state. Hard to retrofit.
- **Markdown-as-source-of-truth.** No vector DB lock-in. Diffable, hand-editable. FTS5 is just an accelerator over disk files.
- **Wikilink graph + lint.** Orphans, broken links, schema violations — drives navigation and integrity checks.
- **Multi-channel queue.** Same DB visible from web + CLI + (future) gesture/Telegram. No channel amnesia.

Everything else (LangChain 1.x, Gemini, FastAPI, React 19, SQLite) is replaceable.

---

## 6 — Market shape

- ~50,000 active fractional CFOs in NA + EU (LinkedIn count, conservative).
- Median manages 4–6 retainers concurrently. Average tool spend per CFO: ~$400–800/mo across Notion, Mercury, QuickBooks, etc.
- TAM at $399/mo × 50k = ~$240M ARR at full saturation.
- **Realistic 12-month target:** 80–200 paying logos, $30–80k MRR. Solo / lifestyle shape.

---

## 7 — Traction & plan

**Now (May 2026):**
- Phase 1 product works end-to-end on a single tenant.
- Domain purchased, landing page live at signkairos.com.
- Audit log wired (2026-05-17). Approval queue persisted across CLI + web.

**90-day plan:**
| Window | Goal |
|---|---|
| Weeks 1–2 | Multi-tenant scoping, Clerk auth, Stripe, Fly.io deploy |
| Week 3 | Per-Client Board Pack Drafter feature |
| Week 4 | Loom + 30 cold emails/week to fractional CFOs |
| Weeks 5–8 | 3 paid pilots at $1,500 setup + $399/mo |
| Weeks 9–13 | Public pricing, LinkedIn cadence, 60 emails/week |

End-of-90 target: **6–8 paying logos, $3–4k MRR, ~$20k earned**.

---

## 8 — Why Bruno

- Operator background; built and shipped Kairos solo over 6 months from a deep research dossier.
- Design and engineering one head. The cockpit's visual quality is uncommon for a B2B SaaS at this stage and converts trial-to-paid intent.
- Lifestyle-business shape is intentional, not a fallback. No fundraising required for the CFO wedge.

---

## 9 — The ask

Bruno is **not raising**. This page exists for:

- **Acquirers** evaluating a tuck-in to a CFO-vertical SaaS (Pilot, Paro, Spendesk, Mercury).
- **Strategic partners** — accounting firms, fractional networks, or tooling that wants a co-build/co-sell motion.
- **Distribution partners** — newsletters, CFO communities, content with the right buyer.

**Right next step:** introductory call → walkthrough → pilot.
**hello@signkairos.com**
