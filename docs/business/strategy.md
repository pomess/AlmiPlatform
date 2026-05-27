# Disease360 — Commercialization strategy

_As of 2026-05-17. Owner: Bruno. Scope: solo/lifestyle business._

## Shape of the business

Disease360 is being commercialized as a **solo / lifestyle business**.

- Target: **$30–80k MRR within 12 months** (~$600k–$1M ARR ceiling at this configuration).
- Bruno stays solo, with at most one part-time contractor after $30k MRR.
- No fundraising. No SOC2 in year one. Optimize for cashflow per hour, not category leadership.
- ~30 hrs/week sustained, not 60. The lifestyle constraint is real.

## Wedge #1 (months 1–4) — Fractional CFOs / fractional CXOs

- ACV **$2.4–4.8k/yr per seat**.
- Reachable on LinkedIn, CFO Connect (Spendesk-run), `r/fractionalCFO`, Pilot/Paro alumni networks.
- Beachhead workflow: **per-client brain isolation + approval-before-send + Board Pack Drafter**.
- Buyer's #1 fear: cross-client send disaster ("I almost sent Client A's runway numbers to Client B").
- No SOC2 required for logo #1. Clean security page is sufficient.
- Pricing: **$199 Solo / $399 Practice / $1,500 setup** (concierge ingest of last 3 engagements).

## Wedge #2 (layer at $10k MRR, ~month 5+) — Boutique M&A advisors

- ACV **$4–8k/seat/yr**, deal teams of 2–10.
- FINRA Rule 2210 + SEC Marketing Rule give the approval-gate a regulatory hook.
- Requires SOC2 Type 1 + broker-dealer-of-record review (60–90 day gate per logo).
- Distribution: founder-led outbound on LinkedIn + Axial + ACG chapter events.
- Park until CFO MRR funds the SOC2 spend.

## Explicitly not pursuing

- **D2C personal AI** — dead category. Apple Intelligence, Gemini-in-Workspace, ChatGPT Tasks ate the $20/mo tier.
- **Prosumer "chief of staff"** — Lindy / Cove / Martin / Cora are funded and direct. Crowded and fickle.
- **Open-source-with-paid-hosting** — too slow for "ASAP." 18+ months to revenue.
- **OEM / white-label** — sales cycle too long for solo founder.
- **Single-family offices** — slow ramp, revisit once 2 finance reference logos exist.
- **Healthcare verticals** — HIPAA + BAA tax not worth it for solo.
- **VC deal memos** — Hebbia owns it.
- **AI engineering teams (HumanLayer space)** — too commoditized, technical buyer is fickle.

## Why this shape

Apple Intelligence / Gemini-in-Workspace / ChatGPT Tasks ate the consumer tier. Disease360's real moat — **approval gate on persisted LangGraph interrupts + markdown-as-source-of-truth + multi-channel queue** — is wasted on consumers who want magic, and exactly what regulated solo professionals will pay $2k+/mo for without blinking.

The wedge fits the moat: fractional CFOs juggle 4–8 clients, live in fear of cross-contamination, are reachable on public channels, and have budget. M&A advisors have higher ACV but a 60–90 day compliance gate per logo that doesn't fit a solo cashflow target.

## How to apply (decision filter)

Frame **all product, copy, and feature decisions** toward fractional CFOs first.

- External words: **client**, **board**, **compliance**, **audit**, **engagement**, **portfolio**.
- Banned external words: **personal AI**, **second brain**, **knowledge graph**, **agent**, **vault**, **wikilink**.
- Bury from the external surface: PowerShell, CLI, gesture input, voice, open-source posture.
- Keep on the demo: **the approvals view**, **the audit log timeline**, **the side-by-side per-client switch**. The graph viz stays — it demos relationship-across-portfolio well to CFOs.

## Brand and domain

- Domain: **signkairos.com** (purchased 2026-05-17). Defensive: also grab `kairossign.com` as a 301 redirect.
- External product line: **Disease360** for end-customer; "Disease360 Engine" for any developer-facing later tier.
- Marketing site: `signkairos.com`. Product: `app.signkairos.com`.

## 90-day plan (high level)

| Phase | Window | Goal |
|---|---|---|
| **Build the plumbing** | Weeks 1–2 | Audit log wired ✅, multi-tenant scoping, Clerk auth, Stripe, Fly.io deploy |
| **Build the wedge feature** | Week 3 | Per-Client Board Pack Drafter |
| **Site + first cold emails** | Week 4 | Loom + 30 cold emails/week to fractional CFOs |
| **First paid pilots** | Weeks 5–8 | 3 logos at $1,500 setup + $399/mo |
| **Content + scale outbound** | Weeks 9–13 | Public pricing, LinkedIn cadence, 60 emails/week |

End-of-90 target: **6–8 paying logos, $3–4k MRR, ~$20k earned**.

## Related docs

- [`docs/business/state.md`](state.md) — what the codebase actually does today.
- [`marketing/hero.md`](../../marketing/hero.md) — homepage copy.
- [`marketing/loom-script.md`](../../marketing/loom-script.md) — 90-second demo script.
