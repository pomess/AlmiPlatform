---
description: Reality-check the project state against docs and live code
---

Cross-reference the README, `docs/business/state.md`, and the actual code to surface drift.

1. Read `README.md` (the "Status" + "Next" sections) and `docs/business/state.md` end-to-end.
2. Verify the three known mismatches called out in `docs/MASTER.md`:
   - Audit log: is `services/harness/disease360_harness/audit.py` hash-chaining events, or only appending JSONL?
   - Multi-tenancy: are there any per-client scoping primitives in `services/memory/` and `services/harness/`, or is everything single-tenant?
   - Gemini training opt-out: is the API client pinned to a paid-tier model + version that excludes training?
3. Check whether each "Phase 1 — working today" bullet in the README has actual code backing it (Streaming chat, approvals flow, brains + render, graph view, lint + solve, gestures, CLI).
4. Report a concise punch list: what works, what's vapor, and which doc claims need updating. Don't edit anything.
