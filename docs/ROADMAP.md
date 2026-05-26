# Kairos — Commercialization roadmap

_As of 2026-05-18. Owner: Bruno. Solo / lifestyle business._

This is the **active** roadmap, scoped to commercialization. It supersedes [`07-roadmap.md`](07-roadmap.md), which describes the original (pre-commercialization) JARVIS phases and is now historical.

Three time horizons. One paying customer in 60 days is the only milestone that matters.

---

## Where we are today (T=0, 2026-05-18)

| | |
|---|---|
| Product | Phase 1 works end-to-end on a single tenant |
| Audit log | Wired 2026-05-17 — tool calls, results, approvals |
| Domain | signkairos.com purchased, landing page live |
| Customers | 0 paying |
| MRR | $0 |

What's broken: multi-tenant scoping, auth, hosted deploy, billing, native send. ~5–7 weeks of plumbing per the state doc.

---

## Horizon 1 — 90 days. Goal: 6–8 paying logos at $3–4k MRR

| Phase | Window | Outcome |
|---|---|---|
| **A. Plumbing** | Wks 1–2 | Multi-tenant scoping. Supabase auth + JWT-on-backend. Stripe. Render deploy. Audit log hash-chain. |
| **B. Wedge feature** | Wk 3 | Per-Client Board Pack Drafter shippable. |
| **C. Site + cold outbound** | Wk 4 | Loom recorded. 30 cold emails/wk to fractional CFOs. |
| **D. First paid pilots** | Wks 5–8 | 3 logos at $1,500 setup + $399/mo. |
| **E. Content + scale** | Wks 9–13 | Public pricing. LinkedIn cadence. 60 emails/wk. |

**End-of-90 target:** 6–8 paying logos · $3–4k MRR · ~$20k earned.

### Definition of done for the plumbing phase

Each item below is a ship-blocker for the first paid customer.

- [x] `tenant_id` scoping on every memory route. (ADR 0001 phase 2 + 5, 2026-05-24 — Postgres-canonical vault under RLS, vault seeded into Supabase.)
- [x] Supabase-authenticated `/app` — no anonymous access. (Cockpit-side; backend JWT check still pending.)
- [ ] Approvals + audit moved to Postgres under tenant scoping. (ADR 0001 phase 3.)
- [ ] Backend JWT plumbing — memory and harness verify the Supabase token and read `tenant_id` from it. (ADR 0001 phase 4. Prerequisite for safe Render deploy.)
- [ ] Stripe Checkout for Solo ($199) and Practice ($399) tiers + one-time setup ($1,500).
- [ ] Render deploy with health checks. Memory + harness containerized. **Blocked on phase 4** — deploying without JWT verification leaks vault data to anyone who knows the URL.
- [ ] Frontend `apps/web/src/lib/api.ts` reads base URLs from env.
- [ ] Audit log hash-chain (each row carries prev-row hash). Removes the "tamper-evident" overpromise.
- [ ] Markdown export command (`kairos vault export`) so Bruno can keep an Obsidian-readable snapshot. (ADR 0001 phase 6.)

### Definition of done for the wedge feature

The Board Pack Drafter is the demo-to-pilot hook. It must:

- Pull from the active client's hot.md, recent meeting notes, latest P&L snapshot.
- Produce a draft with cited sources (per-claim wikilink-style references).
- Land in the approval queue with full preview, recipient, and 5-minute countdown.
- Render an exportable PDF for the engagement-end review on demand.

---

## Horizon 2 — months 4–8. Goal: $10k MRR + open Wedge #2

Triggered when CFO MRR clears $10k. Until then, every hour goes to Wedge #1.

| Workstream | Outcome |
|---|---|
| **Native Gmail send** | Reply, draft, send through the approval queue. Delete the "drafts work; native send doesn't" caveat. |
| **Native Calendar read/write** | Book follow-ups, reschedule, surface "since last meeting" context. |
| **Mobile approvals** | Web push or Telegram. The CFO away from a desktop must be able to approve a board pack. |
| **SOC 2 Type 1 prep** | Vendor onboarding (Vanta/Drata), policy library, evidence collection. ~3–6 months wall-clock. |
| **Boutique M&A wedge — first 2 logos** | Founder-led outbound (Axial, ACG chapters). Each logo is a 60–90 day broker-dealer review. |

**End-of-month-8 target:** $10–15k MRR across CFO + 1–2 M&A pilots.

---

## Horizon 3 — months 9–12. Goal: $30–80k MRR steady state

| Workstream | Outcome |
|---|---|
| **Multi-seat Practice tier** | Today the Practice plan supports one user. Add real RBAC (admin / member). |
| **Concierge → self-serve handoff** | The $1,500 setup is the bottleneck. Convert the 90-min process into guided in-product steps. |
| **Acquisition channels at scale** | LinkedIn cadence + content + 1–2 paid newsletters. Outbound stays founder-led. |
| **Engagement-end PDF report** | Year-end, deal-end, hand-off. The single artifact that makes the audit log pay for itself. |

**End-of-12-month target:** 80–200 paying logos · $30–80k MRR · ~$600k–$1M ARR.

---

## What is explicitly *not* on this roadmap

Per the strategy doc, these are off-limits — pursuing any of them dilutes the wedge.

- D2C personal AI / chief-of-staff consumer plays.
- Open-source-with-paid-hosting.
- OEM / white-label.
- Single-family offices (revisit only after 2 finance reference logos).
- Healthcare verticals (HIPAA tax not worth it solo).
- Anything that requires a second engineer through year one.

---

## Risks and the trigger that flips them

| Risk | What flips it |
|---|---|
| LLM provider changes training-data terms | Lock current Gemini paid-tier version in the DPA; have Anthropic + OpenAI fallback prompts ready. |
| Cross-client data leak before tenant scoping ships | Plumbing phase blocks every other phase. No paid customer until done. |
| Solo burnout at 30 hrs/wk | At $30k MRR, hire a part-time contractor (frontend or growth, not both). |
| "Wall" / "tamper-evident" copy is held against us | Fix in code (hash chain, tenant scoping) before the 4th cold email cycle. |

---

## How this doc stays current

- Each Friday: tick boxes for the active phase. If a box stays unticked two weeks running, write a sentence on why and decide: cut scope, push the milestone, or escalate.
- When a horizon flips, the previous horizon's "outcome" column becomes the new baseline in [`business/state.md`](business/state.md).

---

## Related

- [`business/strategy.md`](business/strategy.md) — Why this wedge, why this shape.
- [`business/state.md`](business/state.md) — What's true today.
- [`07-roadmap.md`](07-roadmap.md) — Historical (pre-commercialization JARVIS phases). Reference only.
