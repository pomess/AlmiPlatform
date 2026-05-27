# Disease360 — Master documentation index

_Last updated: 2026-05-18. Read this first. Everything else is reachable from here._

Disease360 is a single-tenant AI cockpit being commercialized as **a per-client AI workspace for fractional CFOs**. This index points to the right doc for whoever you are.

---

## Pick your starting point

| You are… | Read in this order |
|---|---|
| **Bruno (or future-self)** picking the project back up | [Strategy](business/strategy.md) → [State](business/state.md) → [Architecture](06-jarvis-architecture-proposal.md) → [Roadmap](ROADMAP.md) |
| **A contractor** Bruno hired part-time | [README.md](../README.md) → [ONBOARDING.md](ONBOARDING.md) → [CONTEXT.md](../CONTEXT.md) → [Locked decisions](09-locked-decisions.md) |
| **A prospective customer** (fractional CFO) | [One-pager](external/one-pager.md) → [Security overview](external/security.md) → [marketing/hero.md](../marketing/hero.md) (the live landing copy) |
| **A potential acquirer or strategic partner** | [Pitch outline](investor/pitch-outline.md) → [Strategy](business/strategy.md) → [State](business/state.md) (honest moat + blockers) |

---

## Internal canon

The honest source of truth. Will contradict marketing copy in places — that's the point.

### Strategy
- [`business/strategy.md`](business/strategy.md) — Wedge selection, ACV, GTM, what's explicitly off-limits.
- [`business/state.md`](business/state.md) — What works, what's vapor, productization blockers (~5–7 weeks).

### Architecture & decisions
- [`06-jarvis-architecture-proposal.md`](06-jarvis-architecture-proposal.md) — Three-service composition (memory, harness, web).
- [`09-locked-decisions.md`](09-locked-decisions.md) — Phase-0/1 decisions that are no longer up for debate.
- [`11-hot-cache.md`](11-hot-cache.md) — Why `hot.md` is first-class.
- [`ROADMAP.md`](ROADMAP.md) — **Active 12-month commercialization roadmap.** Three horizons, Friday-review cadence.
- [`07-roadmap.md`](07-roadmap.md) — *Historical.* Pre-commercialization JARVIS phases. Reference only — superseded by `ROADMAP.md`.

### Domain language
- [`../CONTEXT.md`](../CONTEXT.md) — Glossary of terms (cockpit, brain, vault, agent, approval gate). Read before writing code or copy.

### Background research (skim once, refer rarely)
- [`00-overview.md`](00-overview.md), [`01-openclaw.md`](01-openclaw.md) … [`05-existing-project-audit.md`](05-existing-project-audit.md) — The "JARVIS dossier" that informed the design.

---

## External-facing docs

Polished, customer-safe. Must not contradict the landing page or each other.

- [`external/one-pager.md`](external/one-pager.md) — The buyer-facing summary.
- [`external/security.md`](external/security.md) — Security & data handling overview.
- [`../marketing/hero.md`](../marketing/hero.md) — Source of truth for landing copy.
- [`../marketing/loom-script.md`](../marketing/loom-script.md) — 90-second demo script.

> **Three known mismatches to fix in code, not copy** (per `business/state.md` and the audit):
> 1. *"Tamper-evident audit log"* — log is wired (2026-05-17) but not cryptographically chained.
> 2. *"Cross-contamination is impossible by design — a wall"* — vault is single-tenant; "wall" overstates.
> 3. *"No model ever trains on your client's data"* — true under current Google Gemini paid-tier terms; lock the version in the DPA.

---

## Investor / acquirer track

Bruno is **not raising**. These exist for the rare strategic conversation.

- [`investor/pitch-outline.md`](investor/pitch-outline.md) — 10-slide structure.
- A pitch deck PDF is generated from [`exports/decks/pitch.html`](exports/decks/pitch.html) — see [`exports/`](exports/).

---

## Generated exports

Pandoc-style outputs of the markdown docs above, regenerated when the source changes.

- [`exports/`](exports/) — DOCX outputs plus pitch/roadmap deck PDFs.

To regenerate: `python scripts/build_docs.py` (creates DOCX from the canonical markdown and PDFs from the HTML decks via headless Chrome/Edge).

---

## What this index deliberately does not do

- Duplicate content. Each fact lives in exactly one source file.
- Time-stamp every doc. Strategy and state are dated; the rest evolve with the code.
- Hide unfinished work. The state doc is honest about vapor — keep it that way.
